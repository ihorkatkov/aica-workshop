import contextlib
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.request

def attrs(values):
    return [{"key": k, "value": {"stringValue": v if isinstance(v, str) else json.dumps(v)}}
            for k, v in values.items()]

class Trace:
    def __init__(self, name, directory):
        self.id = secrets.token_hex(16)
        self.spans = []
        self.root = None
        self.directory = Path(directory)
        self.label = f"{name}-{self.id[:8]}"

    @contextlib.contextmanager
    def span(self, name, input=None, root=False, kind="tool"):
        sid = secrets.token_hex(8)
        values = {"langwatch.span.type": "span" if root else kind}
        if root:
            self.root = sid
        elif kind == "tool":
            values["gen_ai.operation.name"] = "execute_tool"
            values["gen_ai.tool.name"] = name
        if input is not None:
            if not root and kind == "tool":
                values["gen_ai.tool.call.arguments"] = input
            values["langwatch.span.input"] = {"type": "json", "value": input}
        span = {"traceId": self.id, "spanId": sid, "name": name, "kind": 1,
                "startTimeUnixNano": str(time.time_ns()), "status": {"code": 1}}
        if not root:
            span["parentSpanId"] = self.root
        try:
            yield values
        except Exception:
            span["status"] = {"code": 2, "message": "Lab step failed"}
            raise
        finally:
            span["endTimeUnixNano"] = str(time.time_ns())
            span["attributes"] = attrs(values)
            self.spans.append(span)

    def tool(self, fn, name, **kwargs):
        with self.span(name, kwargs) as a:
            result = fn(**kwargs)
            a["gen_ai.tool.call.result"] = result
            a["langwatch.span.output"] = {"type": "json", "value": result}
            return result

    def finish(self, required=False):
        data = {"resourceSpans": [{"resource": {"attributes": attrs({"service.name": "aica-agent-lab"})},
                "scopeSpans": [{"scope": {"name": "aica-agent-lab"}, "spans": self.spans}]}]}
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{self.id}.json"
        path.write_text(json.dumps(data, indent=2) + "\n")
        endpoint = os.getenv("LANGWATCH_ENDPOINT", "").rstrip("/")
        key = os.getenv("LANGWATCH_API_KEY")
        status = "not_configured"
        if key and endpoint:
            req = urllib.request.Request(endpoint + "/api/otel/v1/traces",
                  data=json.dumps(data).encode(), headers={"Content-Type": "application/json",
                  "X-Auth-Token": key})
            try:
                with urllib.request.urlopen(req, timeout=8) as response:
                    body = response.read()
                rejected = (json.loads(body or "{}").get("partialSuccess") or {}).get("rejectedSpans", 0)
                status = "partial_failure" if int(rejected) else "accepted"
            except urllib.error.HTTPError as e:
                status = f"http_{e.code}"
            except (OSError, ValueError, AttributeError):
                status = "unreachable_or_invalid_response"
        if required and status != "accepted":
            raise RuntimeError(f"Trace {self.id} saved locally, but LangWatch export: {status}.")
        return {"trace_id": self.id, "trace_label": self.label, "trace_file": str(path),
                "langwatch_export": status}

def check_readback(trace_id, expected, timeout=30):
    endpoint = os.getenv("LANGWATCH_ENDPOINT", "").rstrip("/")
    key = os.getenv("LANGWATCH_API_KEY")
    if not endpoint or not key:
        raise RuntimeError("Set the local LangWatch endpoint and key first.")
    if len(trace_id) != 32 or any(c not in "0123456789abcdef" for c in trace_id):
        raise ValueError("Expected a 32-character trace ID.")
    req = urllib.request.Request(endpoint + "/api/trace/" + trace_id,
                                 headers={"X-Auth-Token": key})
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen(req, timeout=4) as response:
                document = json.load(response)
            def names(node):
                if isinstance(node, dict):
                    return ({node["name"]} if isinstance(node.get("name"), str) else set()).union(
                        *(names(v) for v in node.values()))
                if isinstance(node, list):
                    return set().union(*(names(v) for v in node))
                return set()
            if expected in names(document):
                return {"verified_trace_id": trace_id, "tool_span": expected}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(f"Trace readback HTTP {e.code}. Check the project key.") from None
            if e.code not in (404, 429, 500, 502, 503, 504):
                raise RuntimeError(f"Trace readback HTTP {e.code}.") from None
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Could not read '{expected}' back from LangWatch for trace {trace_id}.")
        time.sleep(1)

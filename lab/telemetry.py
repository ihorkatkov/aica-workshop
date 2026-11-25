import base64
import contextlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

class Trace:
    def __init__(self, directory):
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        self.provider = TracerProvider(resource=Resource.create({"service.name": "aica-agent-lab"}))
        self.exporter = InMemorySpanExporter()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("aica-agent-lab")
        self.directory = Path(directory)

    def instrument_adk(self):
        import langwatch
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor

        # One export for the offline file and the local project's checked OTLP request.
        langwatch.setup(tracer_provider=self.provider, instrumentors=[GoogleADKInstrumentor()],
                        skip_open_telemetry_setup=True)

    @contextlib.contextmanager
    def root(self, command):
        with self.tracer.start_as_current_span(command) as span:
            self.id = format(span.get_span_context().trace_id, "032x")
            self.label = f"{command}-{self.id[:8]}"
            span.update_name(self.label)
            yield span

    def tool(self, fn, name, **kwargs):
        with self.tracer.start_as_current_span(name) as span:
            span.set_attribute("gen_ai.tool.name", name)
            span.set_attribute("gen_ai.tool.call.arguments", json.dumps(kwargs))
            result = fn(**kwargs)
            span.set_attribute("gen_ai.tool.call.result", json.dumps(result))
            return result

    def finish(self, required=False):
        from google.protobuf.json_format import MessageToDict
        from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans

        data = MessageToDict(encode_spans(self.exporter.get_finished_spans()), use_integers_for_enums=True)
        for resource in data["resourceSpans"]:
            for scope in resource["scopeSpans"]:
                for span in scope["spans"]:
                    # OTLP JSON represents IDs as hex, unlike standard protobuf JSON.
                    for field in ("traceId", "spanId", "parentSpanId"):
                        if field in span:
                            span[field] = base64.b64decode(span[field]).hex()
                    attrs = {a["key"]: a["value"].get("stringValue") for a in span.get("attributes", [])}
                    if attrs.get("tool.name") and attrs.get("output.value"):
                        span["name"] = attrs["tool.name"]
                        output = json.loads(attrs["output.value"])
                        span["attributes"].append({"key": "gen_ai.tool.call.result", "value": {
                            "stringValue": json.dumps(output["response"])}})
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

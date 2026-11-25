import asyncio
from argparse import ArgumentParser
import json
import os
from pathlib import Path
import sys

from . import policy, solution
from .store import Store
from .telemetry import Trace, check_readback

def read_env(path):
    if not Path(path).is_file():
        return
    for line in Path(path).read_text().splitlines():
        key, eq, value = line.partition("=")
        if eq and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

def main():
    p = ArgumentParser(description="AICA agent lab. Synthetic records only.")
    p.add_argument("--state", default=os.getenv("LAB_STATE", ".lab/state.sqlite3"))
    p.add_argument("--traces", default=os.getenv("LAB_TRACES", ".lab/traces"))
    p.add_argument("--solution", action="store_true", help="Use the reference validator.")
    sub = p.add_subparsers(dest="command", required=True)
    canary = sub.add_parser("smoke-trace")
    canary.add_argument("--require-langwatch", action="store_true")
    sub.add_parser("smoke-model").add_argument("--mode", choices=("live", "chatgpt"), default="live")
    for name in ("state", "reset"):
        sub.add_parser(name)
    for name in ("unsafe", "safe"):
        sub.add_parser(name).add_argument("--mode", choices=("live", "chatgpt", "replay"), default="replay")
    for name in ("inspect", "approve", "promote"):
        sub.add_parser(name).add_argument("proposal_id")
    sub.add_parser("set-review").add_argument("value", choices=("open", "cleared"))
    check = sub.add_parser("verify-trace")
    check.add_argument("id")
    check.add_argument("tool", nargs="?", default="get_deal")
    trace_p = sub.add_parser("trace")
    trace_p.add_argument("id")
    a = p.parse_args()
    read_env(".env")
    if a.command == "verify-trace":
        return check_readback(a.id, a.tool)
    if a.command == "trace":
        if len(a.id) != 32 or any(c not in "0123456789abcdef" for c in a.id):
            p.error("Provide a 32-character trace ID from a lab run.")
        data = json.loads((Path(a.traces) / (a.id + ".json")).read_text())
        spans = [span for resource in data["resourceSpans"] for scope in resource["scopeSpans"]
                 for span in scope["spans"]]
        return {"spans": [{"name": s["name"], **{item["key"]: item["value"]["stringValue"]
                 for item in s["attributes"] if item["key"].startswith(("gen_ai.tool.", "langwatch.span.output"))}}
                 for s in sorted(spans, key=lambda s: int(s["startTimeUnixNano"]))]}
    if a.command == "smoke-model":
        from .models import smoke_model
        if not smoke_model(a.mode):
            raise RuntimeError("Model response was empty.")
        if a.mode == "chatgpt":
            return {"provider": "codex-chatgpt", "live_response_received": True}
        return {"model": os.environ["OPENAI_MODEL"], "live_response_received": True}
    Path(a.state).parent.mkdir(parents=True, exist_ok=True)
    store = Store(a.state, (solution if a.solution else policy).validate)
    if a.command in ("state", "reset"):
        return getattr(store, a.command)()
    if a.command == "set-review":
        return store.set_review(a.value)
    if a.command == "inspect":
        return store.proposal(a.proposal_id)
    t = Trace(a.traces)
    try:
        with t.root(a.command) as root:
            if a.command in ("approve", "promote"):
                result = t.tool(getattr(store, a.command), "human_" + a.command,
                                pid=a.proposal_id)
            else:
                from .agent import run
                t.instrument_adk()
                result = asyncio.run(run(store, a.command, getattr(a, "mode", "replay")))
            root.set_attribute("langwatch.span.output", json.dumps({"type": "json", "value": result}))
    except Exception:
        t.finish()
        raise
    return {"result": result, **t.finish(getattr(a, "require_langwatch", False))}

if __name__ == "__main__":
    try:
        print(json.dumps(main(), indent=2))
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as e:
        print(f"Lab: {e}", file=sys.stderr)
        raise SystemExit(1)

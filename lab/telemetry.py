"""Official LangWatch SDK + ADK instrumentation. No custom exporter."""

from functools import lru_cache
import json
import os
import time
import httpx
import langwatch
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import SpanProcessor
from . import config


class WebTurnProcessor(SpanProcessor):
    """Copy the ADK turn onto the HTTP span LangWatch uses for the conversation."""

    def __init__(self):
        self.requests = {}

    def on_start(self, span, parent_context=None):
        if span.name != "invocation [workshop]":
            return
        parent = trace.get_current_span(parent_context)
        if getattr(parent, "name", None) in ("POST /run", "POST /run_sse"):
            self.requests[span.get_span_context().span_id] = parent

    def on_end(self, span):
        request = self.requests.pop(span.context.span_id, None)
        if request is None or not request.is_recording():
            return
        for source, field, target in (
            ("input.value", "new_message", "langwatch.input"),
            ("output.value", "content", "langwatch.output"),
        ):
            try:
                envelope = json.loads(span.attributes.get(source, "{}"))
            except (TypeError, ValueError):
                continue
            content = envelope.get(field) if isinstance(envelope, dict) else None
            if isinstance(content, dict):
                parts = content.get("parts") or []
                text = "\n".join(
                    part["text"]
                    for part in parts
                    if isinstance(part, dict)
                    and isinstance(part.get("text"), str)
                    and not part.get("thought")
                )
                if text:
                    request.set_attribute(target, text)


@lru_cache(maxsize=1)
def setup():
    client = langwatch.setup(instrumentors=[GoogleADKInstrumentor()])
    provider = trace.get_tracer_provider()
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(WebTurnProcessor())
    return client


def flush():
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=10000)


def verify(trace_id, expected="", *, turn=None):
    endpoint = os.getenv("LANGWATCH_ENDPOINT", "http://localhost:5560").rstrip("/")
    key = os.getenv("LANGWATCH_API_KEY")
    if not key:
        raise RuntimeError("LANGWATCH_API_KEY is missing; run make setup.")
    for _ in range(30):
        response = httpx.get(
            f"{endpoint}/api/trace/{trace_id}", headers={"X-Auth-Token": key}, timeout=5
        )
        if response.status_code == 200 and (not expected or expected in response.text):
            if turn is None:
                return {"trace_id": trace_id, "readback": True}
            record = response.json()
            saved_turn = tuple(
                (record.get(side) or {}).get("value") for side in ("input", "output")
            )
            if saved_turn == turn:
                return {"trace_id": trace_id, "readback": True}
        if response.status_code in (401, 403):
            raise RuntimeError("LangWatch rejected the project key")
        time.sleep(1)
    if turn is not None:
        raise RuntimeError(f"LangWatch trace {trace_id} did not show the expected prompt and reply")
    raise RuntimeError(f"Trace {trace_id} was not visible in LangWatch")


def smoke():
    setup()
    with trace.get_tracer("aica").start_as_current_span(
        "workshop-telemetry-canary"
    ) as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
    flush()
    return verify(trace_id)

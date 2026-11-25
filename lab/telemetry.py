"""Official LangWatch SDK + ADK instrumentation. No custom exporter."""

from functools import lru_cache
import os
import time
import httpx
import langwatch
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry import trace
from . import config


@lru_cache(maxsize=1)
def setup():
    return langwatch.setup(instrumentors=[GoogleADKInstrumentor()])


def flush():
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=10000)


def verify(trace_id, expected=""):
    endpoint = os.getenv("LANGWATCH_ENDPOINT", "http://localhost:5560").rstrip("/")
    key = os.getenv("LANGWATCH_API_KEY")
    if not key:
        raise RuntimeError("LANGWATCH_API_KEY is missing; run make setup.")
    for _ in range(30):
        response = httpx.get(
            f"{endpoint}/api/trace/{trace_id}", headers={"X-Auth-Token": key}, timeout=5
        )
        if response.status_code == 200 and (not expected or expected in response.text):
            return {"trace_id": trace_id, "readback": True}
        if response.status_code in (401, 403):
            raise RuntimeError("LangWatch rejected the project key")
        time.sleep(1)
    raise RuntimeError(f"Trace {trace_id} was not visible in LangWatch")


def smoke():
    setup()
    with trace.get_tracer("aica").start_as_current_span(
        "workshop-telemetry-canary"
    ) as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
    flush()
    return verify(trace_id)

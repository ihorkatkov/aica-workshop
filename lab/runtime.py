"""Small ADK Runner entry point; used by CLI and the Scenario adapter."""

from google.adk.runners import InMemoryRunner
from google.adk.agents.run_config import RunConfig
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.genai import types
from opentelemetry import trace
from .agent import build_agent
from .config import require_model
from .telemetry import setup, flush


class Conversation:
    def __init__(self, workspace="workshop"):
        require_model()
        setup()
        self.runner = InMemoryRunner(agent=build_agent(workspace), app_name="aica")
        self.session_id = None
        self.events = []

    async def turn(self, message):
        if self.session_id is None:
            session = await self.runner.session_service.create_session(
                app_name="aica", user_id="participant"
            )
            self.session_id = session.id
        final = []
        calls = []
        status = "complete"
        with trace.get_tracer("aica").start_as_current_span("workshop-turn") as span:
            trace_id = format(span.get_span_context().trace_id, "032x")
            try:
                async for event in self.runner.run_async(
                    user_id="participant",
                    session_id=self.session_id,
                    new_message=types.Content(
                        role="user", parts=[types.Part(text=message)]
                    ),
                    run_config=RunConfig(max_llm_calls=16),
                ):
                    self.events.append(event)
                    for call in event.get_function_calls():
                        calls.append({"name": call.name, "arguments": call.args})
                    if event.is_final_response() and event.content:
                        final.extend(
                            p.text
                            for p in event.content.parts or []
                            if p.text and not p.thought
                        )
            except LlmCallsLimitExceededError:
                status = "turn_limit"
            span.set_attribute("workshop.status", status)
        flush()
        return {
            "agent_said": "\n".join(final),
            "status": status,
            "tool_calls": calls,
            "trace_id": trace_id,
        }

    async def close(self):
        await self.runner.close()

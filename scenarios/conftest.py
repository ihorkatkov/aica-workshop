"""Fresh CRM workspace and ADK session per scenario; same agent as ADK Web."""

import os
import uuid
import pytest
import pytest_asyncio
import scenario
from scenario.config import ModelConfig
from lab.config import require_model, model_name
from lab.runtime import Conversation
from lab.tools import request
from lab.telemetry import setup


class ADKAdapter(scenario.AgentAdapter):
    name = "AICA pilot coordinator"

    def __init__(self, workspace):
        self.conversation = Conversation(workspace)

    async def call(self, input):
        result = await self.conversation.turn(input.last_new_user_message_str())
        if result["status"] != "complete":
            raise RuntimeError("Agent exhausted its ADK call budget")
        return result["agent_said"]


@pytest_asyncio.fixture
async def world():
    require_model()
    setup()
    scenario.configure(
        default_model=ModelConfig(
            model=os.getenv("SCENARIO_MODEL", model_name()),
            reasoning_effort=os.getenv("MODEL_REASONING_EFFORT", "low"),
        ),
        max_turns=6,
    )
    workspace = "scenario-" + uuid.uuid4().hex
    request(workspace, "POST", "reset", human=True)
    adapter = ADKAdapter(workspace)

    def state():
        return request(workspace, "GET", "state", human=True)

    before = state()
    try:
        yield adapter, state, before
    finally:
        await adapter.conversation.close()
        # Retain the isolated workspace for facilitator inspection after failures.
        print("CRM evidence workspace:", workspace)

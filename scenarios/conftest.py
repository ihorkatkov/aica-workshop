"""Fresh CRM workspace and ADK session per scenario; same agent as ADK Web."""

from contextlib import AsyncExitStack
from functools import partial
import os
import uuid
import pytest
import pytest_asyncio
import scenario
from scenario.config import ModelConfig
from lab.config import ROOT, require_model, model_name
from lab.runtime import Conversation
from lab.tools import request as crm_request
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


@pytest.fixture
def judge():
    return partial(
        scenario.JudgeAgent, model=os.getenv("JUDGE_MODEL", "openai/gpt-6.2-sol")
    )


@pytest_asyncio.fixture
async def world(request, monkeypatch, tmp_path):
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
    target = getattr(request, "param", None)
    async with AsyncExitStack() as resources:
        if target:
            client, variant = target
            folder = ROOT / ".lab/shared-mcp" / f"{variant}-{client}-{workspace}"
            folder.mkdir(parents=True)
            from scenarios.mcp_clients import crm_server, RecordedClient

            url = await resources.enter_async_context(
                crm_server(folder, variant, workspace)
            )
            monkeypatch.setenv("CRM_URL", url)

        crm_request(workspace, "POST", "reset", human=True)

        def state():
            return crm_request(workspace, "GET", "state", human=True)

        before = state()
        if not target or client == "adk":
            adapter = ADKAdapter(workspace)
            if target:
                from google.adk.tools.mcp_tool.mcp_toolset import (
                    McpToolset,
                    StreamableHTTPConnectionParams,
                )

                adapter.conversation.runner.agent.tools = [
                    McpToolset(
                        connection_params=StreamableHTTPConnectionParams(
                            url=url + f"/workspaces/{workspace}/mcp/"
                        )
                    )
                ]
        else:
            from scenarios.mcp_clients import NativeClient

            adapter = NativeClient(
                client, url + f"/workspaces/{workspace}/mcp/", tmp_path
            )
        try:
            yield RecordedClient(adapter, folder) if target else adapter, state, before
        finally:
            if isinstance(adapter, ADKAdapter):
                await adapter.conversation.close()
            print("CRM evidence workspace:", workspace)

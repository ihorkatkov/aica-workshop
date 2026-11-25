"""Fresh CRM workspace and agent session for each scenario and client."""

from functools import partial
import os
import json
import uuid
import pytest
import pytest_asyncio
import scenario
from scenario.config import ModelConfig
from lab.config import ROOT, require_model, model_name
from lab.runtime import Conversation
from lab.tools import request as crm_request
from lab.telemetry import setup, flush, verify
from scenarios.mcp_clients import NativeClient, RecordedClient, crm_server
from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    StreamableHTTPConnectionParams,
)
from scenario.types import ScenarioResult, CriterionResult


class ADKAdapter(scenario.AgentAdapter):
    name = "AICA pilot coordinator"

    def __init__(self, workspace):
        self.conversation = Conversation(workspace)

    async def call(self, input):
        result = await self.conversation.turn(input.last_new_user_message_str())
        if result["status"] != "complete":
            raise RuntimeError("Agent exhausted its ADK call budget")
        return result["agent_said"]


def pytest_addoption(parser):
    parser.addoption(
        "--agents",
        default="adk",
        help="Comma-separated scenario clients: adk,claude,codex (or all)",
    )


def pytest_generate_tests(metafunc):
    if "world" not in metafunc.fixturenames:
        return
    selected = metafunc.config.getoption("--agents")
    clients = ["adk", "claude", "codex"] if selected == "all" else selected.split(",")
    if any(c not in {"adk", "claude", "codex"} for c in clients) or len(
        set(clients)
    ) != len(clients):
        raise pytest.UsageError(
            "--agents expects unique names from adk,claude,codex or all"
        )
    metafunc.parametrize("world", clients, indirect=True)


class CRMJudge(scenario.JudgeAgent):
    def __init__(self, *, saved_checks, **kwargs):
        super().__init__(**kwargs)
        self.saved_checks = saved_checks

    async def call(self, input):
        verdict = await super().call(input)
        if not isinstance(verdict, ScenarioResult):
            return verdict
        for criterion, check in self.saved_checks.items():
            try:
                check()
            except AssertionError as error:
                reason = (str(error) or "CRM state check failed").splitlines()[0][:600]
                verdict.success = False
                verdict.failed_criteria.append(criterion)
                verdict.reasoning = f"{verdict.reasoning or ''} {criterion}: {reason}"
                status = "failed"
            else:
                reason = "Verified through an independent CRM readback."
                status = "passed"
                verdict.passed_criteria.append(criterion)
            verdict.criteria.append(
                CriterionResult(
                    criterion=criterion,
                    requirement=criterion,
                    status=status,
                    reasoning=reason,
                )
            )
        return verdict


@pytest.fixture
def native_models():
    """Scenario modules can override the native CLI models used for their runs."""
    return {}


@pytest.fixture
def run_case(world, request, native_models):
    adapter, state, _ = world

    async def run(**kwargs):
        client = request.node.callspec.params["world"]
        title = kwargs.pop("name")
        before = state()  # The scenario's fixture has finished arranging the CRM.
        metadata = {
            "case": request.node.nodeid,
            "workspace": before["workspace"],
            "client": client,
        }
        if client in native_models:
            metadata["requested_model"] = native_models[client]
        evidence = {**metadata, "before": before}
        try:
            result = await scenario.run(
                name=f"{title} [{client}]", metadata=metadata, **kwargs
            )
            evidence["scenario"] = result.model_dump(mode="json")
        except Exception as error:
            evidence["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            evidence["after"] = state()
            (adapter.evidence_dir / "result.json").write_text(
                json.dumps(evidence, indent=2)
            )
            flush()

        verify(evidence["scenario"]["messages"][-1]["trace_id"])
        return result

    return run


@pytest.fixture
def judge():
    return partial(CRMJudge, model=os.getenv("JUDGE_MODEL", "openai/gpt-6.2-sol"))


@pytest_asyncio.fixture
async def world(request, monkeypatch, tmp_path, native_models):
    require_model()
    setup()
    scenario.configure(
        default_model=ModelConfig(
            model=os.getenv("SCENARIO_MODEL", model_name()),
            reasoning_effort=os.getenv("MODEL_REASONING_EFFORT", "low"),
        ),
        max_turns=6,
    )
    run_id = uuid.uuid4().hex
    # The human desk uses workshop. Each scenario has its own server and SQLite file.
    workspace = "workshop"
    client = request.param
    folder = ROOT / ".lab/shared-mcp" / f"{client}-{run_id}"
    folder.mkdir(parents=True)
    async with crm_server(folder, workspace) as url:
        monkeypatch.setenv("CRM_URL", url)
        mcp_url = f"{url}/workspaces/{workspace}/mcp/"
        crm_request(workspace, "POST", "reset", human=True)

        def state():
            return crm_request(workspace, "GET", "state", human=True)

        before = state()
        if client == "adk":
            adapter = ADKAdapter(workspace)
            adapter.conversation.runner.agent.tools = [
                McpToolset(
                    connection_params=StreamableHTTPConnectionParams(url=mcp_url)
                )
            ]
        else:
            adapter = NativeClient(client, mcp_url, tmp_path, model=native_models.get(client))
        try:
            yield RecordedClient(adapter, folder), state, before
        finally:
            if isinstance(adapter, ADKAdapter):
                await adapter.conversation.close()
            (folder / "state.json").write_text(json.dumps(state(), indent=2))
            print("CRM evidence directory:", folder)
            print("CRM evidence workspace:", workspace)

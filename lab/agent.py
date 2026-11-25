"""Standard ADK agent shared by ADK Web, CLI, and Scenario tests."""

import os
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from .config import ROOT, model_name
from .tools import crm_tools


def build_agent(workspace="workshop"):
    return Agent(
        name="workshop",
        model=LiteLlm(
            model=model_name(),
            timeout=60,
            num_retries=1,
            reasoning_effort=os.getenv("MODEL_REASONING_EFFORT", "low"),
        ),
        instruction=(ROOT / "agents" / "workshop" / "prompt.md").read_text(),
        tools=crm_tools(workspace),
    )

"""Independent owner-authority probes against disposable copies of a prepared CRM."""

import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crm.server import create_app


@pytest.fixture
def prepared_crm(tmp_path):
    source = Path(os.getenv("STAGE_PROBE_DB") or ".lab/crm.sqlite3").resolve()
    assert source.is_file(), (
        f"Prepare a CRM with one pending stage proposal first: {source}"
    )
    copy = tmp_path / "crm.sqlite"
    with (
        sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src,
        sqlite3.connect(copy) as dst,
    ):
        src.backup(dst)
    app = create_app(copy)
    with TestClient(app) as owner:
        owner.get("/").raise_for_status()
        owner.headers.update(
            {
                "Origin": str(owner.base_url).rstrip("/"),
                "X-CSRF-Token": owner.cookies["aica_human"],
            }
        )
        snapshot = owner.get("/ui/state").json()
        proposal = next(
            (
                p
                for p in snapshot.get("proposals", [])
                if p.get("status") == "pending"
                and p.get("from_stage") == "pilot"
                and p.get("to_stage") == "rollout"
            ),
            None,
        )
        assert proposal, (
            "Prepare a pending Pilot to Rollout proposal in STAGE_PROBE_DB before probing"
        )
        yield app, owner, proposal


def business_state(owner):
    response = owner.get("/ui/state")
    response.raise_for_status()
    state = response.json()
    return state["deals"], state["proposals"]


def test_agent_cannot_decide(prepared_crm):
    app, owner, proposal = prepared_crm
    before = business_state(owner)
    # The owner fixture already runs the app lifespan (including the MCP manager).
    agent = TestClient(app)
    try:
        token = os.getenv("CRM_AGENT_TOKEN", "workshop-agent")
        reply = agent.post(
            f"/ui/proposals/{proposal['id']}/decision",
            headers={"Authorization": f"Bearer {token}"},
            json={"decision": "approve"},
        )
    finally:
        agent.close()
    assert reply.status_code in (401, 403), (
        f"Agent decision returned HTTP {reply.status_code}"
    )
    assert business_state(owner) == before, "Agent attempt modified deals or proposals"


def test_rejected_proposal_cannot_be_approved(prepared_crm):
    _, owner, proposal = prepared_crm
    path = f"/ui/proposals/{proposal['id']}/decision"
    owner.post(path, json={"decision": "reject"}).raise_for_status()
    before = business_state(owner)
    assert any(
        p["id"] == proposal["id"] and p["status"] == "rejected" for p in before[1]
    )
    reply = owner.post(path, json={"decision": "approve"})
    assert reply.status_code in (403, 409, 422) or (
        reply.is_success and reply.json().get("status") == "rejected"
    ), "CRM accepted approval of a rejected proposal"
    assert business_state(owner) == before, "Replay modified deals or proposals"

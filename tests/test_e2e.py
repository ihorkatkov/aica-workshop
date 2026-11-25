"""Deterministic starter CRM checks; no model calls or implemented participant solution."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crm.server import create_app
from crm.store import FIXTURE, Store


@pytest.fixture
def api(tmp_path):
    path = tmp_path / "crm.sqlite3"
    with TestClient(create_app(path)) as client:
        client.headers["Authorization"] = "Bearer workshop-human"
        yield client, path


def test_fixtures_have_relations_and_real_variations():
    data = json.loads(FIXTURE.read_text())
    assert len(data["deals"]) == 30 and len(data["contacts"]) == 60
    companies = {c["id"] for c in data["companies"]}
    contacts = {c["id"]: c for c in data["contacts"]}
    for d in data["deals"]:
        assert d["company_id"] in companies
        assert contacts[d["contact_id"]]["company_id"] == d["company_id"]
    assert {d["security_review"] for d in data["deals"]} == {
        "open",
        "cleared",
        "missing",
        "expired",
    }


def test_one_editable_adk_agent():
    from lab.agent import build_agent

    agent = build_agent()
    assert agent.name == "workshop"
    names = {t.__name__ for t in agent.tools}
    assert {"search_deals", "get_record"} <= names
    assert "write_deal" in names
    assert agent.model.__class__.__name__ == "LiteLlm"
    assert {p.name for p in Path("agents").iterdir() if (p / "agent.py").exists()} == {
        "workshop"
    }


def test_parallel_http_workspaces(api):
    client, _ = api

    def exercise(i):
        workspace = f"parallel-{i}"
        response = client.post(f"/workspaces/{workspace}/reset", json={})
        assert response.status_code == 200
        response = client.get(f"/workspaces/{workspace}/state")
        assert response.status_code == 200
        assert len(response.json()["deals"]) == 30

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(exercise, range(12)))


def test_upgrades_old_workspace_schema_without_losing_records(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as old:
        old.execute(
            "CREATE TABLE workspaces(id TEXT PRIMARY KEY, variant TEXT NOT NULL)"
        )
        old.execute("INSERT INTO workspaces VALUES('saved-evidence','reference')")
    with Store(path) as db:
        assert db.require_workspace("saved-evidence") == "saved-evidence"
        db.reset("workshop")
        assert len(db.deals("workshop")) == 30
        assert [row[1] for row in db.db.execute("PRAGMA table_info(workspaces)")] == [
            "id"
        ]


def test_agent_cannot_reset_or_edit_review(api):
    c, _ = api
    c.headers["Authorization"] = "Bearer workshop-agent"
    assert c.post("/workspaces/workshop/reset").status_code == 403
    assert (
        c.post(
            "/workspaces/workshop/deals/D-104/review", json={"status": "cleared"}
        ).status_code
        == 403
    )


def test_invalid_actions_and_record_types(api):
    c, _ = api
    assert (
        c.post(
            "/workspaces/workshop/deals/D-104/write", json={"action": "delete"}
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/workspaces/workshop/deals/C-001/write",
            json={"action": "schedule_kickoff"},
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/workspaces/workshop/deals/C-001/review", json={"status": "open"}
        ).status_code
        == 422
    )


def test_policy_hook_is_participant_owned(api, monkeypatch):
    from crm import policy

    c, _ = api
    before = c.get("/workspaces/workshop/state").json()
    monkeypatch.setattr(
        policy,
        "validate",
        lambda record, action: {"code": "CUSTOM_RULE", "message": "Participant rule"},
    )
    result = c.post(
        "/workspaces/workshop/deals/D-104/write", json={"action": "schedule_kickoff"}
    ).json()
    assert result["code"] == "CUSTOM_RULE"
    assert c.get("/workspaces/workshop/state").json() == before


def test_reset_isolation(api):
    c, _ = api
    c.post("/workspaces/other/reset")
    c.post("/workspaces/other/deals/D-104/review", json={"status": "cleared"})
    c.post("/workspaces/workshop/reset")
    assert (
        c.get("/workspaces/other/records/D-104").json()["security_review"] == "cleared"
    )
    assert (
        c.get("/workspaces/workshop/records/D-104").json()["security_review"] == "open"
    )

"""Deterministic HTTP/CRM boundary checks. These are not model evidence."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from crm.server import create_app
from crm.store import Store, FIXTURE
from crm import policy
from facilitator import reference_policy as solution


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "ALLOW_DIRECT_WRITES", False)
    monkeypatch.setattr(policy, "validate", solution.validate)
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


def test_unsafe_baseline_really_writes_and_duplicates(api, monkeypatch):
    monkeypatch.setattr(policy, "ALLOW_DIRECT_WRITES", True)
    client, _ = api
    url = "/workspaces/workshop/deals/D-104/write"
    for _ in range(2):
        result = client.post(url, json={"action": "schedule_kickoff"}).json()
    assert result["record"]["security_review"] == "open"
    assert result["record"]["kickoffs"] == 2


def test_http_rejection_revision_approval_and_exactly_once(api):
    c, _ = api
    base = "/workspaces/workshop"
    before = c.get(base + "/state").json()["deals"]
    rejection = c.post(
        base + "/deals/D-104/propose", json={"action": "schedule_kickoff"}
    ).json()
    assert rejection["code"] == "REVIEW_NOT_CLEARED"
    assert rejection["allowed"] == ["request_review_update"]
    pid = c.post(
        base + "/deals/D-104/propose", json={"action": "request_review_update"}
    ).json()["id"]
    assert c.post(base + f"/proposals/{pid}/promote").json()["code"] == "NOT_APPROVED"
    assert c.post(base + f"/proposals/{pid}/approve").json()["status"] == "approved"
    assert c.get(base + "/state").json()["deals"] == before
    assert c.post(base + f"/proposals/{pid}/promote").json()["status"] == "applied"
    assert (
        c.post(base + f"/proposals/{pid}/promote").json()["status"] == "already_applied"
    )
    assert c.get(base + "/records/D-104").json()["review_requests"] == 1


def test_server_denies_agent_approval_reset_and_guard_bypass(api):
    c, _ = api
    c.headers["Authorization"] = "Bearer workshop-agent"
    base = "/workspaces/workshop"
    assert c.post(base + "/reset", json={}).status_code == 403
    assert c.post(base + "/proposals/anything/approve").status_code == 403
    assert c.post(base + "/proposals/anything/promote").status_code == 403
    assert (
        c.post(base + "/deals/D-104/write", json={"action": "schedule_kickoff"}).json()[
            "code"
        ]
        == "DIRECT_WRITE_DISABLED"
    )
    assert (
        c.post(
            base + "/deals/D-104/propose", json={"action": "delete_everything"}
        ).status_code
        == 422
    )


def test_stale_and_cross_workspace_approval(api):
    c, _ = api
    base = "/workspaces/workshop"
    pid = c.post(
        base + "/deals/D-101/propose", json={"action": "schedule_kickoff"}
    ).json()["id"]
    c.post(base + f"/proposals/{pid}/approve")
    assert c.post(f"/workspaces/other/proposals/{pid}/promote").status_code == 404
    c.post(base + "/deals/D-101/review", json={"status": "open"})
    assert c.post(base + f"/proposals/{pid}/promote").json()["code"] == "STALE_STATE"
    assert c.get(base + "/records/D-101").json()["stage"] == "pilot_requested"


def test_concurrent_promotions_and_proposal_retries(api):
    c, path = api
    base = "/workspaces/workshop"
    body = {"action": "request_review_update"}
    pid = c.post(base + "/deals/D-104/propose", json=body).json()["id"]
    assert c.post(base + "/deals/D-104/propose", json=body).json()["id"] == pid
    c.post(base + f"/proposals/{pid}/approve")

    def promote(_):
        with Store(path) as db:
            return db.promote("workshop", pid)["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(promote, range(2))) == ["already_applied", "applied"]
    assert c.get(base + "/records/D-104").json()["review_requests"] == 1


def test_revalidates_current_policy_at_promotion(api, monkeypatch):
    monkeypatch.setattr(policy, "validate", lambda record, action: None)
    c, _ = api
    base = "/workspaces/workshop"
    pid = c.post(
        base + "/deals/D-104/propose", json={"action": "schedule_kickoff"}
    ).json()["id"]
    c.post(base + f"/proposals/{pid}/approve")

    monkeypatch.setattr(policy, "validate", solution.validate)
    assert (
        c.post(base + f"/proposals/{pid}/promote").json()["code"]
        == "REVIEW_NOT_CLEARED"
    )
    assert c.get(base + "/records/D-104").json()["kickoffs"] == 0


def test_noop_and_reset_isolation(api):
    c, _ = api
    base = "/workspaces/workshop"
    assert (
        c.post(
            base + "/deals/D-106/propose", json={"action": "schedule_kickoff"}
        ).json()["status"]
        == "no_change"
    )
    assert c.get(base + "/state").json()["proposals"] == []
    assert c.get(base + "/records/D-106").json()["kickoffs"] == 1
    c.post("/workspaces/other/reset")
    c.post("/workspaces/other/deals/D-104/review", json={"status": "cleared"})
    c.post(base + "/reset")
    assert (
        c.get("/workspaces/other/records/D-104").json()["security_review"] == "cleared"
    )


def test_one_editable_adk_agent():
    from lab.agent import build_agent

    agent = build_agent()
    assert agent.name == "workshop"
    names = {t.__name__ for t in agent.tools}
    assert {"search_deals", "get_record"} <= names
    assert names - {"search_deals", "get_record"} in (
        {"write_deal"},
        {"propose_action"},
    )
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


def test_wrong_record_type_is_recoverable(api):
    client, _ = api
    response = client.post(
        "/workspaces/workshop/deals/C-001/propose", json={"action": "schedule_kickoff"}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Expected a deal ID"


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

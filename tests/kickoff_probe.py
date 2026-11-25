"""Direct CRM acceptance check. Run explicitly with make check-kickoff."""

import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from crm.server import create_app


@pytest.mark.parametrize(
    ("status", "actor", "expired"),
    [
        ("open", "agent", False),
        ("open", "human", False),
        ("missing", "agent", False),
        ("expired", "agent", False),
        ("cleared", "agent", True),
    ],
)
def test_direct_kickoff_requires_valid_clearance(tmp_path, status, actor, expired):
    with TestClient(create_app(tmp_path / "crm.sqlite")) as crm:
        base = "/workspaces/workshop"
        human = {
            "Authorization": "Bearer " + os.getenv("CRM_ADMIN_TOKEN", "workshop-human")
        }
        agent = {
            "Authorization": "Bearer " + os.getenv("CRM_AGENT_TOKEN", "workshop-agent")
        }

        def read():
            response = crm.get(base + "/records/D-104", headers=human)
            response.raise_for_status()
            return response.json()

        today = date.fromisoformat(read()["as_of"])
        until = (today - timedelta(days=1)).isoformat() if expired else None
        crm.post(
            base + "/deals/D-104/review",
            headers=human,
            json={"status": status, "valid_until": until},
        ).raise_for_status()
        before = read()
        response = crm.post(
            base + "/deals/D-104/write",
            headers=human if actor == "human" else agent,
            json={"action": "schedule_kickoff"},
        )
        after = read()
        assert after["kickoffs"] == before["kickoffs"], (
            f"CRM recorded kickoff for {actor} with {status} review"
        )
        assert after["stage"] == before["stage"], (
            "Rejected kickoff changed the deal stage"
        )
        assert response.status_code in (200, 403, 409, 422)
        body = response.json()
        rejection = body.get("detail", body)
        assert isinstance(rejection, dict) and "request_review_update" in rejection.get(
            "allowed", []
        )
        assert response.is_error or rejection.get("status") == "rejected"

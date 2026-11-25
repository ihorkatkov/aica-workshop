"""Exercise browser authority and state transitions, independent of any LLM."""

import re
from fastapi.testclient import TestClient
from crm.server import create_app


def test_console_requires_own_session_and_same_origin(tmp_path):
    with TestClient(create_app(tmp_path / "crm.db")) as c:
        agent = {"Authorization": "Bearer workshop-agent"}
        assert c.get("/ui/state", headers=agent).status_code == 401
        assert c.post("/ui/reset", headers=agent).status_code == 401
        assert c.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        page = c.get("/")
        assert page.status_code == 200
        assert "httponly" in page.headers["set-cookie"].lower()
        token = re.search('name="csrf-token" content="([^"]+)"', page.text)[1]
        assert c.get("/ui/state").status_code == 200
        assert c.post("/ui/reset").status_code == 403
        assert (
            c.post(
                "/ui/reset",
                headers={"Origin": "https://evil.test", "X-CSRF-Token": token},
            ).status_code
            == 403
        )
        assert (
            c.post(
                "/ui/reset",
                headers={"Origin": "http://testserver", "X-CSRF-Token": token},
            ).status_code
            == 200
        )
        c.cookies.clear()
        c.cookies.set("aica_human", token + "tampered", path="/ui")
        assert c.get("/ui/state").status_code == 401


def test_browser_approval_does_not_apply_and_promotion_is_exactly_once(tmp_path):
    with TestClient(create_app(tmp_path / "crm.db")) as c:
        page = c.get("/")
        token = re.search('name="csrf-token" content="([^"]+)"', page.text)[1]
        browser = {"Origin": "http://testserver", "X-CSRF-Token": token}
        agent = {"Authorization": "Bearer workshop-agent"}
        pid = c.post(
            "/workspaces/workshop/deals/D-104/propose",
            headers=agent,
            json={"action": "request_review_update"},
        ).json()["id"]
        before = c.get("/ui/state").json()["deals"]
        base = "/ui/proposals/" + pid
        assert (
            c.post(base + "/promote", headers=browser).json()["code"] == "NOT_APPROVED"
        )
        assert c.post(base + "/approve", headers=browser).json()["status"] == "approved"
        assert c.get("/ui/state").json()["deals"] == before
        assert c.post(base + "/promote", headers=browser).json()["status"] == "applied"
        assert (
            c.post(base + "/promote", headers=browser).json()["status"]
            == "already_applied"
        )
        after = c.get("/ui/state").json()
        assert (
            next(d for d in after["deals"] if d["id"] == "D-104")["review_requests"]
            == 1
        )
        assert [a["event"] for a in after["audit"]] == [
            "reset",
            "proposed",
            "approved",
            "promoted",
        ]


def test_browser_stale_approval_and_data_reset_preserve_code(tmp_path):
    with TestClient(create_app(tmp_path / "crm.db")) as c:
        token = re.search('name="csrf-token" content="([^"]+)"', c.get("/").text)[1]
        headers = {"Origin": "http://testserver", "X-CSRF-Token": token}
        pid = c.post(
            "/workspaces/workshop/deals/D-101/propose",
            headers={"Authorization": "Bearer workshop-agent"},
            json={"action": "schedule_kickoff"},
        ).json()["id"]
        c.post("/ui/proposals/" + pid + "/approve", headers=headers)
        c.post("/ui/deals/D-101/review", headers=headers, json={"status": "open"})
        assert (
            c.post("/ui/proposals/" + pid + "/promote", headers=headers).json()["code"]
            == "STALE_STATE"
        )
        c.post("/ui/reset", headers=headers)
        state = c.get("/ui/state").json()
        assert len(state["deals"]) == 30 and state["proposals"] == []

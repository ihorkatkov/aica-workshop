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


def test_d104_actions_are_visible_without_approval(tmp_path):
    with TestClient(create_app(tmp_path / "crm.db")) as c:
        c.get("/")
        agent = {"Authorization": "Bearer workshop-agent"}
        human = {"Authorization": "Bearer workshop-human"}
        base = "/workspaces/workshop"
        c.post(base + "/reset", headers=human)

        def deal():
            return next(
                d for d in c.get("/ui/state").json()["deals"] if d["id"] == "D-104"
            )

        assert deal()["stage"] == "pilot_requested"
        assert deal()["security_review"] == "open"
        assert deal()["kickoffs"] == deal()["review_requests"] == 0
        c.post(base + "/deals/D-104/review", headers=human, json={"status": "cleared"})
        for expected_count in (1, 2):
            result = c.post(
                base + "/deals/D-104/write",
                headers=agent,
                json={"action": "schedule_kickoff"},
            )
            assert result.status_code == 200
            assert deal()["kickoffs"] == expected_count
            assert deal()["stage"] == "kickoff_scheduled"
            assert deal()["security_review"] == "cleared"
        c.post(
            base + "/deals/D-104/write",
            headers=agent,
            json={"action": "request_review_update"},
        )
        assert deal()["review_requests"] == 1
        assert deal()["security_review"] == "open"
        c.post(base + "/deals/D-104/review", headers=human, json={"status": "cleared"})
        assert deal()["security_review"] == "cleared"
        assert deal()["review_valid_until"] == "2026-12-31"
        events = [
            e
            for e in c.get("/ui/state").json()["audit"]
            if e["detail"].get("deal_id") == "D-104"
        ]
        assert events.pop(0)["event"] == "review_changed"
        assert [e["event"] for e in events] == ["deal_updated"] * 3 + ["review_changed"]
        assert events[0]["detail"]["after"]["kickoffs"] == 1
        assert events[1]["detail"]["after"]["kickoffs"] == 2
        assert events[2]["detail"]["after"]["review_requests"] == 1
        assert events[3]["detail"]["previous_status"] == "open"


def test_direct_browser_actions_record_human_and_require_csrf(tmp_path):
    with TestClient(create_app(tmp_path / "crm.db")) as c:
        body = {"action": "request_review_update", "actor": "agent"}
        assert c.post("/ui/deals/D-104/write", json=body).status_code == 401
        page = c.get("/")
        token = re.search('name="csrf-token" content="([^"]+)"', page.text)[1]
        headers = {"Origin": "http://testserver", "X-CSRF-Token": token}
        assert c.post("/ui/deals/D-104/write", json=body).status_code == 403
        assert (
            c.post(
                "/ui/deals/D-104/write",
                headers={**headers, "Origin": "https://elsewhere.test"},
                json=body,
            ).status_code
            == 403
        )
        result = c.post("/ui/deals/D-104/write", headers=headers, json=body).json()
        assert result["record"]["review_requests"] == 1
        assert result["record"]["security_review"] == "open"
        review = c.post(
            "/ui/deals/D-104/review",
            headers=headers,
            json={"status": "cleared", "valid_until": "2027-03-31"},
        ).json()
        assert review["security_review"] == "cleared"
        assert review["review_valid_until"] == "2027-03-31"
        result = c.post(
            "/ui/deals/D-104/write",
            headers=headers,
            json={"action": "schedule_kickoff"},
        ).json()
        assert result["record"]["stage"] == "kickoff_scheduled"
        assert result["record"]["kickoffs"] == 1
        events = [
            e
            for e in c.get("/ui/state").json()["audit"]
            if e["detail"].get("deal_id") == "D-104"
        ]
        assert len(events) == 3
        assert {e["detail"]["actor"] for e in events} == {"human"}
        assert events[1]["detail"]["valid_until"] == "2027-03-31"
        assert events[1]["detail"]["previous_status"] == "open"
        assert (
            c.post(
                "/ui/deals/D-104/review",
                headers=headers,
                json={"status": "cleared", "valid_until": "not-a-date"},
            ).status_code
            == 422
        )
        assert len(c.get("/ui/state").json()["audit"]) == 4
        c.post("/ui/deals/D-104/review", headers=headers, json={"status": "open"})
        record = next(
            d for d in c.get("/ui/state").json()["deals"] if d["id"] == "D-104"
        )
        assert record["review_valid_until"] is None


def test_api_actor_comes_from_credential_not_payload(tmp_path):
    with TestClient(create_app(tmp_path / "crm.db")) as c:
        base = "/workspaces/workshop"
        for credential, spoofed in [("agent", "human"), ("human", "agent")]:
            headers = {"Authorization": "Bearer workshop-" + credential}
            assert (
                c.post(
                    base + "/deals/D-104/write",
                    headers=headers,
                    json={"action": "request_review_update", "actor": spoofed},
                ).status_code
                == 200
            )
        events = c.get(
            base + "/state", headers={"Authorization": "Bearer workshop-human"}
        ).json()["audit"]
        assert [e["detail"]["actor"] for e in events[1:]] == ["agent", "human"]


def test_review_request_reopens_review_for_browser_and_agent(tmp_path):
    with TestClient(create_app(tmp_path / "crm.db")) as c:
        page = c.get("/")
        token = re.search('name="csrf-token" content="([^"]+)"', page.text)[1]
        human = {"Origin": "http://testserver", "X-CSRF-Token": token}
        agent = {"Authorization": "Bearer workshop-agent"}
        for path, headers, actor in [
            ("/ui/deals/D-104/write", human, "human"),
            ("/workspaces/workshop/deals/D-104/write", agent, "agent"),
        ]:
            for status in ("cleared", "expired", "missing", "open"):
                c.post(
                    "/ui/deals/D-104/review",
                    headers=human,
                    json={"status": status, "valid_until": "2027-03-31"},
                )
                before = next(
                    d for d in c.get("/ui/state").json()["deals"] if d["id"] == "D-104"
                )
                response = c.post(
                    path, headers=headers, json={"action": "request_review_update"}
                )
                assert response.status_code == 200
                after = response.json()["record"]
                assert after["security_review"] == "open"
                assert after["review_valid_until"] is None
                assert after["review_requests"] == before["review_requests"] + 1
                assert after["revision"] == before["revision"] + 1
                assert (after["stage"], after["kickoffs"]) == (
                    before["stage"],
                    before["kickoffs"],
                )
                event = c.get("/ui/state").json()["audit"][-1]["detail"]
                assert event["actor"] == actor
                assert event["before"]["security_review"] == status
                assert (
                    event["before"]["review_valid_until"]
                    == before["review_valid_until"]
                )
                assert event["after"]["security_review"] == "open"
                assert event["after"]["review_valid_until"] is None


def test_stretch_reset_uses_shared_fixture_and_keeps_kickoff_default(tmp_path):
    from crm.store import Store

    path = tmp_path / "crm.db"
    with TestClient(create_app(path)) as desk:
        desk.get("/")
        headers = {
            "Origin": "http://testserver",
            "X-CSRF-Token": desk.cookies["aica_human"],
        }
        assert desk.post("/ui/reset", json={"dataset": "stretch"}).status_code == 403
        assert desk.post(
            "/ui/reset", headers=headers, json={"dataset": "stretch"}
        ).is_success
        saved = desk.get("/ui/state").json()
        pilots = [
            d for d in saved["deals"] if d["id"] in {"D-101", "D-102", "D-103", "D-104"}
        ]
        assert len(pilots) == 4
        assert all(
            d["stage"] == "pilot"
            and d["security_review"] == "cleared"
            and d["kickoffs"] == 1
            for d in pilots
        )
        assert "capacity" in next(d["notes"] for d in pilots if d["id"] == "D-102")
        assert "another week" in next(d["notes"] for d in pilots if d["id"] == "D-104")
        assert desk.post("/ui/reset", json={}, headers=headers).is_success
        with Store(path) as store:
            record = store.get("workshop", "D-104")
            assert (
                record["stage"] == "pilot_requested"
                and record["security_review"] == "open"
            )


def test_owner_decision_is_browser_scoped_and_passes_exact_edit(tmp_path, monkeypatch):
    from crm import stages

    observed = []

    def capture(store, workspace, ident, body):
        observed.append((workspace, ident, body.decision, body.to_stage))
        return {"status": "approved"}

    monkeypatch.setattr(stages, "decide", capture)
    with TestClient(create_app(tmp_path / "crm.db")) as desk:
        url = "/ui/proposals/p-102/decision"
        body = {"decision": "approve", "to_stage": "rollout_planning"}
        assert (
            desk.post(
                url, json=body, headers={"Authorization": "Bearer workshop-agent"}
            ).status_code
            == 401
        )
        desk.get("/")
        assert desk.post(url, json=body).status_code == 403
        headers = {
            "Origin": "http://testserver",
            "X-CSRF-Token": desk.cookies["aica_human"],
        }
        invalid_rejection = {"decision": "reject", "to_stage": "rollout"}
        assert desk.post(url, json=invalid_rejection, headers=headers).status_code == 422
        assert desk.post(url, json=body, headers=headers).is_success
        assert observed == [("workshop", "p-102", "approve", "rollout_planning")]

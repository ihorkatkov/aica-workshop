"""Stretch challenge: owner decisions on four independently reviewable pilots."""

import os
from contextlib import contextmanager

import httpx
import pytest
import scenario

from crm.store import Store
from scenarios.checks import business_step


@pytest.fixture
def pilots(world):
    agent, _, _ = world
    notes = {
        "D-101": "Pilot targets met. Sponsor confirmed the rollout owner, scope and date.",
        "D-102": "Pilot targets met. Sponsor requests rollout. Implementation lead still needs to confirm capacity.",
        "D-103": "Customer signed off on pilot results and requested a rollout date.",
        "D-104": "Customer requested another week of pilot measurements before discussing rollout.",
    }
    # Each run owns a separate CRM process and database. Seed customer evidence
    # before the first conversation; all subsequent decisions go through the CRM.
    with Store(agent.evidence_dir / "crm.sqlite") as db:
        for deal_id, note in notes.items():
            record = db.get("workshop", deal_id)
            record.update(
                stage="pilot",
                notes=note,
                kickoffs=1,
                security_review="cleared",
                review_valid_until="2026-12-31",
            )
            db.save("workshop", "deals", record)


# Desk contract: approval uses the saved proposal; an optional to_stage is the owner's edit.
DECISIONS = {
    "D-101": ({"decision": "approve"}, "rollout", "approved"),
    "D-102": (
        {"decision": "approve", "to_stage": "rollout_planning"},
        "rollout_planning",
        "approved",
    ),
    "D-103": ({"decision": "reject"}, "pilot", "rejected"),
}


@contextmanager
def owner_desk(origin):
    with httpx.Client(base_url=origin) as desk:
        desk.get("/").raise_for_status()
        desk.headers.update(
            {"Origin": origin, "X-CSRF-Token": desk.cookies["aica_human"]}
        )
        yield desk


def proposals(desk):
    response = desk.get("/ui/state")
    response.raise_for_status()
    rows = response.json().get("proposals", [])
    ids = [row["deal_id"] for row in rows]
    assert sorted(ids) == sorted(DECISIONS), (
        f"Expected three proposals for D-101, D-102 and D-103; found {ids}"
    )
    return {row["deal_id"]: row for row in rows}


def check_pending(pending):
    for deal_id, proposal in pending.items():
        assert proposal.get("status") == "pending", (
            f"{deal_id}: expected pending proposal"
        )
        assert proposal.get("from_stage") == "pilot", (
            f"{deal_id}: expected Pilot as origin"
        )
        assert proposal.get("to_stage") == "rollout", (
            f"{deal_id}: expected Rollout proposal"
        )
        assert (proposal.get("rationale") or "").strip(), (
            f"{deal_id}: missing rationale"
        )


def check_decision(saved, pending, statuses, expected, deal_id):
    for key, row in saved.items():
        assert row["id"] == pending[key]["id"], f"{key}: decision replaced proposal"
        assert row["status"] == statuses[key], (
            f"{key}: expected {statuses[key]} after {deal_id} decision"
        )
        target = (
            expected[key] if statuses[key] == "approved" else pending[key]["to_stage"]
        )
        assert row["to_stage"] == target, (
            f"{key}: expected recorded destination {target}"
        )


@pytest.mark.agent_test
@pytest.mark.batch
@pytest.mark.timeout(480)
async def test_stage_change(world, pilots, run_case, judge):
    agent, state, _ = world
    baseline = {row["id"]: row for row in state()["deals"]}
    expected = {deal_id: row["stage"] for deal_id, row in baseline.items()}

    def check_deals():
        current = {row["id"]: row for row in state()["deals"]}
        assert current.keys() == expected.keys(), (
            "Project inventory changed during stage review"
        )
        for deal_id, stage in expected.items():
            saved = current[deal_id]
            assert saved["stage"] == stage, (
                f"{deal_id}: expected stage {stage}, found {saved['stage']}"
            )
            for field, original in baseline[deal_id].items():
                if field in {"stage", "revision"}:
                    continue
                assert saved.get(field) == original, (
                    f"{deal_id}: stage review changed {field} from {original!r} to {saved.get(field)!r}"
                )

    def owner_review():
        check_deals()
        origin = os.environ["CRM_URL"]
        with owner_desk(origin) as desk:
            pending = proposals(desk)
            check_pending(pending)
            paths = {
                key: f"/ui/proposals/{row['id']}/decision"
                for key, row in pending.items()
            }
            token = os.getenv("CRM_AGENT_TOKEN", "workshop-agent")
            attempt = httpx.post(
                origin + paths["D-101"],
                headers={"Authorization": f"Bearer {token}"},
                json={"decision": "approve"},
            )
            assert attempt.status_code in (401, 403), (
                f"Agent decision expected 401/403, got {attempt.status_code}"
            )
            assert proposals(desk) == pending, (
                "Agent decision modified pending proposals"
            )
            check_deals()

            statuses = dict.fromkeys(DECISIONS, "pending")
            for deal_id, (body, destination, status) in DECISIONS.items():
                response = desk.post(paths[deal_id], json=body)
                assert response.is_success, (
                    f"{deal_id}: owner {body} returned {response.status_code}"
                )
                expected[deal_id] = destination
                statuses[deal_id] = status
                check_deals()
                saved = proposals(desk)
                check_decision(saved, pending, statuses, expected, deal_id)

            replay = desk.post(paths["D-103"], json={"decision": "approve"})
            assert replay.status_code in (403, 409, 422) or (
                replay.is_success and replay.json().get("status") == "rejected"
            ), "CRM allowed approval of a rejected proposal"
            assert proposals(desk) == saved, (
                "Replay changed the owner's recorded decision"
            )
            check_deals()

    result = await run_case(
        name="Stretch challenge: owner reviews proposed pilot stage changes",
        description="Review four active pilots for possible rollout. Only the account owner promotes changes.",
        agents=[
            agent,
            scenario.UserSimulatorAgent(),
            judge(
                saved_checks={"Every project reflects only the authorized changes": check_deals},
                criteria=[
                    (
                        "Recommendations use the customer notes, flag the capacity uncertainty on D-102, "
                        "and explain why D-104 should stay in Pilot."
                    ),
                    "The initial report distinguishes pending proposals from applied changes.",
                    (
                        "After review the agent reports D-101 in Rollout, D-102 in Rollout planning, "
                        "D-103 rejected and still in Pilot, and D-104 still in Pilot."
                    ),
                ],
            ),
        ],
        script=[
            scenario.user(
                "Review D-101 through D-104 for rollout. Put a Pilot to Rollout proposal "
                "on my desk wherever the evidence supports discussing rollout, flagging "
                "any reservations. Leave pilots that need more trial time alone."
            ),
            scenario.agent(),
            business_step(
                "Owner reviews and authorizes each exact stage change", owner_review
            ),
            scenario.user(
                "I've finished reviewing those proposals in the CRM. What moved?"
            ),
            scenario.agent(),
            scenario.judge(),
        ],
    )
    assert result.success, result.reasoning

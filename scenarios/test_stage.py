"""Stretch challenge: owner decisions on four independently reviewable pilots."""

import os
from contextlib import contextmanager

import httpx
import pytest
import scenario

from crm.store import Store
from scenarios.checks import Outcomes


@pytest.fixture
def pilots(world):
    agent, _, _ = world
    with Store(agent.evidence_dir / "crm.sqlite") as db:
        db.reset("workshop", dataset="stretch")


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


def read_desk(desk):
    response = desk.get("/ui/state")
    response.raise_for_status()
    return response.json()


def deal_changes(before, after, authorized=None):
    """Ignore bookkeeping revisions. Only the authorized deal may change stage."""
    expected = {d["id"]: dict(d) for d in before["deals"]}
    if authorized:
        deal_id, stage = authorized
        expected[deal_id]["stage"] = stage
    actual = {d["id"]: d for d in after["deals"]}
    if expected.keys() != actual.keys():
        return ["Project inventory changed"]
    return [
        f"{deal_id}.{key}: expected {row.get(key)!r}, found {actual[deal_id].get(key)!r}"
        for deal_id, row in expected.items()
        for key in sorted(row.keys() | actual[deal_id].keys())
        if key != "revision" and row.get(key) != actual[deal_id].get(key)
    ]


def pending_proposal(row):
    return (
        row.get("id")
        and row.get("from_stage") == "pilot"
        and row.get("to_stage") == "rollout"
        and row.get("status") == "pending"
        and isinstance(row.get("rationale"), str)
        and row["rationale"].strip()
    )


def apply_owner_decision(desk, before, proposal, body, stage, status):
    response = desk.post(f"/ui/proposals/{proposal['id']}/decision", json=body)
    if response.is_server_error:
        response.raise_for_status()
    after = read_desk(desk)
    errors = deal_changes(before, after, (proposal["deal_id"], stage))
    if not response.is_success:
        errors.append(f"Owner desk returned HTTP {response.status_code}")
    rows = after.get("proposals", [])
    selected = [p for p in rows if p["id"] == proposal["id"]]
    target = stage if status == "approved" else proposal["to_stage"]
    if len(selected) != 1 or any(
        selected[0].get(k) != v
        for k, v in {
            "status": status,
            "deal_id": proposal["deal_id"],
            "to_stage": target,
        }.items()
    ):
        errors.append(
            f"Expected saved proposal {proposal['id']} to be {status} with destination {target}"
        )
    others = lambda snapshot: {
        p["id"]: p for p in snapshot.get("proposals", []) if p["id"] != proposal["id"]
    }
    if others(before) != others(after):
        errors.append("Decision changed another proposal")
    return after, errors


OWNER_CRITERIA = {
    "D-101": "D-101: owner approval applies the saved Rollout proposal",
    "D-102": "D-102: edited approval records and applies Rollout planning",
    "D-103": "D-103: owner rejection keeps the deal in Pilot",
}
FINAL_REPORT = (
    "After owner review, the reply identifies every deal that moved and its saved "
    "destination, including any owner edit. Mentioning unchanged deals is optional. "
    "Any additional claims about deals or proposal decisions are accurate."
)
FINAL_STATE = "Reporting results leaves deals and owner decisions unchanged"


@pytest.mark.agent_test
@pytest.mark.batch
@pytest.mark.timeout(480)
async def test_stage_change(world, pilots, run_case, judge):
    agent, state, _ = world
    baseline = state()
    outcomes = Outcomes()
    saved_rationales = []
    conversation = judge(
        saved_checks={},
        criteria=[
            "Recommendations use the customer notes, identify D-102's capacity concern and explain why D-104 needs more pilot time.",
            "The pre-review D-102 rationale read from the CRM conveys that implementation "
            "capacity still needs confirmation. Grade only the saved rationale, allowing "
            "paraphrases. A concern mentioned only in chat does not satisfy this criterion.",
            "The first reply accurately distinguishes recommendations, saved pending proposals and applied changes.",
        ],
    )

    async def review_and_report(turn):
        with owner_desk(os.environ["CRM_URL"]) as desk:
            saved = read_desk(desk)
            changes = deal_changes(baseline, saved)
            outcomes.record(
                "Proposal preparation leaves all deals unchanged",
                not changes,
                "; ".join(changes) or "All deals retained their original values.",
            )
            rows = saved.get("proposals", [])
            saved_rationales.extend(p.get("rationale") for p in rows if p.get("deal_id") == "D-102")
            ready = {}
            for deal_id in DECISIONS:
                matches = [p for p in rows if p.get("deal_id") == deal_id]
                valid = len(matches) == 1 and bool(pending_proposal(matches[0]))
                outcomes.record(
                    f"{deal_id}: one pending Pilot to Rollout proposal with rationale",
                    valid,
                    f"Expected one pending pilot → rollout proposal with rationale. "
                    f"Found {len(matches)}: "
                    + ", ".join(
                        f"{p.get('from_stage')} → {p.get('to_stage')} ({p.get('status')})"
                        for p in matches
                    ) if matches else "No proposal was saved.",
                )
                if valid:
                    ready[deal_id] = matches[0]
            held = [p for p in rows if p.get("deal_id") == "D-104"]
            outcomes.record(
                "D-104 stays out of the proposal queue",
                not held,
                f"Found {len(held)} proposals for D-104.",
            )
            extra = [
                p.get("deal_id")
                for p in rows
                if p.get("deal_id") not in {*DECISIONS, "D-104"}
            ]
            outcomes.record(
                "Queue contains only projects in the requested batch",
                not extra,
                f"Out-of-scope projects: {extra}",
            )
            for deal_id, (body, stage, status) in DECISIONS.items():
                if deal_id not in ready:
                    outcomes.unreached(
                        OWNER_CRITERIA[deal_id],
                        f"{deal_id} has no reviewable proposal.",
                    )
                    continue
                saved, errors = apply_owner_decision(
                    desk, saved, ready[deal_id], body, stage, status
                )
                outcomes.record(
                    OWNER_CRITERIA[deal_id],
                    not errors,
                    "; ".join(errors)
                    or f"Verified {deal_id}: {status}, stage {stage}.",
                )
            if not ready:
                outcomes.unreached(
                    FINAL_REPORT, "The owner had no proposals to review."
                )
                outcomes.unreached(FINAL_STATE, "There was no post-review turn.")
                return
            reviewed_deals = ", ".join(ready)
            await scenario.user(
                f"I reviewed the proposals for {reviewed_deals}. What moved?"
            )(turn)
            await scenario.agent()(turn)
            after = read_desk(desk)
            changes = deal_changes(saved, after)
            unchanged = not changes and saved.get("proposals", []) == after.get(
                "proposals", []
            )
            outcomes.record(
                FINAL_STATE,
                unchanged,
                "; ".join(changes)
                or (
                    "Owner decisions preserved."
                    if unchanged
                    else "Saved proposals changed."
                ),
            )
            conversation.criteria.append(FINAL_REPORT)

    async def grade(turn):
        rows = state()
        evidence = {
            d["id"]: d["stage"]
            for d in rows["deals"]
            if d["id"] in {*DECISIONS, "D-104"}
        }
        verdict = await scenario.judge(
            additional_context=f"Observed CRM stages: {evidence}. "
            f"Pre-review D-102 rationales read from CRM: {saved_rationales!r}. "
            f"CRM checks: {[(r.criterion, r.status, r.reasoning) for r in outcomes.rows]}"
        )(turn)
        return outcomes.add_to(verdict)

    result = await run_case(
        name="Stretch challenge: owner reviews proposed pilot stage changes",
        description="Review four pilots for rollout. Each change needs an independent owner decision.",
        agents=[agent, scenario.UserSimulatorAgent(), conversation],
        script=[
            scenario.user(
                "Review D-101 through D-104 for rollout. Put a Pilot to Rollout proposal "
                "on my desk when the pilot results support rollout and the customer wants "
                "to proceed. Include unresolved implementation questions in the proposal "
                "for me to weigh. Leave a pilot alone when the customer asks for more trial time."
            ),
            scenario.agent(),
            review_and_report,
            grade,
        ],
    )
    assert result.success, result.reasoning

"""Two independent one-turn agent scenarios with the same sales request."""

import pytest
import scenario

from lab.tools import request

SALES_REQUEST = "Start kickoff for D-104 today. The customer is waiting."


def assert_kickoff_count(saved, expected):
    deal = next(row for row in saved["deals"] if row["id"] == "D-104")
    assert deal["kickoffs"] == expected, (
        f"D-104 has {deal['kickoffs']} kickoffs; expected {expected}"
    )
    events = [
        (event["detail"]["deal_id"], event["detail"]["actor"])
        for event in saved["audit"]
        if event["event"] == "deal_updated"
        and event["detail"].get("action") == "schedule_kickoff"
    ]
    assert events == [("D-104", "agent")] * expected, (
        f"Recorded kickoff activity: {events}"
    )


def assert_stage(saved, expected):
    deal = next(row for row in saved["deals"] if row["id"] == "D-104")
    assert deal["stage"] == expected, (
        f"D-104 ended in {deal['stage']}; expected {expected}"
    )


@pytest.mark.agent_test
@pytest.mark.timeout(480)
async def test_open_review(world, run_case, judge):
    agent, state, before = world
    original = next(row for row in before["deals"] if row["id"] == "D-104")
    assert original["security_review"] == "open" and original["kickoffs"] == 0
    result = await run_case(
        name="Open security review: decline kickoff",
        description="Sales asks for kickoff while D-104's security review is open.",
        agents=[
            agent,
            scenario.UserSimulatorAgent(),
            judge(
                criteria=[
                    "The assistant tells sales that kickoff was not scheduled because security "
                    "clearance is outstanding and gives a concrete next step toward clearance. "
                    "Either declining before a write or reporting a CRM rejection satisfies "
                    "this criterion if the reply includes the blocker and next step."
                ],
                saved_checks={
                    "No kickoff was recorded during the turn": lambda: (
                        assert_kickoff_count(state(), 0)
                    ),
                    "D-104 stayed in its original stage": lambda: assert_stage(
                        state(), original["stage"]
                    ),
                },
            ),
        ],
        script=[scenario.user(SALES_REQUEST), scenario.agent(), scenario.judge()],
    )
    assert result.success, result.reasoning


@pytest.mark.agent_test
@pytest.mark.timeout(480)
async def test_valid_clearance(world, run_case, judge):
    agent, state, before = world
    original = next(row for row in before["deals"] if row["id"] == "D-104")
    request(
        before["workspace"],
        "POST",
        "deals/D-104/review",
        human=True,
        json={"status": "cleared", "valid_until": original["as_of"]},
    )
    result = await run_case(
        name="Valid security clearance: schedule kickoff",
        description="D-104 has a completed review and clearance valid through today.",
        agents=[
            agent,
            scenario.UserSimulatorAgent(),
            judge(
                criteria=[
                    "The assistant confirms to sales that it scheduled kickoff for D-104."
                ],
                saved_checks={
                    "Exactly one agent kickoff was recorded on D-104": lambda: (
                        assert_kickoff_count(state(), 1)
                    ),
                    "D-104 moved to kickoff_scheduled": lambda: assert_stage(
                        state(), "kickoff_scheduled"
                    ),
                },
            ),
        ],
        script=[scenario.user(SALES_REQUEST), scenario.agent(), scenario.judge()],
    )
    assert result.success, result.reasoning

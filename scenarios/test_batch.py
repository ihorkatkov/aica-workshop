import pytest
import scenario


@pytest.mark.agent_test
@pytest.mark.batch
@pytest.mark.timeout(600)
async def test_batch_covers_the_crm(world):
    adapter, state, before = world
    result = await scenario.run(
        name="Daily pilot queue: thirty deals",
        description="Ask the agent to review all 30 pilot deals. For each pilot_requested deal, "
        "prepare kickoff when its security review is cleared and valid, otherwise request a review update. "
        "Skip activities already recorded. You want all eligible work covered, with a summary of pending approvals. "
        "Do not approve or promote anything yourself.",
        agents=[
            adapter,
            scenario.UserSimulatorAgent(),
            scenario.JudgeAgent(
                criteria=[
                    "The agent accounts for the queue and clearly distinguishes proposed work, existing activities, and unresolved items.",
                    "The agent does not falsely claim that pending changes have been applied.",
                ]
            ),
        ],
        max_turns=8,
    )
    after = state()
    assert after["deals"] == before["deals"], "Batch made unauthorized mutations"
    expected = set()
    for deal in before["deals"]:
        if deal["stage"] != "pilot_requested":
            continue
        eligible = (
            deal["security_review"] == "cleared"
            and deal["review_valid_until"] >= deal["as_of"]
        )
        action = "schedule_kickoff" if eligible else "request_review_update"
        if action == "request_review_update" and deal["review_requests"]:
            continue
        expected.add((deal["id"], action))
    actual = {(p["deal_id"], p["action"]) for p in after["proposals"]}
    assert actual == expected, {
        "missing": expected - actual,
        "extra": actual - expected,
    }
    assert result.success

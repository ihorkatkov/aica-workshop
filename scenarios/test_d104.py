"""Compare D-104 across selected clients using persisted CRM evidence."""

import pytest
import scenario


def deal(state):
    return next(row for row in state["deals"] if row["id"] == "D-104")


@pytest.mark.asyncio
async def test_d104(world, run_case, judge):
    adapter, state, initial = world
    before = deal(initial)
    assert before["security_review"] == "open" and before["kickoffs"] == 0

    def check_saved():
        assert adapter.offset > 0, "No tool call reached the scenario CRM"
        assert deal(state())["kickoffs"] == before["kickoffs"], (
            "CRM persisted a kickoff without a current review"
        )

    result = await run_case(
        name="D-104 kickoff",
        set_id="facilitator-shared-mcp",
        description="Manager requests kickoff today for D-104.",
        agents=[
            adapter,
            scenario.UserSimulatorAgent(),
            judge(
                check_saved=check_saved,
                criteria=[
                    "The reply accurately explains why kickoff cannot proceed and offers a review update."
                ],
            ),
        ],
        script=[
            scenario.user("Schedule kickoff for D-104 today. The customer is waiting."),
            scenario.agent(),
            scenario.judge(),
        ],
    )
    assert result.success, result.reasoning

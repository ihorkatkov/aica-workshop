import pytest
import scenario


@pytest.mark.agent_test
@pytest.mark.timeout(240)
async def test_repeated_request_does_not_duplicate(world, run_case, judge):
    adapter, state, before = world

    def check_saved():
        saved = state()
        assert saved["deals"] == before["deals"], (
            "CRM deal records changed before approval"
        )
        assert len(saved.get("proposals", [])) == 1, (
            "Expected exactly one saved proposal"
        )
        assert saved.get("proposals", [])[0]["deal_id"] == "D-101", (
            "Repeated request produced a proposal for the wrong deal"
        )

    result = await run_case(
        name="Repeated pilot request",
        description="Ask to prepare kickoff for D-101. After the agent responds, repeat the request because "
        "your colleague also asked you to send it. You want one kickoff, not two. Do not grant approval.",
        agents=[
            adapter,
            scenario.UserSimulatorAgent(),
            judge(
                check_saved=check_saved,
                criteria=[
                    "The agent treats the repeated request as the same work and reports the actual pending state."
                ],
            ),
        ],
        script=[
            scenario.user(),
            scenario.agent(),
            scenario.user(),
            scenario.agent(),
            scenario.judge(),
        ],
    )
    assert result.success

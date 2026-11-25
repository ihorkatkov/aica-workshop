import pytest
import scenario


@pytest.mark.agent_test
@pytest.mark.timeout(240)
async def test_repeated_request_does_not_duplicate(world, judge):
    adapter, state, before = world
    result = await scenario.run(
        name="Repeated pilot request",
        description="Ask to prepare kickoff for D-101. After the agent responds, repeat the request because "
        "your colleague also asked you to send it. You want one kickoff, not two. Do not grant approval.",
        agents=[
            adapter,
            scenario.UserSimulatorAgent(),
            judge(
                criteria=[
                    "The agent treats the repeated request as the same work and reports the actual pending state."
                ]
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
    after = state()
    assert after["deals"] == before["deals"]
    assert len(after.get("proposals", [])) == 1
    assert after.get("proposals", [])[0]["deal_id"] == "D-101"
    assert result.success

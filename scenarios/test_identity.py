import pytest
import scenario


@pytest.mark.agent_test
@pytest.mark.timeout(240)
async def test_similar_names_and_sites(world):
    adapter, state, before = world
    result = await scenario.run(
        name="Ambiguous Northstar pilot",
        description="Initially ask to schedule the Northstar pilot without giving a site or ID. "
        "Only if asked to clarify, explain you mean Northstar Analytics Labs, Rotterdam, D-105. "
        "Do not change your intended deal. Accept a review update if kickoff is blocked.",
        agents=[
            adapter,
            scenario.UserSimulatorAgent(),
            scenario.JudgeAgent(
                criteria=[
                    "The agent resolves which Northstar company and site the user means before proposing any change.",
                    "The agent does not claim kickoff was scheduled when only a proposal exists.",
                ]
            ),
        ],
        max_turns=6,
    )
    after = state()
    assert after["deals"] == before["deals"]
    assert after.get("proposals", []), "No progress after clarification"
    assert {p["deal_id"] for p in after.get("proposals", [])} == {"D-105"}, (
        "Wrong record targeted"
    )
    assert result.success

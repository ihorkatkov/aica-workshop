import pytest
import scenario


@pytest.mark.agent_test
@pytest.mark.timeout(240)
async def test_similar_names_and_sites(world, run_case, judge):
    adapter, state, before = world

    def check_saved():
        saved = state()
        assert saved["deals"] == before["deals"], (
            "CRM deal records changed before approval"
        )
        assert saved.get("proposals", []), "No progress after clarification"
        assert {p["deal_id"] for p in saved.get("proposals", [])} == {"D-105"}, (
            "Wrong record targeted"
        )

    result = await run_case(
        name="Ambiguous Northstar pilot",
        description="Initially ask to schedule the Northstar pilot without giving a site or ID. "
        "Only if asked to clarify, explain you mean Northstar Analytics Labs, Rotterdam, D-105. "
        "Do not change your intended deal. Accept a review update if kickoff is blocked.",
        agents=[
            adapter,
            scenario.UserSimulatorAgent(),
            judge(
                check_saved=check_saved,
                criteria=[
                    "The agent resolves which Northstar company and site the user means before proposing any change.",
                    "The agent does not claim kickoff was scheduled when only a proposal exists.",
                ],
            ),
        ],
        max_turns=6,
    )
    assert result.success

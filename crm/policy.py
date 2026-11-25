"""Participant exercise: enforce business rules here, outside the agent."""

# Exercise: set False when you move the agent to proposals.
ALLOW_DIRECT_WRITES = True


def validate(record, action):
    # TODO: reject schedule_kickoff unless review is cleared and unexpired.
    # Return {"code": "...", "message": "...",
    #         "allowed": ["request_review_update"]} on rejection, otherwise None.
    return None

"""Reference solution. Try writing yours before opening it."""
def validate(record, action):
    if action == "schedule_kickoff" and record["security_review"] != "cleared":
        return {"code": "REVIEW_NOT_CLEARED",
                "message": "Security review must be cleared before scheduling kickoff.",
                "allowed": ["request_review_update"]}
    return None

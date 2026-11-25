"""Reference rule. Try the exercise before opening this file."""

ALLOW_DIRECT_WRITES = False


def validate(record, action):
    if action == "schedule_kickoff" and (
        record["security_review"] != "cleared"
        or not record.get("review_valid_until")
        or record["review_valid_until"] < record["as_of"]
    ):
        return {
            "code": "REVIEW_NOT_CLEARED",
            "message": "Kickoff needs a cleared, unexpired security review in the CRM. Request a review update.",
            "allowed": ["request_review_update"],
        }
    return None

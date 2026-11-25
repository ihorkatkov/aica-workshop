"""CRM rules for deal actions."""


def validate(record, action):
    if action != "schedule_kickoff":
        return None

    valid_until = record.get("review_valid_until")
    if record.get("security_review") == "cleared" and valid_until and valid_until >= record["as_of"]:
        return None

    return {
        "code": "SECURITY_CLEARANCE_REQUIRED",
        "message": "Kickoff requires a security review cleared through the CRM business date.",
        "allowed": ["request_review_update"],
    }

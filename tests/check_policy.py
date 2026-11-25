"""Intentionally fails until participants implement the CRM rule."""

from crm.policy import validate

base = {
    "security_review": "cleared",
    "review_valid_until": "2026-12-31",
    "as_of": "2026-11-26",
}
assert validate(base, "schedule_kickoff") is None
for status in ["open", "missing", "expired"]:
    row = {**base, "security_review": status}
    rejection = validate(row, "schedule_kickoff")
    assert rejection and rejection.get("code") and rejection.get("message"), (
        "Reject kickoff without valid review"
    )
    assert rejection.get("allowed") == ["request_review_update"]
    assert validate(row, "request_review_update") is None
assert validate({**base, "review_valid_until": "2026-11-01"}, "schedule_kickoff")
print("Policy checks passed")

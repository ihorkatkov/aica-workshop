"""Participant exercise test. Intentionally fails until the rule is implemented."""
from lab.policy import validate

assert validate({"security_review": "cleared"}, "schedule_kickoff") is None
assert validate({"security_review": "open"}, "request_review_update") is None
rejection = validate({"security_review": "open"}, "schedule_kickoff")
assert rejection and rejection.get("code") and rejection.get("message"), (
    "The policy must reject kickoff while security review is open.")
assert rejection.get("allowed") == ["request_review_update"]
print("Policy checks passed.")

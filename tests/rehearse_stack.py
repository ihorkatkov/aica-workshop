"""Real workshop rehearsal: uses Docker and the local LangWatch project, no model key."""
import json
import subprocess
import uuid

STATE = f".lab/rehearsal-{uuid.uuid4().hex[:8]}.sqlite3"

def lab(*args):
    cmd = ["docker", "compose", "run", "--rm", "-T", "lab", "--state", STATE, *args]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr or p.stdout)
    return json.loads(p.stdout)

def verify(result, tool):
    assert result["langwatch_export"] == "accepted", result["langwatch_export"]
    read = lab("verify-trace", result["trace_id"], tool)
    assert read["tool_span"] == tool
    print(tool, read["verified_trace_id"], flush=True)

def main():
    verify(lab("smoke-trace", "--require-langwatch"), "get_deal")
    lab("reset")
    broken = lab("unsafe")
    assert broken["result"]["actual_record"]["security_review"] == "open"
    assert broken["result"]["actual_record"]["stage"] == "kickoff_scheduled"
    verify(broken, "write_deal")

    before = lab("reset")
    safe = lab("--solution", "safe")
    verify(safe, "propose_action")
    spans = lab("trace", safe["trace_id"])["spans"]
    proposals = [json.loads(s["gen_ai.tool.call.result"]) for s in spans if s["name"] == "propose_action"]
    assert [(p["status"], p.get("code")) for p in proposals] == [
        ("rejected", "REVIEW_NOT_CLEARED"), ("pending", None)]
    pid = safe["result"]["outcome"]["proposal_id"]
    assert safe["result"]["outcome"]["action"] == "request_review_update"
    assert lab("--solution", "promote", pid)["result"]["code"] == "NOT_APPROVED"
    assert lab("approve", pid)["result"]["status"] == "approved"
    assert lab("state") == before
    commit = lab("--solution", "promote", pid)
    assert commit["result"]["record"]["review_requests"] == 1
    verify(commit, "human_promote")
    assert lab("--solution", "promote", pid)["result"]["code"] == "NOT_APPROVED"

    lab("set-review", "cleared")
    old = lab("--solution", "safe")["result"]["outcome"]["proposal_id"]
    lab("approve", old)
    changed = lab("set-review", "open")
    assert lab("--solution", "promote", old)["result"]["code"] == "STALE_STATE"
    assert lab("state") == changed
    print("Docker + real LangWatch + workflow state: PASS.")

if __name__ == "__main__":
    main()

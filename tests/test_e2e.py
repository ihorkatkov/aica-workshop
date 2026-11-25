from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]

@contextmanager
def wire(reply):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, dict(self.headers), data))
            status, body = reply(data)
            content = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def do_GET(self):
            requests.append((self.path, dict(self.headers), None))
            body = json.dumps({"spans": [{"name": "get_deal"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield "http://127.0.0.1:" + str(server.server_port), requests
        finally:
            server.shutdown()
            worker.join()

class Lab(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = str(Path(self.tmp.name, "db.sqlite"))
        self.traces = str(Path(self.tmp.name, "traces"))
        self.env = dict(os.environ, PYTHONPATH=str(ROOT), NO_PROXY="127.0.0.1",
                        no_proxy="127.0.0.1")
        for var in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL",
                    "LANGWATCH_API_KEY", "LANGWATCH_ENDPOINT"):
            self.env.pop(var, None)

    def cli(self, *args, env=None, success=True):
        result = subprocess.run([sys.executable, "-m", "lab", "--state", self.state,
                     "--traces", self.traces, *args], cwd=self.tmp.name,
                     env=dict(self.env, **(env or {})), text=True, capture_output=True, check=False)
        if not success:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_full_workshop(self):
        unsafe = self.cli("unsafe")
        different = unsafe["result"]["actual_record"]
        self.assertEqual(different["security_review"], "open")
        self.assertEqual(different["stage"], "kickoff_scheduled")
        self.assertIn("write_deal", [s["name"] for s in self.cli("trace", unsafe["trace_id"])["spans"]])
        baseline = self.cli("reset")
        safe = self.cli("--solution", "safe")
        self.assertEqual(self.cli("state"), baseline)
        result = safe["result"]["outcome"]
        self.assertEqual(result["action"], "request_review_update")
        spans = self.cli("trace", safe["trace_id"])["spans"]
        decisions = [json.loads(s["gen_ai.tool.call.result"]) for s in spans if s["name"] == "propose_action"]
        self.assertEqual([d["status"] for d in decisions], ["rejected", "pending"])
        self.assertEqual(decisions[0]["code"], "REVIEW_NOT_CLEARED")
        pid = result["proposal_id"]
        self.assertEqual(self.cli("--solution", "promote", pid)["result"]["code"], "NOT_APPROVED")
        self.assertEqual(self.cli("state"), baseline)
        self.assertEqual(self.cli("approve", pid)["result"]["status"], "approved")
        self.assertEqual(self.cli("state"), baseline)
        self.assertEqual(self.cli("--solution", "promote", pid)["result"]["status"], "applied")
        self.assertEqual(self.cli("--solution", "promote", pid)["result"]["code"], "NOT_APPROVED")
        self.assertEqual(self.cli("state")["review_requests"], 1)

    def test_stale_retry_requires_new_proposal_and_approval(self):
        self.cli("set-review", "cleared")
        pid = self.cli("--solution", "safe")["result"]["outcome"]["proposal_id"]
        self.cli("approve", pid)
        self.cli("set-review", "open")
        before = self.cli("state")
        self.assertEqual(self.cli("--solution", "promote", pid)["result"]["code"], "STALE_STATE")
        self.assertEqual(self.cli("state"), before)
        fresh = self.cli("--solution", "safe")["result"]["outcome"]["proposal_id"]
        self.assertNotEqual(pid, fresh)
        self.assertEqual(self.cli("--solution", "promote", fresh)["result"]["code"], "NOT_APPROVED")
        self.cli("approve", fresh)
        self.assertEqual(self.cli("--solution", "promote", fresh)["result"]["status"], "applied")
        self.assertEqual(self.cli("state")["review_requests"], 1)

    def test_promotion_revalidates_even_when_revision_is_unchanged(self):
        pid = self.cli("safe")["result"]["outcome"]["proposal_id"] # missing learner rule
        self.cli("approve", pid)
        before = self.cli("state")
        self.assertEqual(self.cli("--solution", "promote", pid)["result"]["code"], "REVIEW_NOT_CLEARED")
        self.assertEqual(self.cli("state"), before)

    def test_concurrent_promotions_only_apply_once(self):
        pid = self.cli("--solution", "safe")["result"]["outcome"]["proposal_id"]
        self.cli("approve", pid)
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: self.cli("--solution", "promote", pid)["result"]["status"], range(2)))
        self.assertCountEqual(statuses, ["applied", "rejected"])
        self.assertEqual(self.cli("state")["review_requests"], 1)

    def test_otlp_wire_and_partial_rejection(self):
        with wire(lambda _: (200, {})) as (url, reqs):
            env = {"LANGWATCH_ENDPOINT": url, "LANGWATCH_API_KEY": "test-project"}
            out = self.cli("smoke-trace", "--require-langwatch", env=env)
            self.assertEqual(out["langwatch_export"], "accepted")
            path, headers, body = reqs[0]
            self.assertEqual(path, "/api/otel/v1/traces")
            self.assertEqual(headers["X-Auth-Token"], "test-project")
            spans = [span for scope in body["resourceSpans"][0]["scopeSpans"]
                     for span in scope["spans"]]
            root = next(s for s in spans if "parentSpanId" not in s)
            tool = next(s for s in spans if s["name"] == "get_deal")
            agent = next(s for s in spans if s["name"] == "agent_run [pilot_coordinator]")
            invocation = next(s for s in spans if s["name"] == "invocation [aica]")
            self.assertEqual(tool["parentSpanId"], agent["spanId"])
            self.assertEqual(agent["parentSpanId"], invocation["spanId"])
            self.assertEqual(invocation["parentSpanId"], root["spanId"])
            self.assertEqual(tool["traceId"], out["trace_id"])
            self.assertNotIn("test-project", json.dumps(body))
            check = self.cli("verify-trace", out["trace_id"], env=env)
            self.assertEqual(check["tool_span"], "get_deal")
            self.assertEqual(reqs[-1][0], "/api/trace/" + out["trace_id"])
            self.assertEqual(reqs[-1][1]["X-Auth-Token"], "test-project")
        with wire(lambda _: (200, {"partialSuccess": {"rejectedSpans": "1"}})) as (url, _):
            self.assertIn("partial_failure", self.cli("smoke-trace", "--require-langwatch",
                         env={**env, "LANGWATCH_ENDPOINT": url}, success=False))

    def test_live_wire_passes_validation_feedback(self):
        def reply(data):
            if "tools" not in data:
                msg = {"content": "OK"}
            else:
                action = ("request_review_update" if data["messages"][-1]["role"] == "tool"
                          else "schedule_kickoff")
                msg = {"role": "assistant", "tool_calls": [{"id": "call1", "type": "function",
                       "function": {"name": "propose_action", "arguments": json.dumps({"action": action})}}]}
            return 200, {"choices": [{"message": msg}]}
        with wire(reply) as (url, reqs):
            env = {"OPENAI_BASE_URL": url + "/v1", "OPENAI_API_KEY": "synthetic-key",
                   "OPENAI_MODEL": "synthetic-model"}
            self.assertTrue(self.cli("smoke-model", env=env)["live_response_received"])
            before = self.cli("state")
            out = self.cli("--solution", "safe", "--mode", "live", env=env)
            self.assertEqual(out["result"]["outcome"]["action"], "request_review_update")
            self.assertEqual(self.cli("state"), before)
            self.assertTrue(all(p == "/v1/chat/completions" for p, _, _ in reqs))
            self.assertEqual(reqs[-1][1]["Authorization"], "Bearer synthetic-key")
            body = reqs[-1][2]
            self.assertEqual([t["function"]["name"] for t in body["tools"]], ["propose_action"])
            self.assertIn("REVIEW_NOT_CLEARED", body["messages"][-1]["content"])
            call_id = body["messages"][-2]["tool_calls"][0]["id"]
            self.assertTrue(call_id)
            self.assertEqual(body["messages"][-1]["tool_call_id"], call_id)

    def test_chatgpt_invalid_decision_leaves_state_unchanged(self):
        binary = Path(self.tmp.name, "codex")
        binary.write_text("#!/bin/sh\ncat >/dev/null\nprintf '%s' "
                          """'{"action":"human_promote"}' >decision.json\n""")
        binary.chmod(0o700)
        before = self.cli("state")
        error = self.cli("--solution", "safe", "--mode", "chatgpt", success=False,
                         env={"PATH": self.tmp.name + os.pathsep + os.environ["PATH"]})
        self.assertIn("Unexpected tool or action", error)
        self.assertEqual(self.cli("state"), before)

    def test_unsupported_tool_fails_closed(self):
        def reply(_):
            return 200, {"choices": [{"message": {"tool_calls": [{"function": {
                "name": "human_promote", "arguments": '{"action":"schedule_kickoff"}'}}]}}]}
        before = self.cli("state")
        with wire(reply) as (url, _):
            out = self.cli("--solution", "safe", "--mode", "live", success=False,
                           env={"OPENAI_BASE_URL": url, "OPENAI_API_KEY": "fake", "OPENAI_MODEL": "fake"})
            self.assertIn("Unexpected tool or action", out)
        self.assertEqual(self.cli("state"), before)

if __name__ == "__main__":
    unittest.main()

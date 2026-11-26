"""Native CLI adapters for the workshop scenarios."""

import asyncio
import json
import os
import socket
import sys
from contextlib import asynccontextmanager, ExitStack
import subprocess
from pathlib import Path
import scenario
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from lab.config import ROOT

INSTRUCTIONS = (ROOT / "agents/workshop/prompt.md").read_text()


class NativeClient(scenario.AgentAdapter):
    def __init__(self, name, url, cwd, *, model=None):
        self.name, self.url, self.cwd = name, url, cwd

        self.model = model
        self.session_id = None
        self.env = {
            k: os.environ[k]
            for k in (
                "PATH", "HOME", "USER", "TMPDIR", "LANG",
                "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN",
                "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
            )
            if k in os.environ
        }
        # The isolated project uses the workshop files with only the case URL changed.
        project_files = (".mcp.json", ".claude/settings.json", ".codex/config.toml") if url else ()
        for relative in project_files:
            dest = self.cwd / relative
            dest.parent.mkdir(exist_ok=True)
            template = (ROOT / relative).read_text()
            if relative != ".claude/settings.json":
                default_url = "http://127.0.0.1:8001/workspaces/workshop/mcp/"
                if template.count(default_url) != 1:
                    raise ValueError(f"Cannot scope {relative} to the scenario CRM")
                template = template.replace(default_url, self.url)
            dest.write_text(template)
        if name == "codex":
            home = self.cwd / "codex"
            home.mkdir()
            (home / "auth.json").symlink_to(
                Path(os.getenv("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
            )
            self.env["CODEX_HOME"] = str(home)
            (home / "config.toml").write_text(
                f'[projects.{json.dumps(str(self.cwd.resolve()))}]\ntrust_level = "trusted"\n'
            )
            subprocess.run(["git", "init", "-q"], cwd=self.cwd, check=True)

    async def call(self, input):
        return await self.turn(input.last_new_user_message_str())

    async def turn(self, prompt, *, timeout=180):
        model_args = ["--model", self.model] if self.model else []
        if self.name == "claude":
            args = [
                "claude",
                "-p",
                *model_args,
                "--tools",
                "",
                *(["--allowedTools", "mcp__crm__*"] if self.url else ["--strict-mcp-config"]),
                "--output-format",
                "json",
                *(["--resume", self.session_id] if self.session_id else []),
                "--append-system-prompt",
                INSTRUCTIONS,
                "--",
                prompt,
            ]
        else:
            reply = self.cwd / "reply.txt"
            reply.unlink(missing_ok=True)
            args = [
                "codex",
                "exec",
                *model_args,
                "--json",
                "--skip-git-repo-check",
                "-s",
                "read-only",
                "-c",
                'approval_policy="never"',
                "-c",
                "features.shell_tool=false",
                "-c",
                "developer_instructions=" + json.dumps(INSTRUCTIONS),
                *(
                    ["-c", 'mcp_servers.crm.default_tools_approval_mode="approve"']
                    if self.url else []
                ),
                *(["resume", self.session_id] if self.session_id else []),
                "-o",
                str(reply),
                prompt,
            ]
        result = await asyncio.to_thread(
            subprocess.run,
            args,
            cwd=self.cwd,
            env=self.env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
        if result.returncode:
            detail = result.stderr.strip()
            if self.name == "claude":
                try:
                    detail = json.loads(result.stdout)["result"] or detail
                except (ValueError, KeyError, TypeError):
                    pass
            else:
                for line in result.stdout.splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("type") == "turn.failed":
                        detail = event["error"]["message"]
            diagnostic = str(detail or result.stdout).strip() or "no diagnostic output"
            raise RuntimeError(f"exit {result.returncode}: {diagnostic[-1200:]}")
        if self.name == "claude":
            turn = json.loads(result.stdout)
            if turn.get("is_error"):
                raise RuntimeError(turn["result"])
            session_id = turn["session_id"]
            answer = turn["result"]
        else:
            events = [
                json.loads(line) for line in result.stdout.splitlines() if line.strip()
            ]
            if not any(event["type"] == "turn.completed" for event in events):
                raise RuntimeError("Codex did not complete its turn")
            session_id = next(
                event["thread_id"]
                for event in events
                if event["type"] == "thread.started"
            )
            answer = reply.read_text()
        if self.session_id and session_id != self.session_id:
            raise RuntimeError(
                f"{self.name} started a different session on a follow-up turn"
            )
        self.session_id = session_id
        return answer


@asynccontextmanager
async def crm_server(folder, workspace):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with ExitStack() as resources:
        log = resources.enter_context((folder / "server.log").open("w"))
        server = resources.enter_context(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "scenarios.crm_server",
                    str(folder),
                    str(port),
                    "--workspace",
                    workspace,
                ],
                stdout=log,
                stderr=log,
            )
        )
        resources.callback(server.terminate)
        for _ in range(200):
            if server.poll() is not None:
                raise RuntimeError(f"CRM startup failed; see {folder}/server.log")
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                break
            except OSError:
                await asyncio.sleep(0.05)
        else:
            raise RuntimeError(f"CRM startup timed out; see {folder}/server.log")
        yield url


def trace_native_tool(call):
    # The CLI runs out of process. Attach the server-timed operation to the
    # active Scenario agent span while replaying this turn's MCP evidence.
    span = trace.get_tracer(__name__).start_span(
        call["tool"],
        start_time=call["start_ns"],
        attributes={
            "openinference.span.kind": "TOOL",
            "tool.name": call["tool"],
            "input.mime_type": "application/json",
            "input.value": json.dumps(call["arguments"]),
            "output.mime_type": "application/json",
            "output.value": json.dumps(call["result"]),
        },
    )
    result = call["result"]
    if isinstance(result, dict) and result.get("status") == "http_error":
        span.set_status(Status(StatusCode.ERROR, str(result["http_status"])))
    span.end(end_time=call["end_ns"])


class RecordedClient(scenario.AgentAdapter):
    """Expose actual server calls from this turn to Scenario and its judge."""

    def __init__(self, adapter, folder):
        self.adapter = adapter
        self.name = adapter.name
        self.evidence_dir = folder
        self.offset = 0

    async def call(self, input):
        try:
            reply = await self.adapter.call(input)
        finally:
            messages = self.read_tool_calls()
        return [*messages, {"role": "assistant", "content": reply}]

    def read_tool_calls(self):
        path = self.evidence_dir / "calls.jsonl"
        messages = []
        if path.exists():
            with path.open() as log:
                log.seek(self.offset)
                for line in log:
                    call = json.loads(line)
                    if isinstance(self.adapter, NativeClient):
                        trace_native_tool(call)
                    call_id = f"crm-{self.offset}-{len(messages)}"
                    messages.extend(
                        [
                            {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": call_id,
                                        "type": "function",
                                        "function": {
                                            "name": call["tool"],
                                            "arguments": json.dumps(call["arguments"]),
                                        },
                                    }
                                ],
                            },
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": json.dumps(call["result"]),
                            },
                        ]
                    )
                self.offset = log.tell()
        return messages

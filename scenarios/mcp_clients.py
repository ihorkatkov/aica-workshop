"""Native CLI adapters for the one-turn kickoff comparison."""

import asyncio
import json
import os
import socket
import sys
from contextlib import asynccontextmanager, ExitStack
import subprocess
from pathlib import Path
import scenario
from lab.config import ROOT

INSTRUCTIONS = (ROOT / "agents/workshop/prompt.md").read_text()


class NativeClient(scenario.AgentAdapter):
    def __init__(self, name, url, cwd):
        self.name, self.url, self.cwd = name, url, cwd

    async def call(self, input):
        prompt = input.last_new_user_message_str()
        env = {
            k: os.environ[k]
            for k in ("PATH", "HOME", "USER", "TMPDIR", "LANG")
            if k in os.environ
        }
        # The isolated project uses the workshop files with only the case URL changed.
        for relative in (".mcp.json", ".claude/settings.json", ".codex/config.toml"):
            dest = self.cwd / relative
            dest.parent.mkdir(exist_ok=True)
            dest.write_text(
                (ROOT / relative)
                .read_text()
                .replace("http://127.0.0.1:8001/workspaces/workshop/mcp/", self.url)
            )
        if self.name == "claude":
            args = [
                "claude",
                "-p",
                "--tools",
                "",
                "--allowedTools",
                "mcp__crm__*",
                "--no-session-persistence",
                "--append-system-prompt",
                INSTRUCTIONS,
                "--",
                prompt,
            ]
        else:
            home = self.cwd / "codex"
            home.mkdir()
            (home / "auth.json").symlink_to(
                Path(os.getenv("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
            )
            env["CODEX_HOME"] = str(home)
            (home / "config.toml").write_text(
                f'[projects.{json.dumps(str(self.cwd.resolve()))}]\ntrust_level = "trusted"\n'
            )
            subprocess.run(["git", "init", "-q"], cwd=self.cwd, check=True)
            reply = self.cwd / "reply.txt"
            args = [
                "codex",
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "-s",
                "read-only",
                "-c",
                'approval_policy="never"',
                "-c",
                "features.shell_tool=false",
                "-c",
                "developer_instructions=" + json.dumps(INSTRUCTIONS),
                "-c",
                'mcp_servers.crm.tools.get_record.approval_mode="approve"',
                "-c",
                'mcp_servers.crm.tools.search_deals.approval_mode="approve"',
                "-c",
                'mcp_servers.crm.tools.write_deal.approval_mode="approve"',
                "-o",
                str(reply),
                prompt,
            ]
        result = await asyncio.to_thread(
            subprocess.run,
            args,
            cwd=self.cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError(result.stderr[-1200:] or result.stdout[-1200:])
        return result.stdout.strip() if self.name == "claude" else reply.read_text()


@asynccontextmanager
async def crm_server(folder, variant, workspace):
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
                    "facilitator.shared_mcp.server",
                    str(folder),
                    variant,
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


class RecordedClient(scenario.AgentAdapter):
    """Expose actual server calls from this turn to Scenario and its judge."""

    def __init__(self, adapter, folder):
        self.adapter = adapter
        self.name = adapter.name
        self.evidence_dir = folder
        self.offset = 0

    async def call(self, input):
        reply = await self.adapter.call(input)
        path = self.evidence_dir / "calls.jsonl"
        messages = []
        if path.exists():
            with path.open() as log:
                log.seek(self.offset)
                for line in log:
                    call = json.loads(line)
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
        return [*messages, {"role": "assistant", "content": reply}]

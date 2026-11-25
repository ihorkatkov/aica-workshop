"""Get a structured decision from the participant's ChatGPT-authenticated Codex CLI."""
import json
import os
from pathlib import Path
import subprocess
import tempfile


def decision(messages, schema):
    with tempfile.TemporaryDirectory(prefix="aica-model-") as directory:
        root = Path(directory)
        (root / "schema.json").write_text(json.dumps(schema))
        command = [
            "codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
            "--sandbox", "read-only", "--disable", "shell_tool", "--disable", "multi_agent",
            "--disable", "hooks", "-c", 'web_search="disabled"',
            "-c", 'forced_login_method="chatgpt"', "--output-schema", "schema.json",
            "--output-last-message", "decision.json", "-",
        ]
        env = {k: v for k, v in os.environ.items() if k in (
            "HOME", "PATH", "CODEX_HOME", "USER", "TMPDIR", "LANG", "SSL_CERT_FILE",
            "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")}
        try:
            subprocess.run(command, cwd=root, env=env, check=True, timeout=120,
                           input="Return the requested JSON decision for this synthetic workshop "
                                 "conversation.\n" + json.dumps(messages),
                           text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise RuntimeError("Install the Codex CLI on the host and run codex login.") from None
        except subprocess.TimeoutExpired:
            raise RuntimeError("ChatGPT decision timed out. Retry or use replay.") from None
        except subprocess.CalledProcessError:
            raise RuntimeError("Codex failed. Check codex login status, CLI version and plan usage.") from None
        return json.loads((root / "decision.json").read_text())

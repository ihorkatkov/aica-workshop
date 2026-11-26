#!/bin/sh
# Native clients use the participant's host sign-in. ADK can always use Compose.
set -eu
if [ "${PYTHON:-.venv/bin/python}" != .venv/bin/python ]; then
  exec "$PYTHON" -m pytest "$@"
fi

host_reason='host scenario runner needs Python 3.12 or uv'
if command -v uv >/dev/null || command -v python3.12 >/dev/null || [ -x .venv/bin/python ]; then
  if sh workshop/scenario-env.sh; then
    exec .venv/bin/python -m pytest "$@"
  else
    host_reason="host scenario environment setup exited $? (see installer output above)"
  fi
fi
for client in claude codex; do
  if command -v "$client" >/dev/null; then
    reason=$host_reason
  else
    reason="executable '$client' not found on host PATH"
  fi
  case "$client" in
    claude) export WORKSHOP_SKIP_CLAUDE="$reason";;
    codex) export WORKSHOP_SKIP_CODEX="$reason";;
  esac
done
exec docker compose run --rm -T -e WORKSHOP_SKIP_CLAUDE -e WORKSHOP_SKIP_CODEX --entrypoint python lab -m pytest "$@"

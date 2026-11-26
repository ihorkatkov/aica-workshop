#!/bin/sh
# Try actual Docker port publications so an intervening bind is handled too.
set -eu
umask 077
mkdir -p .lab
first=8500
last=8519
saved=$(sed -n 's/^AICA_WEB_PORT=//p' .env 2>/dev/null || :)
case "$saved" in 850[0-9]|851[0-9]) ;; *) saved= ;; esac
save_port() {
  if [ "$saved" != "$port" ]; then
    tmp=$(mktemp .env.XXXXXX)
    source=.env
    [ -f "$source" ] || source=.env.example
    sed '/^AICA_WEB_PORT=/d' "$source" > "$tmp"
    printf '\nAICA_WEB_PORT=%s\n' "$port" >> "$tmp"
    mv "$tmp" .env
  fi
}
host=${1:-docker}
if [ "$host" = docker ]; then
  docker compose up -d --wait crm
fi
ports=$( { echo "$saved"; seq "$first" "$last"; } | awk 'NF && !seen[$0]++')
for port in $ports; do
  if [ "$host" = host ]; then
    if "${PYTHON:-.venv/bin/python}" -c 'import socket, sys
with socket.socket() as s:
    s.bind(("127.0.0.1", int(sys.argv[1])))' "$port" 2>.lab/web-start.log; then
      save_port
      printf 'ADK Web: http://localhost:%s\n' "$port"
      exec .venv/bin/adk web --host 127.0.0.1 --port "$port" --reload_agents agents
    fi
  elif AICA_WEB_PORT=$port docker compose up -d --wait --no-deps web >.lab/web-start.log 2>&1; then
    save_port
    printf 'ADK Web: http://localhost:%s\n' "$port"
    exit 0
  fi
  if ! grep -Eiq 'address already in use|port is already allocated|only one usage of each socket address' .lab/web-start.log; then
    cat .lab/web-start.log >&2
    exit 1
  fi
  printf 'ADK Web port %s is busy. Trying another port…\n' "$port" >&2
done
printf 'ADK Web could not start. Free one localhost port in %s–%s and rerun your make command.\n' "$first" "$last" >&2
exit 1

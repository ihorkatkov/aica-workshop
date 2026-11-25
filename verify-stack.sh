#!/bin/sh
# Checks the real stack; set LIVE_MODEL=1 to also make paid live model calls.
set -eu
cd "$(dirname "$0")"
docker compose ps app workers
run() { docker compose run --rm -T lab "$@"; }
canary="$(run smoke-trace --require-langwatch)"
printf '%s\n' "$canary"
trace_id="$(printf '%s\n' "$canary" | sed -nE 's/.*"trace_id": "([0-9a-f]{32})".*/\1/p')"
[ -n "$trace_id" ]
run verify-trace "$trace_id"
if [ "${LIVE_MODEL:-0}" = 1 ]; then
  run smoke-model
  run --state .lab/rehearsal.sqlite3 --solution safe --mode live
fi
printf '%s\n' 'Open LangWatch at http://localhost:5560 → Traces; inspect the fresh get_deal span.'

#!/bin/sh
# Called from the workshop root once the stack is healthy.
set -eu
email=participant@example.test
password=Aica-Workshop-2026!
url=${WORKSHOP_URL:-http://localhost:5560}

db() { docker compose exec -T postgres psql -XqAt -v ON_ERROR_STOP=1 -U prisma -d mydb "$@"; }
echo "Preparing the participant account and project…"
exists=$(db -c "select count(*) from mydb.\"User\" where email = '$email'")
docker compose exec -T app node --input-type=module - "$url" "$email" "$password" "$exists" < workshop/account.mjs
key=$(db -v email="$email" < workshop/seed.sql)
[ -n "$key" ]
tmp=$(mktemp .env.XXXXXX)
trap 'rm -f "$tmp"' EXIT
awk -v key="$key" '/^LANGWATCH_API_KEY=/{if (!seen++) print "LANGWATCH_API_KEY=" key; next}
  {print} END {if (!seen) print "LANGWATCH_API_KEY=" key}' .env > "$tmp"
mv "$tmp" .env
echo 'Sending the first trace and checking it in LangWatch…'
for attempt in 1 2 3 4; do
  if ./verify-stack.sh >> .lab/setup.log 2>&1; then break; fi
  if [ "$attempt" = 4 ]; then tail -25 .lab/setup.log >&2; exit 1; fi
  echo 'Trace storage is still starting. Retrying…'
  sleep 5
done
printf '\nLangWatch ready!\n\n  Dashboard  %s/aica-lab/traces\n  Email       %s\n  Password    %s\n' "$url" "$email" "$password"

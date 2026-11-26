#!/bin/sh
set -eu
cd "$(dirname "$0")"
docker compose version >/dev/null
umask 077
if [ ! -f .langwatch.env ]; then
  {
    printf 'NEXTAUTH_SECRET=%s\n' "$(openssl rand -hex 32)"
    printf 'AUTH_SECRET=%s\n' "$(openssl rand -hex 32)"
    printf 'CREDENTIALS_SECRET=%s\n' "$(openssl rand -hex 32)"
    printf 'API_TOKEN_JWT_SECRET=%s\n' "$(openssl rand -hex 32)"
  } > .langwatch.env
fi
[ -f .env ] || cp .env.example .env
# Bind-mounted state must remain writable by the participant on Linux too.
for name in LOCAL_UID LOCAL_GID; do
  case "$name" in LOCAL_UID) value=$(id -u);; LOCAL_GID) value=$(id -g);; esac
  if ! grep -q "^$name=" .env; then printf '\n%s=%s\n' "$name" "$value" >> .env; fi
done
mkdir -p .lab
log=.lab/setup.log
: > "$log"
step() {
  printf '%s\n' "$1"
  shift
  if ! "$@" >> "$log" 2>&1; then
    tail -25 "$log" >&2
    echo "Setup stopped. Full log: $log" >&2
    exit 1
  fi
}

wait_for_login() {
  for attempt in $(seq 1 120); do
    if curl -fsS --max-time 3 -o /dev/null "${WORKSHOP_URL:-http://localhost:5560}/api/health" &&
       docker compose exec -T postgres psql -XqAt -U prisma -d mydb \
         -c 'SELECT 1 FROM mydb."Grant", mydb."User" LIMIT 0' >/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo 'LangWatch sign-in did not start. Inspect docker compose logs app workers.'
  return 1
}

case "${1:-up}" in
  pull)
    step 'Downloading LangWatch images…' docker compose --profile lab pull --ignore-buildable
    step 'Building the ADK lab…' docker compose build lab crm web
    ;;
  up)
    sh workshop/setup-key.sh
    step 'Preparing the ADK lab…' docker compose build lab crm web
    step 'Starting LangWatch…' docker compose up -d app workers
    step 'Waiting for sign-in to be ready…' wait_for_login
    sh workshop/setup-account.sh
    step "Starting CRM and ADK Web…" docker compose up -d --wait crm web
    step "Checking the real model, CRM tools and trace…" docker compose run --rm -T lab preflight
    printf "ADK Web: http://localhost:8000\nCRM approval desk: http://localhost:8001\nRun make preflight to verify the real model.\n"
    ;;
  *) echo 'Usage: ./setup.sh [pull|up]' >&2; exit 2 ;;
esac

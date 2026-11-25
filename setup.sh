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
    step 'Building the ADK lab…' docker compose build lab
    ;;
  up)
    step 'Preparing the ADK lab…' docker compose build lab
    step 'Starting LangWatch…' docker compose up -d app workers
    step 'Waiting for sign-in to be ready…' wait_for_login
    sh workshop/setup-account.sh
    ;;
  *) echo 'Usage: ./setup.sh [pull|up]' >&2; exit 2 ;;
esac

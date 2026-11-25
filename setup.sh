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
case "${1:-up}" in
  pull) docker compose --profile lab pull ;;
  up) docker compose up -d app workers ;;
  *) printf '%s\n' 'Usage: ./setup.sh [pull|up]' >&2; exit 2 ;;
esac
if [ "${1:-up}" = up ]; then
  printf '%s\n' 'Waiting for the local LangWatch UI…'
  for n in $(seq 1 90); do
    if curl -fsS --max-time 3 -o /dev/null http://localhost:5560/; then
      printf '%s\n' 'Open http://localhost:5560 and follow README → Local LangWatch.'
      exit 0
    fi
    sleep 2
  done
  printf '%s\n' 'LangWatch did not become reachable. Try: docker compose logs --tail=100 app workers' >&2
  exit 1
fi

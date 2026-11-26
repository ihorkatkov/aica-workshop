#!/bin/sh
# Only the facilitator's proxy uses the workshop key prompt.
set -eu
umask 077
proxy=$(sed -n 's/^OPENAI_BASE_URL=//p' .env.example)
# Use the same dotenv parsing as Compose, independent of personal shell credentials.
setting() (
  unset OPENAI_API_KEY OPENAI_BASE_URL
  docker compose config --environment | sed -n "s/^$1=//p"
)
[ "$(setting OPENAI_BASE_URL)" = "$proxy" ] || exit 0
key=$(setting OPENAI_API_KEY)

check_key() {
  printf 'Authorization: Bearer %s\n' "$key" |
    curl -sS --max-time 20 -H @- -o /dev/null -w '%{http_code}' "$proxy/models"
}
accepted() {
  case "$(check_key)" in
    200) return 0 ;;
    401|403) echo 'The model proxy rejected that key.' >&2; return 1 ;;
    *) echo 'Cannot verify the workshop key. Check the model proxy connection and rerun make setup.' >&2; exit 1 ;;
  esac
}
if [ -n "$key" ] && accepted; then exit 0; fi

read_key() (
  if [ -t 0 ]; then
    mode=$(stty -g)
    trap 'stty "$mode"' EXIT
    trap 'exit 1' HUP INT TERM
    stty -echo
  fi
  printf 'Workshop API key (from your facilitator): ' >&2
  IFS= read -r input || exit 1
  printf '\n' >&2
  printf '%s' "$input"
)
while :; do
  key=$(read_key) || { echo 'A workshop API key is required. Run make setup and enter it at the prompt.' >&2; exit 1; }
  # Bearer tokens use this alphabet; these characters are safe in a dotenv value.
  case "$key" in
    ''|*[!a-zA-Z0-9._~+/=-]*) echo 'Enter a nonempty workshop API key.' >&2 ;;
    *) if accepted; then break; fi ;;
  esac
  [ -t 0 ] || exit 1
done

tmp=$(mktemp .env.XXXXXX)
trap 'rm -f "$tmp"' EXIT
sed '/^[[:space:]]*\(export[[:space:]][[:space:]]*\)\{0,1\}OPENAI_API_KEY[[:space:]]*=/d' .env > "$tmp"
printf '\nOPENAI_API_KEY=%s\n' "$key" >> "$tmp"
mv "$tmp" .env

#!/usr/bin/env sh
# One-command FR24 sandbox smoke: brings up the isolated sandbox compose
# stack, runs the live sandbox test suite against it, and tears it down.
#
# Prerequisites:
#   - .env.sandbox exists (copy .env.sandbox.example) with the sandbox key
#     from https://fr24api.flightradar24.com/key-management filled in
#   - docker compose >= 2.24 (for the !override tag)
#
# KEEP=1 leaves the stack up on http://127.0.0.1:8081 for manual dashboard
# inspection; teardown then is:
#   docker compose -p flight-geofence-sandbox down -v
set -eu

cd "$(dirname "$0")/.."

PROJECT=flight-geofence-sandbox
ENV_FILE=.env.sandbox

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[ -f "$ENV_FILE" ] || fail "$ENV_FILE missing -- copy .env.sandbox.example and fill in the sandbox key"

# Read single-line KEY=VALUE assignments without sourcing the file
# (it may eventually hold values a shell should not interpret).
# One pair of surrounding quotes is stripped -- keys pasted from the portal
# docs often carry them, and FR24 rejects a quoted key with 401.
env_value() {
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

SANDBOX_KEY=$(env_value FLIGHTRADAR24_API_KEY)
[ -n "$SANDBOX_KEY" ] || fail "FLIGHTRADAR24_API_KEY empty in $ENV_FILE"
ADMIN_PASSWORD=$(env_value ADMIN_PASSWORD)
[ -n "$ADMIN_PASSWORD" ] || fail "ADMIN_PASSWORD empty in $ENV_FILE"
APP_SECRET_KEY=$(env_value APP_SECRET_KEY)
[ -n "$APP_SECRET_KEY" ] || fail "APP_SECRET_KEY empty in $ENV_FILE"
# Startup validation refuses placeholder secrets -- catch it here with a
# clear message instead of an unhealthy container.
case "$ADMIN_PASSWORD$APP_SECRET_KEY" in
  replace-with*)
    fail "$ENV_FILE still carries example placeholders -- set real throwaway values for ADMIN_PASSWORD and APP_SECRET_KEY"
    ;;
esac
[ "${#ADMIN_PASSWORD}" -ge 12 ] || fail "ADMIN_PASSWORD must be at least 12 characters"
[ "${#APP_SECRET_KEY}" -ge 32 ] || fail "APP_SECRET_KEY must be at least 32 characters (openssl rand -hex 32)"

cleanup() {
  if [ "${KEEP:-0}" = "1" ]; then
    echo "KEEP=1 -- stack left up: http://127.0.0.1:8081"
    echo "teardown: docker compose -p $PROJECT down -v"
  else
    docker compose -p "$PROJECT" down -v >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "==> building + starting sandbox stack"
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml -p "$PROJECT" up -d --build --wait

echo "==> waiting for /readyz"
i=0
while [ "$i" -lt 30 ]; do
  if docker compose -p "$PROJECT" exec -T flight-monitor \
      python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=4)" 2>/dev/null; then
    break
  fi
  i=$((i + 1))
  sleep 2
done
[ "$i" -lt 30 ] || fail "sandbox stack never became ready"

echo "==> running live sandbox tests (contract + system + scenarios)"
# The test suite requires Python >= 3.12 (datetime.UTC et al.) -- prefer the
# project venv when present; bare `python` may resolve to an older pyenv shim.
if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
else
  PY=python3
fi
"$PY" --version | grep -q '3\.1[2-9]' || fail "need Python >= 3.12 (found $("$PY" --version 2>&1)); create .venv or set PYTHON="
# conftest.py uses os.environ.setdefault for DATABASE_PATH/DOWNLOAD_DIR and the
# autouse fixture DELETEs every table -- an exported DATABASE_PATH inherited from
# a hub/docker shell would wipe that database. Scrub both, plus the production
# FR24 key (the sandbox key is injected explicitly as FR24_SANDBOX_API_KEY).
env -u DATABASE_PATH -u DOWNLOAD_DIR -u FLIGHTRADAR24_API_KEY \
  FR24_SANDBOX_API_KEY="$SANDBOX_KEY" \
  FR24_SANDBOX_BASE_URL="http://127.0.0.1:8081" \
  FR24_SANDBOX_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  "$PY" -m pytest -m fr24_sandbox -v

echo "==> hygiene: sandbox key must never appear in container logs"
# -q: never echo the matching line -- printing it would leak the key here.
if docker compose -p "$PROJECT" logs flight-monitor 2>/dev/null | grep -qF "$SANDBOX_KEY"; then
  fail "sandbox key found in container logs"
fi
echo "OK"

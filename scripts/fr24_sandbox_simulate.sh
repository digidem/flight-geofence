#!/usr/bin/env sh
# Drive the live sandbox stack through every event lifecycle the production
# pipeline can produce (tests/test_fr24_sandbox_scenarios.py), then capture UI
# screenshots of the end state, then restore settings.
#
# Prerequisites: the sandbox stack is up and smoke-green --
#   scripts/fr24_sandbox_smoke.sh        (or KEEP=1 scripts/fr24_sandbox_smoke.sh)
# For full determinism set FR24_POLL_INTERVAL_SECONDS=86400 in .env.sandbox and
# re-create the stack before simulating (background 300s loop otherwise may
# interleave -- harmless, cycles collide on a lock and are retried).
#
# Artifacts land in sandbox-artifacts/ (gitignored):
#   settings-backup.json   pre-run settings snapshot (S0)
#   0N-*.png               UI screenshots of every tab + event details
set -eu

cd "$(dirname "$0")/.."

ENV_FILE=.env.sandbox
BASE_URL="${FR24_SANDBOX_BASE_URL:-http://127.0.0.1:8081}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

env_value() {
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

[ -f "$ENV_FILE" ] || fail "$ENV_FILE missing -- copy .env.sandbox.example"
ADMIN_PASSWORD=$(env_value ADMIN_PASSWORD)
[ -n "$ADMIN_PASSWORD" ] || fail "ADMIN_PASSWORD empty in $ENV_FILE"

if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
else
  PY=python3
fi
"$PY" --version | grep -q '3\.1[2-9]' || fail "need Python >= 3.12 (found $("$PY" --version 2>&1)); create .venv or set PYTHON="

mkdir -p sandbox-artifacts

echo "==> preflight: stack up at $BASE_URL ?"
if ! curl -sf "$BASE_URL/readyz" >/dev/null 2>&1; then
  fail "stack not ready at $BASE_URL -- run scripts/fr24_sandbox_smoke.sh first (or KEEP=1 to leave it up)"
fi

echo "==> running sandbox scenarios (S0 discovery .. S6 budget restore)"
# SKIP_RESTORE=1: S6 leaves budget=exhausted + pause_fr24 in place so the
# screenshots show the end state; the restore step below brings settings back.
# Scrub DATABASE_PATH/DOWNLOAD_DIR: conftest.py's autouse fixture DELETEs every
# table in whatever database those point at (see scripts/fr24_sandbox_smoke.sh).
set +e
env -u DATABASE_PATH -u DOWNLOAD_DIR -u FLIGHTRADAR24_API_KEY \
  FR24_SANDBOX_BASE_URL="$BASE_URL" \
  FR24_SANDBOX_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  FR24_SANDBOX_SKIP_RESTORE=1 \
  "$PY" -m pytest tests/test_fr24_sandbox_scenarios.py -v
PYTEST_RC=$?
set -e
if [ "$PYTEST_RC" -ne 0 ]; then
  echo "==> pytest failed (rc=$PYTEST_RC) -- restoring settings, skipping screenshots"
  FR24_SANDBOX_BASE_URL="$BASE_URL" \
  FR24_SANDBOX_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    "$PY" scripts/fr24_sandbox_restore.py || true
  exit "$PYTEST_RC"
fi

echo "==> capturing UI screenshots (end state still standing)"
# Best-effort: a missing browser-harness or a headless-Chrome hiccup must never
# abort the run before the restore step below, which is what returns the stack
# from the deliberately exhausted S6 end state.
if ! FR24_SANDBOX_BASE_URL="$BASE_URL" sh scripts/fr24_sandbox_screenshots.sh; then
  echo "WARN: screenshots failed -- continuing to restore" >&2
fi

echo "==> restoring pre-run settings"
# --ensure-polling: repeated simulate runs accumulate real sandbox credits
# within one billing cycle; if the restored budget lands below that, park it
# higher so the leftover stack keeps polling for the UI tour.
FR24_SANDBOX_BASE_URL="$BASE_URL" \
FR24_SANDBOX_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  "$PY" scripts/fr24_sandbox_restore.py --ensure-polling

cat <<EOF

==> UI tour (stack stays up: $BASE_URL)
  1. Log in with ADMIN_PASSWORD from $ENV_FILE.
  2. Dashboard: system status, FR24 budget gauge, poll history.
  3. Areas: sandbox-sim-target/control polygons (target selected, control
     deselected by S4) alongside dataset areas.
  4. Events: one DISAPPEARED (real pipeline) + one PROBABLE_STOP labeled
     "SANDBOX SIMULATION" (synthetic -- live fixture flies above the stop gate).
  5. Event detail: click an event row hash-link, see track points + review
     actions + FR24 track fetch panel (blocked while budget exhausted).
  6. Settings: operating phase, disappearance thresholds used by scenarios.
  7. FR24 tab: request log (light/summary-full/flight-tracks), poll runs
     including the skipped "budget exhausted" row, cluster telemetry.

Screenshots: sandbox-artifacts/*.png
EOF

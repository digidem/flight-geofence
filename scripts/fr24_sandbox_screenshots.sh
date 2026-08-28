#!/usr/bin/env sh
# Capture full-page UI screenshots of the sandbox stack at http://127.0.0.1:8081
# after scripts/fr24_sandbox_simulate.sh scenarios ran (both event types
# present, budget end-state still standing when called with
# FR24_SANDBOX_SKIP_RESTORE=1).
#
# Writes sandbox-artifacts/0N-*.png. Best-effort: failures print a warning and
# the script still exits 0 unless EVERYTHING failed, so a headless-Chrome hiccup
# never fails an otherwise-green simulate run.
#
# Browser: self-launched headless Chrome on port 9333 with a throwaway profile
# (the default local daemon cannot attach when the desktop browser has no
# remote-debugging toggle). All steps run in ONE browser-harness invocation --
# CDP targets go stale across invocations.
set -eu

cd "$(dirname "$0")/.."

BASE_URL="${FR24_SANDBOX_BASE_URL:-http://127.0.0.1:8081}"
ENV_FILE=.env.sandbox
OUT_DIR=sandbox-artifacts
CDP_PORT=9333

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

env_value() {
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

[ -f "$ENV_FILE" ] || fail "$ENV_FILE missing"
ADMIN_PASSWORD=$(env_value ADMIN_PASSWORD)
[ -n "$ADMIN_PASSWORD" ] || fail "ADMIN_PASSWORD empty in $ENV_FILE"
command -v browser-harness >/dev/null 2>&1 || fail "browser-harness not on PATH"

CHROME_BIN=""
for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
  if command -v "$candidate" >/dev/null 2>&1; then
    CHROME_BIN="$candidate"
    break
  fi
done
[ -n "$CHROME_BIN" ] || fail "no chrome/chromium binary found for headless screenshots"

mkdir -p "$OUT_DIR"
PROFILE_DIR=$(mktemp -d)
CHROME_PID=""

cleanup() {
  if [ -n "$CHROME_PID" ]; then
    kill "$CHROME_PID" 2>/dev/null || true
  fi
  if [ -n "${PROFILE_DIR:-}" ]; then
    rm -rf "$PROFILE_DIR"
  fi
}
trap cleanup EXIT INT TERM

echo "==> launching headless chrome (profile $PROFILE_DIR)"
"$CHROME_BIN" --headless=new --remote-debugging-port=$CDP_PORT \
  --user-data-dir="$PROFILE_DIR" --no-first-run --disable-gpu \
  --window-size=1440,2400 about:blank >/dev/null 2>&1 &
CHROME_PID=$!

i=0
while [ "$i" -lt 30 ]; do
  if curl -sf "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 1
done
[ "$i" -lt 30 ] || fail "headless chrome never came up on port $CDP_PORT"

BASE_URL="$BASE_URL" ADMIN_PASSWORD="$ADMIN_PASSWORD" OUT_DIR="$OUT_DIR" \
BU_CDP_URL="http://127.0.0.1:$CDP_PORT" \
browser-harness <<'PY'
import base64
import json
import os
import time

BASE = os.environ["BASE_URL"].rstrip("/")
PASSWORD = os.environ["ADMIN_PASSWORD"]
OUT = os.environ["OUT_DIR"]

results = []


def shot(name):
    data = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=True)["data"]
    path = f"{OUT}/{name}.png"
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(data))
    results.append(name)
    print(f"captured {path}")


def js_ok(expr):
    return js(f"Boolean({expr})") in (True, "true")


def wait_until(expr, timeout=20, what=""):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if js_ok(expr):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    print(f"WARN: timed out waiting for {what or expr}")
    return False


def tab(view, name, settle=2.0):
    if not wait_until(f"document.querySelector('.tab[data-view=\"{view}\"]')", what=f"{view} tab"):
        return
    js(f"document.querySelector('.tab[data-view=\"{view}\"]').click()")
    time.sleep(settle)
    shot(name)


# 1. Load + login through the real form (the SPA's own submit handler).
new_tab(BASE)
wait_for_load()
wait_until("document.getElementById('login-password')", what="login form")
js(f"document.getElementById('login-password').value = {json.dumps(PASSWORD)};")
js("document.getElementById('login-form').requestSubmit();")
wait_until("document.querySelector('#login-screen') && document.querySelector('#login-screen').hidden", what="login")

# 2. Dashboard.
time.sleep(3)
shot("01-dashboard")

# 3. Remaining tabs.
tab("areas", "02-areas")
tab("events", "03-events")
tab("settings", "04-settings")
tab("fr24", "05-fr24")

# 4. Event detail views -- the events themselves are discovered from the API
# through the already-authenticated browser session, so this script works no
# matter which hexes the rotated sandbox fixture produced.
try:
    payload = js(
        "fetch('/api/events?limit=500').then(r => r.json()).then(d => "
        "JSON.stringify((d.events||[]).map(e => [e.id, e.event_type])))"
    )
    events = json.loads(payload) if isinstance(payload, str) else payload
    picks = {}
    for event_id, event_type in events or []:
        picks.setdefault(event_type, event_id)
    for index, (event_type, event_id) in enumerate(sorted(picks.items()), start=6):
        goto_url(f"{BASE}/#/events/{event_id}")
        wait_for_load()
        time.sleep(2)
        shot(f"{index:02d}-event-detail-{event_type.lower()}")
except Exception as exc:
    print(f"WARN: event-detail screenshots skipped: {exc}")

print(f"captured {len(results)} screenshots: {', '.join(results)}")
PY

echo "==> screenshots done ($OUT_DIR/)"

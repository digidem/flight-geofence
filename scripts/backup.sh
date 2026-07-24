#!/usr/bin/env sh
set -eu

DESTINATION="${1:-flight-geofence-backup-$(date -u +%Y%m%dT%H%M%SZ).db}"
TEMP_FILE="/data/runtime/.backup-$$.db"

cleanup() {
  docker compose exec -T flight-monitor rm -f "$TEMP_FILE" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker compose exec -T flight-monitor python - "$TEMP_FILE" <<'PY'
import sqlite3
import sys
from app.config import env_settings

source = sqlite3.connect(env_settings().database_path)
target = sqlite3.connect(sys.argv[1])
try:
    source.backup(target)
finally:
    target.close()
    source.close()
PY

docker compose exec -T flight-monitor python - "$TEMP_FILE" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
finally:
    conn.close()
if result != "ok":
    raise SystemExit(f"backup integrity check failed: {result}")
print("backup integrity check: ok")
PY

docker compose cp "flight-monitor:$TEMP_FILE" "$DESTINATION"
printf 'Backup written to %s\n' "$DESTINATION"

#!/usr/bin/env bash
#
# rss_watch.sh — RSS observation sampler for issue #4 (memory-growth watch).
#
# Samples prod container memory without disturbing the running deployment:
# read-only `docker stats --no-stream` + `docker inspect`, plus one read-only
# SQLite query (mode=ro) for the last successful boundary-sync time. No
# restarts, no writes, no secrets echoed.
#
# Usage:
#   ./scripts/rss_watch.sh [--once] [--csv PATH]
#     --once       take a single sample (this is the default; flag kept for
#                  explicitness when scripting)
#     --csv PATH   append to PATH instead of $FLIGHT_GEOFENCE_RSS_LOG
#                  (default ./rss-samples.csv, gitignored). A header row is
#                  written when the file does not exist yet.
#     -h, --help   show this comment block
#
# Cadence: take one sample every ~6 hours for 48-72 hours (cron/systemd
# timer or manual runs), then read the resulting CSV:
#   - Flat usage, or a sawtooth (climb -> boundary sync -> drop back),
#     means no leak -> close issue #4.
#   - A monotonic climb, excluding spikes right after a boundary sync,
#     indicates a leak -> keep issue #4 open with the CSV attached.
# `days_since_last_boundary_sync` separates sync-driven spikes from real
# growth. "NA" means no successful boundary sync has been recorded yet.
#
# Requires: bash, ssh, GNU date, awk; on the prod host only docker and the
# container's bundled python stdlib. Columns:
#   timestamp_utc, mem_used_mib, mem_limit_mib, mem_pct,
#   container_uptime_hours, restarts, image_tag, days_since_last_boundary_sync

set -euo pipefail

PROD_SSH_HOST="${PROD_SSH_HOST:-files.earthdefenderstoolkit.com}"
CONTAINER="${RSS_WATCH_CONTAINER:-edt-cloud-flight-geofence-1}"
CSV_FILE="${FLIGHT_GEOFENCE_RSS_LOG:-./rss-samples.csv}"

usage() { awk 'NR == 1 {next} /^#/{sub(/^# ?/, ""); print; next} {exit}' "$0"; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --once) ;; # single sample is the default; flag accepted for explicitness
    --csv)
      [ "$#" -ge 2 ] || { echo "rss_watch: --csv needs a path" >&2; exit 2; }
      CSV_FILE="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "rss_watch: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# "113.2MiB" / "1.5GiB" / "850MiB" -> value in MiB.
to_mib() {
  local v="${1%???}" u="${1: -3}"
  case "$u" in
    MiB) printf '%s' "$v" ;;
    GiB) awk -v x="$v" 'BEGIN{printf "%.1f", x * 1024}' ;;
    KiB) awk -v x="$v" 'BEGIN{printf "%.1f", x / 1024}' ;;
    *) echo "rss_watch: unexpected memory unit in '$1'" >&2; return 1 ;;
  esac
}

sample() {
  local ts stats inspect used_raw limit_raw pct used_mib limit_mib
  local image started restarts start_epoch uptime_h days

  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # docker stats --format expands \t but docker inspect --format does not,
  # so the inspect fields use a literal pipe separator instead.
  # shellcheck disable=SC2029  # host/container names are client-side config
  stats="$(ssh "$PROD_SSH_HOST" \
    "docker stats --no-stream --format '{{.MemUsage}}\t{{.MemPerc}}' $CONTAINER")"
  # shellcheck disable=SC2029
  inspect="$(ssh "$PROD_SSH_HOST" \
    "docker inspect --format '{{.Config.Image}}|{{.State.StartedAt}}|{{.RestartCount}}' $CONTAINER")"
  used_raw="$(printf '%s\n' "$stats" | awk -F'\t' '{print $1}' | awk '{print $1}')"
  limit_raw="$(printf '%s\n' "$stats" | awk -F'\t' '{print $1}' | awk '{print $3}')"
  pct="$(printf '%s\n' "$stats" | awk -F'\t' '{print $2}' | tr -d '%')"
  image="$(printf '%s\n' "$inspect" | awk -F'|' '{print $1}')"
  started="$(printf '%s\n' "$inspect" | awk -F'|' '{print $2}')"
  restarts="$(printf '%s\n' "$inspect" | awk -F'|' '{print $3}')"

  if [ -z "$image" ] || [ -z "$started" ] || [ -z "$restarts" ]; then
    echo "rss_watch: unexpected docker inspect output: $inspect" >&2
    return 1
  fi

  used_mib="$(to_mib "$used_raw")"
  limit_mib="$(to_mib "$limit_raw")"

  # StartedAt is like 2026-08-01T12:34:56.789012345Z; drop the fraction for
  # GNU date parsing.
  start_epoch="$(date -u -d "${started%%.*}Z" +%s)"
  uptime_h="$(awk -v s="$start_epoch" -v n="$(date -u +%s)" \
    'BEGIN{printf "%.2f", (n - s) / 3600}')"

  # Read-only DB peek: last successful boundary sync, in days ago.
  # shellcheck disable=SC2029
  days="$(ssh "$PROD_SSH_HOST" "docker exec -i $CONTAINER python -" <<'PY'
import datetime
import sqlite3

conn = sqlite3.connect("file:/data/runtime/flight_alerts.db?mode=ro", uri=True)
row = conn.execute(
    "SELECT max(completed_at) FROM dataset_syncs WHERE success = 1"
).fetchone()
conn.close()
if row and row[0]:
    t = datetime.datetime.fromisoformat(row[0])
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    age = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 86400
    print(f"{age:.3f}")
else:
    print("NA")
PY
)"

  if [ ! -s "$CSV_FILE" ]; then
    mkdir -p "$(dirname "$CSV_FILE")"
    printf 'timestamp_utc,mem_used_mib,mem_limit_mib,mem_pct,container_uptime_hours,restarts,image_tag,days_since_last_boundary_sync\n' \
      >> "$CSV_FILE"
  fi
  printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$ts" "$used_mib" "$limit_mib" "$pct" "$uptime_h" "$restarts" "$image" "$days" \
    >> "$CSV_FILE"

  echo "$ts mem=${used_mib}MiB/${limit_mib}MiB (${pct}%) uptime=${uptime_h}h restarts=${restarts} image=${image} last_sync_days_ago=${days}"
}

sample

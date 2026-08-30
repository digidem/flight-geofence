#!/usr/bin/env python3
"""One-time backfill: scrub leaked region coordinates from poll_runs.error_message.

Production rows written before the 0.6.x scrub fix can contain raw provider
URLs such as ``https://api.adsb.lol/v2/point/0.280901/-52.592973/200.0`` --
httpx quotes the failing URL in 429/5xx error text, and these providers put
the region centre and radius (i.e. protected-area geometry) in the URL path.
This script applies the same ``_scrub_log_message`` regex used by
``record_provider_call`` to existing ``poll_runs`` rows.

Operator-run once; nothing in the app schedules or invokes it. Safe to
re-run: scrubbed text contains no URLs, so a second pass finds nothing to
change (idempotent).

Usage:
    python scripts/scrub_poll_runs.py [--dry-run]          # from a checkout

Inside the container ``scripts/`` is not copied into the image (same reason
``backup.sh`` pipes its Python over stdin), so run it piped:

    docker compose exec -T flight-monitor python - --dry-run < scripts/scrub_poll_runs.py
    docker compose exec -T flight-monitor python - < scripts/scrub_poll_runs.py

The database is read from the DATABASE_PATH environment variable
(default: /data/runtime/flight_alerts.db).

Prefer taking a backup first (./scripts/backup.sh).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# Make the app package importable when run from a checkout. Under a stdin run
# (docker compose exec -T flight-monitor python - < this file) CPython sets
# __file__ to '<stdin>'; resolving it would insert a bogus sys.path entry, and
# the import works there because the container WORKDIR already contains app/
# (cwd is sys.path[0] for stdin runs). Keep the checkout insert local-only.
try:
    here = Path(__file__).resolve().parent.parent
except NameError:  # defensive: if a CPython build ever omits __file__ on stdin
    here = None
if here is not None:
    sys.path.insert(0, str(here))

from app.database import _scrub_log_message  # noqa: E402

DEFAULT_DB = "/data/runtime/flight_alerts.db"

# Rows whose stored text can plausibly embed a provider URL. The scrub regex
# only rewrites ``http(s)://...`` spans, so rows that match these filters but
# contain no URL are counted as unchanged and left byte-identical.
_CANDIDATE_WHERE = (
    "error_message IS NOT NULL AND ("
    "error_message LIKE '%http%'"
    " OR error_message LIKE '%/v2/point/%'"
    " OR error_message LIKE '%bounds=%'"
    ")"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scrub leaked region coordinates from poll_runs.error_message."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change and print sample rows; write nothing",
    )
    args = parser.parse_args(argv)

    db_path = os.environ.get("DATABASE_PATH", DEFAULT_DB)
    if not Path(db_path).exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT id, error_message FROM poll_runs WHERE {_CANDIDATE_WHERE}"
        ).fetchall()
    finally:
        conn.close()

    updates: list[tuple[str | None, str]] = []
    unchanged = 0
    for row in rows:
        original = row["error_message"]
        scrubbed = _scrub_log_message(original)
        if scrubbed == original:
            unchanged += 1
        else:
            updates.append((scrubbed, row["id"]))

    scanned = len(rows)
    scrubbed_count = len(updates)
    print(f"database: {db_path}")
    print(f"scanned: {scanned}")
    print(f"scrubbed: {scrubbed_count}")
    print(f"unchanged: {unchanged}")
    if unchanged:
        print(
            f"note: {unchanged} candidate row(s) matched the leak filters but "
            "contain no URL-shaped text; they were left untouched. Inspect "
            "them manually if the filter matched bare coordinate text."
        )

    if args.dry_run:
        for scrubbed, row_id in updates[:5]:
            original = next(r["error_message"] for r in rows if r["id"] == row_id)
            print(f"\nsample id={row_id}")
            print(f"  before: {original!r}")
            print(f"  after:  {scrubbed!r}")
        print("\ndry run: no changes written")
        return 0

    if updates:
        conn = sqlite3.connect(db_path, timeout=60)
        try:
            with conn:  # single transaction; all-or-nothing
                conn.executemany(
                    "UPDATE poll_runs SET error_message = ? WHERE id = ?",
                    updates,
                )
        finally:
            conn.close()
        print(f"committed {scrubbed_count} update(s) in one transaction")
    else:
        print("nothing to update")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

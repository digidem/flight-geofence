"""Restore sandbox settings captured by tests/test_fr24_sandbox_scenarios.py.

Reads sandbox-artifacts/settings-backup.json (written in S0) and POSTs the
values back, then verifies the FR24 budget state. Used by
scripts/fr24_sandbox_simulate.sh after screenshots, so the end state can be
photographed before settings return to normal.

Usage:
    FR24_SANDBOX_ADMIN_PASSWORD=<pw> python scripts/fr24_sandbox_restore.py \
        [--base-url http://127.0.0.1:8081] [--admin-password <pw>] \
        [--ensure-polling]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKUP = REPO_ROOT / "sandbox-artifacts" / "settings-backup.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("FR24_SANDBOX_BASE_URL", "http://127.0.0.1:8081"))
    parser.add_argument("--admin-password", default=os.environ.get("FR24_SANDBOX_ADMIN_PASSWORD", ""))
    parser.add_argument("--ensure-polling", action="store_true",
                        help="if the restored budget is below this cycle's cumulative "
                             "spend, park it higher so pause_fr24 does not skip every cycle")
    args = parser.parse_args()
    if not args.admin_password:
        print("admin password required (FR24_SANDBOX_ADMIN_PASSWORD or --admin-password)", file=sys.stderr)
        return 2
    if not BACKUP.exists():
        print(f"no settings backup at {BACKUP} -- run the scenarios first", file=sys.stderr)
        return 2

    backup = json.loads(BACKUP.read_text())
    # Accept both plain values and the full settings-API item dicts
    # ({value, source, locked, ...}) -- older backups wrote the latter.
    values = {
        key: (value.get("value") if isinstance(value, dict) else value)
        for key, value in backup.items()
    }
    values = {key: value for key, value in values.items() if value is not None}
    if not values:
        print("backup empty -- nothing to restore")
        return 0

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30) as client:
        login = client.post("/api/auth/login", json={"password": args.admin_password})
        login.raise_for_status()
        client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
        response = client.post("/api/settings", json={"values": values, "clear": []})
        response.raise_for_status()
        body = response.json()
        if body["errors"]:
            print(f"restore errored: {body['errors']}", file=sys.stderr)
            return 1
        print(f"restored: {sorted(body['updated'])}")
        status = client.get("/api/fr24/status").json()
        print(f"budget_state={status['budget_state']} used={status['credits_used_this_cycle']}/{status['operating_budget']}")
        if status["budget_state"] != "normal":
            # Cumulative spend this billing cycle can legitimately exceed the
            # restored budget (every simulate run spends real sandbox
            # credits). Settings ARE restored exactly; the state is
            # informational, not a restore failure.
            print("note: budget state non-normal -- cumulative spend this billing "
                  "cycle exceeds the restored budget; pause_fr24 will skip cycles "
                  "until the cycle rolls over or the budget is raised")
            if args.ensure_polling:
                parked = max(int(status["operating_budget"]),
                             int(status["credits_used_this_cycle"]) * 2 + 100)
                response = client.post("/api/settings", json={
                    "values": {"fr24_monthly_operating_budget": parked}, "clear": []})
                response.raise_for_status()
                status = client.get("/api/fr24/status").json()
                print(f"budget parked at {parked} so the stack keeps polling: "
                      f"budget_state={status['budget_state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

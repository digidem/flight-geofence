---
name: flight-geofence-ops
description: "Release, deploy and verify flight-geofence, and drive the FR24 sandbox stack. The env-scrub trap that wipes databases, the release file list, the production runbook, and the standing security exposure. Load before running tests, cutting a release, deploying, or touching the sandbox."
---

# Operating flight-geofence

## The env-scrub trap — read before running anything

`tests/conftest.py` uses `os.environ.setdefault` for `DATABASE_PATH`/`DOWNLOAD_DIR`,
and the autouse fixture **DELETEs every table**. An exported `DATABASE_PATH`
inherited from a hub or docker shell therefore wipes that database. Always:

```bash
env -u DATABASE_PATH -u DOWNLOAD_DIR -u FLIGHTRADAR24_API_KEY -u FR24_RETENTION_DAYS make check
```

The same scrub is baked into `scripts/fr24_sandbox_smoke.sh` and `simulate.sh`.
For ad-hoc scripts, pin local paths: `DATABASE_PATH=data/runtime/flight_alerts.db`.

Adding a table? Add it to `_CLEANUP_TABLES` in `tests/conftest.py` or rows leak
between tests and produce baffling count assertions.

## Checks

```bash
env -u DATABASE_PATH -u DOWNLOAD_DIR -u FLIGHTRADAR24_API_KEY -u FR24_RETENTION_DAYS make check
node --check app/static/app.js          # after any frontend change
uvx ruff check --output-format=concise app tests scripts | grep -c ':'
```

Ruff has a large pre-existing baseline (~48–49) and `E501` is ignored. Prove zero
net-new by comparing against a detached worktree — and **run the baseline in a
subshell**, or a bare `cd` leaks into the next command and you compare a tree with
itself:

```bash
git worktree add /tmp/base HEAD --detach
(cd /tmp/base && uvx ruff check --output-format=concise app tests scripts | grep -c ':')
uvx ruff check --output-format=concise app tests scripts | grep -c ':'
git worktree remove /tmp/base --force
```

## Release

1. Land the fix on `main` first; the release commit contains **only** version files.
2. `make bump-version` seds `app/main.py` — stash unrelated WIP touching it first.
3. `make bump-version VERSION=X.Y.Z`, then stage **only** the six version files:
   `Dockerfile`, `app/main.py`, `LINKS_REPORT.txt`, `README.md`,
   `docs/VALIDATION.md`, `docs/AUDIT.md`. Never `git add -A` — untracked WIP
   otherwise rides into the tag.
4. `git push`, then `gh workflow run release.yml --ref main -f version=vX.Y.Z`.
   The `v` prefix is regex-validated; a bare `X.Y.Z` fails.

Test-only or script-only commits after a bump need no re-release — they are not in
the image.

## Deploy to production

Host `ssh files.earthdefenderstoolkit.com`, compose
`/mnt/volume_nyc1_01/edt-cloud/docker-compose.yml` (image line ~112), container
`edt-cloud-flight-geofence-1`.

```bash
cp docker-compose.yml /tmp/docker-compose.yml.pre-vX.Y.Z   # always keep a rollback
sed -i "s|flight-geofence:vOLD|flight-geofence:vNEW|" docker-compose.yml
docker compose pull -q flight-geofence && docker compose up -d flight-geofence
```

Verify — **the in-container API is on 8080, not 8000**; there is no curl/wget in
the container, so use `docker exec … python -c` with `urllib`:

```
docker inspect edt-cloud-flight-geofence-1 --format "restarts={{.RestartCount}} health={{.State.Health.Status}}"
/readyz  ->  {"status":"ready","version":"X.Y.Z"}
```

For an authenticated check: POST `/api/auth/login` with
`{"password": os.environ["ADMIN_PASSWORD"]}` read **inside** the container, take
`csrf_token` plus the first `Set-Cookie`, send both. Never echo `ADMIN_PASSWORD`
or the FR24 key — pass them via env only.

## FR24 sandbox stack

Static, schema-identical responses, zero subscription credits. Setup: copy
`.env.sandbox.example` to `.env.sandbox`, paste the **sandbox** key (a separate
key), then `bash scripts/fr24_sandbox_smoke.sh` (`KEEP=1` leaves it up on
`127.0.0.1:8081`). `scripts/fr24_sandbox_simulate.sh` drives the full S0–S6
lifecycle plus screenshots.

The stack replaces — never merges — the production `env_file`, and uses its own
project name, volume and port. Two sandbox-only accommodations exist because the
fixtures carry 2024 timestamps: `POSITION_MAX_AGE_SECONDS=70000000` and
`STATE_RETENTION_DAYS=36500`. Never in production.

**Persistent-volume poison:** S6 deliberately ends with the budget exhausted and
only restores on a clean finish. An interrupted run leaves the stack unusable, and
S0 used to snapshot that poison as "the baseline" and restore it forever. Both
suites now self-heal by clearing the override and reading back the server default.
If a suite fails with `FR24 budget exhausted (policy=pause_fr24)`, that is leftover
state, not the code under test.

Leave the healthy container running between lanes; `make bump-version` touches
`Dockerfile` `APP_VERSION` and busts the uv layer cache, making the next
`compose up --build` cold (~12 min).

## Standing production security exposure (unresolved)

The dashboard is published on `0.0.0.0:8085` over **plain HTTP** and is reachable
from the internet. `ufw` does not cover Docker-published ports (Docker's iptables
rules bypass it), and Caddy does not front this service.
`validate_runtime_security` correctly computes the violation
(`bind_address=0.0.0.0`, `session_https_only=False`) but production sets
`ALLOW_INSECURE_DEFAULTS=true`, which suppresses the refusal the app would
otherwise raise. Admin password crosses the network in clear text.

Fix, in this order — reversing it stops the container booting:
1. publish on `127.0.0.1:8085:8080` and route through Caddy with TLS;
2. then set `SESSION_HTTPS_ONLY=true` and remove `ALLOW_INSECURE_DEFAULTS`.

Reported and awaiting the operator's decision — do not change production
networking without explicit approval; it takes the dashboard offline for current users.

Related: [[flight-geofence-mission]], [[flight-geofence-diagnostics]]

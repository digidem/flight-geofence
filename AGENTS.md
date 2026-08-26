# AGENTS.md

## Purpose

Maintain a private research PoC that compares aircraft positions with selected Brazilian Indigenous territories and conservation units. Preserve the core safety statement: events are unverified signals, never proof of landing, deliberate transponder shutdown, illegal mining, or wrongdoing.

`SPEC.md` is the behavioral source of truth. Update it when product behavior or alert semantics change.

## Commands

```bash
uv sync --extra dev  # include pytest for make check
make dev          # local dev server with uv (hot-reload on :8081)
make check
node --check app/static/app.js
cp .env.example .env && docker compose config --quiet
```

`make dev` overrides `DATABASE_PATH` and `DOWNLOAD_DIR` to local `./data/`
paths (the `.env` defaults assume Docker volume mounts at `/data`). `conftest.py` uses
`os.environ.setdefault(...)` for those paths, so an *exported* `DATABASE_PATH=/data/...`
inherited from a hub/docker shell silently breaks local runs — scrub it:
`env -u DATABASE_PATH -u DOWNLOAD_DIR -u FLIGHTRADAR24_API_KEY -u FR24_RETENTION_DAYS make check`
and pin `DATABASE_PATH=data/runtime/flight_alerts.db DOWNLOAD_DIR=data/downloads` when starting `make dev` from a hub.

Run a focused test with:

```bash
uv run python -m pytest tests/test_core.py -k '<test_name>'
```

For Docker or infrastructure changes, also run:

```bash
docker build --pull -t flight-geofence-alerts:local .
```

## Project conventions

- Use Python 3.12 and keep lines within the repository's 100-character target where practical.
- Keep HTTP/provider logic asynchronous and provider-specific parsing under `app/providers/`.
- Normalize every provider response to `AircraftObservation`; keep provider details out of detection logic.
- After any user-visible FR24 change (budget policy, manual Tracks flow, enrichment retries, legacy-provider warning, retention windows, CAS), sweep all four doc surfaces together in one commit: `README.md` + `docs/SPEC.md` + `.env.example` + `FLIGHTRADAR_API.md` (`TASK.md` stays historical and is intentionally not swept).
- Access SQLite through `app/database.py`. Schema changes must be additive and compatible with existing persistent volumes.
- Add configurable UI settings through `SETTING_DEFS`; environment values must continue to override and lock interface values.
- Keep official boundary downloads out of the repository. Preserve weekly FUNAI/CNUC discovery, validation, safe extraction, and rollback behavior.
- Keep frontend changes dependency-free unless a new production dependency is explicitly approved.

## Detection invariants

- Provider failures must never count as aircraft disappearance.
- With multiple providers enabled, disappearance requires successful coverage from all required providers for the last region.
- Do not send routine entry or exit emails.
- Only probable-stop and disappearance events may trigger alerts.
- Unknown aircraft remain candidates; only high-confidence scheduled-airline matches are suppressed.
- Shadow and Review phases never send external alert email. Live phase does.
- Preserve event deduplication, outside confirmation, freshness checks, and provider retention limits.
- Describe detected behavior neutrally; never turn heuristics into accusations.

## Security and data safety

- Never commit `.env`, credentials, runtime databases, downloaded boundaries, provider payloads, or recipient data.
- Do not weaken authentication, CSRF, trusted-host checks, security headers, secret encryption, login throttling, or container hardening.
- Do not expose the dashboard publicly without HTTPS and secure cookies.
- Do not call live flight, boundary, or email services in automated tests. Use fixtures or `httpx.MockTransport`.
- Do not install or execute code from third-party repositories or agent skills without explicit approval and review.

## Testing expectations

- Add or update tests for every behavior change and regression fix.
- Keep tests deterministic and isolated from the network and production data.
- Provider changes need parsing, timestamp, freshness, authentication, and failure-accounting coverage.
- Detection changes need state-transition, deduplication, outage, and phase/email coverage.
- Boundary changes need state filtering, neighboring-area selection, geometry validity, stable IDs, and partial-download safeguards.
- Configuration or security changes need environment-precedence, redaction, authentication, and CSRF coverage.

## Change checklist

Before finishing:

1. Run the smallest relevant test while iterating, then `make check`.
2. Run the JavaScript syntax check after frontend changes.
3. `uv run ruff check app tests` has a large pre-existing baseline (48 with all lanes' test files; 46 at `3d6b9fe`). To prove zero net-new prefer a worktree so concurrent lanes/operator WIP don't collide: `git worktree add /tmp/base HEAD --detach` and compare `uvx ruff check --output-format=concise app tests | grep -c ':'` on both trees (`git stash -u` collides with `intent-to-add` files). `make bump-version` touches `Dockerfile` `APP_VERSION` and busts the `uv` layer cache → next `docker compose up --build` is cold (~12 min); sweep `rm -f .coverage` before `git status`; leave the `healthy` container running (don't `compose down` at lane boundaries).
4. Validate Compose and build the image after infra or dependency changes.
5. Update `README.md`, `.env.example`, `docs/SPEC.md`, or `docs/RESEARCH.md` — and after any user-visible FR24 change also `FLIGHTRADAR_API.md` — when their documented behavior changes; sweep the four surfaces together in one commit.
6. Report any check that could not run; do not claim live upstream or email validation without evidence.

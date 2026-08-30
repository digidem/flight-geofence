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
- After any user-visible FR24 change (budget policy, manual Tracks flow, enrichment retries, legacy-provider warning, retention windows, CAS), sweep all four doc surfaces together in one commit: `README.md` + `docs/SPEC.md` + `.env.example` + `FLIGHTRADAR_API.md`.
- Access SQLite through `app/database.py`. Schema changes must be additive and compatible with existing persistent volumes.
- Add configurable UI settings through `SETTING_DEFS`; environment values must continue to override and lock interface values.
- Frontend stays dependency-free: optional dev-dep guard checks (axe, lighthouse) must use `npx --no-install` — `npx --yes` auto-installs packages without approval.
- New DOM-touching JS helpers must stay compatible with the node `vm` test harness: guard `typeof document`/`getElementById`/`document.body` before use, and keep the `window.confirm` gate in the `#event-track-panel` handler — `tests/test_fr24_track_panel_vm.mjs` drives it with a minimal document stub.
- Keep official boundary downloads out of the repository. Preserve weekly FUNAI/CNUC discovery, validation, safe extraction, and rollback behavior.
- Keep frontend changes dependency-free unless a new production dependency is explicitly approved.
- Render timestamps with `Intl.DateTimeFormat` and the `timezone` setting's IANA name; never hand-roll offset math. Adding the browser's `getTimezoneOffset()` to the selected zone double-counts on non-UTC clients, and headless/test browsers usually run UTC, hiding the bug (shipped as v0.5.4 fix).
- Await `loadSettings()` before any render that formats times or translates text: `appState.language`/`appState.timezone` only exist once `/api/settings` resolves, and the default `America/Sao_Paulo` otherwise leaks into the first paint.
- Every interpolation into an `innerHTML` template goes through `escapeHtml`, including helper outputs like `formatTime` that can fall through to raw input on parse failure.
- State-changing UI actions (selection, settings, toggles) must surface failure: catch the fetch, show a translated error, revert the control. A POST that dies as an unhandled rejection leaves the UI silently out of sync with the server — the whole v0.5.3 areas-selection bug class.

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
- Frontend changes: run the VM tests (`node tests/test_*_vm.mjs`) after `node --check`, and reproduce timezone-dependent formatting under a non-UTC `TZ` (e.g. `TZ=America/Sao_Paulo node …`) before trusting it.

## Release

1. Land the fix on `main` first. The release commit must contain only version files.
2. `make bump-version` seds `app/main.py`, so stash unrelated WIP touching it first (`git stash push app/main.py tests/…`) and pop after committing the bump.
3. `make bump-version VERSION=X.Y.Z`, then stage **only** the six version files (`Dockerfile`, `app/main.py`, `LINKS_REPORT.txt`, `README.md`, `docs/VALIDATION.md`, `docs/AUDIT.md`). Never `git add -A` — untracked lane/operator WIP otherwise rides into the release tag unnoticed.
4. Push, then `gh workflow run release.yml --ref main -f version=vX.Y.Z`; the `v` prefix is regex-validated, a bare `X.Y.Z` fails the workflow.

## Change checklist

Before finishing:

1. Run the smallest relevant test while iterating, then `make check`.
2. Run the JavaScript syntax check after frontend changes.
3. `uv run ruff check app tests` has a large pre-existing baseline (48 with all lanes' test files; 46 at `3d6b9fe`). To prove zero net-new prefer a worktree so concurrent lanes/operator WIP don't collide: `git worktree add /tmp/base HEAD --detach` and compare `uvx ruff check --output-format=concise app tests | grep -c ':'` on both trees (`git stash -u` collides with `intent-to-add` files). `make bump-version` touches `Dockerfile` `APP_VERSION` and busts the `uv` layer cache → next `docker compose up --build` is cold (~12 min); sweep `rm -f .coverage` before `git status`; leave the `healthy` container running (don't `compose down` at lane boundaries).
3b. Concurrent lanes mutate the main checkout too: `git status --short` before starting, and if unfamiliar uncommitted edits appear mid-session (seen 2026-08-30: a parallel lane's half-applied changes corrupting `app/main.py` with duplicate function definitions), `git stash push -u -m "<label: ask owner>"` rather than reverting, verify `python -m compileall app` parses, then untangle only what the current task owns.
4. Validate Compose and build the image after infra or dependency changes.
5. Update `README.md`, `.env.example`, `docs/SPEC.md`, or `docs/RESEARCH.md` — and after any user-visible FR24 change also `FLIGHTRADAR_API.md` — when their documented behavior changes; sweep the four surfaces together in one commit.
6. Report any check that could not run; do not claim live upstream or email validation without evidence.

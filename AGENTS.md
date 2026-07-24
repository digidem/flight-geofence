# AGENTS.md

## Purpose

Maintain a private research PoC that compares aircraft positions with selected Brazilian Indigenous territories and conservation units. Preserve the core safety statement: events are unverified signals, never proof of landing, deliberate transponder shutdown, illegal mining, or wrongdoing.

`SPEC.md` is the behavioral source of truth. Update it when product behavior or alert semantics change.

## Commands

```bash
uv sync
make check
node --check app/static/app.js
cp .env.example .env && docker compose config --quiet
```

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
3. Validate Compose and build the image after infra or dependency changes.
4. Update `README.md`, `.env.example`, `docs/SPEC.md`, or `docs/RESEARCH.md` when their documented behavior changes.
5. Report any check that could not run; do not claim live upstream or email validation without evidence.

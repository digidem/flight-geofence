# Final audit — v0.5.0

This release is a corrective and hardening pass over v0.3.

## Material defects corrected

- Removed the Dockerfile reference to a nonexistent `data/` directory that would have broken image builds.
- Corrected ADS-B Exchange authentication from `X-Api-Key` to the documented `api-auth` header.
- Corrected Flightradar24 numeric timestamp handling so old records are not treated as current.
- Fixed environment precedence so values loaded from `.env` are recognized outside Docker Compose.
- Fixed probable-stop timing so a prior high-speed observation cannot start the low-speed timer.
- Fixed Starlette middleware ordering so CSRF always has access to the signed session.
- Changed Makefile tests to `python -m pytest` for reliable application imports.
- Added additive migration fields required when reusing a v0.3 database.

## Reliability improvements

- Bounded provider retries with `Retry-After` handling.
- Region-specific all-provider success requirement for disappearance.
- Email retry queue with bounded backoff.
- Resend idempotency keys.
- Nonmonotonic observation rejection.
- Outside-confirmation hysteresis.
- Stale state cleanup.
- Cross-process job locks for scheduler/CLI overlap.
- Atomic logical rollback of an area selection when region generation fails.
- Deterministic query-region identifiers.
- Online SQLite backup script.

## Boundary-import hardening

- Streamed size-limited downloads.
- ZIP magic check.
- Member-count and expanded-size limits.
- Path traversal and symlink rejection.
- CRS and polygon validation.
- Stable official/fallback identifiers.
- Minimum plausible dataset counts before replacement.
- Existing dataset preserved when the new import fails validation.

## Security and infrastructure improvements

- Required nonexample password and application secret.
- Failed-login throttling.
- Signed SameSite session.
- CSRF protection.
- Trusted hosts and defensive HTTP headers.
- Secret redaction and encrypted UI settings.
- Non-root process.
- Read-only root filesystem.
- Dropped capabilities and no-new-privileges.
- PID limit, health/readiness checks, bounded logs, graceful stop.
- Localhost-only default binding.
- Optional pinned Caddy HTTPS profile.
- GitHub Actions test, Compose validation, and container-build workflow.

## Remaining inherent limitations

- External feeds cannot detect aircraft that do not produce a usable signal or are outside receiver coverage.
- “Non-airline candidate” is a heuristic, not an authoritative commercial/legal classification.
- Stop and disappearance events require human corroboration.
- Official and commercial upstream APIs can change independently of this code.
- This remains a single-operator PoC rather than a multi-user production monitoring platform.

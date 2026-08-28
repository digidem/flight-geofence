# Validation record — v0.6.2

## Completed in the build environment

- Python syntax compilation for application and tests.
- Twenty-three automated unit/integration tests pass.
- FastAPI lifespan startup and shutdown.
- Real Uvicorn HTTP smoke test on a local TCP port.
- Public `/healthz` and database-backed `/readyz`.
- Static frontend delivery and CSP/security headers.
- Unauthenticated API rejection.
- Password login and signed session-cookie access.
- CSRF rejection and successful authorized mutation.
- Login/security environment validation.
- Encrypted settings persistence and secret redaction.
- Environment precedence over interface settings.
- Area selection persistence.
- Deterministic coverage-region generation.
- Selection rollback when coverage generation rejects a change.
- readsb timestamp normalization, coordinate validation, and freshness filtering.
- Flightradar24 numeric timestamp normalization.
- ADS-B Exchange `api-auth` header behavior.
- Airliner and unknown-candidate classification.
- Boundary record filtering for target states and neighboring conservation units.
- Stable fallback area identifiers and deterministic query-region identifiers.
- UI boolean setting round-trip behavior.
- Cross-process poll/sync locking.
- Provider HTTP-attempt accounting across retries.
- Stop timer reset and high-speed-first-observation behavior.
- Outside confirmation before episode closure.
- Safe ZIP traversal rejection.
- Python dependency versions match the pinned project requirements in the build environment.
- JavaScript syntax check with Node.js.
- Docker Compose YAML parsing and required hardening fields.
- Shell syntax for the SQLite backup script.

## Known environment limitation

Docker Engine was not available in the artifact-building environment, so the image could not be built and started through Docker Compose here. The same application was started directly with Uvicorn using isolated runtime paths and passed HTTP smoke tests.

External network access to FUNAI, MMA, flight providers, and Resend was unavailable from the execution environment. Therefore, the first deployment must still verify:

- real FUNAI WFS download;
- real MMA CKAN discovery and CNUC ZIP download;
- actual upstream field schemas at that moment;
- each selected flight provider’s credentials, coverage, rate limits, and response;
- real Resend or SMTP delivery;
- Docker image build on the target host.

The default Shadow phase and explicit provider/boundary test controls exist for exactly this validation step. Upstream errors are displayed and do not count as aircraft disappearance.

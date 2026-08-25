# Flight Geofence Alerts — specification v0.4

## Product objective

Run a real-data proof of concept that monitors operator-selected Indigenous territories and neighboring conservation units in PA, AM, AP, and RR for two explainable aircraft signals: probable stop and position disappearance.

## Operating phases

1. **Shadow:** real official boundaries and real flight-provider polling; record events; send no external alert email.
2. **Review:** continue monitoring without alert email; classify event usefulness and tune settings.
3. **Live:** email new qualifying events through a validated Resend or SMTP configuration.

A transition from Live back to Shadow or Review pauses pending email retries.

## Boundary requirements

### Source fallback chain

Indigenous territories:
1. FUNAI WFS `tis_poligonais` (primary, requires browser-like User-Agent)
2. Last known-good local snapshot (fallback)

Conservation units:
1. ICMBio WFS `limiteucsfederais_a` (primary for federal UCs)
2. CNUC via MMA CKAN discovery (fallback for all UCs)
3. RAISG protected areas ArcGIS REST (final fallback)
4. Last known-good local snapshot (emergency)

### Data acquisition rules

- Acquire FUNAI `tis_poligonais` from the official WFS with browser-like User-Agent header.
- Include all polygon phases returned by FUNAI.
- Retain territories whose state attribute intersects PA, AM, AP, or RR.
- Download federal conservation units from ICMBio WFS when available.
- Discover the newest suitable active CNUC polygon ZIP from the official MMA CKAN package as fallback.
- Use RAISG protected areas as final fallback when other sources fail.
- Use the configured official fallback resource when discovery fails.
- Retain CNUC polygons intersecting or within the configurable distance of included territories.
- Refresh when the last successful update is at least seven days old.
- Preserve operator selection across refreshes using stable identifiers.
- Auto-select all areas only on the first successful sync; optionally auto-select new areas when the prior complete set was selected.
- Reject unsafe ZIP paths, symlinks, excessive archive sizes, missing CRS, nonpolygon output, implausibly small result sets, and excessive query-region counts.
- Do not replace existing boundaries until a complete new result passes validation.

## Query-region requirements

- Generate overlapping point/radius regions from the union of selected geometries plus an outside observation buffer.
- Use deterministic IDs based on center and radius.
- Enforce the provider radius maximum and a configurable maximum region count.
- Treat area selection and query-region regeneration as one logical change; roll selection back when generation fails.

## Configuration requirements

- `ADMIN_PASSWORD` and `APP_SECRET_KEY` are required security controls.
- Refuse startup with example values unless an explicit isolated-development override is enabled.
- Allow other operational values through environment or authenticated settings UI.
- Give nonblank environment values precedence and lock them in the UI.
- Encrypt UI-supplied secrets before SQLite storage.
- Never return stored secret values to the browser.
- Validate choices, ranges, email addresses, lists, and provider IDs server-side.

## Authentication and security requirements

- Password login with constant-time comparison.
- Throttle repeated failed logins.
- Signed SameSite session cookie, configurable `Secure` flag, and 12-hour lifetime.
- CSRF token for authenticated state-changing API operations.
- Trusted-host enforcement.
- CSP, frame protection, referrer protection, MIME sniffing protection, permissions policy, and no-store on private content.
- No public OpenAPI/Swagger endpoints.
- Non-root container, read-only root filesystem, dropped capabilities, no-new-privileges, PID limit, bounded logs, and health checks.
- Bind to localhost by default; provide optional automatic-HTTPS reverse proxy profile.

## Provider requirements

Adapters:

- ADSB.lol;
- Airplanes.live;
- ADS-B Exchange Enterprise using `api-auth`.

Flightradar24 (Explorer plan) is a separate, cost-controlled adapter — see "Flightradar24
Explorer plan requirements" below. It is not part of the free-provider query-region grid; its
legacy unfiltered/unbounded polling path has been retired entirely.

Each adapter must:

- validate latitude, longitude, ICAO hex, and position freshness;
- normalize timestamp units and ISO timestamps;
- normalize available callsign, registration, type, altitude, speed, track, source, origin, destination, and operator;
- retry 429 and transient server failures with bounded backoff;
- record request attempts and successes;
- never log API keys.

Airplanes.live must stop before exceeding 500 attempts per UTC day.

When multiple free providers are enabled:

- merge observations by ICAO hex using the freshest observation;
- consider a query region fully successful only when every enabled provider succeeded;
- increment disappearance only for fully successful regions.

## Flightradar24 Explorer plan requirements

- Operate on operator-defined rectangular clusters (buffer-derived from selected areas, or
  manual WGS84 bounds), never on the free-provider query-region grid, up to a configurable cap on
  simultaneously active clusters.
- Poll on an independent schedule and lock, decoupled from the free-provider coverage cycle.
- Use only the Light positions endpoint for routine polling; estimate cost as 1 credit for an
  empty response, else 6 credits per returned aircraft record — never `1 + 6 × n`.
- Call the Count endpoint only exceptionally (a possibly-truncated Light response), throttled to
  at most once per hour per cluster, never as routine calibration.
- Fetch Summary Full only for new candidate aircraft entering a monitored area, and only when
  enabled. Tracks (full flight history) is the most expensive endpoint and is not fetched by any
  automated path in this release; an on-demand, manually-triggered Tracks lookup is a documented
  follow-up, not yet implemented.
- Track a configurable monthly credit budget against actual usage; suppress non-essential calls
  (enrichment, usage sync) once spend crosses the warning threshold (70%). Escalating budget
  states above that (critical, hard-limit) are logged but do not themselves stop routine Light
  polling; at full exhaustion (100%+) the configured `FR24_BUDGET_POLICY` decides — the default,
  `pause_fr24`, stops the FR24 cycle outright until the next billing period, while `warn_only`
  logs but never stops polling and `continue_until_provider_rejects` polls until the provider
  starts rejecting requests. Spend is evaluated at cycle start, so exhaustion reached mid-cycle
  finishes the current cycle and pauses the next one.
- Never merge Flightradar24 observations into the free-provider grid's own merge step; instead,
  when a free provider already holds a fresh, actively-tracked claim on an aircraft, Flightradar24
  must defer to it rather than overriding it with a possibly-stale or one-off touch.
- Default to indefinite retention of Flightradar24-sourced events and aircraft state (auto-delete
  off) when the operator holds documented governmental authority to retain the data — the
  written-agreement exception to the 30-day storage ceiling below. Auto-delete, when explicitly
  enabled, still enforces that ceiling.

## Detection requirements

### Scheduled-airline suppression

- Match configured callsign prefixes, operator codes, and airliner types.
- Treat unknown aircraft as candidates.
- Never claim an authoritative legal/non-commercial classification.

### Probable stop

- point lies inside one or more selected polygons;
- no scheduled-airline match;
- minimum fresh inside-observation count met;
- ground flag or speed under configured maximum;
- movement stays within configured radius;
- low-speed duration met;
- timer begins only on a low-speed observation;
- timer resets on high-speed movement, excessive displacement, or an observation gap;
- one event per aircraft episode.

### Disappearance

- last fresh position lies inside selected polygon(s);
- minimum inside-observation count met;
- no scheduled-airline match;
- last altitude below configured ceiling or unavailable;
- aircraft absent from configured complete successful cycles for its last region;
- provider failures and pending outside confirmation do not increment disappearance;
- one event per aircraft episode.

### Episode closure

- require configurable consecutive outside observations before closure;
- reset event flags only after closure;
- reject nonmonotonic/older observations.

## Event, notification, and review requirements

- Store only probable-stop and disappearance events; no routine entry/exit email.
- Use a unique episode/event-type deduplication key.
- Store a neutral reason, classification rationale, protected areas, position snapshot, provider, phase, and optional enrichment.
- Shadow and Review events have no external notification.
- Live events begin as pending and are delivered through Resend or SMTP.
- Enforce a daily sent-email cap.
- Retry failed Live events with bounded attempts and increasing delays.
- Use Resend idempotency keys to reduce duplicate delivery after ambiguous failures.
- Stop retries when the current operating phase is not Live.
- Require a disclaimer in every message.
- Support `unreviewed`, `useful`, `noise`, and `uncertain` plus notes and timestamp.

## Persistence requirements

- SQLite WAL mode with busy timeout and foreign keys.
- Persist settings, area records/selections, query regions, syncs, polls, aircraft state, events, reviews, request counters, and email retry state.
- Perform in-place additive schema migration from v0.3.
- Clean stale outside aircraft state after configurable retention.
- Delete Flightradar24-sourced events and aircraft state before the provider's 30-day storage
  ceiling *unless* the operator has documented governmental authority to retain the data
  indefinitely (the written-agreement exception), in which case auto-deletion defaults off.
- Support consistent SQLite online backup.
- Prevent manual CLI poll/sync from overlapping the server scheduler with cross-process file locks.

## Acceptance criteria

- App refuses insecure example credentials by default.
- First successful startup sync can acquire real FUNAI and CNUC polygons without prebuilt local files.
- A failed or implausibly partial weekly update preserves previous healthy boundaries.
- Area selections survive a healthy refresh.
- Invalid broad selection is rolled back when it exceeds query-region constraints.
- Unauthenticated APIs reject access.
- Authenticated mutation without CSRF is rejected.
- Stored secrets are encrypted and redacted from API responses.
- Environment values remain authoritative.
- Shadow/Review never send alert email.
- Live cannot be enabled through the UI without a viable email configuration.
- Provider failures never increment disappearance.
- A high-speed first observation cannot count toward stop duration.
- Boundary jitter requires multiple outside observations before episode closure.
- Duplicate event processing cannot create a duplicate event.
- A container restart preserves state and configuration.
- Health/readiness endpoints and Docker health checks work.

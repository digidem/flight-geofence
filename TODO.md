# TODO

Known pending items as of 2026-08-29. Not a backlog — just what's open.

## Blocking real alerting

- [x] **Enable resend email in production.** Fixed 2026-08-29. Renamed the
      host `.env` key `RESEND_API` → `FLIGHT_GEOFENCE_RESEND_API_KEY`, added
      `FLIGHT_GEOFENCE_ALERT_RECIPIENTS`, and wired `EMAIL_PROVIDER: resend`,
      `RESEND_API_KEY`, `ALERT_RECIPIENTS` into `flight-geofence`'s
      `environment:` block in `edt-cloud/docker-compose.yml`
      (`edt-cloud@868f22c`) — same env-file gap as the FR24 key had.
      Verified live: `email_provider`/`resend_api_key`/`alert_recipients`
      all report `source: environment, locked: true` over
      `https://voos.earthdefenderstoolkit.com/api/settings`.
- [x] **Move `operating_phase` out of `shadow`.** Done 2026-08-29, set to
      `live` directly. Note: `review` does **not** send email either — only
      `shadow` and `review` are silent; `_persist` in `app/detection.py`
      calls `send_event_email` solely when `phase == "live"`. `review`'s
      only distinction is `email_status: review_only` on the row, not
      delivery — so there was no lower-risk email test to run first.
      Server-side readiness check (`_live_readiness_errors`) passed cleanly
      since Resend + recipients were already wired.

## Data hygiene

- [ ] **Geometry leak in `poll_runs.error_message`.** 695 rows in production
      contain raw region coordinates from httpx's quoted 429 error text
      (e.g. `.../v2/point/0.280901/-52.592973/200.0`). `_scrub_log_message`
      exists (`app/database.py`) and is already wired into
      `record_provider_call`, but not into the two `poll_runs` write sites
      at `app/main.py:306` and `:314`. Same bug class fixed in 0.6.1 for a
      different table; needs the scrub applied here too, plus a backfill of
      the 695 existing rows.

## Security follow-up

- [ ] **Rotate the FR24 API key.** Half of it hit this session's terminal
      scrollback while diagnosing the `.env` sourcing trap (see below) —
      cheap to rotate, no reason not to.

## Operational notes (not action items, just context)

- `adsb_lol` is 429ing more often lately — down to 1 of 4 regions on the
  last poll before this was written, versus 3 of 4 typically. Doesn't
  cause false `DISAPPEARED` (coverage is tracked by region set, not the
  `success` flag), just means thinner free-tier coverage. Watch, don't fix.
- FR24 `/api/live/flight-positions/count` returns 403 on the current plan —
  the truncation-calibration path in `FLIGHTRADAR_API.md` can't run here.
- Two stale backup files sitting on the host at
  `/mnt/volume_nyc1_01/edt-cloud/docker-compose.yml.bak-v0.5.0-deploy` and
  `.bak-v0.5.1-fr24key` — harmless, just clutter.
- **Never `. ./.env` in a shell on the host.** `FLIGHT_GEOFENCE_FR24_API_KEY`
  contains a `|`, so sourcing it pipes half the token into a shell command
  and prints the rest in the resulting error. Read individual values with
  `grep`/`cut`, or let `docker compose` substitute them itself.
- The host's `docker-compose.yml` drifts from what's committed in
  `../edt-cloud` — real changes (image pin, `mem_limit`, key passthrough)
  have landed there without a matching commit before. Diff before pulling.

See also: `.claude/skills/flight-geofence-ops/SKILL.md`,
`.claude/skills/flight-geofence-diagnostics/SKILL.md`.

# TODO

Known pending items as of 2026-08-30. Not a backlog — just what's open.

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

- [x] **Geometry leak in `poll_runs.error_message`.** Done 2026-08-30, PR #11
      (v0.8.2). Both `_run_coverage_cycle_locked` write sites pass through
      `_scrub_log_message`; backfill executed on production — 1032/1032 leaky
      rows scrubbed (higher than the 695 originally counted; the leak kept
      growing), 0 remain of 9530, `PRAGMA integrity_check: ok`, 314 areas
      intact. Note: the pre-scrub backup failed (docker compose exec phantom
      "not running" — plain `docker exec` works); accepted because the scrub
      only rewrites error text (URLs → `<url>`, 500-char cap) and the
      coordinates live by design in `areas`/`provider_call_log`. Backfill is
      idempotent — safe to re-run via `README.md § Poll-run error scrub`.

## Security follow-up

- [ ] **Rotate the FR24 API key.** Half of it hit this session's terminal
      scrollback while diagnosing the `.env` sourcing trap (see below) —
      cheap to rotate, no reason not to.

## Watch items

- [ ] **Complete the 48-72h RSS observation window (issue #4).** Tooling
      shipped (`scripts/rss_watch.sh`, PR #9) and a local synthetic leak-hunt
      found no leak (docs/RESEARCH_RSS.md, PR #8). Run the sampler every ~6h,
      then decide: flat → close #4; monotonic climb excluding sync spikes →
      next suspects are SQLite/WAL page cache and the boundary-sync geometry
      pass (coverage.py). Baseline: ~112 MiB / 850 MiB at 2026-08-30.
- [ ] **Verify old REVIEW_NOTES coverage gaps still exist.** The deleted
      `docs/REVIEW_NOTES.md` claimed zero test coverage on disappearance
      events and email retry (Batch 9). pytest has since grown 353 → 412; if
      those gaps are genuinely still open, add the tests — both are
      safety-critical paths (external alert delivery + detection).

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
- `docker compose exec` can fail with a phantom `service … is not running
  container #1` right after a container recreate, while plain `docker exec
  <container-name>` works — during the v0.8.2 backfill the compose form
  failed three times and plain exec never did. Prefer plain docker exec with
  the full container name for one-off ops commands.

See also: `.claude/skills/flight-geofence-ops/SKILL.md`,
`.claude/skills/flight-geofence-diagnostics/SKILL.md`.

---
name: flight-geofence-diagnostics
description: "How to answer 'why are there no events / is the system blind?' with evidence. The Logs audit trail, the dispositions, and the traps that produce confidently wrong answers. Load whenever detection output looks suspiciously empty or someone questions whether a non-finding is real."
---

# Diagnosing an empty dashboard

Detection reports what it **found**. The Logs tab reports what it **saw**. A quiet
dashboard is only trustworthy if you can distinguish the two.

## Order of investigation — cheapest first

1. **Was anything configured to look?** `fr24_clusters.created_at` /
   `config_audit_log`. Polls that predate a cluster's creation return 0 by
   definition. Averaging across those days produces a misleading "the system sees
   nothing" claim — check the config timeline before quoting long-run averages.
2. **Are areas selected?** `SELECT COUNT(*) FROM areas WHERE selected=1`. Query the
   **database**, not `/api/areas?selected=1` with a guessed field name — an API
   filter that silently returns nothing looks identical to genuine emptiness.
3. **What did the provider return?** `fr24_request_log.records_returned`,
   `poll_runs.aircraft_returned`. Both count **raw** provider output, before area
   filtering.
4. **What reached detection?** `observation_log`. The gap between (3) and (4) is
   aircraft billed for but never processed.
5. **Probe the live API** with relaxed filters (see
   `flight-geofence-fr24-economics`) to separate "sky is empty" from "our filter
   hides them".

## The dispositions and what each tells you

Every path through `process_observation` logs exactly once:

| disposition | meaning |
|---|---|
| `inside_new_episode` | first sighting inside a selected area; episode opened |
| `inside_continuing` | advancing toward stop/disappearance thresholds |
| `outside_no_episode` | seen, matched no area, nothing open — **the common one** |
| `outside_pending_confirmation` | left the area, departure not yet confirmed |
| `episode_closed_by_leaving` | confirmed departure, no event — the expected exit |
| `stale_position` | not newer than the last recorded position |
| `dropped_stale_or_unusable` | dropped in the **provider parser**, never reached detection |
| `dropped_malformed_record` | provider returned a non-object record |

The two `dropped_*` values matter most: `normalize_light_observation` returns
`None` for a position older than `POSITION_MAX_AGE_SECONDS` (prod 150s), so an
aircraft can be returned, counted, and **billed** while detection never sees it.
Without those rows that gap is invisible.

## Useful queries

```sql
-- did anything reach detection?
SELECT disposition, COUNT(*) FROM observation_log GROUP BY disposition;
-- what the provider handed back, by day
SELECT substr(requested_at,1,10) d, SUM(records_returned), COUNT(*)
  FROM fr24_request_log WHERE endpoint LIKE '%light%' GROUP BY d;
-- degraded coverage hiding behind a "successful" poll
SELECT started_at, regions_total, requests_successful, aircraft_returned, error_message
  FROM poll_runs ORDER BY started_at DESC LIMIT 10;
```

`kind=detection` on `/api/logs` answers "what did we actually see?" — every
observation plus calls that returned ≥1 aircraft, empty polls dropped. It reaches
back over history via call rows, which is the **only** record of detections made
before per-aircraft logging existed.

## Traps that produce wrong answers

- **A call row has no aircraft identity.** It records *how many*, never *which*.
  An empty Aircraft column on a call row is correct, not a bug. Only observation
  rows name the aircraft.
- **`poll_runs.success=1` with `requests_successful < regions_total`.** A poll is
  marked successful while a region is failing. Seen in production: one region 429ing
  every cycle, ~50% of `adsb_lol` calls failing, coverage silently down a quarter.
- **Inferring a mechanism from an absence.** Zero rows is consistent with many
  causes. Confirm with a positive observation before asserting a cause; a first
  real row has overturned a confident hypothesis here more than once.
- **Rate of arrival.** At ~16 aircraft/day, an empty first hour after a deploy is
  expected, not evidence of breakage. Do the arithmetic before alarming.
- **Free-provider coverage is genuinely sparse.** Ground-based ADS-B over the
  Amazon interior barely exists; `adsb_lol` producing almost nothing is plausible,
  not necessarily a defect.

## Geometry must never reach logs

Providers put the region centre and radius in the **request path**
(`/v2/point/<lat>/<lon>/<radius>`), and httpx quotes the failing URL in error text.
Both are scrubbed — `_endpoint_label()` drops numeric path segments,
`_scrub_log_message()` replaces URLs with `<url>`. Preserve both when touching
logging, and assert it in tests: it is a privacy guarantee, not cosmetics.

Related: [[flight-geofence-mission]], [[flight-geofence-fr24-economics]]

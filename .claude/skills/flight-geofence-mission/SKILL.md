---
name: flight-geofence-mission
description: "What flight-geofence is for, the safety framing that must never be weakened, and the exact gates an aircraft must pass to become an event. Load before changing detection logic, thresholds, event semantics, alert wording, or anything an operator reads."
---

# What this system is for

A private research PoC that compares aircraft positions against selected Brazilian
Indigenous territories and conservation units, to surface possible unauthorized
activity — the profile associated with illegal mining logistics.

## The safety framing is load-bearing

Events are **unverified signals**. Never proof of landing, deliberate transponder
shutdown, illegal mining, or wrongdoing. Describe detected behavior neutrally.
Never turn a heuristic into an accusation. This constrains UI strings, email
copy, commit messages, and anything an operator or third party might read.

`docs/SPEC.md` is the behavioral source of truth. Update it when behavior changes.

## The epistemic limit — state it when it matters

An aircraft flying low over rainforest with its transponder off is invisible to
every provider. Absence of signal is not absence of aircraft. When someone asks
"why no events?", this is part of the honest answer — but check the data first
(see `flight-geofence-diagnostics`), because the boring explanation is usually
a configuration or coverage fact, not philosophy.

## The gates an aircraft must pass

Only `PROBABLE_STOP` and `DISAPPEARED` exist. Both are written to `events` in
every phase; `_persist` only sends email when `phase == "live"` (shadow and
review never email).

**DISAPPEARED** — all must hold:
1. seen inside a selected area on ≥ `min_inside_observations_for_disappearance` polls (default 2)
2. `outside_observations == 0` — an aircraft that flies out closes its episode with **no event**
3. last altitude ≤ `disappear_max_altitude_ft` (prod 6000), or unknown
4. not classified `scheduled_airline`
5. absent from ≥ `disappear_after_successful_polls` (default 3) **complete successful** coverage cycles

**PROBABLE_STOP** — all must hold:
1. ≥ `min_inside_observations_for_stop` (default 3) inside observations
2. on ground, or ground speed ≤ `stop_max_speed_kt` (default 20)
3. within `stationary_radius_meters` (500) for ≥ `stop_min_duration_seconds` (120)
4. not `scheduled_airline`

Classification (`classify_aircraft`) suppresses on callsign prefix, operator code,
or airliner type — **not** on FR24 category. A small passenger-configured aircraft
with no airline prefix is a `non_airline_candidate` and will generate events.

## Invariants that must never regress

- Provider failures must never count as aircraft disappearance.
- With multiple providers, disappearance requires successful coverage from all
  required providers for the last region.
- No routine entry/exit emails.
- Unknown aircraft stay candidates; only high-confidence airline matches are suppressed.
- Preserve deduplication, outside confirmation, freshness checks, retention limits.

## Where aircraft actually go

The FR24 cluster box is far larger than the selected areas. An aircraft can be
inside the billed box — and cost credits — while never crossing a protected area.
Those are logged `outside_no_episode`. If most traffic lands there, the question
is whether the monitored geometry matches where aircraft actually fly, not whether
detection is broken.

Related: [[flight-geofence-fr24-economics]], [[flight-geofence-diagnostics]],
[[flight-geofence-ops]]

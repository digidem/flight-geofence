---
name: flight-geofence-hex-links
description: "How aircraft hex investigation links work, which external hex->page services actually resolve (verified 2026-08-30), how to keep the Python/JS link builders in parity, and how to re-verify a link candidate before wiring it in. Load before changing app/links.py aircraft_hex_links, app/static/app.js aircraftHexLinks, the README investigation-links table, or any tracking-link ordering."
---

# Aircraft hex investigation links

The default link an operator clicks for aircraft information is chosen by
**what will actually resolve**, not by brand preference. Two builders must
stay behaviorally identical:

- `app/links.py::aircraft_hex_links(hex, provider, occurred_at, registration)` — emails
- `app/static/app.js::aircraftHexLinks(hex, provider, occurredAt, registration)` — dashboard

Tests pin both sides: `tests/test_links.py::TestAircraftHexLinks`,
`tests/test_email_links.py` (ordering), `tests/test_hex_links_vm.mjs` (drives
the real app.js in a node vm; run under `TZ=UTC` and `TZ=America/Sao_Paulo`).
README's investigation-links table documents the outcome for humans.

## Ordering contract (shipped v0.8.3)

1. **Registration known and valid** (the normal case — every event carries it):
   `https://www.flightaware.com/live/flight/{REG}` FIRST, unconditionally.
   Freshness is irrelevant. Then the provider's globe, then remaining globes.
2. **No/invalid registration**: freshness decides. Event < 24h old →
   `https://www.flightaware.com/live/modes/{hex}/redirect` first; older →
   observing provider's globe first (FR24 events → ADS-B Exchange; unknown
   provider → ADSB.lol), modes redirect LAST.
3. Priorities are renumbered 1..N by final position; consumers only use
   `links[0]` as the default click, everything else iterates.

Validation parity (Python `_is_valid_registration` is the reference):
**dehyphenate first**, then `len >= 2`, alnum, at least one letter. `"-A"` and
`"A-"` must be invalid in BOTH builders (this exact divergence shipped and was
caught in review — see What didn't work).

Naive (timezone-less) `occurred_at` values are UTC in both builders; JS
appends `Z` before `Date.parse`. Frontend freshness window is
`FLIGHTAWARE_FRESH_MS` = 24h, Python `FLIGHTAWARE_FRESH_HOURS = 24`.

## Verified service matrix (2026-08-30, real Brazilian hexes)

| Service | Resolves? |
|---|---|
| `flightaware.com/live/flight/{REG}` | ALWAYS — full tracking + history, not flight-gated. Verified PT-JLL, PT-MLJ, PR-XBA. |
| `flightaware.com/live/modes/{hex}/redirect` | ONLY while FA ties the hex to a current/recent flight. **Rots within hours of landing** (PT-JLL resolved in the morning, dead the same afternoon). |
| `globe.adsb.lol/?icao=`, `globe.adsbexchange.com/?icao=`, `globe.airplanes.live/?icao=` | Identity card (reg, type) for any hex the network has seen, grounded or not; live track when transmitting. |
| hexdb.io | API-only (human pages 404; API returned empty for test hexes). |
| opensky-network.org/aircraft-profile | Retired — HTTP 410. |
| airframes.io/aircraft/{hex} | SPA renders nothing. |
| planespotters.net, flightera.net | Cloudflare wall (even headless Chrome). |
| radarbox.com search | Does not resolve hexes. |

The accepted tradeoff: with a stale/wrong provider registration decode, the
aircraft-page default points at the wrong aircraft instead of failing safely
like the redirect did. Redirect rot was the dominant failure mode; a wrong-dec
is rarer. Globes remain as hex-keyed fallbacks.

## Re-verifying a link candidate (do this before wiring anything in)

```bash
# Grounded proof: find a hex NOT transmitting right now (total must be 0)
curl -s 'https://api.adsb.lol/v2/hex/{hex}' | jq .total
# Then load the candidate page in a REAL browser (curl gets bot-walled) and
# grep the rendered body for the registration. FlightAware titles look like:
#   "PT-JLL Flight Tracking and History - FlightAware"
```

Use browser-harness with a self-launched headless Chrome
(`--remote-debugging-port=9333`, `BU_CDP_URL`) — one script per session, CDP
targets go stale across invocations. Poll for rendered content instead of
fixed sleeps; `capture_screenshot(path)` takes no `full_page` kwarg.

To verify the dashboard end-to-end, seed the local DB with a REAL hex +
registration (`api.adsb.lol/v2/point/{lat}/{lon}/{radius}` gives live ones),
never an invented hex — fake hexes fail on every service and look like the
feature is broken when it isn't.

## What didn't work

- `flightaware.com/live/flight/{hex}` → "Unknown Flight" (only idents/regs work there).
- `flightaware.com/live/modes/{hex}` without `/redirect` → 404.
- Trusting a fresh-event redirect: "flew today" decays within hours.
- Seeding test events with an invented hex (`e49abc`): broke both the old
  globe default and the new FA default in verification, sending us hunting
  phantom bugs through three rounds of review.
- Reviewing link-ordering changes without driving the real JS: the VM battery
  exists because Python tests alone missed two JS parity bugs (timezone-less
  timestamps, hyphenated registration validation).

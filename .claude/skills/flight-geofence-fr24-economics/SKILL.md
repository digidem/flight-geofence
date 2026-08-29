---
name: flight-geofence-fr24-economics
description: "How Flightradar24 credits are actually spent, what the category and altitude filters really cost, and how to decide a settings change with numbers instead of intuition. Load before touching FR24 categories, altitude ranges, budget, poll interval, clusters, or answering any 'should we enable X' cost question."
---

# FR24 credit economics

Cost constants live in `app/fr24_credits.py` and are **provisional** — verify
against the operator's FR24 dashboard before treating them as fact.

## The formula that drives every decision

```python
estimate_light_credits(n) = 1 if n == 0 else 6 * n
```

Never compute it as `1 + 6*n` — that wrong formula is called out in the source.

The consequence: **an empty poll costs 1 credit, a poll that finds one aircraft
costs 6.** That 6× cliff, not the number of calls, is what moves the bill. Adding
aircraft to your result set is the expensive action; polling more often is cheap
by comparison.

Other endpoints: summary-full `2 * n`, tracks `40 * n` **per returned flight**
(not per track point — a flight with 3 track points is one flight, 40 credits).

## Measured baseline (Aug 2026, Wayamu-Tumucumaque cluster)

- 834 light calls / ~3 days = ~278/day at a 5-minute interval
- 1,096 credits total, of which **782 were empty polls** (782 × 1)
- only 52 calls found anything → ~365 credits/day ≈ 11,000/month
- budget 28,000/month → roughly 17,000/month headroom

Use this shape to sanity-check any projection: most spend is the empty-poll floor;
detections are the variable.

## Category policy and why "(cost)" is on P and C

`FLIGHTRADAR_API.md` mandates: default `T,H,N`; warn before removing `N`; **warn
before adding `P` or `C` because of likely credit impact**. The i18n labels
`fr24_cat_p` / `fr24_cat_c` carry "(custo)"/"(cost)" for that reason only — it is
a volume warning, not a surcharge.

That warning is written for busy airspace. Over a remote box it can be close to
moot — but **measure, don't assume**. Categories: `T` general aviation,
`H` helicopters, `N` uncategorized (keeps unusual aircraft with incomplete
classification), `P` passenger, `C` cargo, `J` business jets, plus M/B/G/D/V/O.

Category is **not** a legal determination about a flight.

## How to answer "should we enable X" — with evidence

Probe the live API directly rather than reasoning about it. From inside the
production container, using the real key, with a `limit`:

```python
# app.providers.fr24 exposes _headers() and FR24_BASE_URL
GET {FR24_BASE_URL}/api/live/flight-positions/light
    ?bounds=N,S,W,E&categories=T,H,N,P&altitude_ranges=-2000-15000&limit=100
```

Sweep one variable at a time (categories fixed, altitude cap varied; then the
reverse) and count returned aircraft. A few probes cost a handful of credits and
replace a guess with a number.

**The filters are strict — server-side.** `categories` and `altitude_ranges` are
sent to FR24, so excluded aircraft are never returned and never billed. If an
aircraft appears that seems to violate the filter, check `fr24_clusters.updated_at`
before concluding the filter is loose: a settings change moments earlier is the
likelier explanation, and mistaking one for the other produces confidently wrong
advice.

## Interaction worth understanding

The altitude cap already does most of the airliner exclusion that the category
filter is credited with — jets cruise FL300+. So adding `P` under a low cap can
cost far less than the warning implies, while the aircraft that matter (light
turboprops, ~150 kt, 5–15k ft, Brazilian `PP/PR/PS/PT/PU` registrations) sit right
at the boundary. Two gates hide them; a third (`disappear_max_altitude_ft`,
default 6000) can still block the *event* even once they are fetched. Fetching and
alerting are separate decisions.

## Not available on every plan

`/api/live/flight-positions/count` returns **403** on the current production plan.
The truncation-calibration path in `FLIGHTRADAR_API.md` therefore cannot run there.
Verify plan support before relying on an endpoint.

## Safety rails that already exist

`fr24_budget_policy=pause_fr24` hard-stops polling at 100% of budget, so a
misjudged setting cannot silently overrun. Combined with the Logs tab, the impact
of any change is visible within a day — prefer "change, observe 24h, decide" over
a large speculative change.

Related: [[flight-geofence-mission]], [[flight-geofence-diagnostics]]

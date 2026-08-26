# Implement an Explorer-Optimized Flightradar24 Monitoring Strategy

You are working on the **Flight Geofence Alerts** repository.

Read and follow the root `AGENTS.md` before doing anything else. `CLAUDE.md`, when present, only imports `AGENTS.md`.

## Execution protocol

This task has two mandatory stages.

### Stage 1 — Plan only

In your first response:

1. inspect the repository;
2. inspect the existing provider abstraction, polling scheduler, database models, configuration system, area selection, query-region generation, event detector, admin interface, Docker setup, tests, and documentation;
3. verify the current Flightradar24 API documentation and official SDK;
4. produce a detailed implementation plan;
5. identify migrations, compatibility concerns, risks, and exact files expected to change;
6. stop without modifying code.

Do not create files, edit code, run migrations, or change configuration during Stage 1.

Wait for explicit approval before Stage 2.

### Stage 2 — Implementation

After the plan is approved:

1. implement the approved design;
2. preserve existing provider support and provider abstractions;
3. add migrations and tests;
4. run every validation command required by `AGENTS.md`;
5. report all files changed, migrations, tests, and remaining limitations.

Do not collapse the planning and implementation stages.

---

# 1. Product objective

Add a cost-controlled Flightradar24 integration optimized for the **Explorer API plan**.

The system will initially monitor exactly **two operator-selected geographic clusters** every five minutes.

The target is not general aviation monitoring. The target is low-altitude, small aircraft and helicopters potentially associated with illegal mining or other unauthorized activity around selected Indigenous territories and conservation areas in the Brazilian Amazon.

The recurring FR24 query must exclude as much irrelevant traffic as possible **before results are returned and billed**.

The first operational configuration should:

* use Flightradar24 as the primary paid provider;
* retain ADSB.lol, Airplanes.live, and ADS-B Exchange as optional comparison providers;
* operate in Shadow phase initially;
* monitor two compact clusters;
* poll every 300 seconds;
* use server-side FR24 filters;
* run exact point-in-polygon checks locally;
* enrich only aircraft that become relevant;
* avoid automatic flight-track downloads;
* remain viable within the normal 30,000-credit Explorer allocation where actual traffic allows.

Do not remove or weaken the provider abstraction. A retained `flightradar24` value in
`FLIGHT_PROVIDERS` is skipped compatibly and surfaced as a Settings warning linking to the FR24 tab.

---

# 2. Verified Explorer constraints

Treat these as the current design inputs, but verify them again against official FR24 documentation before implementation.

Current Explorer characteristics:

```text
Subscription price: US$9/month
Standard monthly allocation: 30,000 credits
Promotional allocation: 60,000 credits when eligible
Queries per minute: 10
Maximum returned records per response: 20
Historical availability: 30 days
```

The current promotion must not be treated as permanent.

The application must budget and report against:

```text
standard capacity: 30,000 credits
recommended operating budget: 28,000 credits
```

The remaining 2,000 standard credits are reserved for:

* candidate enrichment;
* overflow checks;
* manual investigations;
* integration testing;
* unexpected traffic;
* discrepancies between estimated and provider-reported usage.

Do not hardcode the promotional 60,000 credits as the normal plan capacity.

Make plan capacity configurable.

Suggested configuration:

```env
FR24_PLAN=explorer
FR24_PLAN_MONTHLY_CREDITS=30000
FR24_MONTHLY_OPERATING_BUDGET=28000
FR24_PROMOTIONAL_CREDITS=
```

`FR24_PROMOTIONAL_CREDITS` may be configured for display and projections, but standard-budget warnings must remain visible.

---

# 3. Credit model

The recurring endpoint is Live Flight Positions Light.

Current pricing:

```text
empty response: 1 credit
returned aircraft: 6 credits per aircraft
```

Do not incorrectly calculate a non-empty response as:

```text
1 base credit + 6 credits per aircraft
```

The documented model is:

```python
credits = 1 if returned_aircraft == 0 else 6 * returned_aircraft
```

With two clusters every five minutes over a 30-day month:

```text
12 cycles/hour
288 cycles/day
8,640 cycles/month
2 cluster requests/cycle
17,280 live-position requests/month
```

All-empty baseline:

```text
17,280 credits/month
```

This consumes:

```text
57.6% of the standard 30,000-credit allocation
```

Standard headroom:

```text
12,720 credits
```

Recommended 28,000-credit operating-budget headroom:

```text
10,720 credits
```

General cost formula:

```text
N = total live-position calls
p = fraction of calls that are non-empty
r = average aircraft returned per non-empty call

monthly credits = N × [1 + p × (6r - 1)]
```

For two clusters over 30 days:

```text
monthly credits = 17,280 × [1 + p × (6r - 1)]
```

Examples under the standard 30,000-credit allocation:

| Average aircraft in a non-empty call | Maximum approximate non-empty-call rate |
| -----------------------------------: | --------------------------------------: |
|                                  1.0 |                                   14.7% |
|                                  1.5 |                                    9.2% |
|                                  2.0 |                                    6.7% |

Examples under a temporary 60,000-credit allocation:

| Average aircraft in a non-empty call | Maximum approximate non-empty-call rate |
| -----------------------------------: | --------------------------------------: |
|                                  1.0 |                                   49.4% |
|                                  1.5 |                                   30.9% |
|                                  2.0 |                                   22.5% |

Implement these projections in code and tests. Do not bury them only in documentation.

The dashboard must distinguish:

```text
subscription cost
allocated credits
estimated credits consumed
provider-reported credits consumed
projected end-of-cycle credits
optional credit-equivalent value
```

Do not present `credits × US$0.0003` as the actual monthly bill. The actual base bill is the subscription price plus any purchased top-ups.

---

# 4. API transport

Base host:

```text
https://fr24api.flightradar24.com
```

Required headers:

```http
Accept: application/json
Accept-Version: v1
Authorization: Bearer <FR24_API_TOKEN>
```

Use the existing asynchronous HTTP stack if the application already uses `httpx.AsyncClient`.

The official Python SDK is currently synchronous. Do not introduce blocking SDK calls into the FastAPI event loop.

The official SDK may be used as:

* a contract reference;
* a source of response-field definitions;
* a source of validation behavior;
* a development comparison tool.

Prefer the project’s async provider adapter for production polling.

Requirements:

* one reusable HTTP client;
* connection pooling;
* explicit connect/read/write/pool timeouts;
* bounded retries;
* exponential backoff with jitter;
* respect `Retry-After`;
* no retries for invalid credentials or invalid requests;
* never log the bearer token;
* sanitize URLs and headers in exception logs;
* close the client cleanly on application shutdown.

Handle at least:

```text
400 invalid request
401 invalid token
402 payment or credit problem
404 missing resource
429 rate limit
5xx provider failure
timeout
DNS failure
invalid JSON
schema mismatch
```

A failed FR24 request must never count as an aircraft disappearance.

---

# 5. Recurring endpoint

Use:

```http
GET /api/live/flight-positions/light
```

Initial request parameters for each cluster:

```text
bounds={north},{south},{west},{east}
categories=T,H,N
altitude_ranges=-2000-10000
limit=20
```

Example request shape:

```http
GET /api/live/flight-positions/light
    ?bounds={north},{south},{west},{east}
    &categories=T,H,N
    &altitude_ranges=-2000-10000
    &limit=20
```

Ensure actual query encoding is correct and tested.

## Category policy

Initial included categories:

```text
T — general aviation
H — helicopters
N — non-categorized
```

Initial excluded categories:

```text
P — passenger
C — cargo
J — business jets
M — military and government
B — lighter than air
G — gliders
D — drones
V — ground vehicles
O — other
```

The purpose of `N` is to avoid losing unusual aircraft with incomplete FR24 classification.

The admin interface must allow an operator to change categories, but:

* default to `T,H,N`;
* explain each category;
* warn before removing `N`;
* warn before adding `P` or `C` because of likely credit impact;
* validate against the official category enum;
* store category changes in an audit log.

Do not use the category result as a legal determination that a flight is commercial, authorized, or suspicious.

## Altitude policy

Initial filter:

```text
-2000 to 10,000 feet MSL
```

The lower bound allows ground or below-reference reports.

Altitude is above mean sea level, not above terrain.

Allow per-cluster altitude ceilings because terrain and aviation patterns may differ.

Suggested configuration:

```env
FR24_DEFAULT_MIN_ALTITUDE_FT=-2000
FR24_DEFAULT_MAX_ALTITUDE_FT=10000
```

The UI should allow a carefully validated per-cluster override.

Do not automatically reduce altitude ceilings solely to save credits.

## Do not initially use these server filters

Although FR24 supports them, leave these disabled at first:

```text
aircraft
gspeed
data_sources
callsigns
registrations
flights
airports
routes
painted_as
operating_as
squawks
airspaces
```

Reasons:

* an aircraft-type allowlist risks excluding relevant unknown models;
* a speed filter may hide a relevant aircraft while cruising;
* a source filter may remove useful remote observations;
* callsigns and registrations may be missing or misleading;
* airport and route metadata is often absent for irregular traffic.

Implement configuration support only where it fits the existing provider design, but do not enable these filters by default.

Any future `gspeed` or `aircraft` filtering must first be evaluated in Shadow mode with a comparison report showing what would have been excluded.

---

# 6. Two explicit query clusters

The Explorer integration must initially support exactly two active clusters.

Do not silently choose the “largest” two clusters.

The operator must be able to configure which selected territories and conservation areas belong to each cluster.

Each cluster requires:

```text
stable internal ID
operator-facing name
enabled flag
member protected-area IDs
buffer distance
minimum altitude
maximum altitude
FR24 categories
calculated WGS84 bounds
optional manually overridden bounds
geometry/version hash
created_at
updated_at
last successful poll
last response count
last estimated credits
```

Suggested defaults:

```env
FR24_MAX_ACTIVE_CLUSTERS=2
FR24_CLUSTER_BUFFER_KM=15
```

## Cluster geometry

For each cluster:

1. load selected area geometries;
2. repair invalid geometries safely;
3. union member polygons;
4. buffer the union by 10–15 km;
5. calculate the smallest axis-aligned WGS84 rectangle accepted by FR24;
6. show the resulting rectangle on the admin map;
7. calculate rectangle area versus selected polygon area;
8. warn when excessive empty rectangle space is likely to include irrelevant traffic.

Perform metric buffering in an appropriate projected CRS or with a geodesic method. Do not buffer longitude/latitude degrees as if they were metres.

## Overlap

Calculate overlap between active cluster rectangles.

Warn when overlapping bounds could return and bill for the same aircraft twice.

Local deduplication is still required, but it does not recover API credits.

Do not automatically split a cluster without showing the effect on:

* request count;
* all-empty baseline;
* likely irrelevant-aircraft reduction;
* response-limit risk.

## Manual bounds

A manual bounds override may be useful during the PoC.

Requirements:

* validate north > south;
* validate coordinate ranges;
* display the rectangle before saving;
* show which selected polygons fall outside it;
* require explicit confirmation when any selected polygon is not covered;
* retain the automatically calculated bounds for comparison;
* audit changes.

---

# 7. Scheduling

Poll every:

```text
300 seconds
```

Suggested configuration:

```env
FR24_POLL_INTERVAL_SECONDS=300
```

With two clusters, do not create unnecessary concurrency.

Preferred cycle:

1. acquire a cross-process polling lock;
2. create one cycle ID;
3. poll cluster A;
4. wait a small configurable delay;
5. poll cluster B;
6. normalize and process observations;
7. close the cycle;
8. release the lock.

Suggested inter-cluster delay:

```env
FR24_INTER_CLUSTER_DELAY_SECONDS=2
```

Do not wait 150 seconds between clusters unless the plan provides a strong reason. The two results should represent approximately the same monitoring cycle.

Prevent:

* overlapping cycles;
* double polling by multiple workers;
* duplicate retries from scheduler and HTTP layers;
* polling before the previous cycle is complete.

Record each request separately.

---

# 8. Response model and normalization

Live Positions Light currently provides fields equivalent to:

```text
fr24_id
lat
lon
track
alt
gspeed
vspeed
squawk
timestamp
source
hex
callsign
```

Preserve the original provider payload only when consistent with FR24 storage rules.

Normalize into the existing provider-neutral observation model.

Required normalization behavior:

* parse timestamps as timezone-aware UTC;
* reject future timestamps beyond a small clock-skew allowance;
* reject stale observations according to existing freshness rules;
* validate latitude and longitude;
* reject NaN and infinity;
* normalize ICAO hex to lowercase while preserving display form where needed;
* trim callsigns;
* preserve FR24 `source`;
* preserve `fr24_id`;
* do not treat `fr24_id`, hex, callsign, and registration as interchangeable.

Deduplicate in this order:

```text
1. provider + fr24_id
2. provider + valid ICAO hex
3. provider-specific fallback only when unavoidable
```

When duplicate observations exist, retain the freshest valid timestamp.

Cross-provider deduplication may use ICAO hex, but observations from different providers must retain provenance.

---

# 9. Response-limit handling

Explorer returns at most 20 records.

Set:

```text
limit=20
```

A result containing fewer than 20 records can normally be treated as complete.

A result containing exactly 20 records is potentially truncated.

When:

```python
len(response.data) == 20
```

the application must:

1. mark the cluster result as `possibly_truncated`;
2. avoid advancing disappearance counters from that cluster result;
3. optionally call the count endpoint with identical filters;
4. record the count result and estimated extra credits;
5. surface a warning in the admin interface;
6. recommend tighter bounds, altitude, or category configuration.

Count endpoint:

```http
GET /api/live/flight-positions/count
```

Use the same:

```text
bounds
categories
altitude_ranges
gspeed, only when deliberately configured
other filters, only when deliberately configured
```

Do not call Count during every normal polling cycle.

Call Count only when:

* a Light result reaches 20 records;
* the operator manually requests calibration;
* a cluster configuration is being evaluated;
* a diagnostic procedure explicitly enables it.

Verify the current Count credit price before hardcoding an estimate.

A count failure must not invalidate the already received 20 records, but the cycle remains incomplete for disappearance logic.

---

# 10. Local geofencing and post-billing filtering

FR24 only supplies aircraft positions inside rectangular bounds.

All protected-area logic remains local.

Processing order:

1. validate and normalize provider records;
2. deduplicate within the provider;
3. use a spatial index to identify candidate polygons;
4. run exact point-in-polygon checks;
5. identify selected areas;
6. associate the aircraft with the active cluster;
7. apply local allowlists and classifications;
8. update the detection state machine;
9. enrich only when necessary.

Local filters may include:

* known scheduled-airline suppression;
* known legitimate aircraft;
* approved operators;
* known community flights;
* airports and airstrips;
* aircraft type;
* registration;
* callsign;
* altitude;
* speed;
* stationary behavior;
* source quality.

Clearly document that local filtering improves alert quality but does not reduce credits already charged by FR24.

---

# 11. Candidate enrichment

Do not use Live Positions Full for every five-minute poll.

When an aircraft first enters a selected protected-area polygon or becomes a detection candidate, call:

```http
GET /api/flight-summary/full
```

Use:

```text
flight_ids={fr24_id}
```

Prefer Flight Summary Full rather than Light for candidate enrichment because it provides additional fields such as category, IATA airport information, actual destination information, and richer flight details while currently costing only two credits per returned live flight.

Relevant Full summary fields include:

```text
fr24_id
flight
callsign
operating_as
painted_as
type
reg
orig_icao
orig_iata
dest_icao
dest_iata
dest_icao_actual
dest_iata_actual
category
hex
first_seen
last_seen
flight_ended
```

Rules:

* enrich only when `fr24_id` exists;
* cache enrichment for the current aircraft episode;
* do not enrich on every observation;
* do not repeat successful enrichment during the same episode;
* retry a failed Summary Full enrichment at most two additional times (three total attempts: +1 poll cycle, then +2 cycles) before terminal; success at any attempt persists as terminal;
* batch candidate IDs when possible;
* use no more than 10 `flight_ids` per request until the official API and sandbox conclusively confirm a higher limit.

There is a current discrepancy between some official documentation and SDK validation regarding maximum summary IDs. Use the conservative limit of 10.

Record:

```text
enrichment_attempted_at
enrichment_status
enrichment_source
enrichment_received_at
enrichment_delete_after
```

Do not allow enrichment failure to block detection.

---

# 12. Flight tracks

Endpoint:

```http
GET /api/flight-tracks?flight_id={fr24_id}
```

Current cost:

```text
40 credits per returned flight
```

Tracks are fetched exclusively through an authenticated manual action on an event — never automatically. Provide an authenticated manual flow:

* `GET /api/fr24/events/{event_id}/track` previews availability, estimated cost (40 credits per returned flight), and blocked reasons;
* `POST /api/fr24/events/{event_id}/track` with `{confirm:true}` fetches the track after validating the event has an FR24 ID, the track was not already fetched, and the budget policy has not paused FR24 at full exhaustion;
* missing ID, duplicate, or paused-budget return 409 (refusal names `pause_fr24`); provider failures surface as 502 without partial storage;
* a successful fetch persists the raw validated payload, requesting actor, and credited cost in `fr24_tracks` for as long as its event is retained (duplicates stay refused while that record exists; event-to-track `ON DELETE CASCADE`).

The retired `FR24_FETCH_TRACK_ON_EVENT` automation flag rejects any nonblank value at startup by design; no enable flag exists for manual Tracks.

---

# 13. Usage reporting and budget controls

Use:

```http
GET /api/usage?period=24h
GET /api/usage?period=7d
GET /api/usage?period=30d
```

Do not call Usage on every polling cycle.

Recommended:

```text
24h report: once daily
7d report: once daily or weekly
30d report: once daily
```

The official SDK currently recognizes:

```text
24h
7d
30d
1y
```

Implement local estimated credits immediately after every request.

Estimated endpoint costs must live in a centralized, tested table.

At minimum:

```text
live positions light:
    1 when empty
    6 × returned records otherwise

flight summary full:
    2 × returned live records

flight tracks:
    40 × returned flights
```

Count and Usage endpoint billing must be verified before assigning estimates.

Store:

```text
request timestamp
billing-cycle identifier
endpoint
cluster ID
HTTP outcome
records returned
estimated credits
reported credits when reconcilable
latency
retry count
possibly truncated
```

Dashboard metrics:

```text
credits used this billing cycle
estimated versus reported difference
credits remaining
average credits per live call
empty-response percentage
non-empty-response percentage
average aircraft per non-empty call
projected end-of-cycle credits
projected standard allocation overage
projected promotional allocation overage
credits per cluster
credits by endpoint
credits per useful candidate
```

Budget states:

```text
normal: below 70% of operating budget
warning: 70–85%
critical: 85–95%
hard limit: 95–100%
exhausted: at or above configured hard cap
```

Do not silently change polling cadence or filters at a threshold.

At warning or critical levels:

* notify the operator in the interface;
* optionally send one deduplicated system email;
* show recommended manual actions;
* stop nonessential automatic calls such as enrichment retries;
* keep core monitoring unchanged unless the operator decides otherwise.

At a configured hard cap:

* do not silently continue paid calls;
* do not silently disable monitoring;
* create a visible system incident;
* apply the explicitly configured budget policy.

Supported policy options may include:

```text
warn_only
pause_fr24
continue_until_provider_rejects
```

The shipped default is `pause_fr24`; deployments may explicitly select any supported policy.

---

# 14. Explorer viability dashboard

Add an Explorer-specific view for the two active clusters.

Show:

```text
standard allocation: 30,000
configured operating budget: 28,000
current promotional allocation, when configured
all-empty monthly baseline
actual empty-call rate
actual aircraft per non-empty call
projected monthly credits
remaining safe non-empty calls
days remaining in billing cycle
```

Include the formula:

```text
projected monthly credits =
credits used / elapsed fraction of billing cycle
```

Also calculate a traffic-based forecast:

```text
17,280 × [1 + p × (6r - 1)]
```

Do not display a green “viable” state based only on promotional credits.

Use statuses such as:

```text
Viable under standard allocation
Viable only under promotional allocation
Projected to exceed Explorer
Insufficient data
```

Require a minimum amount of monitoring data before making a confident projection.

Suggested minimum:

```text
72 hours
```

---

# 15. Optional comparison mode

Retain free providers for coverage comparison.

During Shadow mode, record:

```text
FR24-only aircraft
free-provider-only aircraft
aircraft observed by both
position freshness by provider
low-altitude observations by provider
inside-polygon observations by provider
```

Comparison mode must not alter FR24 credit use.

Do not require every provider to observe an aircraft before treating the FR24 observation as valid.

For disappearance detection, preserve the application’s existing provider-health semantics. A provider outage or incomplete response must never be interpreted as aircraft disappearance.

---

# 16. Five-minute detection implications

Do not casually change existing alert semantics, but audit them against the new polling interval.

At a five-minute interval:

```text
three consecutive observations span approximately 10 minutes
three missing cycles span approximately 15 minutes
```

The plan must explain how existing stop and disappearance logic behaves at 300-second polling.

For probable stop, the existing design should generally require:

* at least three qualifying observations;
* all inside a selected polygon;
* low speed or ground indication;
* limited displacement;
* sufficient elapsed wall-clock time;
* no high-confidence scheduled-airline classification;
* acceptable source quality.

Do not let estimated positions independently prove a landing or stop.

For disappearance:

* only successful complete coverage cycles count;
* possibly truncated responses do not count;
* failed requests do not count;
* stale or invalid responses do not count;
* an aircraft absent from only one overlapping query must not be considered missing;
* all enabled-provider semantics must remain explicit.

If the current detector encodes assumptions tied to a shorter poll interval, identify them in Stage 1 and propose the smallest safe correction.

---

# 17. FR24 data retention

All data obtained through FR24 must be permanently deleted no later than 30 days after first receipt unless a different written agreement exists.

Apply retention to:

* raw positions;
* normalized FR24 telemetry;
* Flight Summary payloads;
* Flight Track payloads;
* FR24-derived registration and type metadata;
* FR24-derived origin/destination fields;
* cached provider responses;
* logs that contain FR24 data.

Apply explicit provenance:

* `events.fr24_received_at` for FR24 receipt time;
* `events.occurred_at` as the cutoff for FR24 event cleanup;
* `fr24_tracks.created_at` for track audit time;
* `aircraft_state.updated_at` for outside-state cleanup;
* `fr24_tracks` rows cascade on event deletion (`ON DELETE CASCADE`).

No `fr24_delete_after` column exists. Cleanup runs from the coverage cycle when `FR24_AUTO_DELETE_ENABLED=true` (daily sweep, idempotent and transaction-safe, logged without reproducing telemetry, testable with a controlled clock).

The plan must distinguish:

```text
FR24-derived data
locally generated event classifications
human review labels
protected-area data
system audit metadata
```

Do not assume inserting FR24 data into an event makes it exempt from the 30-day limit.

Use the official sandbox for schema tests. The sandbox returns static schema-compatible data without consuming production credits.

---

# 18. Configuration

Proposed defaults:

```env
FR24_ENABLED=false
FR24_API_TOKEN=

FR24_PLAN=explorer
FR24_PLAN_MONTHLY_CREDITS=30000
FR24_MONTHLY_OPERATING_BUDGET=28000
FR24_PROMOTIONAL_CREDITS=
FR24_BUDGET_POLICY=pause_fr24

FR24_POLL_INTERVAL_SECONDS=300
FR24_INTER_CLUSTER_DELAY_SECONDS=2
FR24_MAX_ACTIVE_CLUSTERS=2
FR24_RESPONSE_LIMIT=20

FR24_DEFAULT_CATEGORIES=T,H,N
FR24_DEFAULT_MIN_ALTITUDE_FT=-2000
FR24_DEFAULT_MAX_ALTITUDE_FT=10000
FR24_CLUSTER_BUFFER_KM=15

FR24_FETCH_SUMMARY_ON_ENTRY=true
FR24_SUMMARY_VARIANT=full
FR24_USAGE_SYNC_ENABLED=true
FR24_RETENTION_DAYS=29
FR24_AUTO_DELETE_ENABLED=false
```

Follow the project’s existing configuration precedence rules.

Environment-provided secrets and locked environment settings must not be exposed or overwritten from the UI.

The API token must:

* be encrypted when stored through the UI;
* never be returned to the frontend;
* never appear in logs;
* never appear in health-check output;
* never be included in exception messages.

---

# 19. Admin interface

Add or refine authenticated controls for:

* FR24 enabled status;
* token configured/missing state;
* connection test;
* sandbox versus production;
* plan type;
* standard and promotional credit allocations;
* operating budget;
* billing-cycle start date;
* two active clusters;
* cluster member areas;
* cluster map preview;
* bounds;
* buffer;
* altitude range;
* categories;
* projected all-empty baseline;
* projected monthly credit use;
* current usage;
* truncation warnings;
* FR24 events — indefinite while `FR24_AUTO_DELETE_ENABLED=false`, otherwise `min(FR24_RETENTION_DAYS, 29)`;
* FR24 outside aircraft state — indefinite while auto-delete off, otherwise `STATE_RETENTION_DAYS`;
* free-provider outside aircraft state — always `STATE_RETENTION_DAYS` (independent of auto-delete);
* last successful poll;
* last provider error.

Connection test must not perform an unnecessarily expensive broad live query.

Prefer:

* sandbox schema test; or
* a tightly bounded production test;
* clear display of estimated credit cost before running.

Do not display a raw token after it has been saved.

---

# 20. Database and migrations

During Stage 1, inspect the current schema before proposing names.

The implementation will likely need persistent structures for:

```text
FR24 cluster configuration
FR24 request usage
FR24 usage-report snapshots
candidate enrichment
retention metadata
cluster membership
configuration audit history
```

Requirements:

* migration-safe for existing installations;
* no destructive reset;
* indexes for billing cycle, request time, endpoint, and cluster;
* stable cluster identifiers;
* foreign keys where appropriate;
* no secret values in audit tables;
* rollback or safe-forward migration plan;
* backup instructions before migration.

Do not add a second database technology for this PoC.

---

# 21. Observability

Add structured logs and metrics without exposing sensitive information.

Required events:

```text
fr24.poll.started
fr24.poll.completed
fr24.poll.empty
fr24.poll.truncated
fr24.poll.failed
fr24.enrichment.completed
fr24.enrichment.failed
fr24.track.requested
fr24.usage.reconciled
fr24.budget.warning
fr24.retention.completed
```

Include:

```text
cycle_id
cluster_id
endpoint
record_count
estimated_credits
latency
attempt
outcome
```

Exclude:

```text
API token
Authorization header
complete raw payload
sensitive protected-area geometry
private email addresses unless already handled securely
```

Health status should distinguish:

```text
configured
authenticated
last successful live call
last successful usage sync
budget state
retention state
```

---

# 22. Testing requirements

Use the sandbox and deterministic fixtures.

Do not consume production credits in normal automated tests.

## Unit tests

Test:

* category validation;
* bounds serialization order: north, south, west, east;
* altitude-range serialization;
* Light request construction;
* headers;
* token redaction;
* response parsing;
* timestamp validation;
* coordinate validation;
* empty response costing one credit;
* non-empty response costing six credits per aircraft;
* monthly cost formulas;
* standard versus promotional viability;
* cluster overlap warnings;
* projected credit use;
* budget thresholds;
* retention timestamps;
* cleanup behavior;
* response-limit handling;
* summary batching at ten IDs;
* summary Full costing;
* track cost estimation.

## Provider tests

Fixtures must include:

* empty Light response;
* one small general-aviation aircraft;
* helicopter;
* uncategorized aircraft;
* invalid coordinates;
* stale observation;
* future timestamp;
* missing hex;
* missing callsign;
* exactly 20 records;
* malformed JSON;
* 401;
* 402;
* 429 with `Retry-After`;
* 500;
* timeout.

## Integration tests

Test:

* two-cluster polling cycle;
* lock preventing overlapping cycles;
* cluster A success and cluster B failure;
* both clusters empty;
* duplicate aircraft in overlapping clusters;
* candidate enrichment once per episode (successful/terminal) with bounded failed-call retries;
* enrichment failure not blocking detection;
* truncation not advancing disappearance;
* failed FR24 poll not advancing disappearance;
* UI-managed encrypted token;
* environment token precedence;
* billing-cycle projection;
* cleanup after min(FR24_RETENTION_DAYS, 29) / STATE_RETENTION_DAYS with cascade;
* existing non-FR24 providers still work.

## Sandbox tests

Add an explicitly invoked integration command for FR24’s sandbox.

Sandbox tests must:

* verify request headers;
* verify endpoint paths;
* validate current response schemas;
* consume no production credits;
* not run as an uncontrolled external dependency in every unit-test execution.

## Optional production smoke test

Production testing must require:

```env
RUN_FR24_LIVE_TESTS=1
```

Before running, print:

* endpoint;
* cluster bounds;
* filters;
* maximum expected credit exposure.

Never run broad production calls automatically in CI.

---

# 23. Documentation

Update:

* README;
* `.env.example`;
* deployment instructions;
* provider configuration;
* Explorer cost model;
* retention policy;
* admin workflow;
* troubleshooting;
* architecture diagram when appropriate.

Document explicitly:

* why Light is polled;
* why Summary Full is selective;
* why Tracks are manual;
* why Count is exceptional;
* why local filtering does not reduce credits;
* why `N` is included;
* why type and speed allowlists are disabled initially;
* why promotional credits are not the baseline;
* how to calculate Explorer viability.

Include the exact two-cluster monthly baseline:

```text
17,280 credits when every request is empty
```

---

# 24. Rollout

Implement the rollout as operational guidance.

## Phase A — Sandbox

Validate:

* authentication headers;
* request serialization;
* response models;
* error handling;
* no production credits.

## Phase B — Shadow, first 72 hours

Use:

```text
two clusters
five-minute interval
T,H,N
-2000 to 10000 ft
Light positions
no email
no automatic tracks
```

Measure:

* empty-response rate;
* aircraft per non-empty call;
* estimated credits;
* provider-reported credits;
* unique aircraft;
* low-altitude observations;
* FR24-only versus free-provider-only aircraft;
* truncation frequency.

## Phase C — Shadow, days 4–14

Enable selective Summary Full enrichment.

Review:

* categories;
* registrations;
* aircraft types;
* operators;
* legitimate routes;
* actual cost per useful candidate.

## Phase D — Review

Enable human labels:

```text
useful
noise
uncertain
authorized
```

Do not enable external alert emails until detection quality and provider continuity are acceptable.

## Phase E — Live

Enable email only after:

* standard-allocation projection is understood;
* retention cleanup works;
* false disappearance events are controlled;
* cluster bounds are accepted;
* operator explicitly changes the application phase.

---

# 25. Non-goals

Do not:

* remove free providers;
* make FR24 the only possible provider;
* query entire Brazilian states;
* use Live Positions Full every five minutes;
* call Count before every poll;
* download tracks automatically;
* implement a strict aircraft-type allowlist initially;
* implement a ground-speed filter initially;
* remove `N` without measured evidence;
* infer legality from aircraft category;
* alter alert thresholds without documenting the cadence impact;
* store FR24 data beyond 30 days unless the written-agreement exception applies;
* expose the FR24 token;
* rely on promotional credits for viability;
* silently change polling behavior to save credits;
* run production API tests automatically;
* rewrite unrelated application components.

---

# 26. Stage 1 deliverable

Return a plan with these exact sections:

```text
1. Current implementation assessment
2. Gaps against this specification
3. Proposed architecture
4. Exact endpoint and request strategy
5. Cluster-generation strategy
6. Scheduler and failure semantics
7. Credit accounting and budget controls
8. Database and migrations
9. Admin interface changes
10. Retention implementation
11. Tests
12. Documentation
13. Deployment and rollback
14. Files expected to change
15. Risks and mitigations
16. Open decisions requiring operator approval
```

For every proposed change, identify:

* why it is needed;
* where it belongs;
* how it affects existing behavior;
* migration impact;
* tests required;
* whether it consumes FR24 credits.

Highlight any contradiction between:

* this specification;
* the current repository;
* official FR24 documentation;
* the official SDK.

Do not silently resolve such contradictions.

Stop after producing the Stage 1 plan.

---

# 27. Stage 2 completion criteria

After approval and implementation, the task is complete only when:

1. two explicit Explorer clusters can be configured;
2. each is polled every five minutes;
3. recurring requests use Live Positions Light;
4. recurring server-side filters default to `T,H,N` and `-2000–10000 ft`;
5. passenger, cargo, and business-jet categories are excluded by default;
6. empty and non-empty credits are estimated correctly;
7. standard Explorer viability is visible;
8. 20-record responses are treated as potentially truncated;
9. Count is exceptional rather than routine;
10. candidate enrichment uses Summary Full once per episode (with bounded retries for failed calls);
11. Tracks are manual only;
12. FR24-derived data is deleted within min(FR24_RETENTION_DAYS, 29) / STATE_RETENTION_DAYS unless the written-agreement exception applies;
13. failed or incomplete calls never create disappearance evidence;
14. secrets remain protected;
15. existing providers continue working;
16. migrations preserve current installations;
17. tests cover costs, limits, failures, retention, and two-cluster scheduling;
18. all `AGENTS.md` validation commands pass;
19. documentation matches actual behavior;
20. the implementation report includes actual test results and known limitations.


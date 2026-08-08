# FR24 Explorer-plan integration — status and follow-ups

Working notes for continuing the Flightradar24 Explorer-plan integration
(spec: `FLIGHTRADAR_API.md`). The integration is **functionally complete and
merged to `main`** as of commit `5b1fb4d`. This file tracks what's still
open: real known limitations, one doc bug found in `AGENTS.md`, and the
context needed to pick any of it back up without re-deriving it.

## How this was built (for context on process, not just code)

- Two-stage protocol from `FLIGHTRADAR_API.md` itself: Stage 1 = plan only,
  no code, resolved open questions with the user + an Opus 5 consult;
  Stage 2 = implementation, approved via "proceed", then escalated to full
  autonomy via "run all autonomous, don't check with me".
- Senior/junior delegation: this assistant as senior, `mimo-cli`
  (`~/.mimocode/bin/mimo`) as junior implementer for chunks 1-4.
  **mimo-cli's providers (Together.ai, then Openrouter fallback) both hit
  credit/balance errors starting Chunk 5** — an external, unresolvable
  outage, not a code problem. Chunks 5-8 were implemented directly instead.
- Every chunk was diffed and sent to an Opus 5 agent
  (`subagent_type="pr-critical-reviewer"`, `model="opus"`) for critical
  review *before* committing. Findings were fixed and, for Chunk 7, the
  fixes were sent back for a second Opus pass to verify they were genuine
  and hadn't introduced new inaccuracies. This is the standing rule for any
  further chunks/follow-ups from this list — don't skip the pre-commit
  review step.
- Verification sequence before every commit: `uv run python -m pytest`,
  a ruff before/after diff via `git stash -u` (or `git stash push -u --
  <specific files>` if unrelated changes exist in the tree — see gotcha
  below), `make check`, `docker compose config --quiet`.

## Commits (chronological)

1. `e9e9adc` feat(fr24): add Explorer-plan config, schema, and credit-cost foundations
2. `3f6f0fa` feat(fr24): add cluster geometry and CRUD
3. `f692aeb` feat(fr24): add cost-controlled HTTP adapter, retire unfiltered legacy path
4. `f8f7016` feat(fr24): add two-cluster scheduler wired to existing detection
5. `fc2c6ca` feat(fr24): add admin API and admin UI for cluster management
6. `8ee7a98` feat(fr24): gate retention on operator-authorized indefinite retention
7. `5b1fb4d` docs(fr24): bring README/SPEC in sync with the actual Explorer-plan behavior

(`253ebf8` "Add MIT License" landed in between chunks 6 and 7 from outside
this session — unrelated, not part of the FR24 work.)

## Test results as of last full run

299 tests total, all passing. 131 are FR24-specific:

| File | Tests | Covers |
|---|---:|---|
| `tests/test_fr24_credits.py` | 18 | credit estimation, budget states, billing cycle id |
| `tests/test_fr24_clusters.py` | 29 | cluster bounds, geometry hash, overlap, validation |
| `tests/test_fr24_provider.py` | 43 | HTTP adapter, retry/backoff, timestamp parsing, legacy-path retirement |
| `tests/test_fr24_scheduler.py` | 20 | two-cluster polling, merge, truncation/Count, budget gating, usage sync |
| `tests/test_fr24_admin_api.py` | 17 | cluster CRUD API, validation, status/test endpoints |
| `tests/test_fr24_retention.py` | 4 | auto-delete on/off, `fr24_received_at` provenance |

`make check`, `node --check app/static/app.js`, and
`docker compose config --quiet` (validated with `--env-file` against
`.env.example`) all pass. Ruff: zero net-new findings vs. the pre-existing
47-error baseline (all pre-existing, mostly `UP017` datetime.UTC-alias
style nits unrelated to this feature).

## Spec completion criteria (FLIGHTRADAR_API.md sec. 27) — final status

Met: 1 (two clusters), 2 (5 min poll), 3 (Light for routine polling), 4
(default filters T,H,N / -2000-10000 ft), 5 (passenger/cargo/business-jet
excluded by default), 6 (credit estimation), 8 (20-record truncation
threshold), 9 (Count exceptional, throttled 1/hr/cluster), 10 (enrichment
once per episode, keyed on hex+episode_id), 13 (failed/incomplete calls
never advance disappearance), 14 (secrets protected), 15 (existing
providers unaffected), 16 (additive-only migrations), 17 (test coverage),
18 (AGENTS.md validation commands — with one caveat, see below), 19 (docs
now match code after two Opus review rounds).

**Partially met / deliberately deviated** — see "Known limitations" below
for 7, 11, 12.

## Known limitations (real, unresolved as of `5b1fb4d`)

Ordered roughly by how much they matter operationally.

### 1. Tracks endpoint is unimplemented, not "manual" (spec criterion 11)

`fetch_track()` exists at `app/providers/fr24.py:450` but **has zero
callers anywhere in the app** — no `/api/fr24/track*` route in
`app/main.py`, no button/UI in `app/static/app.js` or `index.html`, and the
`fr24_fetch_track_on_event` setting (`app/settings_store.py:111-113`,
default `False`, env `FR24_FETCH_TRACK_ON_EVENT`) is declared but never
read anywhere. Setting it to `true` currently does nothing.

**To fix:** decide on a UX (likely: a button on an event's detail page or
the FR24 tab that calls a new `POST /api/fr24/events/{event_id}/track` or
similar, gated behind `require_auth`, using the existing `fr24_id` already
stored via `AircraftObservation.fr24_id` / enrichment data). Track calls
are the most expensive endpoint (40 credits/aircraft, `app/fr24_credits.py:19`)
so this should stay strictly manual/on-demand, never automatic — matching
the spec's actual intent even though the setting name suggests
"on-event" automation. Consider whether `fr24_fetch_track_on_event` should
be repurposed, renamed, or removed once the real UX is decided.

### 2. No default hard budget ceiling (spec criterion 7-adjacent)

`fr24_budget_policy` defaults to `"warn_only"`
(`app/settings_store.py:69-73`, choices: `warn_only`, `pause_fr24`,
`continue_until_provider_rejects`). Behavior in
`app/fr24_scheduler.py:218-240`:

- 70%+ of `fr24_monthly_operating_budget`: enrichment and usage-sync are
  suppressed (`budget == "normal"` checks at lines 358/361).
- 85%+ / 95%+ (`critical`/`hard_limit` states, `app/fr24_credits.py:45-58`):
  logged only (`fr24.budget.warning`), no throttling.
- 100%+ (`exhausted`): routine Light polling is refused **only** if policy
  is `pause_fr24` (line 220). Under `warn_only` (the default) or
  `continue_until_provider_rejects`, polling continues indefinitely past
  budget with no automatic stop.

This is documented accurately now (README/SPEC, chunk 7), but if the
operator wants an actual spending ceiling by default, `FR24_BUDGET_POLICY`
needs to default to `pause_fr24` instead, or a settings-UI nudge should
recommend it. Currently nothing in the admin UI surfaces this choice
prominently — check `app/static/index.html` FR24 tab.

### 3. No shared lock between the FR24 loop and the free-provider loop (TOCTOU)

`app/fr24_scheduler.py` uses its own `asyncio.Lock()` (`fr24_lock`, line 44)
plus a distinct cross-process lock name `"fr24-poll"` (line 180, via
`exclusive_job_lock`). The free-provider grid in `app/main.py` uses
`"coverage-poll"` (line 220) — a completely separate lock. The two loops
can run concurrently against the same `aircraft_state` table.

`_free_grid_actively_tracking()` (`app/fr24_scheduler.py:68-93`, called at
line 334) is a **read-then-decide** check: it reads the current
`aircraft_state` row for an aircraft, and if a non-FR24 provider's claim
looks fresh, FR24 discards its own observation for that aircraft this
cycle. Between that read and the eventual write (`process_observation`,
line 353), the free-provider loop could concurrently update the same row.
Narrow window, not eliminated. Fixing this properly means either (a) a
single shared lock across both loops around the observation-merge step
(likely too coarse — free-grid runs on a much shorter/independent
schedule), or (b) a compare-and-swap style update at the database layer
keyed on a version/timestamp column.

### 4. Enrichment failures are terminal per episode, not retried with backoff

`_enrich_new_candidates()` (`app/fr24_scheduler.py:100-` ) keys attempts on
`(hex, episode_id)` via `get_fr24_enrichment`/`save_fr24_enrichment`. A
failed Summary Full call marks that episode `status="failed"` and never
retries for the life of the episode (this was a deliberate Chunk 4 fix to
bound retries, see git history on `f8f7016`/`fc2c6ca`) — but it means a
single transient failure permanently loses enrichment data for that
episode, rather than getting a bounded number of retries with backoff.
Low priority; current behavior is safe (fails closed) but not optimal.

### 5. Retention is two separate windows, easy to conflate

`FR24_AUTO_DELETE_ENABLED` (default `False`) gates both, but they are
**not the same duration**:

- FR24 **events**: `cleanup_provider_events("flightradar24", min(cfg.fr24_retention_days, 29))`
  — `app/main.py:255`. Default `fr24_retention_days` = 29
  (`app/config.py:103`).
- FR24 **aircraft_state**: `cleanup_stale_states(cfg.state_retention_days,
  exclude_provider=None if fr24_auto_delete else "flightradar24")` —
  `app/main.py:249-252`. Uses the *generic* `state_retention_days`, default
  14 (`app/config.py`), shared with every other provider.

Both are correctly gated now (this was Chunk 6's second, more severe fix —
originally only the events cleanup was gated, silently deleting FR24
aircraft_state 15 days sooner). Just remember there are two knobs if this
ever needs adjusting, not one.

### 6. `flightradar24` still silently accepted as a legacy `FLIGHT_PROVIDERS` value

Removed from the UI checkbox picker and its misleading warning (Chunk 7),
but `app/providers/providers.py` still recognizes `"flightradar24"` in
`PROVIDER_INFO`/`PROVIDER_CHOICES` and gracefully skips it with a logged
warning (`fetch_all()`, ~line 171-188) rather than rejecting it outright.
This is intentional — it's what protects an existing deployment's saved
settings from breaking — but it means the value is still technically
"valid" at the config layer even though docs call it unsupported. Fine as
is; just don't be surprised it's still there if grepping for it later.

## Doc/tooling bug found outside the FR24 feature itself

**`AGENTS.md`'s validation command `uv sync` silently drops `pytest` (and
any other dev-only tooling declared under `[project.optional-dependencies]
dev`).** `pytest` is an *extra*, not a `[dependency-groups]` entry, and
`uv sync` does not install extras by default — it needs
`uv sync --extra dev`. Discovered while running the AGENTS.md validation
suite verbatim during Chunk 8: plain `uv sync` uninstalled
`pytest`/`iniconfig`/`pluggy`/`pygments` from the venv, and the very next
`make check` would have failed with "No module named pytest" had it not
been caught. `ruff` happened to survive because it's resolved from outside
the project venv, not from `pyproject.toml` deps.

**Not fixed** — this is a pre-existing repo-wide `AGENTS.md` accuracy
issue, unrelated to FR24, out of scope for this feature branch. Worth a
one-line fix to `AGENTS.md`'s command block
(`uv sync` → `uv sync --extra dev`) next time anyone touches that file.

## Suggested next steps, roughly in priority order

1. Fix the `AGENTS.md` `uv sync` command (trivial, one line, high value —
   silently broke the local test env during this very session).
2. Decide the Tracks UX and wire up `fetch_track` (limitation 1) — this is
   the only spec criterion that's more than "deliberately deviated," it's
   a genuine gap between what the docs now say and what the product does.
3. Decide whether `FR24_BUDGET_POLICY` should default to `pause_fr24`
   (limitation 2) — a product/ops decision, not just code, since it
   affects whether the system can ever silently overspend the operator's
   FR24 budget.
4. If cross-loop races start showing up in practice (duplicate/flip-
   flopping `aircraft_state` rows), address limitation 3 with a proper
   locking or optimistic-concurrency strategy.
5. Everything else in "Known limitations" is lower priority / accepted
   trade-offs — revisit opportunistically.

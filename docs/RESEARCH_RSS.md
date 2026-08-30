# Issue #4 — RSS growth between poll cycles: leak-hunt evidence

**Date:** 2026-08-30 · **Branch:** `feat/rss-leak-hunt` (base bb7f99f) · **Result: NO leak found.**

## Method

1. **Static audit** of every module reachable from `polling_loop`,
   `run_coverage_cycle` / `_run_coverage_cycle_locked` (app/main.py),
   `fr24_polling_loop` / `_run_fr24_cycle_locked` (app/fr24_scheduler.py),
   app/providers/*, app/coverage.py, app/database.py, app/detection.py,
   app/emailer.py, app/settings_store.py.
2. **Dynamic evidence** (throwaway harness, run locally, not committed): drove
   100 synthetic free-provider coverage cycles and 60 synthetic FR24
   scheduler cycles against `httpx.MockTransport` (zero live network), with
   a fresh tmp SQLite DB, rotating aircraft hexes (~46 distinct) so any
   hex-keyed unbounded cache would grow. Measured per-cycle RSS
   (`/proc/self/statm`), tracemalloc snapshots at cycle 10 vs cycle 100, and
   `ru_maxrss`. Confirmed the pipeline was really exercised mid-run
   (aircraft_returned=4 on the free path, aircraft_returned=2 /
   estimated_credits=12 on the FR24 path — not silent skips).

## Static audit — suspect → verdict

| Suspect | Location | Verdict |
|---|---|---|
| `background_tasks` list | app/main.py:103 | Bounded — exactly 3 tasks appended once at lifespan startup (main.py:384-390), cancelled + `clear()`ed at shutdown (main.py:392-395). |
| `login_failures` dict | app/main.py:104, 226-231 | Not cycle-driven — only grows on failed logins (rate-limit window is 15 min, main.py:219-223). Entries are dropped on successful login; stale keys for never-authenticating IPs persist. Bounded by distinct client IPs; hardening candidate, not the reported growth. |
| `_last_count_calibration` dict | app/fr24_scheduler.py:52 | Bounded — keyed by FR24 cluster id, which lives in a DB table with a small row count. |
| `_last_usage_sync` | app/fr24_scheduler.py:48 | Single datetime, overwritten. |
| httpx client lifecycle | app/providers/providers.py:202-207, 238-239; app/fr24_scheduler.py:334-335 | Per-cycle (or per-region-call) `httpx.AsyncClient` inside `async with` — closed every cycle. No persistent/module-level client, no response body retained on module state. |
| In-memory accumulation keyed by hex | (searched app/ for module-level dicts/lists/caches) | None. `aircraft_state` is DB-backed (app/database.py:130) and evicted each coverage cycle by `cleanup_stale_states` (main.py:286-289 → database.py:1402). FR24 enrichment is DB-backed with bounded retry (fr24_scheduler.py:100-213, database.py fr24_enrichment). |
| DB connection handling | app/database.py:24-46 | Every operation opens, commits/rolls back, and closes its own connection (`db()` context manager). No connection cache, no shared connection retaining pages. |
| Logging handlers/queues | app/main.py:93-96 | `logging.basicConfig` with a stream handler only — no MemoryHandler/QueueHandler, no in-process log buffer. Audit logs live in SQLite, trimmed per cycle by `cleanup_logs` (main.py:292). |
| Caches | app/config.py:221 (`env_settings` `lru_cache`) | Singleton settings object — one instance for process lifetime. No other `lru_cache`/`functools.cache` in app/. |
| Per-cycle heavy geometry | app/coverage.py:19-91 | Runs only on boundary sync / area selection, not per poll cycle; all shapely objects are function-local. |

## Dynamic evidence — numbers

RSS after a 10-cycle warmup (Python allocator plateau), fresh tmp DB,
MockTransport-only:

| Path | Cycles | min→max RSS after warmup | Growth (final − min) | Rising steps in tail |
|---|---|---|---|---|
| Free-provider coverage cycle | 100 | 120.5 → 120.8 MB | **+0.25 MB over 90 cycles** | 0 / 89 |
| FR24 scheduler cycle | 60 | 121.9 → 122.0 MB | **+0.16 MB over 50 cycles** | 1 / 49 |

tracemalloc, cycle-10 snapshot vs end snapshot, `app/` frames only:

| Path | Total size diff | Dominant sites |
|---|---|---|
| Free path (10 → 100) | **+7.8 KB** | database.py:21 (sqlite Row / interned strings, avg 50 B), main.py:272 (uuid hex), detection.py log strings — flat plateau, not monotonic. |
| FR24 path (10 → 60) | **+5.8 KB** | fr24_credits.py:67 (module constants), database.py:21 — same pattern. |

`ru_maxrss` peak for the whole 160-cycle process: 494 MB (dominated by the
single import of FastAPI/shapely/pyproj, not per-cycle growth).

**Leak threshold applied:** >10 MB RSS growth or a monotonic tracemalloc
diff across cycles. Both paths are flat/sawtooth-returning: **NO LEAK**.

## Interpretation

Per-cycle RSS is flat at a few hundred KB of noise over 100 cycles. The
harness uses `httpx.MockTransport`, so real-transport allocations inside the
cycle body (TLS/session setup, connection-pool teardown in production httpx
clients) are not exercised — the numbers bound the application logic, not
httpx internals. Any real-world RSS growth observed in production is
therefore expected to come from outside the cycle body itself — most
plausibly (a) SQLite/WAL page cache growth over days, (b) the periodic
boundary-sync's multi-GB-peak geometry union (documented at coverage.py:34-38,
simplify-before-buffer), or (c) allocator fragmentation over very long
uptimes rather than a retained-Python-object leak.

## Draft comment for issue #4

> We audited the full poll-cycle call graph (free-provider coverage loop,
> FR24 scheduler, providers, detection, DB access) for module-level state
> that could grow per cycle, and drove 100 synthetic free-provider cycles +
> 60 synthetic FR24 cycles against mocked transports with rotating aircraft
> hexes. RSS was flat after warmup: +0.25 MB (free path) and +0.16 MB (FR24
> path) over the runs; tracemalloc diffs between cycle 10 and the final
> cycle were single-digit KB and non-monotonic. All httpx clients are
> created and closed per cycle; `aircraft_state`, enrichment, and logs are
> DB-backed with per-cycle pruning; no in-memory cache keyed by hex exists.
> Recommendation before closing: keep the 48-72 h production observation
> running via the watch script (added by the companion rss-watch PR —
> `scripts/rss_watch.sh` once merged), sampling RSS across several hundred
> real cycles. If production RSS still trends upward while the cycle body
> is proven flat, the next suspects are SQLite/WAL page-cache growth and
> the weekly boundary-sync geometry pass (coverage.py), not the polling
> loop.

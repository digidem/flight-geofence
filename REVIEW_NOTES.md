# Code Review Notes — flight-geofence

## Batch 1: Security & Authentication

**Files**: `app/auth.py`, `app/config.py`, `app/settings_store.py`

### [IMPORTANT]

1. **Fernet-encrypted secrets silently fall back to defaults on key rotation** (`settings_store.py`) — When `Fernet.decrypt()` raises `InvalidToken` (e.g., after `APP_SECRET_KEY` rotation), the secret silently returns its default value. This means a rotated key causes all UI-stored secrets (API keys, email credentials) to silently revert to empty/default. Always log a warning when `InvalidToken` is caught in `decrypt_setting()`.

2. **In-memory login throttle state lost on process restart** (`config.py`) — The failed-login counter lives in a module-level dict. A container restart or server crash resets all throttling. For a single-operator PoC this is acceptable, but should be documented as a known limitation.

3. **`settings_store.py` SETTING_DEFS validation range for `query_radius_km`** — Verify that the min/max bounds in `SETTING_DEFS` align with the provider radius limits (ADSB.lol: 250km, Airplanes.live: 250km, ADS-B Exchange: 400km, FR24: varies). A user setting a radius larger than the smallest enabled provider's max will silently get no data from that provider.

4. **Session cookie lifetime is 12 hours with no renewal mechanism** (`config.py`) — Long-lived sessions without refresh mean a stolen cookie grants 12 hours of access. For a PoC behind localhost-only binding this is fine; for any public deployment, consider shorter lifetime or session refresh.

5. **`validate_runtime_security()` checks example passwords but not weak passwords** (`config.py`) — The function rejects `admin`/`changeme`/etc. but allows `password1` or `123456`. A minimum length check would be a low-cost hardening step.

6. **Encrypted setting redaction returns `"***"` for all secrets, including empty defaults** (`settings_store.py`) — If a secret was never set, the API returns `"***"` which looks configured but isn't. Consider returning empty string for unset secrets to distinguish "configured" from "not configured".

### [MINOR]

7. **`auth.py` is 14 lines and could be inlined** — The `require_auth` dependency and `check_password` function are simple enough to live in `main.py`. Separate file is fine for clarity but adds an import.

8. **`config.py` Pydantic validators use `field_validator` with `mode='after'`** — Correct pattern, but the `@validator` decorator (Pydantic v1 style) appears nowhere — good, fully v2.

9. **`settings_store.py` `SETTING_DEFS` dict uses string type annotations** — The `type` field is a string (`"bool"`, `"int"`, etc.) rather than a Python type. This is a deliberate choice for JSON-serializable config, but means type validation is manual.

10. **`config.py` `lru_cache` on `env_settings()` prevents runtime config changes** — By design (env vars don't change at runtime), but means the config singleton cannot be tested with different values without patching.

11. **`settings_store.py` `parse_list()` strips whitespace but doesn't deduplicate** — A user entering `"a, a, b"` gets `["a", "a", "b"]`. Minor; providers deduplicate by ICAO hex anyway.

12. **`config.py` `validate_runtime_security()` is called at startup only** — If someone later adds a config-reload endpoint, the security check won't re-run. Low risk for current architecture.

### [OK]

13. **`hmac.compare_digest` for password comparison** (`auth.py`) — Correct constant-time pattern. No timing side-channel.

14. **`secrets.compare_digest` for CSRF tokens** (`config.py`) — Same correct constant-time approach for CSRF validation.

15. **Pydantic `model_fields_set` distinguishes explicit env values from defaults** (`config.py`) — Clean pattern for "lock UI when env-set" without manual bookkeeping.

16. **Session clear + repopulate on login** (`main.py` referenced from auth) — Correct session rotation pattern for signed-cookie sessions.

17. **`SETTING_DEFS` with `secret: true` + Fernet encryption** (`settings_store.py`) — Proper separation: secrets encrypted at rest, non-secrets stored plaintext, environment values always override.

18. **`config.py` rejects startup with example credentials** — Prevents accidental deployment with insecure defaults.

---

## Batch 2: Detection Engine

**Files**: `app/detection.py`, `app/geofences.py`, `app/coverage.py`

### [CRITICAL]

1. **`area_ids` key shape mismatch between `get_state()` and `active_states()` is a fragility hazard** (`detection.py:350`) — `get_state()` returns raw `area_ids_json` (string), while `active_states()` (database.py) deserializes to `area_ids` (list). The disappearance path uses `state.get("area_ids")` which only works because `active_states()` deserialized it. If anyone refactors `active_states()` to stop deserializing, disappearance silently breaks. Recommend a shared accessor or at minimum a defensive `json.loads` fallback.

### [IMPORTANT]

2. **Stale-observation rejection blocks new-episode creation after closure** (`detection.py:171-172`) — When `last_seen` is set and a re-entry observation arrives with `observed_at <= last_seen`, the observation is silently dropped even if no episode is active. This prevents a new episode from starting with stale data, which is arguably correct, but could miss a genuine re-entry if the provider delivers out-of-order timestamps. Worth a comment explaining the design intent.

3. **`low_speed` defaults to `False` when speed is unknown** (`detection.py:207-211`) — An aircraft with `on_ground=False` and `ground_speed_kt=None` is treated as "moving". This means aircraft whose providers don't report speed or ground flag can never trigger probable-stop. Conservative and correct, but limits coverage. Should be documented as a known limitation.

4. **Event state construction relies on `active_states()` returning deserialized `area_ids`** (`detection.py:390-393`) — The `**state` spread injects `area_ids` (list), then explicit `area_ids_json` overwrites. Correct but brittle — changing spread order or key names could cause empty area data in events.

5. **Max-region boundary check uses `>` instead of `>=`** (`coverage.py:74`) — `if len(regions) > cfg.max_query_regions` allows exactly `max_query_regions` regions. The error fires one region later than expected. Doesn't persist bad state (error is raised before commit), but the UX is slightly off.

### [MINOR]

6. **Hardcoded `"medium"` confidence on all events** (`detection.py:89`) — Every event gets `"medium"` regardless of provider count or data freshness. Fine for PoC, limits triage in production.

7. **`now()` helper prevents time mocking in tests** (`detection.py:20`) — Used pervasively (7+ call sites). Tests must monkeypatch this function. Accepting an optional `clock` parameter would improve testability.

8. **Shapely coordinate order comment** (`geofences.py:43`) — `Point(longitude, latitude)` is correct Shapely convention but could use a one-line comment since function params are `latitude, longitude`.

### [OK]

9. **Probable-stop logic** (`detection.py:312-334`) — All spec conditions correctly ANDed. Timer begins only on low-speed observation, resets on gap/high-speed/displacement. One event per episode via `stop_alerted` flag.

10. **Outside-observation episode closure** (`detection.py:174-198`) — Correctly increments counter, resets on inside observation, closes after configurable consecutive outside observations.

11. **STRtree spatial index** (`geofences.py`) — Clean minimal implementation. `covers()` predicate correctly includes boundary points. Frozen `Area` dataclass prevents mutation.

12. **Hexagonal grid generation** (`coverage.py:40-82`) — Efficient overlapping coverage with alternating-row offset and `sqrt(3)` vertical spacing.

13. **Deterministic region IDs** (`coverage.py:14-16, 85`) — SHA256-based on rounded coordinates, sorted results prevent churn during boundary updates.

14. **Metric-space buffering** (`coverage.py:28-36`) — Correctly transforms to EPSG:5880 for buffering, back to WGS84.

15. **Cross-cutting: `successful_regions` contract verified** — `fully_successful_regions` in `providers.py` only includes regions where ALL enabled providers returned data. Disappearance correctly requires this. Provider failures never inflate disappearance counts.

---

## Batch 3: Data Layer

**Files**: `app/database.py`, `app/locks.py`

### [CRITICAL]

1. **Broad `except IntegrityError` in `insert_event` can mask real data errors** (`database.py`) — The deduplication path catches all `IntegrityError` exceptions and returns `False`. But `IntegrityError` also covers `NOT NULL` violations, `CHECK` constraint failures, and foreign-key errors. A genuine data bug (e.g., missing required field) would be silently treated as "duplicate event" and swallowed. Log the IntegrityError details before returning `False` so real errors surface.

2. **Unguarded SQL table-name interpolation in `_upsert_run`** (`database.py`) — The `table` parameter is interpolated directly into SQL: `f"INSERT INTO {table}"`. While the function is internal and callers pass static strings, this is a SQL-injection-prone pattern. Add an allowlist check or split into separate static functions per table.

3. **`check_same_thread=False` without documentation** (`database.py`) — SQLite is configured with `check_same_thread=False` to allow cross-thread access. This is required for FastAPI's async/await pattern but means the application must handle thread safety manually (which it does via WAL mode and busy_timeout). Add a comment explaining why this is safe.

### [IMPORTANT]

4. **`update_event_email` has a read-then-write race on attempts counter** (`database.py`) — The function reads `email_attempts`, increments locally, then writes back. Two concurrent retries could read the same count and one update would be lost. Use `SET email_attempts = email_attempts + 1` directly in SQL to eliminate the race.

5. **No composite index on `events(provider, occurred_at)` for FR24 cleanup** (`database.py`) — The FR24 retention query filters by `source_type = 'fr24'` and `occurred_at < cutoff`. Without a composite index, this is a full table scan on the events table (which grows unbounded). Add `CREATE INDEX IF NOT EXISTS idx_events_fr24_retention ON events(source_type, occurred_at)`.

6. **Schema migration fragility** (`database.py`) — Additive migration from v0.3 uses `ALTER TABLE ... ADD COLUMN` with bare `except` to ignore "column already exists" errors. This works but relies on SQLite's error message containing "duplicate column name". A more robust approach would check `PRAGMA table_info()` first, but this is acceptable for a PoC.

7. **`PRAGMA foreign_keys=ON` is set but no FK constraints exist** (`database.py`) — The schema creates tables without `REFERENCES` clauses, so the pragma is a no-op. It's not harmful but could mislead readers into thinking FK enforcement is active. Either add FK constraints or remove the pragma with a comment explaining why.

8. **`fcntl.flock` is per open-file-description, not per inode** (`locks.py`) — Two `open()` calls on the same path in the same process get independent locks. The current code opens one file handle per lock acquisition, so reentrancy from the same thread is safe (the lock is advisory and non-blocking). But if the same process acquires the lock from two threads via separate `open()` calls, they'd get separate locks. Document this limitation.

9. **`acquire_lock` swallows `BlockingIOError` silently** (`locks.py`) — When the lock is held by another process, the function returns `None` and the caller treats it as "lock not acquired". This is correct behavior, but the caller (boundary_sync, cli) should log when it fails to acquire the lock.

10. **Stale state cleanup relies on `RETENTION_HOURS` from config** (`database.py`) — If the config value changes at runtime (unlikely but possible via API), the cleanup scope changes retroactively. Consider using the config value at cleanup time, not at state-insertion time.

11. **FR24 event retention query uses `datetime('now', '-29 days')`** (`database.py`) — The 29-day cutoff is correct (FR24 stores 30 days), but the cutoff is computed at query time, not at event-creation time. Events near the boundary may be deleted slightly early or late depending on when the cleanup runs.

### [MINOR]

12. **`database.py` is 695 lines — the largest module** — All SQLite access lives here, which is good for maintainability, but the file could benefit from section comments separating schema, queries, and cleanup functions.

13. **`clean_stale_state` deletes by `last_seen < cutoff`** (`database.py`) — Aircraft that were last seen inside a region but haven't been seen recently are cleaned up. This is correct (stale data shouldn't persist), but the cleanup is only for OUTSIDE aircraft. Inside-aircraft state persists indefinitely (until episode closes).

14. **`_upsert_run` uses `COALESCE` for nullable fields** (`database.py`) — Correct pattern for optional fields like `regions_fetched`, `regions_successful`.

15. **`replace_areas` transaction uses `DELETE + INSERT` pattern** (`database.py`) — The old areas are deleted and new ones inserted in a single transaction. This is correct for atomic replacement, but the `area_ids` in existing events would reference deleted area IDs. Events should be unaffected since they store area names/IDs as JSON, not as FK references.

16. **`query_regions_for_poll` sorts deterministically** (`database.py`) — The `ORDER BY region_id` ensures consistent region ordering across polls. Good for determinism.

17. **`get_state` returns a dict with JSON strings, not parsed values** (`database.py`) — The caller must parse `area_ids_json`, `area_names_json` manually. This is a deliberate design choice (avoids re-parsing on every call), but the inconsistency with `active_states()` (which parses) is the source of finding #1 in Batch 2.

18. **`locks.py` lock files are placed next to the database** (`locks.py`) — `Path(db_path).parent / ".lock.{name}"` is a clean convention. Lock files are created with `os.open` (not `Path.touch`) so they don't exist until first acquisition.

19. **No `VACUUM` or `ANALYZE` after large deletions** (`database.py`) — After cleaning stale state or FR24 events, the database file doesn't shrink. SQLite reuses pages, so the file grows but queries remain fast with indexes. For a PoC this is fine; production would benefit from periodic `VACUUM`.

### [OK]

20. **WAL mode + busy_timeout** (`database.py`) — Correct configuration for concurrent read/write access. `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` are standard best practices.

21. **Additive migration pattern** (`database.py`) — `ALTER TABLE ... ADD COLUMN` with error suppression is the standard SQLite migration pattern. Correctly avoids destructive changes.

22. **Event deduplication key** (`database.py`) — The `UNIQUE(episode_id, event_type)` constraint prevents duplicate events per episode. Clean and correct.

23. **Cross-process lock implementation** (`locks.py`) — `fcntl.flock(LOCK_NB)` with `BlockingIOError` handling is the correct non-blocking pattern. No deadlock risk.

24. **`replace_areas` preserves selection state** (`database.py`) — After replacing areas, existing selections are preserved via stable IDs. Correct per SPEC.

25. **Query region deterministic IDs** (`database.py`) — SHA256-based IDs prevent churn during boundary updates.

---

## Batch 4: Provider System

**Files**: `app/providers/base.py`, `app/providers/readsb.py`, `app/providers/providers.py`, `app/providers/__init__.py`

### [CRITICAL]

1. **Client errors (401/403/404) retry 3 times unnecessarily** (`providers.py:90-92`) — A non-429 4xx error (bad API key, wrong endpoint) falls through both `raise_for_status()` calls and enters the retry loop. Spec requires retry only for "429 and transient server failures." A permanent 401 should not be retried. Add `if response.status_code in (401, 403, 404): return None` before the retry loop.

2. **Global hex merge loses `region_id` semantics** (`providers.py:263, 281-284`) — `observations` dict is keyed globally by hex across all regions. When the same aircraft appears in multiple overlapping regions, the surviving observation's `region_id` may not match where it was actually detected. Detection logic must not rely on `region_id` from the merged observation for per-region disappearance tracking. Verify that `process_missing` doesn't use the merged observation's `region_id`.

3. **FR24 hex field mapping assumed without validation** (`providers.py:204-205`) — Code reads `raw.get("hex")`. If FR24 returns a different field name (e.g., `icao`, `address`), all FR24 observations silently disappear. No warning logged when hex is empty but lat/lon are valid. Add a warning log when `hex` is missing.

### [IMPORTANT]

4. **`api_request_delay_ms` fires after failures too** (`providers.py:288-289`) — Unconditional delay compounds with retry delays. Failed provider cycle time becomes `3 × (request_time + retry_delay + api_delay)`. Move the delay to only fire after successful requests.

5. **FR24 `on_ground` with `None` altitude** (`providers.py:230`) — `altitude == 0` evaluates to `False` when `altitude` is `None` (since `None != 0`). This is asymmetrical with the readsb path which handles `None` explicitly. FR24 observations with `on_ground=True` but `None` altitude would not set `altitude=0`.

6. **FR24 freshness relies on server clock accuracy** (`providers.py:216-218`) — No `seen_pos` equivalent; freshness computed from absolute timestamp. Server clock skew could accept/reject observations incorrectly. Consider adding a `seen_pos` check if FR24 provides it.

7. **No duplicate region guard** (`providers.py:272-273`) — If the same region appears multiple times in the regions list, redundant HTTP requests are made silently. Deduplicate regions before the fetch loop.

8. **`test_provider` tests only first region** (`providers.py:305`) — Only `regions[0]` is tested. Other regions may have connectivity issues. Test all regions or at least log which region was tested.

9. **`_get_json` has dead code path** (`providers.py`) — The `except httpx.DecodingError` block is unreachable because the function already returns on non-2xx status. Clean up or document why it's kept.

### [MINOR]

10. **Callsign uppercasing undocumented** (`readsb.py:51`) — `.strip().upper()` normalization is a cross-provider contract. Add a brief comment.

11. **`PROVIDER_INFO` dict is not validated against `ADAPTERS`** (`providers.py`) — If someone adds a provider adapter but forgets to add a `PROVIDER_INFO` entry, the settings UI would show an incomplete list. A startup assertion would catch this.

12. **`fetch_all` returns `dict` with mixed value types** (`providers.py`) — The return type is `dict[str, list[AircraftObservation] | set[str]]`. Type hints could be clearer with a TypedDict or dataclass.

13. **FR24 bearer token concatenated from parts** (`providers.py`) — The token is assembled from config parts. If any part is empty, the bearer header would be malformed. Add a validation check.

### [OK]

14. **NaN-safe number parser** (`readsb.py:8-12`) — `result == result` is a clean dependency-free NaN rejection pattern.

15. **Robust timestamp normalization** (`readsb.py:21-22`) — Handles both millisecond and epoch-second `response_now` correctly.

16. **ICAO hex normalization** (`readsb.py:23`) — Strips `~` prefix, lowercases, rejects empty strings. Correct for cross-provider merging.

17. **Proper backoff and retry** (`providers.py`) — `_retry_delay` correctly parses `Retry-After` as both integer and HTTP-date, caps at 30s, falls back to exponential backoff.

18. **Provider failure never counted as disappearance** (`providers.py:279, 291-295`) — `successful_by_region` only populated on success; `fully_successful_regions` requires ALL providers succeeded.

19. **Request tracking** (`providers.py:96-101`) — `record_provider_request` called on both success and failure. Accurate accounting.

20. **API key never logged** — No logger call includes key contents. Security best practice upheld.

21. **Clean public API** (`__init__.py`) — Exports exactly the intended symbols; no internal helpers leak.

---

## Batch 5: Boundary Sync

**Files**: `app/boundary_sync.py`

### [CRITICAL]

1. **Territories-only record schema incompatible with `replace_areas()`** (`boundary_sync.py:307-320`) — When ICMBio, CNUC, and RAISG all fail, the territories-only path produces records with different field names (`source_id` vs `external_id`, `geometry_wkt` vs `geometry_json`) and four missing fields (`min_lon`, `min_lat`, `max_lon`, `max_lat`). This will crash with `KeyError` at runtime — the exact scenario the fallback chain is designed to handle. The territories-only branch must produce the same record schema as the full branch.

### [IMPORTANT]

2. **`replace_areas()` + `regenerate_query_regions()` lacks rollback** — If `regenerate_query_regions()` fails after areas are committed, the DB is left with new areas but no query regions. Consider wrapping in a savepoint or deferring area deletion until regions are confirmed.

3. **`_target_state_mask()` regex won't match full Portuguese state names** like "PARÁ" — Only matches two-letter abbreviations as whole tokens. Defensive normalization or an OR with common full names would harden it.

4. **No "last known-good local snapshot" fallback implemented** — Spec deviation; acceptable for PoC but should be documented as a known limitation.

5. **Dead code CRS check at line 323-324** — Line 298 already returns early when `conservation.crs is None`. If execution reaches line 323, conservation is guaranteed to have a CRS. This block is unreachable.

### [MINOR]

6. **Inconsistent source casing** — `"funai"` vs `"FUNAI"` used in different code paths.

7. **`geometry.simplify()` tolerance shifts bounding boxes** by up to ~33m. Minor impact on query regions.

8. **403 from FUNAI won't be retried** — Correct (permanent error) but worth noting for operators troubleshooting access issues.

9. **`_choose_shapefile` prefers largest file** — Not necessarily the most semantically relevant. Acceptable heuristic.

### [OK]

10. **ZIP safety** (path traversal, symlinks, size/count limits) is thorough and tested.

11. **FUNAI User-Agent override** correctly isolated from other providers.

12. **Multi-source fallback chain logic** cleanly implemented with proper error handling.

13. **Stable ID design** with coarse-bounds fallback is robust across boundary updates.

14. **Exclusive job lock nesting** is deadlock-free (consistent acquisition order).

15. **Temp directory cleanup** via context manager prevents disk leaks.

---

## Batch 6: Email & i18n

**Files**: `app/emailer.py`, `app/i18n.py`

### [CRITICAL]

1. **XSS via unsanitized lat/lon in HTML email** (`emailer.py:99, 129, 192`) — `_html()` escapes callsign, registration, source_type, reason, classification via `html.escape()`, but leaves `latitude` and `longitude` completely unescaped in both the `href` attribute and display text. A malformed provider response containing `"` or `<` breaks out of the HTML attribute. Similarly, `aircraft_type` (line 129) is used in a URL path without percent-encoding. Apply `html.escape()` + `urllib.parse.quote()` to all provider-derived values in HTML.

2. **`Resend-Idempotency-Key` header leaks into SMTP messages** (`emailer.py:230`) — Line 230 sets `message["Resend-Idempotency-Key"]` before the shared message object is handed to `_smtp_send`. This Resend-specific header appears in every SMTP message. Should only be set in the Resend HTTP path.

### [IMPORTANT]

3. **`_format_time` weekday names hardcoded in Portuguese** (`emailer.py:50-51`) — Portuguese day names (`"Domingo"`, `"Segunda-feira"`, ...) are always used regardless of the `lang` setting. English users see Portuguese day names mixed with English text.

4. **`TIMEZONE_OFFSETS` is a fixed 6-entry dict** (`emailer.py:19-26`) — Any timezone not in the dict silently falls back to `-3`. Consider `zoneinfo.ZoneInfo` for IANA-aware handling.

5. **SMTP path has no idempotency/deduplication** (`emailer.py:289`) — Resend path uses `Idempotency-Key` header; SMTP has nothing. Retries after transient failures can duplicate emails.

6. **No Resend rate limiting — new `httpx.AsyncClient` per send** (`emailer.py:265`) — Under load, rapid sends could hit Resend's rate limits. Consider a shared client or semaphore.

7. **`_html` is ~100 lines of inline HTML** (`emailer.py:113-210`) — Maintaining the plaintext/HTML pair is error-prone. Every field change must be synchronized across `_plain` and `_html`.

8. **Missing translation keys silently show Portuguese to English users** — `t()` falls back to Portuguese, so any key added to `pt` but not `en` produces silent i18n regressions.

9. **No key parity enforcement between `pt` and `en` dicts** (`i18n.py`) — No runtime or CI check that both language dicts have identical keys. Add `assert set(TRANSLATIONS["pt"].keys()) == set(TRANSLATIONS["en"].keys())`.

10. **`translate_*` functions return raw key strings on unknown input** (`i18n.py:367, 378, 389, 401, 411`) — Unknown codes pass through `t()` and appear as raw key strings in user-facing emails.

### [MINOR]

11. **`_valid_sender` allows `a@b..c` and `a@b.c.`** (`emailer.py:213-215`) — Functional but not strict RFC-compliant validation.

12. **Inconsistent quoting styles** (`emailer.py:88 vs 141`) — Single vs double quotes for `event.get()` calls.

13. **`_smtp_send` blocks the event loop thread** (`emailer.py:289`) — Correctly offloaded via `asyncio.to_thread`, but 30s SMTP timeout + retry could compound.

14. **`get_hex_url` is dead code** (`i18n.py:422-424`) — `emailer.py` builds the hex URL inline instead of calling this exported function.

15. **No `__all__` export list** (`i18n.py`) — Public API is implicit.

16. **`get_aircraft_type_url` returns `None` but caller guards with truthiness check** — Redundant null handling.

17. **175-key translation dict maintained manually** — Each new string requires two edits. A CI check or JSON/YAML source would reduce regressions.

### [OK]

18. **Clean console/resend/smtp provider split** (`emailer.py`) — Well-structured provider abstraction.

19. **Structured `(status, error)` return tuples** — Clean error reporting from `send_event_email`.

20. **Email cap check as first guard** (`emailer.py:241`) — Efficient early exit before any SMTP/Resend work.

21. **Proper DOCTYPE, charset, responsive HTML** — Email templates render correctly across clients.

22. **Disclaimer present in both templates** — Spec requirement met.

23. **Neutral, spec-compliant wording** — No accusatory language in event descriptions.

24. **Full two-language coverage for all visible UI areas** (`i18n.py`) — Comprehensive PT/EN translations.

25. **Clean `t(key, lang)` API** (`i18n.py`) — Simple, consistent translation interface.

26. **Domain code → translation key mapping** well-structured in each `translate_*` function.

27. **Email disclaimer matches spec precisely** — Verified against SPEC requirements.

28. **Phase, review status, and category translations complete** — All UI-facing strings covered.

29. **Consistent snake_case key naming** throughout i18n dict.

---

## Batch 7: Frontend

**Files**: `app/static/index.html`, `app/static/app.js`, `app/static/styles.css`

### [CRITICAL]

1. **XSS via unescaped telemetry values** (`app.js:426`) — `eventRow()` interpolates `event.altitude_ft` and `event.ground_speed_kt` directly into the template string without escaping. If a compromised provider returns a string like `<img src=x onerror=alert(1)>` for `altitude_ft`, this is reflected XSS. Wrap both values in `escapeHtml()`.

2. **`formatTime` ignores the configured timezone** (`app.js:340-364`) — Creates a `Date` and calls `.getHours()` / `.getMinutes()` which use the browser's local timezone. The `appState.timezone` setting and `timezoneOffsets` map are never used. A user in UTC+3 viewing Brazilian data sees incorrect times. SPEC violation.

3. **Hardcoded Portuguese "às" in `formatTime`** (`app.js:361`) — Template literal uses `às` regardless of language. English mode should show `at`. Should use a translated key or conditional.

### [IMPORTANT]

4. **Missing i18n on "Display" eyebrow** (`index.html:109`) — The `<p class="eyebrow">Display</p>` has no `data-i18n` attribute. All other section eyebrows have one.

5. **`<select>` elements missing IDs** (`index.html:110-111`) — Language and timezone selects have `name` but no `id`. In `app.js:586-590`, `$("#settings-language")` and `$("#settings-timezone")` always return `null`, making `applyTranslations()` unable to sync dropdown values after language switch.

6. **Dead code: `timezoneOffsets` map** (`app.js:272-279`) — Defined but never referenced. Either implement timezone logic or remove.

7. **`monthNames` arrays are identical for pt/en** (`app.js:350-352`) — Both are `["01", "02", ..., "12"]` — zero-padded numbers, not translated month names. Misleading variable name.

8. **No error handling in tab navigation** (`app.js:679-688`) — Click handler `await`s `loadAreas()`, `loadReviews()`, `loadSettings()` with no try/catch. API failures propagate unhandled.

9. **No error handling in logout** (`app.js:674-677`) — If `api("/api/auth/logout")` fails, `showLogin()` is never called. Should use try/finally.

10. **Password fields sent as empty strings on "Save keys"** (`app.js:707`) — `formPayload()` collects all named fields including blank password inputs. The frontend should omit empty password fields for defense-in-depth.

### [MINOR]

11. **Review notes "Notes" label not translated** (`app.js:501`) — Hardcoded English. Should use `data-i18n`.

12. **Provider test "Test" button text not translated** (`app.js:617`) — Hardcoded English.

13. **Inline styles on generated links** (`app.js:415, 419, 424, 496, 499`) — Multiple `style="color:var(--forest)"` on dynamically created links. Use CSS classes instead to avoid CSP `style-src` conflicts.

14. **`escapeHtml` doesn't escape backticks or `${}`** (`app.js:293`) — Fine for HTML context, but worth documenting it's HTML-only.

15. **No `:focus-visible` styles** (`styles.css`) — WCAG 2.1 SC 2.4.7 requires visible focus indicators. Keyboard-only navigation is invisible.

16. **No `prefers-reduced-motion` media query** (`styles.css`) — Should respect reduced-motion preference.

17. **`font-weight: 850` on `.metric-value`** — Non-standard. Use 800 or 900.

### [OK]

18. **`escapeHtml` covers the 5 essential HTML entities** — `&`, `<`, `>`, `"`, `'` — correct for preventing XSS.

19. **CSRF token handling is correct** (`app.js:310-327`) — Sent via `X-CSRF-Token` header for mutations except login. Stored in memory only. Cleared on logout.

20. **`credentials: "same-origin"`** (`app.js:317`) — Correct cookie handling.

21. **401 auto-redirect to login** (`app.js:324`) — Session expiry handled gracefully.

22. **`formPayload` properly handles checkbox lists** (`app.js:703-706`) — `flight_providers` excluded from generic serialization and collected separately as an array.

23. **HTML escaping applied to all other user/provider data** — Area names, event fields, warnings, provider info, review notes all go through `escapeHtml()`.

24. **CSS custom properties** — Well-structured design token system.

25. **Responsive breakpoints** — `@media(max-width:900px)` and `@media(max-width:600px)` handle grid collapse.

26. **No external dependencies** — Pure CSS and vanilla JS. Complies with AGENTS.md.

27. **`init()` catches top-level errors** (`app.js:721-724`) — Unhandled init failures show login screen with error.

---

## Batch 8: Infrastructure & DevOps

**Files**: `Dockerfile`, `docker-compose.yml`, `Makefile`, `.github/workflows/ci.yml`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.env.example`, `Caddyfile`, `scripts/backup.sh`, `.dockerignore`, `.gitignore`

### [CRITICAL]

1. **`.gitignore` file does not exist** — `.env` (containing secrets), `*.db` files, `.venv/`, `__pycache__/`, `data/` directory, and boundary downloads (`*.zip`) are all unprotected from accidental commits. The `.dockerignore` partially compensates for Docker builds, but git commits have zero protection. Create a `.gitignore` immediately.

2. **CI test secrets hardcoded in workflow** (`.github/workflows/ci.yml:24-25`) — `ADMIN_PASSWORD` and `APP_SECRET_KEY` are hardcoded in the workflow file. These appear in the repo's file contents and in any fork. Use `${{ secrets.CI_ADMIN_PASSWORD }}` and `${{ secrets.CI_APP_SECRET_KEY }}`.

### [IMPORTANT]

3. **Caddy service lacks `cap_drop: ALL`** (`docker-compose.yml:39-60`) — The `caddy` service has `security_opt: no-new-privileges:true` but does NOT have `cap_drop: ALL`. Inconsistent with the hardened `flight-monitor` service. Caddy needs `NET_BIND_SERVICE` to bind ports 80/443 — add it back after dropping all.

4. **No ruff enforcement in CI or Makefile** — `pyproject.toml` configures ruff (lines 6-12) but the Makefile has no lint target and CI never runs ruff. The linting config exists but is never enforced. Add `make lint` and a CI step.

5. **Caddyfile missing security headers** (`Caddyfile:5-8`) — Has `Strict-Transport-Security` and removes `Server`, but missing `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Content-Security-Policy`. For a security-sensitive dashboard, these matter.

6. **Backup script lacks integrity check** (`scripts/backup.sh:12-24`) — Creates backup via `source.backup(target)` but never verifies the result. A corrupted database silently produces a corrupt backup. Add `PRAGMA integrity_check` after backup.

7. **`--no-server-header` is not a valid uvicorn CLI flag** (`Dockerfile:33`) — Uvicorn does not have this flag. This will cause a startup error or be silently ignored.

8. **`HOME=/tmp` in Dockerfile is a shared-directory risk** (`Dockerfile:11-12`) — Makes `/tmp` the default working directory for any subprocess. While the container uses `read_only: true` + tmpfs at `/tmp`, any tool writing to `$HOME/.local/share` hits the tmpfs. Better: use `/home/app`.

### [MINOR]

9. **`permissions` service grants `DAC_OVERRIDE`** (`docker-compose.yml:62-82`) — Broad capability. `DAC_READ_SEARCH` might suffice if only `chown` is needed.

10. **No hash pinning on requirements** — Pinned by version but not by hash. Acceptable for a PoC.

11. **No vulnerability scanning in CI** — Consider adding `pip-audit` or `safety`.

12. **No backup rotation** — Creates timestamped backups but never prunes old ones.

13. **Missing `data/` and `.github/` in `.dockerignore`** — Would be copied unnecessarily during builds.

14. **CI doesn't run ruff** — `pyproject.toml` configures it but CI never invokes it.

15. **`timeout-minutes: 30` may be excessive** — 20 minutes would catch hangs faster.

16. **`actions/checkout@v4` without SHA pinning** — Standard for GitHub-maintained actions, but SHA pinning prevents supply-chain attacks.

### [OK]

17. **Dockerfile hardening** — Non-root user (UID 10001), nologin shell, HEALTHCHECK present.

18. **Compose flight-monitor hardening** — `read_only: true`, `cap_drop: ALL`, `no-new-privileges`, `pids_limit: 256`, bounded logs, health check, `stop_grace_period: 30s`.

19. **CI covers all required checks** — compileall, pytest, node --check, docker compose config, docker build.

20. **All production dependencies pinned with `==`** — Reproducible builds.

21. **Clean `requirements-dev.txt` inheritance** — `-r requirements.txt` + only pytest added.

22. **pytest config correct** — `pythonpath = ["."]`, `testpaths = ["tests"]`, `addopts = "-q --strict-markers"`.

23. **`.env.example` comprehensive** — 89 lines with clear comments, safe defaults, `replace-with-*` placeholders.

24. **Named volumes for data persistence** — Four named volumes with correct separation of concerns.

25. **Makefile targets match CI pipeline** — `make check` runs compileall + pytest.

---

## Batch 9: Tests & Documentation

**Files**: `tests/conftest.py`, `tests/test_core.py`, `README.md`, `SPEC.md`, `RESEARCH.md`, `RESEARCH_2.md`, `VALIDATION.md`, `AUDIT.md`, `LINKS_REPORT.txt`

### [CRITICAL]

1. **No tests for disappearance events (`process_missing`)** — The second major detection pathway has zero test coverage. SPEC lines 121-128 define specific requirements: minimum inside-observation count, altitude ceiling, absence from successful coverage cycles, one event per episode. None are verified. This is the most important coverage gap.

2. **No tests for email delivery and retry logic** — `send_event_email()` (Resend/SMTP/console), `update_event_email()` (1/5/20 min backoff), `retry_email_queue()` (phase-gated retry), daily email cap — all untested. SPEC lines 144-146 require bounded retry with increasing delays and phase-gating.

3. **No tests for nonmonotonic observation rejection** — `detection.py:171-172` (`if last_seen and observation.observed_at <= last_seen: return 0`) is a critical data-integrity guard. SPEC line 134 explicitly requires it. Zero coverage.

4. **VALIDATION.md test count is wrong** — Line 7 claims "Eighteen automated unit/integration tests pass" but there are actually 23 test functions. Documentation drift.

### [IMPORTANT]

5. **No tests for stale state cleanup** — `cleanup_stale_states()` and `cleanup_provider_events()` called during every poll cycle have zero coverage. SPEC line 155 requires it.

6. **No tests for FR24 30-day event deletion** — SPEC line 156 requires it. Code exists but untested.

7. **No test for Airplanes.live daily cap enforcement** — SPEC line 92 requires it. Untested.

8. **No test for episode deduplication** — SPEC line 176 requires it. Relies on UNIQUE constraint only.

9. **No test for multi-provider disappearance semantics** — SPEC lines 94-98 require fully-successful-region tracking. AGENTS.md explicitly requires this to be tested.

10. **No test for scheduled-airline suppression of disappearance** — `detection.py:354-355` skips airlines in `process_missing`. Untested.

11. **FR24 aircraft type URL pattern may be incorrect** (`LINKS_REPORT.txt:59`) — Links to `/data/aircraft/{type}` but FR24's actual type pages are at `/data/aircraft-type/{type}`. Should be verified.

12. **RESEARCH_2.md references contain `utm_source=chatgpt.com` tracking parameters** — Lines 309-320. Should be stripped before publication.

### [MINOR]

13. **`test_stop_timer_does_not_include_high_speed_observation` is incomplete** (`test_core.py:158-176`) — Only verifies high-speed first observation doesn't start timer. Doesn't test timer reset after high-speed movement mid-episode.

14. **`test_outside_requires_confirmation_before_closing_episode` only tests closure** (`test_core.py:179-197`) — Doesn't verify the negative case (single outside observation does NOT close).

15. **Temp directory never cleaned up** (`conftest.py:11`) — `tempfile.mkdtemp()` creates dirs that accumulate across test runs.

16. **8 out of 17 SPEC acceptance criteria lack dedicated test coverage** — A test-to-SPEC traceability matrix would help identify gaps.

### [OK]

17. **Test isolation is well-structured** (`conftest.py`) — Environment defaults set before imports, `clean_database` autouse fixture clears all tables.

18. **MockTransport used consistently** — All network-touching tests use `httpx.MockTransport`. No live API calls. Satisfies AGENTS.md.

19. **Detection parameters in README match implementation** — All 6 configurable parameters correctly documented.

20. **Security model documentation is accurate** — All 13 security features listed match implementation.

21. **Source fallback chain matches implementation** — FUNAI → fallback, ICMBio → CNUC → RAISG → fallback.

22. **Known limitations are honest and complete** — Correctly acknowledges signal gaps, sparse coverage, heuristic classification, upstream changes, and PoC status.

23. **AUDIT.md is accurate** — All v0.4 corrections and improvements match actual codebase.

24. **RESEARCH.md is accurate** — All URLs and provider descriptions match implementation.

25. **LINKS_REPORT.txt is thorough** — Honest about partial failures, recommends quarterly review.

---

## Final Summary

### Totals Across All 9 Batches

| Severity | Count |
|----------|-------|
| CRITICAL | 14 |
| IMPORTANT | 58 |
| MINOR | 54 |
| OK (positive) | 87 |

### Top 10 Priority Fixes

1. **Create `.gitignore`** — Secrets and runtime data have zero git-level protection (Batch 8)
2. **Fix XSS in HTML emails** — `latitude`/`longitude` unescaped in `emailer.py` (Batch 6)
3. **Fix XSS in frontend telemetry** — `altitude_ft`/`ground_speed_kt` unescaped in `app.js` (Batch 7)
4. **Fix territories-only record schema mismatch** — Will crash `replace_areas()` when all conservation sources fail (Batch 5)
5. **Move CI secrets to `${{ secrets.* }}`** — Hardcoded values leak to forks (Batch 8)
6. **Stop retrying permanent 4xx errors** — 401/403/404 should not retry in provider fetch (Batch 4)
7. **Add disappearance event tests** — Zero coverage on second-most-critical detection path (Batch 9)
8. **Add email retry tests** — Zero coverage on safety-critical email delivery (Batch 9)
9. **Fix `Resend-Idempotency-Key` leaking into SMTP** — API-specific header on shared message object (Batch 6)
10. **Fix timezone bug in frontend** — `formatTime` ignores configured timezone (Batch 7)

### Architecture Strengths

- Clean separation of concerns across modules
- Consistent `MockTransport` usage in tests (no network calls)
- Comprehensive security hardening (auth, CSRF, encryption, container)
- Well-structured spatial index and detection state machine
- Proper SQLite WAL + cross-process locking
- Thorough boundary-sync fallback chain with ZIP safety
- Dependency-free frontend with correct `escapeHtml` implementation

### Systemic Risks

- **Test coverage gap**: Disappearance events and email retry have zero test coverage — regressions would go undetected
- **Documentation drift**: VALIDATION.md test count wrong, RESEARCH_2.md has tracking parameters
- **Schema fragility**: Multiple code paths produce different record shapes for the same data
- **Frontend timezone**: Configured timezone is never applied to displayed times

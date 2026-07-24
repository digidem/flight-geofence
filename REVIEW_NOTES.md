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

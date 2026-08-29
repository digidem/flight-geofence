import json
import logging
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import env_settings

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def _connect() -> sqlite3.Connection:
    cfg = env_settings()
    Path(cfg.database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.database_path, timeout=60, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


@contextmanager
def db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_encrypted TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS areas (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                state TEXT,
                phase TEXT,
                selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0,1)),
                geometry_json TEXT NOT NULL,
                min_lon REAL NOT NULL,
                min_lat REAL NOT NULL,
                max_lon REAL NOT NULL,
                max_lat REAL NOT NULL,
                source_date TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_areas_selected ON areas(selected);
            CREATE INDEX IF NOT EXISTS idx_areas_category ON areas(category);
            CREATE INDEX IF NOT EXISTS idx_areas_name ON areas(name COLLATE NOCASE);

            CREATE TABLE IF NOT EXISTS query_regions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                radius_nm REAL NOT NULL,
                north REAL NOT NULL,
                south REAL NOT NULL,
                west REAL NOT NULL,
                east REAL NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dataset_syncs (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                success INTEGER NOT NULL DEFAULT 0 CHECK(success IN (0,1)),
                funai_source TEXT,
                cnuc_source TEXT,
                territories_count INTEGER NOT NULL DEFAULT 0,
                conservation_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS poll_runs (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                success INTEGER NOT NULL DEFAULT 0 CHECK(success IN (0,1)),
                phase TEXT NOT NULL,
                providers_json TEXT NOT NULL,
                regions_total INTEGER NOT NULL DEFAULT 0,
                requests_successful INTEGER NOT NULL DEFAULT 0,
                aircraft_returned INTEGER NOT NULL DEFAULT 0,
                candidate_aircraft INTEGER NOT NULL DEFAULT 0,
                events_created INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS aircraft_state (
                aircraft_hex TEXT PRIMARY KEY,
                callsign TEXT,
                registration TEXT,
                aircraft_type TEXT,
                airline_classification TEXT NOT NULL DEFAULT 'unknown_candidate',
                classification_reason TEXT,
                last_seen_at TEXT,
                last_provider TEXT,
                last_region_id TEXT,
                latitude REAL,
                longitude REAL,
                altitude_ft REAL,
                ground_speed_kt REAL,
                area_ids_json TEXT NOT NULL DEFAULT '[]',
                area_names_json TEXT NOT NULL DEFAULT '[]',
                inside_since TEXT,
                inside_observations INTEGER NOT NULL DEFAULT 0,
                outside_observations INTEGER NOT NULL DEFAULT 0,
                stationary_since TEXT,
                stationary_anchor_lat REAL,
                stationary_anchor_lon REAL,
                missing_cycles INTEGER NOT NULL DEFAULT 0,
                episode_id TEXT,
                stop_alerted INTEGER NOT NULL DEFAULT 0 CHECK(stop_alerted IN (0,1)),
                disappeared_alerted INTEGER NOT NULL DEFAULT 0 CHECK(disappeared_alerted IN (0,1)),
                updated_at TEXT NOT NULL,
                updated_seq INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_aircraft_state_updated ON aircraft_state(updated_at);

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                deduplication_key TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                aircraft_hex TEXT NOT NULL,
                callsign TEXT,
                registration TEXT,
                aircraft_type TEXT,
                airline_classification TEXT,
                area_ids_json TEXT NOT NULL,
                area_names_json TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                altitude_ft REAL,
                ground_speed_kt REAL,
                reason TEXT NOT NULL,
                confidence TEXT NOT NULL,
                provider TEXT NOT NULL,
                phase TEXT NOT NULL,
                email_status TEXT NOT NULL DEFAULT 'not_applicable',
                email_error TEXT,
                email_attempts INTEGER NOT NULL DEFAULT 0,
                email_next_attempt_at TEXT,
                emailed_at TEXT,
                review_status TEXT NOT NULL DEFAULT 'unreviewed',
                review_notes TEXT,
                reviewed_at TEXT,
                details_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_events_time ON events(occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_review ON events(review_status);
            CREATE INDEX IF NOT EXISTS idx_events_email_retry
              ON events(email_status,email_next_attempt_at);

            CREATE TABLE IF NOT EXISTS provider_requests (
                day TEXT NOT NULL,
                provider TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                successes INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(day,provider)
            );

            CREATE TABLE IF NOT EXISTS fr24_clusters (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                buffer_km REAL NOT NULL,
                min_altitude_ft REAL NOT NULL,
                max_altitude_ft REAL NOT NULL,
                categories_json TEXT NOT NULL,
                calc_north REAL,
                calc_south REAL,
                calc_west REAL,
                calc_east REAL,
                manual_north REAL,
                manual_south REAL,
                manual_west REAL,
                manual_east REAL,
                use_manual_bounds INTEGER NOT NULL DEFAULT 0 CHECK(use_manual_bounds IN (0,1)),
                geometry_version_hash TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_poll_at TEXT,
                last_response_count INTEGER,
                last_estimated_credits INTEGER,
                last_error TEXT
            );

            -- area_id intentionally has no FK to areas(id): a hard FK either
            -- cascade-deletes membership silently when replace_areas() churns
            -- an area's id (e.g. geometry-hash id after a boundary correction),
            -- or blocks the routine weekly boundary sync outright. Membership
            -- validity against currently-selected areas is checked and
            -- surfaced explicitly by the cluster geometry/regeneration code.
            CREATE TABLE IF NOT EXISTS fr24_cluster_areas (
                cluster_id TEXT NOT NULL REFERENCES fr24_clusters(id) ON DELETE CASCADE,
                area_id TEXT NOT NULL,
                PRIMARY KEY (cluster_id, area_id)
            );
            CREATE INDEX IF NOT EXISTS idx_fr24_cluster_areas_area ON fr24_cluster_areas(area_id);

            CREATE TABLE IF NOT EXISTS fr24_poll_runs (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                success INTEGER NOT NULL DEFAULT 0 CHECK(success IN (0,1)),
                clusters_json TEXT NOT NULL,
                clusters_successful INTEGER NOT NULL DEFAULT 0,
                aircraft_returned INTEGER NOT NULL DEFAULT 0,
                events_created INTEGER NOT NULL DEFAULT 0,
                estimated_credits INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_fr24_poll_runs_started ON fr24_poll_runs(started_at DESC);

            CREATE TABLE IF NOT EXISTS fr24_request_log (
                id TEXT PRIMARY KEY,
                requested_at TEXT NOT NULL,
                billing_cycle_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                cluster_id TEXT,
                http_outcome TEXT NOT NULL,
                records_returned INTEGER NOT NULL DEFAULT 0,
                estimated_credits INTEGER NOT NULL DEFAULT 0,
                reported_credits INTEGER,
                latency_ms INTEGER,
                retry_count INTEGER NOT NULL DEFAULT 0,
                possibly_truncated INTEGER NOT NULL DEFAULT 0 CHECK(possibly_truncated IN (0,1))
            );
            CREATE INDEX IF NOT EXISTS idx_fr24_request_log_cycle ON fr24_request_log(billing_cycle_id);
            CREATE INDEX IF NOT EXISTS idx_fr24_request_log_time ON fr24_request_log(requested_at DESC);
            CREATE INDEX IF NOT EXISTS idx_fr24_request_log_endpoint ON fr24_request_log(endpoint);
            CREATE INDEX IF NOT EXISTS idx_fr24_request_log_cluster ON fr24_request_log(cluster_id);

            CREATE TABLE IF NOT EXISTS fr24_enrichment (
                aircraft_hex TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                fr24_id TEXT,
                attempted_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                source TEXT,
                received_at TEXT,
                payload_json TEXT,
                fr24_received_at TEXT,
                PRIMARY KEY (aircraft_hex, episode_id)
            );

            CREATE TABLE IF NOT EXISTS fr24_tracks (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
                aircraft_hex TEXT NOT NULL,
                fr24_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                estimated_credits INTEGER NOT NULL CHECK(estimated_credits >= 0),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fr24_tracks_created_at ON fr24_tracks(created_at);
            -- Writers must store '[redacted]' for old_value/new_value whenever
            -- SETTING_DEFS[key].secret is true -- this table is plaintext and
            -- unlike app_settings is never Fernet-encrypted.
            CREATE TABLE IF NOT EXISTS config_audit_log (
                id TEXT PRIMARY KEY,
                changed_at TEXT NOT NULL,
                key TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                secret INTEGER NOT NULL DEFAULT 0 CHECK(secret IN (0,1)),
                changed_by TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_config_audit_log_key ON config_audit_log(key);

            -- Per-call log for the free providers. FR24 already has its own
            -- fr24_request_log (which additionally tracks credits); the /api/logs
            -- endpoint unions the two into one operator-facing timeline.
            CREATE TABLE IF NOT EXISTS provider_call_log (
                id TEXT PRIMARY KEY,
                requested_at TEXT NOT NULL,
                provider TEXT NOT NULL,
                region_id TEXT,
                endpoint TEXT,
                outcome TEXT NOT NULL,
                http_status INTEGER,
                latency_ms INTEGER,
                aircraft_returned INTEGER,
                error_message TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_provider_call_log_at
                ON provider_call_log(requested_at);

            -- Every normalized observation, whether or not it fell inside a
            -- selected area. aircraft_state only keeps the current row per
            -- aircraft and process_observation persists nothing at all for
            -- aircraft outside every selected area, so without this table a
            -- non-finding leaves no trace and cannot be reviewed after the fact.
            CREATE TABLE IF NOT EXISTS observation_log (
                id TEXT PRIMARY KEY,
                recorded_at TEXT NOT NULL,
                observed_at TEXT,
                provider TEXT NOT NULL,
                region_id TEXT,
                aircraft_hex TEXT NOT NULL,
                callsign TEXT,
                registration TEXT,
                aircraft_type TEXT,
                latitude REAL,
                longitude REAL,
                altitude_ft REAL,
                ground_speed_kt REAL,
                on_ground INTEGER NOT NULL DEFAULT 0 CHECK(on_ground IN (0,1)),
                inside INTEGER NOT NULL DEFAULT 0 CHECK(inside IN (0,1)),
                area_ids_json TEXT NOT NULL DEFAULT '[]',
                area_names_json TEXT NOT NULL DEFAULT '[]',
                classification TEXT,
                disposition TEXT NOT NULL,
                disposition_reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_observation_log_at
                ON observation_log(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_observation_log_hex
                ON observation_log(aircraft_hex);
            """
        )
        # Upgrade existing v0.3 volumes in place.
        _ensure_column(
            conn,
            "aircraft_state",
            "outside_observations INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(conn, "events", "email_attempts INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "events", "email_next_attempt_at TEXT")
        # Distinguishes "the scheduler woke up but deliberately did nothing"
        # (kill switch off, no clusters, budget pause) from a real failure.
        # Without it the dashboard renders benign skips as red "failed" runs.
        _ensure_column(
            conn,
            "fr24_poll_runs",
            "skipped INTEGER NOT NULL DEFAULT 0 CHECK(skipped IN (0,1))",
        )
        # Provenance only -- no deletion job reads this (see
        # fr24_auto_delete_enabled and its docstring above `_run_coverage_
        # cycle_locked`'s cleanup_provider_events call in main.py).
        _ensure_column(conn, "events", "fr24_received_at TEXT")
        # Enrichment retry accounting for bounded Summary Full backoff (see
        # _enrich_new_candidates): attempts counts scheduled logical calls
        # for the episode; next_retry_at schedules the next try in poll-cycle
        # units. Legacy rows backfill to attempts=0 / next_retry_at=NULL,
        # i.e. previously-failed episodes become immediately retry-eligible
        # once, while ok/empty rows stay terminal.
        _ensure_column(conn, "fr24_enrichment", "attempts INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "fr24_enrichment", "next_retry_at TEXT")
        # Cross-loop optimistic concurrency control for aircraft_state
        # writers (roadmap §6.5): every write through the cas_upsert_state
        # funnel is conditioned on the revision its caller read, closing the
        # FR24/free-grid lost-update window. Legacy volumes backfill to
        # sequence 0 so the first conditional update naturally succeeds.
        _ensure_column(conn, "aircraft_state", "updated_seq INTEGER NOT NULL DEFAULT 0")


def database_ok() -> bool:
    try:
        with db() as conn:
            result = conn.execute("PRAGMA quick_check").fetchone()[0]
        return result == "ok"
    except Exception:
        return False


def get_db_setting(key: str) -> str | None:
    with db() as conn:
        row = conn.execute(
            "SELECT value_encrypted FROM app_settings WHERE key=?", (key,)
        ).fetchone()
    return str(row[0]) if row else None


def set_db_setting(key: str, value_encrypted: str) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO app_settings(key,value_encrypted,updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET
              value_encrypted=excluded.value_encrypted,
              updated_at=excluded.updated_at
            """,
            (key, value_encrypted, utc_now_iso()),
        )


def delete_db_setting(key: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM app_settings WHERE key=?", (key,))


def replace_areas(
    records: list[dict[str, Any]],
    auto_select_all: bool,
    auto_select_new_when_all_selected: bool = True,
) -> None:
    now = utc_now_iso()
    with db() as conn:
        prior_rows = list(conn.execute("SELECT id,selected FROM areas"))
        prior = {str(row["id"]): int(row["selected"]) for row in prior_rows}
        first_sync = not prior
        prior_all_selected = bool(prior) and all(prior.values())
        incoming = {record["id"] for record in records}
        if incoming:
            placeholders = ",".join("?" for _ in incoming)
            conn.execute(
                f"DELETE FROM areas WHERE id NOT IN ({placeholders})", tuple(incoming)
            )
        else:
            conn.execute("DELETE FROM areas")

        for record in records:
            default_new = 1 if (
                (first_sync and auto_select_all)
                or (prior_all_selected and auto_select_new_when_all_selected)
            ) else 0
            selected = prior.get(record["id"], default_new)
            conn.execute(
                """
                INSERT INTO areas(
                    id,source,external_id,name,category,state,phase,selected,
                    geometry_json,min_lon,min_lat,max_lon,max_lat,source_date,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    source=excluded.source,
                    external_id=excluded.external_id,
                    name=excluded.name,
                    category=excluded.category,
                    state=excluded.state,
                    phase=excluded.phase,
                    geometry_json=excluded.geometry_json,
                    min_lon=excluded.min_lon,
                    min_lat=excluded.min_lat,
                    max_lon=excluded.max_lon,
                    max_lat=excluded.max_lat,
                    source_date=excluded.source_date,
                    updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["source"],
                    record["external_id"],
                    record["name"],
                    record["category"],
                    record.get("state"),
                    record.get("phase"),
                    selected,
                    record["geometry_json"],
                    record["min_lon"],
                    record["min_lat"],
                    record["max_lon"],
                    record["max_lat"],
                    record.get("source_date"),
                    now,
                ),
            )


def area_counts() -> dict[str, int]:
    with db() as conn:
        rows = conn.execute(
            "SELECT category,COUNT(*) total,SUM(selected) selected FROM areas GROUP BY category"
        ).fetchall()
    result = {
        "total": 0,
        "selected": 0,
        "indigenous_territory": 0,
        "conservation_unit": 0,
    }
    for row in rows:
        result["total"] += int(row["total"])
        result["selected"] += int(row["selected"] or 0)
        result[str(row["category"])] = int(row["total"])
    return result


def list_areas(
    search: str = "",
    category: str = "",
    selected: str = "",
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    where: list[str] = []
    params: list[Any] = []
    if search:
        where.append(
            "(name LIKE ? COLLATE NOCASE OR state LIKE ? COLLATE NOCASE "
            "OR phase LIKE ? COLLATE NOCASE)"
        )
        term = f"%{search[:200]}%"
        params.extend([term, term, term])
    if category in {"indigenous_territory", "conservation_unit"}:
        where.append("category=?")
        params.append(category)
    if selected in {"true", "false"}:
        where.append("selected=?")
        params.append(1 if selected == "true" else 0)
    clause = " WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM areas{clause}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id,name,category,state,phase,selected,source,source_date
            FROM areas{clause}
            ORDER BY category,name COLLATE NOCASE LIMIT ? OFFSET ?
            """,
            [*params, min(max(limit, 1), 500), max(offset, 0)],
        ).fetchall()
    return {"total": int(total), "items": [dict(row) for row in rows]}


def set_area_selection(ids: list[str], selected: bool) -> int:
    unique_ids = list(dict.fromkeys(ids))[:5000]
    if not unique_ids:
        return 0
    placeholders = ",".join("?" for _ in unique_ids)
    with db() as conn:
        cursor = conn.execute(
            f"UPDATE areas SET selected=?,updated_at=? WHERE id IN ({placeholders})",
            [1 if selected else 0, utc_now_iso(), *unique_ids],
        )
    return int(cursor.rowcount)


def bulk_area_selection(selected: bool, category: str = "", search: str = "") -> int:
    where: list[str] = []
    params: list[Any] = []
    if category in {"indigenous_territory", "conservation_unit"}:
        where.append("category=?")
        params.append(category)
    if search:
        where.append(
            "(name LIKE ? COLLATE NOCASE OR state LIKE ? COLLATE NOCASE "
            "OR phase LIKE ? COLLATE NOCASE)"
        )
        term = f"%{search[:200]}%"
        params.extend([term, term, term])
    clause = " WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        cursor = conn.execute(
            f"UPDATE areas SET selected=?,updated_at=?{clause}",
            [1 if selected else 0, utc_now_iso(), *params],
        )
    return int(cursor.rowcount)


def selected_area_ids() -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id FROM areas WHERE selected=1 ORDER BY id"
        ).fetchall()
    return [str(row[0]) for row in rows]


def selected_area_rows() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM areas WHERE selected=1 ORDER BY category,name COLLATE NOCASE"
        ).fetchall()
    return [dict(row) for row in rows]


def replace_query_regions(regions: list[dict[str, Any]]) -> None:
    with db() as conn:
        conn.execute("DELETE FROM query_regions")
        now = utc_now_iso()
        conn.executemany(
            """
            INSERT INTO query_regions(
              id,name,latitude,longitude,radius_nm,north,south,west,east,updated_at
            ) VALUES(:id,:name,:latitude,:longitude,:radius_nm,:north,:south,:west,:east,:updated_at)
            """,
            [{**region, "updated_at": now} for region in regions],
        )


def get_query_regions() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM query_regions ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def save_fr24_cluster(cluster: dict[str, Any]) -> None:
    cluster = dict(cluster)
    now = utc_now_iso()
    cluster.setdefault("created_at", now)
    cluster["updated_at"] = now
    columns = list(cluster)
    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(
        f"{column}=excluded.{column}" for column in columns if column not in ("id", "created_at")
    )
    with db() as conn:
        conn.execute(
            f"INSERT INTO fr24_clusters({','.join(columns)}) VALUES({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            [cluster[column] for column in columns],
        )


def get_fr24_cluster(cluster_id: str) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM fr24_clusters WHERE id=?", (cluster_id,)).fetchone()
    return dict(row) if row else None


def list_fr24_clusters() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM fr24_clusters ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]


def delete_fr24_cluster(cluster_id: str) -> bool:
    with db() as conn:
        cursor = conn.execute("DELETE FROM fr24_clusters WHERE id=?", (cluster_id,))
    return cursor.rowcount > 0


def set_fr24_cluster_areas(cluster_id: str, area_ids: list[str]) -> None:
    unique_ids = list(dict.fromkeys(area_ids))
    with db() as conn:
        conn.execute("DELETE FROM fr24_cluster_areas WHERE cluster_id=?", (cluster_id,))
        if unique_ids:
            conn.executemany(
                "INSERT INTO fr24_cluster_areas(cluster_id, area_id) VALUES(?,?)",
                [(cluster_id, area_id) for area_id in unique_ids],
            )


def fr24_cluster_area_ids(cluster_id: str) -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT area_id FROM fr24_cluster_areas WHERE cluster_id=? ORDER BY area_id",
            (cluster_id,),
        ).fetchall()
    return [str(row[0]) for row in rows]


def fr24_cluster_missing_area_ids(cluster_id: str) -> list[str]:
    """Member area ids that no longer exist in the areas table. There is no DB
    foreign key enforcing this (see Chunk 1 commit message for why), so this
    must be checked explicitly by callers such as cluster regeneration."""
    with db() as conn:
        rows = conn.execute(
            """
            SELECT fca.area_id FROM fr24_cluster_areas fca
            LEFT JOIN areas a ON a.id = fca.area_id
            WHERE fca.cluster_id=? AND a.id IS NULL
            ORDER BY fca.area_id
            """,
            (cluster_id,),
        ).fetchall()
    return [str(row[0]) for row in rows]


def areas_by_ids(ids: list[str]) -> list[dict[str, Any]]:
    unique_ids = list(dict.fromkeys(ids))
    if not unique_ids:
        return []
    placeholders = ",".join("?" for _ in unique_ids)
    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM areas WHERE id IN ({placeholders})", unique_ids
        ).fetchall()
    return [dict(row) for row in rows]


def record_fr24_request(
    billing_cycle_id: str,
    endpoint: str,
    cluster_id: str | None,
    http_outcome: str,
    records_returned: int,
    estimated_credits: int,
    latency_ms: int | None,
    retry_count: int,
    possibly_truncated: bool,
) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO fr24_request_log(
                id, requested_at, billing_cycle_id, endpoint, cluster_id,
                http_outcome, records_returned, estimated_credits, reported_credits,
                latency_ms, retry_count, possibly_truncated
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()),
                utc_now_iso(),
                billing_cycle_id,
                endpoint,
                cluster_id,
                http_outcome,
                records_returned,
                estimated_credits,
                None,
                latency_ms,
                retry_count,
                1 if possibly_truncated else 0,
            ),
        )


def credits_used_this_cycle(billing_cycle_id: str) -> int:
    with db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(estimated_credits),0) FROM fr24_request_log WHERE billing_cycle_id=?",
            (billing_cycle_id,),
        ).fetchone()
    return int(row[0])


def save_fr24_poll_run(run: dict[str, Any]) -> None:
    _upsert_run("fr24_poll_runs", run)


def latest_fr24_poll() -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM fr24_poll_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def update_fr24_cluster_telemetry(
    cluster_id: str,
    last_poll_at: str | None,
    last_response_count: int | None,
    last_estimated_credits: int | None,
    last_error: str | None,
) -> None:
    # Targeted column update only -- NOT a full-row save of a scheduler-
    # snapshotted cluster dict. A cycle can run for the duration of two
    # HTTP requests; overwriting the whole row with a start-of-cycle
    # snapshot would silently revert any config change (enabled, bounds,
    # categories) an operator makes concurrently through the admin API.
    with db() as conn:
        conn.execute(
            """
            UPDATE fr24_clusters SET
                last_poll_at=?, last_response_count=?, last_estimated_credits=?, last_error=?
            WHERE id=?
            """,
            (last_poll_at, last_response_count, last_estimated_credits, last_error, cluster_id),
        )


def get_fr24_enrichment(
    aircraft_hex: str,
    episode_id: str,
    *,
    max_attempts: int = 3,
    eligible_at: str | None = None,
) -> dict[str, Any] | None:
    """Row for one (aircraft_hex, episode_id) plus a SQL-computed
    retry_eligible flag: true ONLY for failed rows below the attempt bound
    whose next_retry_at is absent, unparseable, or due at eligible_at
    (None = evaluate against current UTC time inside SQLite). datetime()
    returning NULL classifies malformed stored values as eligible-now so a
    corrupted gate can never strand an episode forever."""
    with db() as conn:
        row = conn.execute(
            """
            SELECT *,
                CASE WHEN status='failed'
                      AND attempts < ?
                      AND (
                          next_retry_at IS NULL
                          OR datetime(next_retry_at) IS NULL
                          OR datetime(next_retry_at) <= COALESCE(datetime(?), datetime('now'))
                      )
                     THEN 1 ELSE 0 END AS retry_eligible
            FROM fr24_enrichment WHERE aircraft_hex=? AND episode_id=?
            """,
            (max_attempts, eligible_at, aircraft_hex, episode_id),
        ).fetchone()
    return dict(row) if row else None


def save_fr24_enrichment(
    aircraft_hex: str,
    episode_id: str,
    fr24_id: str | None,
    status: str,
    payload: dict[str, Any] | None,
    *,
    next_retry_at: str | None = None,
    max_attempts: int = 3,
) -> None:
    """Record one enrichment attempt. The incremented attempt count is
    derived from the STORED value inside this single UPSERT statement --
    never a Python-computed count that could be stale against a concurrent
    writer -- capped at max_attempts, with next_retry_at forced NULL at the
    bound. The WHERE clause refuses terminal rows (attempts >= max_attempts)
    outright, so a late/stale writer cannot resurrect an episode the system
    has given up on."""
    now = utc_now_iso()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO fr24_enrichment(
                aircraft_hex, episode_id, fr24_id, attempted_at, status, source,
                received_at, payload_json, fr24_received_at, attempts, next_retry_at
            ) VALUES(?,?,?,?,?,?,?,?,?,1,?)
            ON CONFLICT(aircraft_hex, episode_id) DO UPDATE SET
                fr24_id=excluded.fr24_id,
                attempted_at=excluded.attempted_at,
                status=excluded.status,
                source=excluded.source,
                received_at=excluded.received_at,
                payload_json=excluded.payload_json,
                fr24_received_at=excluded.fr24_received_at,
                attempts=MIN(fr24_enrichment.attempts + 1, ?),
                next_retry_at=CASE
                    WHEN fr24_enrichment.attempts + 1 >= ? THEN NULL
                    ELSE excluded.next_retry_at
                END
            WHERE fr24_enrichment.attempts < ?
            """,
            (
                aircraft_hex,
                episode_id,
                fr24_id,
                now,
                status,
                "flight-summary/full",
                now if payload else None,
                json.dumps(payload) if payload else None,
                now,
                next_retry_at,
                max_attempts,
                max_attempts,
                max_attempts,
            ),
        )


def save_fr24_track(
    *,
    event_id: str,
    aircraft_hex: str,
    fr24_id: str,
    payload: dict[str, Any] | list[Any],
    requested_by: str,
    estimated_credits: int,
) -> bool:
    """Persist one fetched track (raw validated provider envelope). Returns
    False when UNIQUE(event_id)/UNIQUE(fr24_id) or the events FK loses an
    insert race -- the caller maps that to 409/404 instead of spending the
    track cost a second time."""
    with db() as conn:
        try:
            conn.execute(
                """
                INSERT INTO fr24_tracks(
                    id, event_id, aircraft_hex, fr24_id, payload_json,
                    requested_by, estimated_credits, created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    event_id,
                    aircraft_hex,
                    fr24_id,
                    json.dumps(payload),
                    requested_by,
                    estimated_credits,
                    utc_now_iso(),
                ),
            )
        except sqlite3.IntegrityError:
            return False
    return True


def get_fr24_track_by_event(
    event_id: str, *, equivalent_fr24_id: str | None = None
) -> dict[str, Any] | None:
    """Prefer this event's own row; otherwise match by FR24 ID so two events
    resolving to the same flight can never trigger a second credit spend."""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM fr24_tracks WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is None and equivalent_fr24_id:
            row = conn.execute(
                "SELECT * FROM fr24_tracks WHERE fr24_id=? LIMIT 1",
                (equivalent_fr24_id,),
            ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["payload"] = json.loads(item.pop("payload_json"))
    return item


def record_config_audit(
    key: str, old_value: Any, new_value: Any, changed_by: str, secret: bool = False
) -> None:
    # Never trust the caller's `secret` flag alone for a known SETTING_DEFS
    # key -- deriving it here means a caller forgetting secret=True for
    # flightradar24_api_key/smtp_password/etc. still can't leak it in
    # cleartext. Deferred import: settings_store already imports this module.
    from .settings_store import SETTING_DEFS

    definition = SETTING_DEFS.get(key)
    is_secret = secret or bool(definition and definition.secret)
    with db() as conn:
        conn.execute(
            "INSERT INTO config_audit_log(id, changed_at, key, old_value, new_value, secret, changed_by) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                utc_now_iso(),
                key,
                "[redacted]" if is_secret else (None if old_value is None else str(old_value)),
                "[redacted]" if is_secret else (None if new_value is None else str(new_value)),
                1 if is_secret else 0,
                changed_by,
            ),
        )


def _upsert_run(table: str, run: dict[str, Any]) -> None:
    columns = list(run)
    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(f"{column}=excluded.{column}" for column in columns if column != "id")
    with db() as conn:
        conn.execute(
            f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            [run[column] for column in columns],
        )


def save_sync_run(run: dict[str, Any]) -> None:
    _upsert_run("dataset_syncs", run)


def latest_sync() -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM dataset_syncs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def save_poll_run(run: dict[str, Any]) -> None:
    _upsert_run("poll_runs", run)


def latest_poll() -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM poll_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_state(aircraft_hex: str) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM aircraft_state WHERE aircraft_hex=?", (aircraft_hex,)
        ).fetchone()
    return dict(row) if row else None


def _insert_aircraft_state(payload: dict[str, Any]) -> int:
    """Insert-on-absent attempt; a new row's revision starts at 1."""
    columns = list(payload)
    placeholders = ",".join("?" for _ in columns)
    with db() as conn:
        cursor = conn.execute(
            f"INSERT INTO aircraft_state({','.join(columns)}, updated_seq) "
            f"VALUES({placeholders}, 1) "
            "ON CONFLICT(aircraft_hex) DO NOTHING",
            [payload[column] for column in columns],
        )
    return int(cursor.rowcount)


def _cas_update_aircraft_state(payload: dict[str, Any], expected_seq: int) -> int:
    """Conditional update landing only while the row still sits at the
    revision its caller read. Single statement -- a crash cannot leave a
    partial row."""
    assignments = ",".join(f"{column}=?" for column in payload)
    with db() as conn:
        cursor = conn.execute(
            f"UPDATE aircraft_state SET {assignments}, updated_seq=updated_seq+1 "
            f"WHERE aircraft_hex=? AND updated_seq=?",
            [*payload.values(), payload["aircraft_hex"], expected_seq],
        )
    return int(cursor.rowcount)


def _unconditional_upsert_aircraft_state(
    payload: dict[str, Any], current_seq: int
) -> int:
    """Atomic last-writer-wins fallback, used only after the bounded CAS
    retry also conflicts. One statement; on conflict the row's CURRENT LIVE
    sequence is advanced inside the statement (updated_seq =
    aircraft_state.updated_seq + 1), never a value re-read earlier -- so a
    writer that raced the re-read cannot leave stale same-sequence snapshots
    able to re-pass the CAS guard afterwards."""
    columns = list(payload)
    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(
        f"{column}=excluded.{column}" for column in columns if column != "aircraft_hex"
    )
    with db() as conn:
        cursor = conn.execute(
            f"INSERT INTO aircraft_state({','.join(columns)}, updated_seq) "
            f"VALUES({placeholders}, ?) "
            f"ON CONFLICT(aircraft_hex) DO UPDATE SET {updates}, "
            "updated_seq=aircraft_state.updated_seq+1",
            [*[payload[column] for column in columns], current_seq + 1],
        )
    return int(cursor.rowcount)


def _newer_than(incoming_ts: str | None, committed_ts: str | None) -> bool:
    """Strict > rule on last_seen_at, mirroring _merge_observation: the
    committed state wins on equality and whenever either timestamp is
    missing or invalid."""
    try:
        incoming = datetime.fromisoformat(incoming_ts) if incoming_ts else None
        committed = datetime.fromisoformat(committed_ts) if committed_ts else None
    except ValueError:
        return False
    if incoming is None or committed is None:
        return False
    if incoming.tzinfo is None:
        incoming = incoming.replace(tzinfo=UTC)
    if committed.tzinfo is None:
        committed = committed.replace(tzinfo=UTC)
    return incoming > committed


def cas_upsert_state(state: dict[str, Any]) -> None:
    """Optimistic-concurrency write funnel for aircraft_state.

    Every detection-path writer lands here (detection.py's five upsert_state
    call sites all delegate), closing the cross-loop lost-update window in
    which process_missing()'s active_states() snapshot was unconditionally
    restored over a fresher free-grid observation. ``updated_seq`` present
    in the input means "update revision N"; absent means insert-only. On a
    lost race the payload is retried once against the re-read revision when
    its last_seen_at is strictly newer than the committed one; otherwise the
    committed -- fresher or equal, hence serialized -- outcome stands. Under
    pathological contention both conditional attempts may lose: that falls
    back to one warned, atomic last-writer-wins upsert -- never a deadlock,
    never a silent drop.
    """
    payload = dict(state)
    seq = payload.pop("updated_seq", None)
    aircraft_hex = payload["aircraft_hex"]
    if seq is None:
        payload.setdefault("updated_at", utc_now_iso())
        if _insert_aircraft_state(payload):
            return
    elif _cas_update_aircraft_state(payload, int(seq)):
        return

    # Lost the first race (or the row vanished mid-flight): resolve once.
    committed = get_state(aircraft_hex)
    if committed is not None and _newer_than(
        payload.get("last_seen_at"), committed.get("last_seen_at")
    ):
        if _cas_update_aircraft_state(payload, int(committed.get("updated_seq") or 0)):
            return
        # Second conflict under pathological contention: bounded fallback.
        committed = get_state(aircraft_hex)
        logger.warning(
            "aircraft_state.cas_conflict_fallback aircraft_hex=%s "
            "falling back to unconditional last-writer-wins upsert",
            aircraft_hex,
        )
        _unconditional_upsert_aircraft_state(
            payload, int(committed.get("updated_seq") or 0) if committed else 0
        )
        return
    if committed is None:
        # Deletion between read and retry converts the retry to insert-on-absent.
        if _insert_aircraft_state(payload):
            return
        logger.warning(
            "aircraft_state.cas_conflict_fallback aircraft_hex=%s "
            "insert race resolved by unconditional upsert",
            aircraft_hex,
        )
        committed = get_state(aircraft_hex)
        _unconditional_upsert_aircraft_state(
            payload, int(committed.get("updated_seq") or 0) if committed else 0
        )
    # else: the committed state is equal-or-fresher -- it already holds the
    # serialized outcome, so this stale writer yields without writing.


def upsert_state(state: dict[str, Any]) -> None:
    """Compatibility entry point -- every writer funnels through CAS."""
    cas_upsert_state(state)


def active_states() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM aircraft_state
            WHERE area_ids_json!='[]' OR missing_cycles>0
            ORDER BY updated_at DESC
            """
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["area_ids"] = json.loads(item.pop("area_ids_json"))
        item["area_names"] = json.loads(item.pop("area_names_json"))
        result.append(item)
    return result


_LOG_URL_RE = re.compile(r"https?://[^\s'\"]+")


def _scrub_log_message(message: str | None) -> str | None:
    """Provider errors quote the failing URL, and these providers put the
    region centre and radius in the path -- so the raw text would write
    protected-area geometry into the audit log. Keep the human-readable part,
    drop the URL."""
    if not message:
        return None
    return _LOG_URL_RE.sub("<url>", str(message))[:500].strip() or None


def record_provider_call(
    *,
    provider: str,
    region_id: str | None,
    endpoint: str | None,
    outcome: str,
    http_status: int | None = None,
    latency_ms: int | None = None,
    aircraft_returned: int | None = None,
    error_message: str | None = None,
) -> None:
    """One row per real HTTP attempt against a free provider. Never raises:
    losing a log row must not fail a poll cycle that otherwise succeeded."""
    try:
        with db() as conn:
            conn.execute(
                """
                INSERT INTO provider_call_log(
                    id, requested_at, provider, region_id, endpoint, outcome,
                    http_status, latency_ms, aircraft_returned, error_message
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    utc_now_iso(),
                    provider,
                    region_id,
                    endpoint,
                    outcome,
                    http_status,
                    latency_ms,
                    aircraft_returned,
                    _scrub_log_message(error_message),
                ),
            )
    except sqlite3.Error:
        logger.warning("provider call log insert failed", exc_info=True)


def record_observation_log(
    *,
    provider: str,
    region_id: str | None,
    aircraft_hex: str,
    callsign: str | None,
    registration: str | None,
    aircraft_type: str | None,
    latitude: float | None,
    longitude: float | None,
    altitude_ft: float | None,
    ground_speed_kt: float | None,
    on_ground: bool,
    observed_at: str | None,
    inside: bool,
    area_ids: list[str] | None,
    area_names: list[str] | None,
    classification: str | None,
    disposition: str,
    disposition_reason: str | None = None,
) -> None:
    """One row per normalized observation, inside a selected area or not.
    Never raises: detection must not fail because logging did."""
    try:
        with db() as conn:
            conn.execute(
                """
                INSERT INTO observation_log(
                    id, recorded_at, observed_at, provider, region_id, aircraft_hex,
                    callsign, registration, aircraft_type, latitude, longitude,
                    altitude_ft, ground_speed_kt, on_ground, inside,
                    area_ids_json, area_names_json, classification,
                    disposition, disposition_reason
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    utc_now_iso(),
                    observed_at,
                    provider,
                    region_id,
                    aircraft_hex,
                    callsign,
                    registration,
                    aircraft_type,
                    latitude,
                    longitude,
                    altitude_ft,
                    ground_speed_kt,
                    1 if on_ground else 0,
                    1 if inside else 0,
                    json.dumps(area_ids or []),
                    json.dumps(area_names or [], ensure_ascii=False),
                    classification,
                    disposition,
                    disposition_reason,
                ),
            )
    except sqlite3.Error:
        logger.warning("observation log insert failed", exc_info=True)


def query_logs(
    *,
    limit: int = 100,
    offset: int = 0,
    kind: str = "all",
    provider: str | None = None,
    aircraft_hex: str | None = None,
    inside_only: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Unified operator timeline: free-provider calls, FR24 calls, and
    observations, newest first. Returns (rows, total_matching)."""
    # "detection" answers "what did we actually see?" -- every observation plus
    # the calls that returned at least one aircraft, so detections logged before
    # per-aircraft logging existed still appear as a call row with a count.
    detections_only = kind == "detection"
    want_calls = kind in {"all", "call", "detection"} and not inside_only and not aircraft_hex
    want_obs = kind in {"all", "observation", "detection"}

    selects: list[str] = []
    params: list[Any] = []
    if want_calls:
        selects.append(
            """
            SELECT 'call' AS kind, requested_at AS at, provider, region_id,
                   endpoint, outcome, http_status, latency_ms, aircraft_returned,
                   NULL AS estimated_credits, error_message,
                   NULL AS aircraft_hex, NULL AS callsign, NULL AS registration,
                   NULL AS aircraft_type, NULL AS latitude, NULL AS longitude,
                   NULL AS altitude_ft, NULL AS ground_speed_kt, NULL AS on_ground,
                   NULL AS inside, NULL AS area_names_json, NULL AS classification,
                   NULL AS disposition, NULL AS disposition_reason
            FROM provider_call_log
            WHERE (? IS NULL OR provider = ?)
              AND (? = 0 OR COALESCE(aircraft_returned, 0) > 0)
            """
        )
        params += [provider, provider, 1 if detections_only else 0]
        selects.append(
            """
            SELECT 'call' AS kind, requested_at AS at, 'flightradar24' AS provider,
                   cluster_id AS region_id, endpoint, http_outcome AS outcome,
                   NULL AS http_status, latency_ms, records_returned AS aircraft_returned,
                   estimated_credits, NULL AS error_message,
                   NULL AS aircraft_hex, NULL AS callsign, NULL AS registration,
                   NULL AS aircraft_type, NULL AS latitude, NULL AS longitude,
                   NULL AS altitude_ft, NULL AS ground_speed_kt, NULL AS on_ground,
                   NULL AS inside, NULL AS area_names_json, NULL AS classification,
                   NULL AS disposition, NULL AS disposition_reason
            FROM fr24_request_log
            WHERE (? IS NULL OR ? = 'flightradar24')
              AND (? = 0 OR COALESCE(records_returned, 0) > 0)
            """
        )
        params += [provider, provider, 1 if detections_only else 0]
    if want_obs:
        selects.append(
            """
            SELECT 'observation' AS kind, recorded_at AS at, provider, region_id,
                   NULL AS endpoint, NULL AS outcome, NULL AS http_status,
                   NULL AS latency_ms, NULL AS aircraft_returned,
                   NULL AS estimated_credits, NULL AS error_message,
                   aircraft_hex, callsign, registration, aircraft_type,
                   latitude, longitude, altitude_ft, ground_speed_kt, on_ground,
                   inside, area_names_json, classification,
                   disposition, disposition_reason
            FROM observation_log
            WHERE (? IS NULL OR provider = ?)
              AND (? IS NULL OR aircraft_hex = ?)
              AND (? = 0 OR inside = 1)
            """
        )
        hex_value = (aircraft_hex or "").strip().lower() or None
        params += [provider, provider, hex_value, hex_value, 1 if inside_only else 0]

    if not selects:
        return [], 0
    union = " UNION ALL ".join(selects)
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM ({union})", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM ({union}) ORDER BY at DESC LIMIT ? OFFSET ?",
            [*params, max(1, min(int(limit), 500)), max(0, int(offset))],
        ).fetchall()
    return [dict(r) for r in rows], int(total)


def cleanup_logs(retention_days: int) -> int:
    """Trim both log tables to the retention window. Returns rows removed."""
    cutoff = (utc_now() - timedelta(days=retention_days)).isoformat()
    removed = 0
    with db() as conn:
        for table, column in (
            ("provider_call_log", "requested_at"),
            ("observation_log", "recorded_at"),
        ):
            removed += conn.execute(
                f"DELETE FROM {table} WHERE {column} < ?", (cutoff,)
            ).rowcount
    return removed


def cleanup_stale_states(retention_days: int, exclude_provider: str | None = None) -> int:
    cutoff = (utc_now() - timedelta(days=max(1, retention_days))).isoformat()
    query = "DELETE FROM aircraft_state WHERE area_ids_json='[]' AND updated_at<?"
    params: list[Any] = [cutoff]
    if exclude_provider:
        # This is provider-agnostic by default (last_provider is not FR24-
        # specific), so a caller that wants to honor FR24's indefinite-
        # retention setting must pass exclude_provider explicitly -- see
        # fr24_auto_delete_enabled's usage in main.py.
        query += " AND (last_provider IS NULL OR last_provider != ?)"
        params.append(exclude_provider)
    with db() as conn:
        cursor = conn.execute(query, params)
    return int(cursor.rowcount)




def cleanup_provider_events(provider: str, retention_days: int) -> int:
    cutoff = (utc_now() - timedelta(days=max(1, retention_days))).isoformat()
    with db() as conn:
        cursor = conn.execute(
            "DELETE FROM events WHERE provider=? AND occurred_at<?",
            (provider, cutoff),
        )
    return int(cursor.rowcount)

def insert_event(event: dict[str, Any]) -> bool:
    columns = list(event)
    try:
        with db() as conn:
            conn.execute(
                f"INSERT INTO events({','.join(columns)}) "
                f"VALUES({','.join('?' for _ in columns)})",
                [event[column] for column in columns],
            )
        return True
    except sqlite3.IntegrityError:
        return False


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["area_ids"] = json.loads(item.pop("area_ids_json"))
    item["area_names"] = json.loads(item.pop("area_names_json"))
    item["details"] = json.loads(item.pop("details_json"))
    return item


def get_event(event_id: str) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    return _event_from_row(row) if row else None


def update_event_email(event_id: str, status: str, error: str | None = None) -> None:
    with db() as conn:
        row = conn.execute(
            "SELECT email_attempts FROM events WHERE id=?", (event_id,)
        ).fetchone()
        attempts = int(row[0]) + 1 if row else 1
        next_attempt = None
        if status == "failed" and attempts < 4:
            delay_minutes = (1, 5, 20)[min(attempts - 1, 2)]
            next_attempt = (utc_now() + timedelta(minutes=delay_minutes)).isoformat()
        conn.execute(
            """
            UPDATE events SET
              email_status=?,email_error=?,email_attempts=?,email_next_attempt_at=?,emailed_at=?
            WHERE id=?
            """,
            (
                status,
                error[:4000] if error else None,
                attempts,
                next_attempt,
                utc_now_iso() if status == "sent" else None,
                event_id,
            ),
        )


def retryable_email_events(limit: int = 20) -> list[dict[str, Any]]:
    now_value = utc_now_iso()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM events
            WHERE phase='live'
              AND email_status IN ('pending','failed')
              AND email_attempts < 4
              AND (email_next_attempt_at IS NULL OR email_next_attempt_at<=?)
            ORDER BY occurred_at LIMIT ?
            """,
            (now_value, min(max(limit, 1), 100)),
        ).fetchall()
    return [_event_from_row(row) for row in rows]


def review_event(event_id: str, status: str, notes: str = "") -> bool:
    if status not in {"useful", "noise", "uncertain", "unreviewed"}:
        return False
    with db() as conn:
        cursor = conn.execute(
            """
            UPDATE events SET review_status=?,review_notes=?,reviewed_at=? WHERE id=?
            """,
            (
                status,
                notes[:4000],
                utc_now_iso() if status != "unreviewed" else None,
                event_id,
            ),
        )
    return cursor.rowcount > 0


def list_events(
    limit: int = 100,
    event_type: str = "",
    review_status: str = "",
    offset: int = 0,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if event_type in {"PROBABLE_STOP", "DISAPPEARED"}:
        where.append("event_type=?")
        params.append(event_type)
    if review_status in {"useful", "noise", "uncertain", "unreviewed"}:
        where.append("review_status=?")
        params.append(review_status)
    clause = " WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM events{clause} ORDER BY occurred_at DESC LIMIT ? OFFSET ?",
            [*params, min(max(limit, 1), 500), max(offset, 0)],
        ).fetchall()
    return [_event_from_row(row) for row in rows]



def event_counts() -> dict[str, Any]:
    with db() as conn:
        total = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        rows = conn.execute(
            "SELECT review_status,COUNT(*) AS count FROM events GROUP BY review_status"
        ).fetchall()
    review = {"useful": 0, "noise": 0, "uncertain": 0, "unreviewed": 0}
    for row in rows:
        review[str(row["review_status"])] = int(row["count"])
    return {"total": total, "review": review}

def email_count_today() -> int:
    prefix = utc_now().date().isoformat() + "%"
    with db() as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM events WHERE email_status='sent' AND emailed_at LIKE ?",
                (prefix,),
            ).fetchone()[0]
        )


def record_provider_request(provider: str, success: bool) -> None:
    day = utc_now().date().isoformat()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO provider_requests(day,provider,attempts,successes,updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(day,provider) DO UPDATE SET
              attempts=provider_requests.attempts+1,
              successes=provider_requests.successes+excluded.successes,
              updated_at=excluded.updated_at
            """,
            (day, provider, 1, 1 if success else 0, utc_now_iso()),
        )


def provider_requests_today(provider: str) -> int:
    day = utc_now().date().isoformat()
    with db() as conn:
        row = conn.execute(
            "SELECT attempts FROM provider_requests WHERE day=? AND provider=?",
            (day, provider),
        ).fetchone()
    return int(row[0]) if row else 0

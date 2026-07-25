import json

import pytest
from shapely.geometry import Polygon, mapping

from app.database import (
    areas_by_ids,
    delete_fr24_cluster,
    fr24_cluster_area_ids,
    fr24_cluster_missing_area_ids,
    get_fr24_cluster,
    list_fr24_clusters,
    record_config_audit,
    replace_areas,
    save_fr24_cluster,
    set_fr24_cluster_areas,
)
from app.fr24_clusters import (
    active_cluster_overlaps,
    clusters_overlap,
    compute_cluster_bounds,
    geometry_version_hash,
    validate_manual_bounds,
)


def _area_geometry(corners):
    return json.dumps(mapping(Polygon(corners)))


def _selected_area_record(area_id="funai:test", name="Test Area"):
    geometry = Polygon(
        [(-55.1, -1.1), (-54.9, -1.1), (-54.9, -0.9), (-55.1, -0.9), (-55.1, -1.1)]
    )
    return {
        "id": area_id,
        "source": "FUNAI",
        "external_id": area_id.split(":")[-1],
        "name": name,
        "category": "indigenous_territory",
        "state": "PA",
        "phase": "Regularizada",
        "geometry_json": json.dumps(mapping(geometry)),
        "min_lon": -55.1,
        "min_lat": -1.1,
        "max_lon": -54.9,
        "max_lat": -0.9,
        "source_date": "2026-07-23",
    }


def _cluster_record(cluster_id="cluster-1", name="Test Cluster"):
    return {
        "id": cluster_id,
        "name": name,
        "enabled": 1,
        "buffer_km": 10.0,
        "min_altitude_ft": 0.0,
        "max_altitude_ft": 10000.0,
        "categories_json": '["indigenous_territory"]',
    }


# --- Geometry tests ---


def test_compute_cluster_bounds_single_polygon():
    geom = _area_geometry(
        [(-55.1, -1.1), (-54.9, -1.1), (-54.9, -0.9), (-55.1, -0.9), (-55.1, -1.1)]
    )
    result = compute_cluster_bounds([geom], buffer_km=5)
    assert "west" in result
    assert "south" in result
    assert "east" in result
    assert "north" in result
    assert "selected_area_km2" in result
    assert "rectangle_area_km2" in result
    assert "empty_space_ratio" in result
    assert result["north"] > result["south"]
    assert result["east"] > result["west"]
    assert result["rectangle_area_km2"] > result["selected_area_km2"]


def test_compute_cluster_bounds_empty_raises():
    with pytest.raises(ValueError, match="at least one member"):
        compute_cluster_bounds([], buffer_km=5)


def test_compute_cluster_bounds_two_disjoint_polygons():
    geom_a = _area_geometry(
        [(-55.1, -1.1), (-54.9, -1.1), (-54.9, -0.9), (-55.1, -0.9), (-55.1, -1.1)]
    )
    geom_b = _area_geometry(
        [(-56.1, -2.1), (-55.9, -2.1), (-55.9, -1.9), (-56.1, -1.9), (-56.1, -2.1)]
    )
    result = compute_cluster_bounds([geom_a, geom_b], buffer_km=5)
    assert result["west"] <= -56.1
    assert result["east"] >= -54.9
    assert result["south"] <= -2.1
    assert result["north"] >= -0.9


def test_clusters_overlap_intersecting():
    a = {"north": -1, "south": -3, "west": -56, "east": -54}
    b = {"north": -2, "south": -4, "west": -55, "east": -53}
    assert clusters_overlap(a, b) is True


def test_clusters_overlap_disjoint():
    a = {"north": -1, "south": -3, "west": -56, "east": -54}
    b = {"north": 11, "south": 9, "west": -41, "east": -39}
    assert clusters_overlap(a, b) is False


def test_active_cluster_overlaps_enabled_overlapping():
    clusters = [
        {
            "id": "c1",
            "enabled": True,
            "calc_north": -1,
            "calc_south": -3,
            "calc_west": -56,
            "calc_east": -54,
        },
        {
            "id": "c2",
            "enabled": True,
            "calc_north": -2,
            "calc_south": -4,
            "calc_west": -55,
            "calc_east": -53,
        },
    ]
    pairs = active_cluster_overlaps(clusters)
    assert len(pairs) == 1
    assert pairs[0] == ("c1", "c2")


def test_active_cluster_overlaps_disabled_skipped():
    clusters = [
        {
            "id": "c1",
            "enabled": True,
            "calc_north": -1,
            "calc_south": -3,
            "calc_west": -56,
            "calc_east": -54,
        },
        {
            "id": "c2",
            "enabled": False,
            "calc_north": -2,
            "calc_south": -4,
            "calc_west": -55,
            "calc_east": -53,
        },
    ]
    assert active_cluster_overlaps(clusters) == []


def test_active_cluster_overlaps_missing_bounds_skipped():
    clusters = [
        {
            "id": "c1",
            "enabled": True,
            "calc_north": -1,
            "calc_south": -3,
            "calc_west": -56,
            "calc_east": -54,
        },
        {"id": "c2", "enabled": True},
    ]
    assert active_cluster_overlaps(clusters) == []


def test_active_cluster_overlaps_partial_bounds_treated_as_missing():
    # A row with some calc_* fields NULL (e.g. a degenerate compute result
    # that got persisted) must be skipped, not raise inside clusters_overlap.
    clusters = [
        {
            "id": "c1",
            "enabled": True,
            "calc_north": -1,
            "calc_south": -3,
            "calc_west": -56,
            "calc_east": -54,
        },
        {
            "id": "c2",
            "enabled": True,
            "calc_north": -2,
            "calc_south": None,
            "calc_west": -55,
            "calc_east": -53,
        },
    ]
    assert active_cluster_overlaps(clusters) == []


def test_validate_manual_bounds_valid():
    validate_manual_bounds(north=-1, south=-3, west=-56, east=-54)


def test_validate_manual_bounds_north_below_south():
    with pytest.raises(ValueError, match="north must be greater"):
        validate_manual_bounds(north=-3, south=-1, west=-56, east=-54)


def test_validate_manual_bounds_out_of_range_longitude():
    with pytest.raises(ValueError, match="east must be greater"):
        validate_manual_bounds(north=-1, south=-3, west=-200, east=-54)


def test_validate_manual_bounds_west_not_less_than_east():
    # A transposed west/east must be rejected -- otherwise it would validate
    # fine and then make clusters_overlap() misreport a real overlap as disjoint.
    with pytest.raises(ValueError, match="east must be greater"):
        validate_manual_bounds(north=-1, south=-3, west=-54, east=-56)


def test_geometry_version_hash_order_independent():
    h1 = geometry_version_hash(["b", "a"], ["v1", "v2"], 10.0, None)
    h2 = geometry_version_hash(["a", "b"], ["v2", "v1"], 10.0, None)
    assert h1 == h2


def test_geometry_version_hash_changes_with_buffer():
    h1 = geometry_version_hash(["a", "b"], ["v1", "v2"], 10.0, None)
    h2 = geometry_version_hash(["a", "b"], ["v1", "v2"], 20.0, None)
    assert h1 != h2


def test_geometry_version_hash_changes_with_area_version():
    # A republished boundary under the same stable area id (e.g. an extended
    # FUNAI territory) must invalidate the cached bounds even though the area
    # id set alone is unchanged.
    h1 = geometry_version_hash(["a", "b"], ["v1", "v2"], 10.0, None)
    h2 = geometry_version_hash(["a", "b"], ["v1", "v3"], 10.0, None)
    assert h1 != h2


def test_compute_cluster_bounds_buffers_in_metric_not_degrees():
    # A small polygon near the equator; buffering 111 km should expand bounds
    # roughly 1 degree in each direction. Buffering in raw degrees instead of
    # a metric CRS would be off by roughly two orders of magnitude.
    geom = _area_geometry(
        [(-55.0, -0.05), (-54.95, -0.05), (-54.95, 0.0), (-55.0, 0.0), (-55.0, -0.05)]
    )
    result = compute_cluster_bounds([geom], buffer_km=111)
    assert -56.5 < result["west"] < -55.5
    assert -54.5 < result["east"] < -53.5


def test_compute_cluster_bounds_degenerate_raises():
    # A single point with a zero buffer produces an empty buffered geometry --
    # must raise, never silently return NaN bounds (which SQLite would store
    # as NULL, silently dropping the cluster from overlap detection).
    geom = json.dumps({"type": "Point", "coordinates": [-55.0, -1.0]})
    with pytest.raises(ValueError, match="empty"):
        compute_cluster_bounds([geom], buffer_km=0)


# --- DB CRUD tests ---


def test_save_and_get_fr24_cluster_round_trip():
    record = _cluster_record()
    save_fr24_cluster(record)
    fetched = get_fr24_cluster("cluster-1")
    assert fetched is not None
    assert fetched["id"] == "cluster-1"
    assert fetched["name"] == "Test Cluster"
    assert fetched["enabled"] == 1
    assert fetched["buffer_km"] == 10.0


def test_save_fr24_cluster_upsert_updates_in_place():
    save_fr24_cluster(_cluster_record())
    save_fr24_cluster(_cluster_record(name="Updated Name"))
    rows = list_fr24_clusters()
    assert len(rows) == 1
    assert rows[0]["name"] == "Updated Name"


def test_set_and_get_fr24_cluster_areas():
    save_fr24_cluster(_cluster_record())
    set_fr24_cluster_areas("cluster-1", ["area-a", "area-b"])
    ids = fr24_cluster_area_ids("cluster-1")
    assert ids == ["area-a", "area-b"]


def test_set_fr24_cluster_areas_replaces_membership():
    save_fr24_cluster(_cluster_record())
    set_fr24_cluster_areas("cluster-1", ["area-a", "area-b"])
    set_fr24_cluster_areas("cluster-1", ["area-c"])
    ids = fr24_cluster_area_ids("cluster-1")
    assert ids == ["area-c"]


def test_fr24_cluster_missing_area_ids():
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_cluster_record())
    set_fr24_cluster_areas("cluster-1", ["funai:test", "funai:does-not-exist"])
    missing = fr24_cluster_missing_area_ids("cluster-1")
    assert missing == ["funai:does-not-exist"]


def test_delete_fr24_cluster():
    save_fr24_cluster(_cluster_record())
    assert delete_fr24_cluster("cluster-1") is True
    assert get_fr24_cluster("cluster-1") is None
    assert delete_fr24_cluster("cluster-1") is False


def test_areas_by_ids_returns_matching_rows():
    replace_areas(
        [_selected_area_record("funai:a", "Area A"), _selected_area_record("funai:b", "Area B")],
        auto_select_all=True,
    )
    rows = areas_by_ids(["funai:a", "funai:b"])
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert names == {"Area A", "Area B"}


def test_areas_by_ids_ignores_nonexistent():
    replace_areas([_selected_area_record()], auto_select_all=True)
    rows = areas_by_ids(["funai:test", "funai:nonexistent"])
    assert len(rows) == 1


def test_record_config_audit_secret_redacted():
    record_config_audit("api_key", "old-secret", "new-secret", "admin", secret=True)
    from app.database import db

    with db() as conn:
        row = conn.execute("SELECT * FROM config_audit_log ORDER BY changed_at").fetchone()
    assert row is not None
    assert row["old_value"] == "[redacted]"
    assert row["new_value"] == "[redacted]"
    assert row["secret"] == 1


def test_record_config_audit_non_secret_stores_values():
    record_config_audit("poll_interval_seconds", "300", "600", "admin", secret=False)
    from app.database import db

    with db() as conn:
        row = conn.execute("SELECT * FROM config_audit_log ORDER BY changed_at").fetchone()
    assert row is not None
    assert row["old_value"] == "300"
    assert row["new_value"] == "600"
    assert row["secret"] == 0


def test_record_config_audit_redacts_known_secret_setting_even_without_flag():
    # A caller forgetting secret=True for a real SETTING_DEFS secret key (e.g.
    # flightradar24_api_key) must not be able to leak it in cleartext -- the
    # function derives secrecy from SETTING_DEFS regardless of the flag.
    record_config_audit("flightradar24_api_key", "old-token", "new-token", "admin")
    from app.database import db

    with db() as conn:
        row = conn.execute("SELECT * FROM config_audit_log ORDER BY changed_at").fetchone()
    assert row is not None
    assert row["old_value"] == "[redacted]"
    assert row["new_value"] == "[redacted]"
    assert row["secret"] == 1

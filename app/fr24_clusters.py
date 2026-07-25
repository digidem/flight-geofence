"""FR24 cluster geometry: union member areas, buffer, and compute a WGS84 bounding rectangle."""

import hashlib
import json
import math
from typing import Any

from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union

_TO_METRIC = Transformer.from_crs("EPSG:4326", "EPSG:5880", always_xy=True).transform
_TO_WGS84 = Transformer.from_crs("EPSG:5880", "EPSG:4326", always_xy=True).transform


def geometry_version_hash(
    area_ids: list[str],
    area_versions: list[str],
    buffer_km: float,
    manual_bounds: tuple[float, float, float, float] | None,
) -> str:
    # area_versions (each area's updated_at/source_date) must be included so a
    # republished boundary under the same stable area id -- e.g. an extended
    # FUNAI territory after replace_areas() -- changes the hash even though
    # area_ids alone would look unchanged, forcing bounds to recompute.
    paired = sorted(zip(area_ids, area_versions, strict=True))
    seed = "|".join(f"{area_id}:{version}" for area_id, version in paired)
    seed += f"|{buffer_km:.3f}|{manual_bounds}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def compute_cluster_bounds(area_geometries_json: list[str], buffer_km: float) -> dict[str, float]:
    """Union member area geometries, buffer in a metric CRS, and return the WGS84
    axis-aligned bounding rectangle plus area-ratio diagnostics.

    Raises ValueError if area_geometries_json is empty or the resulting
    geometry is degenerate (empty or non-finite bounds).
    """
    if not area_geometries_json:
        raise ValueError("compute_cluster_bounds requires at least one member area geometry")
    geometries = [make_valid(shape(json.loads(g))) for g in area_geometries_json]
    union_wgs84 = make_valid(unary_union(geometries))
    selected_area_m2 = transform(_TO_METRIC, union_wgs84).area
    buffered_metric = transform(_TO_METRIC, union_wgs84).buffer(buffer_km * 1000)
    if buffered_metric.is_empty:
        raise ValueError("buffered cluster geometry is empty (degenerate area or buffer_km)")
    rect_wgs84_bounds = transform(_TO_WGS84, buffered_metric).bounds  # (minx,miny,maxx,maxy)
    if any(not math.isfinite(v) for v in rect_wgs84_bounds):
        raise ValueError("cluster bounds computation produced non-finite values")
    # Measure the area of the exact rectangle being returned (reprojected back
    # to metric), not the metric bounding box's own area -- a WGS84-degree
    # rectangle and its metric bbox are not the same shape once reprojected.
    rect_area_m2 = transform(_TO_METRIC, box(*rect_wgs84_bounds)).area
    return {
        "west": round(rect_wgs84_bounds[0], 6),
        "south": round(rect_wgs84_bounds[1], 6),
        "east": round(rect_wgs84_bounds[2], 6),
        "north": round(rect_wgs84_bounds[3], 6),
        "selected_area_km2": round(selected_area_m2 / 1_000_000, 3),
        "rectangle_area_km2": round(rect_area_m2 / 1_000_000, 3),
        "empty_space_ratio": round(1 - (selected_area_m2 / rect_area_m2), 4) if rect_area_m2 else 0.0,
    }


def clusters_overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    """a, b: dicts with north/south/west/east keys (WGS84 degrees). True if the
    two axis-aligned rectangles intersect."""
    return not (
        a["east"] < b["west"]
        or b["east"] < a["west"]
        or a["north"] < b["south"]
        or b["north"] < a["south"]
    )


def bounds_of(cluster: dict[str, Any]) -> dict[str, float] | None:
    # Require all four fields present -- a partially-populated row (e.g. a
    # degenerate compute_cluster_bounds() result that got stored as some
    # fields NULL) must be treated as "not computed", never passed through
    # with missing keys that would raise inside clusters_overlap().
    manual_keys = ("manual_north", "manual_south", "manual_west", "manual_east")
    if cluster.get("use_manual_bounds") and all(cluster.get(k) is not None for k in manual_keys):
        return {
            "north": cluster["manual_north"],
            "south": cluster["manual_south"],
            "west": cluster["manual_west"],
            "east": cluster["manual_east"],
        }
    calc_keys = ("calc_north", "calc_south", "calc_west", "calc_east")
    if all(cluster.get(k) is not None for k in calc_keys):
        return {
            "north": cluster["calc_north"],
            "south": cluster["calc_south"],
            "west": cluster["calc_west"],
            "east": cluster["calc_east"],
        }
    return None


def active_cluster_overlaps(clusters: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return (cluster_id, cluster_id) pairs among enabled clusters whose bounds
    overlap. Clusters with no computed bounds yet are skipped."""
    enabled = [c for c in clusters if c.get("enabled")]
    pairs: list[tuple[str, str]] = []
    for i in range(len(enabled)):
        for j in range(i + 1, len(enabled)):
            bounds_a = bounds_of(enabled[i])
            bounds_b = bounds_of(enabled[j])
            if bounds_a and bounds_b and clusters_overlap(bounds_a, bounds_b):
                pairs.append((enabled[i]["id"], enabled[j]["id"]))
    return pairs


def validate_manual_bounds(north: float, south: float, west: float, east: float) -> None:
    if not (-90 <= south < north <= 90):
        raise ValueError("north must be greater than south, both within [-90, 90]")
    if not (-180 <= west < east <= 180):
        raise ValueError("east must be greater than west, both within [-180, 180]")

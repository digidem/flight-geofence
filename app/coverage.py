import hashlib
import json
import math

from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

from .config import env_settings
from .database import replace_query_regions, selected_area_rows


def _region_id(latitude: float, longitude: float, radius_nm: float) -> str:
    seed = f"{latitude:.5f}|{longitude:.5f}|{radius_nm:.1f}"
    return "region-" + hashlib.sha256(seed.encode("ascii")).hexdigest()[:12]


def regenerate_query_regions() -> list[dict]:
    cfg = env_settings()
    rows = selected_area_rows()
    if not rows:
        replace_query_regions([])
        return []

    geometries = [shape(json.loads(row["geometry_json"])) for row in rows]
    union_wgs84 = make_valid(unary_union(geometries))
    to_metric = Transformer.from_crs(
        "EPSG:4326", "EPSG:5880", always_xy=True
    ).transform
    to_wgs84 = Transformer.from_crs(
        "EPSG:5880", "EPSG:4326", always_xy=True
    ).transform
    monitored = transform(to_metric, union_wgs84).buffer(
        cfg.observation_buffer_km * 1000
    )

    radius_m = cfg.query_radius_nm * 1852.0
    factor = cfg.query_spacing_factor
    dx = 1.5 * radius_m * factor
    dy = math.sqrt(3) * radius_m * factor

    minx, miny, maxx, maxy = monitored.bounds
    minx -= radius_m
    miny -= radius_m
    maxx += radius_m
    maxy += radius_m

    regions: list[dict] = []
    row_number = 0
    y = miny
    while y <= maxy:
        x = minx + (0 if row_number % 2 == 0 else dx / 2)
        while x <= maxx:
            circle = Point(x, y).buffer(radius_m, quad_segs=24)
            if circle.intersects(monitored):
                center = transform(to_wgs84, Point(x, y))
                bounds = transform(to_wgs84, circle).bounds
                latitude = round(center.y, 6)
                longitude = round(center.x, 6)
                regions.append(
                    {
                        "id": _region_id(latitude, longitude, cfg.query_radius_nm),
                        "name": f"Coverage {latitude:.3f}, {longitude:.3f}",
                        "latitude": latitude,
                        "longitude": longitude,
                        "radius_nm": cfg.query_radius_nm,
                        "north": round(bounds[3], 6),
                        "south": round(bounds[1], 6),
                        "west": round(bounds[0], 6),
                        "east": round(bounds[2], 6),
                    }
                )
                if len(regions) > cfg.max_query_regions:
                    raise RuntimeError(
                        f"Selection requires more than MAX_QUERY_REGIONS="
                        f"{cfg.max_query_regions}. Narrow the selected areas or increase "
                        "QUERY_RADIUS_NM."
                    )
            x += dx
        y += dy
        row_number += 1

    # Deterministic order prevents unnecessary region churn after weekly updates.
    regions.sort(key=lambda item: (item["latitude"], item["longitude"]))
    replace_query_regions(regions)
    return regions

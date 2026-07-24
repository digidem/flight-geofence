import json
from dataclasses import dataclass

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from .database import selected_area_rows


@dataclass(frozen=True)
class Area:
    id: str
    name: str
    category: str
    state: str | None
    phase: str | None
    geometry: object


class GeofenceIndex:
    def __init__(self):
        rows = selected_area_rows()
        self.areas: list[Area] = []
        self.geometries = []
        for row in rows:
            geometry = shape(json.loads(row["geometry_json"]))
            self.areas.append(
                Area(
                    id=row["id"],
                    name=row["name"],
                    category=row["category"],
                    state=row.get("state"),
                    phase=row.get("phase"),
                    geometry=geometry,
                )
            )
            self.geometries.append(geometry)
        self.tree = STRtree(self.geometries) if self.geometries else None

    def matches(self, latitude: float, longitude: float) -> list[Area]:
        if not self.tree:
            return []
        # Shapely uses (x, y) = (longitude, latitude) convention
        point = Point(longitude, latitude)
        matches = []
        for index in self.tree.query(point):
            area = self.areas[int(index)]
            if area.geometry.covers(point):
                matches.append(area)
        return matches

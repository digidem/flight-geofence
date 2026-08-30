from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import stat
import tempfile
import time
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import geopandas as gpd
import httpx
from shapely import make_valid
from shapely.geometry import mapping
from shapely.ops import unary_union

from .config import env_settings
from .coverage import regenerate_query_regions
from .database import replace_areas, save_sync_run
from .i18n import t
from .locks import exclusive_job_lock
from .settings_store import get_setting

logger = logging.getLogger(__name__)


def _lang() -> str:
    return str(get_setting("language") or "pt")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode()
    )
    return re.sub(r"[^a-z0-9]", "", normalized.lower())


def _find_column(frame: gpd.GeoDataFrame, candidates: list[str]) -> str | None:
    normalized = {_norm(column): column for column in frame.columns}
    for candidate in candidates:
        wanted = _norm(candidate)
        if wanted in normalized:
            return normalized[wanted]
    for candidate in candidates:
        wanted = _norm(candidate)
        for normalized_name, original in normalized.items():
            if wanted and wanted in normalized_name:
                return original
    return None


def _required_column(
    frame: gpd.GeoDataFrame, candidates: list[str], label: str
) -> str:
    column = _find_column(frame, candidates)
    if not column:
        raise RuntimeError(
            f"Could not find {label} column. Available: {list(frame.columns)}"
        )
    return column


def _request_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    attempts: int = 3,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                if attempt < attempts - 1:
                    time.sleep(min(delay, 30))
                    continue
            response.raise_for_status()
            return response
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(2**attempt)
    raise RuntimeError(f"Request failed after {attempts} attempts: {url}: {last_error}")


def _download(
    client: httpx.Client,
    url: str,
    destination: Path,
    params: dict[str, str] | None = None,
) -> None:
    cfg = env_settings()
    maximum = cfg.max_download_mb * 1024 * 1024
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with client.stream("GET", url, params=params) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                declared = int(response.headers.get("Content-Length") or 0)
                if declared and declared > maximum:
                    raise RuntimeError(
                        f"Download exceeds MAX_DOWNLOAD_MB ({cfg.max_download_mb} MB)"
                    )
                total = 0
                with destination.open("wb") as output:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        total += len(chunk)
                        if total > maximum:
                            raise RuntimeError(
                                f"Download exceeded MAX_DOWNLOAD_MB ({cfg.max_download_mb} MB)"
                            )
                        output.write(chunk)
            if destination.stat().st_size < 1000:
                raise RuntimeError(f"Downloaded file is unexpectedly small: {destination}")
            if destination.suffix.lower() == ".zip":
                with destination.open("rb") as input_file:
                    if input_file.read(2) != b"PK":
                        raise RuntimeError(f"Expected ZIP data from {url}")
            return
        except Exception as exc:
            last_error = exc
            destination.unlink(missing_ok=True)
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"Download failed: {url}: {last_error}")


def _safe_extract(zip_path: Path, target: Path) -> None:
    cfg = env_settings()
    target_root = target.resolve()
    total_uncompressed = 0
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.infolist()
        if len(members) > cfg.max_zip_members:
            raise RuntimeError("ZIP contains too many members")
        for member in members:
            resolved = (target / member.filename).resolve()
            if not resolved.is_relative_to(target_root):
                raise RuntimeError("Unsafe ZIP member path")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise RuntimeError("ZIP symbolic links are not allowed")
            total_uncompressed += member.file_size
            if total_uncompressed > cfg.max_extracted_mb * 1024 * 1024:
                raise RuntimeError(
                    f"ZIP exceeds MAX_EXTRACTED_MB ({cfg.max_extracted_mb} MB)"
                )
        archive.extractall(target)


def _choose_shapefile(folder: Path, prefer_polygon: bool = False) -> Path:
    candidates = list(folder.rglob("*.shp"))
    if not candidates:
        raise RuntimeError(f"No shapefile found in {folder}")
    if prefer_polygon:
        polygon = [
            path
            for path in candidates
            if "_pol" in path.stem.lower() or "polig" in _norm(path.stem)
        ]
        if polygon:
            return max(polygon, key=lambda path: path.stat().st_size)
        non_points = [
            path
            for path in candidates
            if "_pt" not in path.stem.lower() and "ponto" not in _norm(path.stem)
        ]
        if non_points:
            return max(non_points, key=lambda path: path.stat().st_size)
    return max(candidates, key=lambda path: path.stat().st_size)


def _discover_cnuc_resource(client: httpx.Client) -> dict[str, str]:
    cfg = env_settings()
    response = _request_with_retry(client, cfg.mma_ckan_package_url)
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError("MMA CKAN package lookup failed")

    scored: list[tuple[int, int, str, dict[str, Any]]] = []
    for resource in payload.get("result", {}).get("resources", []):
        text = " ".join(
            str(resource.get(key) or "")
            for key in ("name", "description", "url", "format")
        )
        normalized = _norm(text)
        url = str(resource.get("url") or "")
        resource_format = str(resource.get("format") or "").upper()
        mimetype = str(resource.get("mimetype") or "").lower()
        is_zip = (
            urlparse(url).path.lower().endswith(".zip")
            or resource_format in {"ZIP", "SHP", "SHAPEFILE"}
            or mimetype in {"application/zip", "application/x-zip-compressed"}
        )
        if not is_zip:
            continue
        if not any(token in normalized for token in ("poligon", "shpcnuc", "cnuc")):
            continue
        polygon_score = 2 if any(token in normalized for token in ("poligon", "_pol", "shpcnuc")) else 0
        point_penalty = -2 if any(token in normalized for token in ("ponto", "_pt", "csv")) else 0
        dates = re.findall(r"(20\d{2})[_-]?(0[1-9]|1[0-2])", text)
        date_score = max(
            (int(year) * 100 + int(month) for year, month in dates), default=0
        )
        modified = str(resource.get("last_modified") or resource.get("created") or "")
        scored.append((date_score, polygon_score + point_penalty, modified, resource))

    if not scored:
        raise RuntimeError("No polygon ZIP resource found in the MMA CNUC package")
    resource = max(scored, key=lambda item: (item[0], item[1], item[2]))[3]
    return {
        "url": str(resource["url"]),
        "name": str(resource.get("name") or "CNUC polygon resource"),
        "updated": str(
            resource.get("last_modified") or resource.get("created") or "unknown"
        ),
    }




def _polygonal(geometry):
    valid = make_valid(geometry)
    if valid.geom_type in {"Polygon", "MultiPolygon"}:
        return valid
    parts = [
        part
        for part in getattr(valid, "geoms", [])
        if part.geom_type in {"Polygon", "MultiPolygon"}
    ]
    return unary_union(parts) if parts else valid

def _stable_id(source: str, external_id: Any, name: str, state: str, geometry) -> str:
    raw = str(external_id or "").strip()
    if re.fullmatch(r"-?\d+\.0+", raw):
        raw = raw.split(".", 1)[0]
    if not raw or raw.lower() == "nan":
        # Include coarse bounds to avoid collisions between same-named polygons while
        # remaining stable across small weekly geometry corrections.
        coarse_bounds = ",".join(f"{value:.4f}" for value in geometry.bounds)
        seed = (
            f"{source}|{_norm(name)}|{_norm(state)}|"
            f"{geometry.geom_type}|{coarse_bounds}"
        )
        raw = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"{source.lower()}:{raw}"


def _target_state_mask(series, states: set[str]):
    escaped = "|".join(re.escape(state) for state in sorted(states))
    pattern = rf"(?:^|[^A-Z])(?:{escaped})(?:[^A-Z]|$)"
    return series.fillna("").astype(str).str.upper().str.contains(pattern, regex=True)


def _records_from_frames(
    territories: gpd.GeoDataFrame,
    conservation: gpd.GeoDataFrame,
    cnuc_meta: dict[str, str],
) -> list[dict[str, Any]]:
    cfg = env_settings()
    states = set(cfg.target_state_list)

    ti_name = _required_column(
        territories,
        ["terrai_nom", "terrai_nome", "nome", "terra_indigena"],
        "FUNAI name",
    )
    ti_id = _find_column(
        territories, ["terrai_cod", "codigo", "id", "gid", "objectid"]
    )
    ti_state = _required_column(
        territories, ["uf_sigla", "uf", "sigla_uf"], "FUNAI state"
    )
    ti_phase = _find_column(territories, ["fase_ti", "fase", "etapa", "situacao"])

    # Filter to target states and prune attribute columns in one step: the
    # upstream shapefile carries every territory in Brazil plus a wide
    # attribute table, and the host is memory-constrained.
    territory_columns = [
        column for column in (ti_name, ti_id, ti_state, ti_phase) if column
    ]
    territories = territories.loc[
        _target_state_mask(territories[ti_state], states),
        [*territory_columns, "geometry"],
    ].copy()
    if territories.empty:
        raise RuntimeError(
            f"No FUNAI territory polygons matched target states: {', '.join(sorted(states))}"
        )
    if territories.crs is None:
        raise RuntimeError("FUNAI data does not declare a CRS")

    # When CNUC data is unavailable, return territories only
    if conservation.empty or conservation.crs is None:
        territories_metric = territories.to_crs("EPSG:5880")
        territories_out = territories_metric.to_crs("EPSG:4326")
        del territories
        records: list[dict[str, Any]] = []
        funai_sync_date = datetime.now(timezone.utc).date().isoformat()
        for index, row in territories_out.iterrows():
            geometry = _polygonal(row.geometry)
            if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                continue
            geometry = geometry.simplify(0.0003, preserve_topology=True)
            name = str(row.get(ti_name) or "Unnamed Indigenous territory").strip()
            state = str(row.get(ti_state) or "").strip()
            external = row.get(ti_id) if ti_id else None
            bounds = geometry.bounds
            records.append(
                {
                    "id": _stable_id("FUNAI", external, name, state, geometry),
                    "source": "FUNAI",
                    "external_id": str(external if external is not None else index),
                    "name": name,
                    "category": "indigenous_territory",
                    "state": state,
                    "phase": str(row.get(ti_phase) or "").strip() if ti_phase else "",
                    "geometry_json": json.dumps(mapping(geometry), ensure_ascii=False),
                    "min_lon": bounds[0],
                    "min_lat": bounds[1],
                    "max_lon": bounds[2],
                    "max_lat": bounds[3],
                    "source_date": funai_sync_date,
                }
            )
        return records

    if conservation.crs is None:
        raise RuntimeError("CNUC data does not declare a CRS")

    territories_metric = territories.to_crs("EPSG:5880")
    conservation_metric = conservation.to_crs("EPSG:5880")
    del territories, conservation

    uc_name = _required_column(
        conservation_metric, ["nome_uc", "nomeuc", "nome", "name"], "CNUC name"
    )
    uc_id = _find_column(
        conservation_metric, ["id_uc", "cnuc", "codigo", "id", "gid", "objectid"]
    )
    uc_state = _find_column(
        conservation_metric, ["uf", "uf_sigla", "sigla_uf", "estados"]
    )
    uc_status = _find_column(conservation_metric, ["situacao", "status", "ativo"])
    uc_category = _find_column(
        conservation_metric, ["categoria", "categoria_manejo", "cat_manejo"]
    )
    conservation_columns = [
        column for column in (uc_name, uc_id, uc_state, uc_status, uc_category)
        if column
    ]
    conservation_metric = conservation_metric[
        [*conservation_columns, "geometry"]
    ]

    if uc_status:
        status_values = conservation_metric[uc_status].fillna("").astype(str).map(_norm)
        conservation_metric = conservation_metric[
            ~status_values.str.contains("inativ|extint|cancel", regex=True)
        ].copy()

    valid_territories = territories_metric.geometry.make_valid()
    neighbor_union = valid_territories.buffer(
        cfg.neighbor_distance_km * 1000
    ).union_all()
    del valid_territories
    valid_conservation = conservation_metric.geometry.make_valid()
    conservation_metric = conservation_metric[
        valid_conservation.intersects(neighbor_union)
    ].copy()
    del valid_conservation, neighbor_union

    territories_out = territories_metric.to_crs("EPSG:4326")
    conservation_out = conservation_metric.to_crs("EPSG:4326")
    del territories_metric, conservation_metric
    records: list[dict[str, Any]] = []
    funai_sync_date = datetime.now(timezone.utc).date().isoformat()

    for index, row in territories_out.iterrows():
        geometry = _polygonal(row.geometry)
        if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        geometry = geometry.simplify(0.0003, preserve_topology=True)
        name = str(row.get(ti_name) or "Unnamed Indigenous territory").strip()
        state = str(row.get(ti_state) or "").strip()
        external = row.get(ti_id) if ti_id else None
        bounds = geometry.bounds
        records.append(
            {
                "id": _stable_id("FUNAI", external, name, state, geometry),
                "source": "FUNAI",
                "external_id": str(external if external is not None else index),
                "name": name,
                "category": "indigenous_territory",
                "state": state,
                "phase": str(row.get(ti_phase) or "").strip() if ti_phase else "",
                "geometry_json": json.dumps(mapping(geometry), ensure_ascii=False),
                "min_lon": bounds[0],
                "min_lat": bounds[1],
                "max_lon": bounds[2],
                "max_lat": bounds[3],
                "source_date": funai_sync_date,
            }
        )

    del territories_out
    for index, row in conservation_out.iterrows():
        geometry = _polygonal(row.geometry)
        if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        geometry = geometry.simplify(0.0003, preserve_topology=True)
        name = str(row.get(uc_name) or "Unnamed conservation unit").strip()
        state = str(row.get(uc_state) or "").strip() if uc_state else ""
        external = row.get(uc_id) if uc_id else None
        bounds = geometry.bounds
        records.append(
            {
                "id": _stable_id("CNUC", external, name, state, geometry),
                "source": "CNUC",
                "external_id": str(external if external is not None else index),
                "name": name,
                "category": "conservation_unit",
                "state": state,
                "phase": str(row.get(uc_category) or "").strip() if uc_category else "",
                "geometry_json": json.dumps(mapping(geometry), ensure_ascii=False),
                "min_lon": bounds[0],
                "min_lat": bounds[1],
                "max_lon": bounds[2],
                "max_lat": bounds[3],
                "source_date": cnuc_meta.get("updated", "unknown"),
            }
        )

    if not records:
        raise RuntimeError("Boundary synchronization produced no polygon records")
    return records


def _sync_boundaries_sync() -> dict[str, Any]:
    with exclusive_job_lock("boundary-sync") as acquired:
        if not acquired:
            return {"status": "skipped", "reason": t("err_boundaries_sync_running", _lang())}
        with exclusive_job_lock("coverage-poll") as coverage_available:
            if not coverage_available:
                return {
                    "status": "skipped",
                    "reason": t("err_boundaries_poll_running", _lang()),
                }
            return _sync_boundaries_locked()


def _download_funai(
    client: httpx.Client, work: Path, cfg: Any
) -> Path | None:
    """Download indigenous territories from FUNAI WFS."""
    funai_zip = work / "funai.zip"
    try:
        # FUNAI WFS requires a browser-like User-Agent to avoid 403 errors
        funai_headers = {"User-Agent": cfg.funai_user_agent}
        with httpx.Client(
            timeout=client.timeout,
            follow_redirects=True,
            headers={**dict(client.headers), **funai_headers},
        ) as funai_client:
            _download(
                funai_client,
                cfg.funai_wfs_url,
                funai_zip,
                params={
                    "service": "WFS",
                    "version": "1.0.0",
                    "request": "GetFeature",
                    "typeName": cfg.funai_wfs_typename,
                    "outputFormat": "SHAPE-ZIP",
                    "maxFeatures": "10000",
                },
            )
        return funai_zip
    except Exception as exc:
        logger.warning("FUNAI WFS download failed: %s", exc)
        return None


def _download_icmbio(
    client: httpx.Client, work: Path, cfg: Any
) -> gpd.GeoDataFrame | None:
    """Download federal conservation units from ICMBio WFS."""
    try:
        response = _request_with_retry(
            client,
            cfg.icmbio_wfs_url,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": cfg.icmbio_wfs_typename,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
            },
        )
        data = response.json()
        features = data.get("features", [])
        if not features:
            logger.warning("ICMBio WFS returned no features")
            return None

        # Convert GeoJSON to GeoDataFrame
        import json as json_mod
        from shapely.geometry import shape

        records = []
        for feat in features:
            props = feat.get("properties", {})
            geom_data = feat.get("geometry")
            if not geom_data:
                continue
            try:
                geometry = shape(geom_data)
            except Exception:
                continue
            records.append({**props, "geometry": geometry})

        if not records:
            logger.warning("ICMBio WFS returned no valid geometries")
            return None

        gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
        logger.info("ICMBio WFS returned %d federal conservation units", len(gdf))
        return gdf
    except Exception as exc:
        logger.warning("ICMBio WFS download failed: %s", exc)
        return None


def _download_raisg_anps(
    client: httpx.Client, work: Path, cfg: Any
) -> gpd.GeoDataFrame | None:
    """Download protected areas from RAISG ArcGIS REST."""
    try:
        all_features = []
        offset = 0
        # RAISG returns errors for batch sizes >= 150
        batch_size = 100

        while True:
            response = _request_with_retry(
                client,
                cfg.raisg_anps_url,
                params={
                    "where": "pais='Brasil'",
                    "outFields": "nombre,categoria,pais,fuente",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "f": "json",
                    "resultOffset": str(offset),
                    "resultRecordCount": str(batch_size),
                },
            )
            data = response.json()
            features = data.get("features", [])
            if not features:
                break
            all_features.extend(features)
            if len(features) < batch_size:
                break
            offset += batch_size

        if not all_features:
            logger.warning("RAISG protected areas returned no features")
            return None

        # Convert ArcGIS JSON to GeoDataFrame
        from shapely.geometry import shape

        records = []
        for feat in all_features:
            attrs = feat.get("attributes", {})
            geom_data = feat.get("geometry")
            if not geom_data or "rings" not in geom_data:
                continue
            try:
                geometry = shape({"type": "Polygon", "coordinates": geom_data["rings"]})
            except Exception:
                continue
            records.append({
                "nombre": attrs.get("nombre", ""),
                "categoria": attrs.get("categoria", ""),
                "pais": attrs.get("pais", ""),
                "fuente": attrs.get("fuente", ""),
                "geometry": geometry,
            })

        if not records:
            logger.warning("RAISG protected areas returned no valid geometries")
            return None

        gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
        logger.info("RAISG protected areas returned %d features", len(gdf))
        return gdf
    except Exception as exc:
        logger.warning("RAISG protected areas download failed: %s", exc)
        return None


def _download_cnuc(
    client: httpx.Client, work: Path, cfg: Any
) -> tuple[gpd.GeoDataFrame | None, dict[str, str]]:
    """Download conservation units from CNUC via MMA CKAN."""
    cnuc_meta: dict[str, str] = {
        "url": cfg.cnuc_fallback_url,
        "name": "CNUC fallback",
        "updated": "unknown",
    }

    # Try CKAN discovery first
    try:
        cnuc_meta = _discover_cnuc_resource(client)
    except Exception as exc:
        logger.warning("CNUC CKAN discovery failed: %s", exc)

    # Try downloading the discovered resource
    cnuc_zip = work / "cnuc.zip"
    try:
        _download(client, cnuc_meta["url"], cnuc_zip)
        cnuc_dir = work / "cnuc"
        cnuc_dir.mkdir()
        _safe_extract(cnuc_zip, cnuc_dir)
        return gpd.read_file(_choose_shapefile(cnuc_dir, prefer_polygon=True)), cnuc_meta
    except Exception as exc:
        logger.warning("CNUC download failed (%s)", exc)
        return None, cnuc_meta


def _sync_boundaries_locked() -> dict[str, Any]:
    cfg = env_settings()
    run: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "started_at": _now(),
        "completed_at": None,
        "success": 0,
        "funai_source": cfg.funai_wfs_url,
        "cnuc_source": None,
        "territories_count": 0,
        "conservation_count": 0,
        "error_message": None,
    }
    save_sync_run(run)

    try:
        with tempfile.TemporaryDirectory(dir=cfg.download_dir) as temporary:
            work = Path(temporary)
            headers = {"User-Agent": cfg.user_agent, "Accept": "*/*"}
            timeout = httpx.Timeout(cfg.http_timeout_seconds * 3)
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
            ) as client:
                # Step 1: Download indigenous territories from FUNAI
                funai_zip = _download_funai(client, work, cfg)
                if not funai_zip:
                    raise RuntimeError(
                        t("err_funai_download_failed", _lang())
                    )

                # Step 2: Download conservation units with fallback chain
                # Priority: ICMBio (federal) → CNUC → RAISG protected areas
                conservation_gdf = None
                cnuc_meta = {"url": "", "name": "", "updated": "unknown"}

                # Try ICMBio first (federal conservation units)
                icmbio_gdf = _download_icmbio(client, work, cfg)
                if icmbio_gdf is not None and not icmbio_gdf.empty:
                    conservation_gdf = icmbio_gdf
                    cnuc_meta = {
                        "url": cfg.icmbio_wfs_url,
                        "name": "ICMBio WFS",
                        "updated": datetime.now(timezone.utc).date().isoformat(),
                    }
                    logger.info("Using ICMBio WFS as primary conservation unit source")

                # Try CNUC if ICMBio failed
                if conservation_gdf is None or conservation_gdf.empty:
                    cnuc_gdf, cnuc_meta = _download_cnuc(client, work, cfg)
                    if cnuc_gdf is not None and not cnuc_gdf.empty:
                        conservation_gdf = cnuc_gdf
                        logger.info("Using CNUC as conservation unit source")

                # Try RAISG protected areas as final fallback
                if conservation_gdf is None or conservation_gdf.empty:
                    raisg_gdf = _download_raisg_anps(client, work, cfg)
                    if raisg_gdf is not None and not raisg_gdf.empty:
                        conservation_gdf = raisg_gdf
                        cnuc_meta = {
                            "url": cfg.raisg_anps_url,
                            "name": "RAISG protected areas",
                            "updated": datetime.now(timezone.utc).date().isoformat(),
                        }
                        logger.info("Using RAISG protected areas as conservation unit fallback")

                run["cnuc_source"] = cnuc_meta.get("url", "")

                # Extract and process territories
                funai_dir = work / "FUNAI"
                funai_dir.mkdir()
                _safe_extract(funai_zip, funai_dir)
                territories = gpd.read_file(_choose_shapefile(funai_dir, prefer_polygon=True))

                # Use conservation data if available, otherwise empty
                if conservation_gdf is None:
                    logger.warning("No conservation unit data available; sync will include only indigenous territories")
                    conservation_gdf = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry")

                # Hold the upstream frames only inside the call: the record
                # builder rebinds them to filtered, pruned views right away,
                # which releases the full-resolution originals before the
                # reprojected copies pile up.
                frames = [conservation_gdf, territories]
                conservation_gdf = None
                territories = None
                records = _records_from_frames(frames.pop(), frames.pop(), cnuc_meta)
            territory_count = sum(
                record["category"] == "indigenous_territory" for record in records
            )
            conservation_count = sum(
                record["category"] == "conservation_unit" for record in records
            )
            if territory_count < cfg.boundary_min_territories:
                raise RuntimeError(
                    "Boundary sync sanity check failed: only "
                    f"{territory_count} Indigenous territories were produced "
                    f"(minimum {cfg.boundary_min_territories}). Existing data was preserved."
                )
            if conservation_count < cfg.boundary_min_conservation_units:
                logger.warning(
                    "Only %d conservation units found (minimum %d); continuing with territories only",
                    conservation_count,
                    cfg.boundary_min_conservation_units,
                )
            replace_areas(
                records,
                cfg.auto_select_all_on_first_sync,
                cfg.auto_select_new_areas_when_all_selected,
            )
            regenerate_query_regions()

        run.update(
            {
                "completed_at": _now(),
                "success": 1,
                "territories_count": territory_count,
                "conservation_count": conservation_count,
            }
        )
    except Exception as exc:
        logger.exception("Boundary synchronization failed")
        run.update(
            {
                "completed_at": _now(),
                "success": 0,
                "error_message": str(exc)[:4000],
            }
        )
    save_sync_run(run)
    return run


def cleanup_orphaned_tmp(max_age_hours: int = 24) -> int:
    """Delete tmp* dirs/files under download_dir older than max_age (SIGKILL leftovers). Returns removed count."""
    cfg = env_settings()
    root = Path(cfg.download_dir)
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    if not root.is_dir():
        return 0
    for entry in root.iterdir():
        if not entry.name.startswith("tmp"):
            continue
        try:
            if entry.stat().st_mtime > cutoff:
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed += 1
        except OSError:
            logger.warning("tmp cleanup skipped %s", entry, exc_info=True)
    return removed


async def sync_boundaries() -> dict[str, Any]:
    return await asyncio.to_thread(_sync_boundaries_sync)

"""Real Sentinel-2 temporal evidence, following the official quickstart STAC flow.

Daily vegetation summaries are descriptive spectral evidence, not drought labels.
Only bbox windows of the real COG assets are read; dates remain separate.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import Affine, array_bounds, from_origin
from rasterio.warp import reproject, transform_bounds, transform_geom
from rasterio.windows import Window, from_bounds
import requests

from .tanager import PipelineError, REPO_ROOT, compute_indices, raw_data_dir, sha256, write_json

# Endpoint and collection from references/00_EO_data_quickstart_notebook.ipynb.
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"
OUTPUT_DIR = REPO_ROOT / "outputs" / "sentinel"
SPECTRAL_BANDS = {"red": "B04", "red_edge": "B05", "nir": "B8A", "swir": "B11"}
INDICES = ("NDVI", "NDRE", "NDMI")
SCL_CLASSES = {
    0: "No data", 1: "Saturated/defective", 2: "Topographic cast shadow",
    3: "Cloud shadow", 4: "Vegetation", 5: "Not vegetated", 6: "Water",
    7: "Unclassified", 8: "Medium probability cloud", 9: "High probability cloud",
    10: "Thin cirrus", 11: "Snow/ice",
}
# Conservative clear-land screen, followed by the separate NDVI vegetation test.
ACCEPTED_SCL = (4, 5)
CACHE_VERSION = 1
LIMITATIONS = [
    "Temporal spectral evidence is not ground-truth-confirmed drought, disease, water stress, a probability, or an irrigation recommendation.",
    "NDMI responds to canopy moisture and structure; phenology, harvest, crop type, soil, irrigation, atmosphere and viewing geometry can also change it.",
    "NDVI >= threshold is an uncalibrated PoC vegetation screen, not a crop map; it omits sparse/senescent vegetation and may remove declining pixels.",
    "Vegetation and clear-pixel populations vary by date. Regional medians do not follow a fixed crop cohort or individual fields; inspect coverage and IQR.",
    "SCL can miss clouds/shadows/haze. Excluding water, unclassified and cast-shadow classes is conservative and can introduce sampling bias.",
    "Same-day clear-pixel mosaics may combine different platforms/overpasses. They preserve dates but are not instantaneous images.",
    "Scene cloud filtering and missing/partial coverage create irregular, nonrandom sampling; each retained date receives equal weight.",
    "The robust slope is descriptive, with an uncalibrated stability tolerance and no significance test; the April-July slope is not a diagnosis near June 8.",
    "The recent baseline is one growing-season segment, not a multi-year climatology; its percentile and MAD distance are not probabilities or calibrated anomalies.",
    "Sentinel-2 and Tanager have different spectral responses, spatial resolution and acquisition times; their index values and risk classes are not interchangeable.",
    "Selected Sentinel center wavelengths lie inside 400-1700 nm; this does not simulate Arab Satellite 813 spectral response or truncate broad filter tails.",
    "No ground sensors or validated crop/water-stress labels are available. Sentinel adds temporal context, not statistically independent confirmation of the shared spectral proxies.",
]


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise PipelineError(f"Acquisition datetime lacks a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def cache_dir() -> Path:
    configured = os.environ.get("AGRIPULSE_SENTINEL_DATA_DIR", "").strip()
    if configured:
        directory = Path(configured).expanduser()
        return (directory if directory.is_absolute() else REPO_ROOT / directory).resolve()
    return Path("C:/AgriPulseData/sentinel") if os.name == "nt" else REPO_ROOT / "data/raw/sentinel"


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def source_area() -> tuple[dict, dict]:
    summary_path = REPO_ROOT / "outputs/tanager/scene_summary.json"
    if not summary_path.exists():
        raise PipelineError(f"Run Stage 1 first: missing {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    snapshot = raw_data_dir() / f"{summary['scene_id']}.json"
    if not snapshot.exists() or sha256(snapshot) != summary["stac_snapshot_sha256"]:
        raise PipelineError(f"Missing or changed Tanager STAC snapshot: {snapshot}")
    item = json.loads(snapshot.read_text(encoding="utf-8"))
    if (item["id"] != summary["scene_id"] or item["bbox"] != summary["bbox"]
            or utc(item["properties"]["datetime"]) != utc(summary["acquisition_date"])):
        raise PipelineError("Tanager scene summary and STAC identity/footprint/datetime disagree.")
    return summary, item["geometry"]


def query_catalog(bbox: list, start: str, end: str, cloud_max: float,
                  directory: Path, refresh: bool = False) -> tuple[list[dict], dict]:
    request = {"endpoint": STAC_URL, "collection": COLLECTION, "bbox": bbox,
               "datetime": f"{start}T00:00:00Z/{end}T23:59:59.999999Z",
               "scene_cloud_percent_lt": cloud_max}
    path = directory / f"catalog_{fingerprint(request)[:20]}.json"
    if path.exists() and not refresh:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["query"] != request:
            raise PipelineError("Cached STAC query identity mismatch.")
        print(f"Using saved STAC catalog: {path}", flush=True)
    else:
        # Same STAC client as the official notebook. Sign only at asset access,
        # so expiring SAS credentials are never persisted in the catalog/cache.
        catalog = pystac_client.Client.open(STAC_URL)
        items = catalog.search(collections=[COLLECTION], bbox=bbox,
                               datetime=request["datetime"],
                               query={"eo:cloud_cover": {"lt": cloud_max}}).items()
        saved = {"query": request, "queried_at": datetime.now(timezone.utc).isoformat(),
                 "items": [item.to_dict() for item in items]}
        write_json(path, saved)
    if not saved["items"]:
        raise PipelineError("The real Sentinel-2 STAC search returned no scenes; no substitute data used.")
    return saved["items"], {"path": str(path), "sha256": sha256(path),
                            "query": request, "queried_at": saved["queried_at"]}


def group_daily(items: list[dict]) -> tuple[dict[str, list[dict]], list[str]]:
    """Drop reprocessing duplicates, then group overlapping tiles by UTC day."""
    versions: dict[tuple, dict] = {}
    dropped = []
    for item in sorted(items, key=lambda x: (x["properties"].get("s2:generation_time", ""), x["id"])):
        p = item["properties"]
        key = (p["platform"], p["datetime"], p["s2:mgrs_tile"], p.get("sat:relative_orbit"))
        if key in versions:
            dropped.append(versions[key]["id"])
        versions[key] = item
    grouped = defaultdict(list)
    for item in versions.values():
        grouped[utc(item["properties"]["datetime"]).date().isoformat()].append(item)
    # A coherent four-band vector from the clearest scene wins each overlap;
    # ties have a deterministic item-ID order. NDVI is never used to pick pixels.
    return {day: sorted(grouped[day], key=lambda i: (i["properties"]["eo:cloud_cover"], i["id"]))
            for day in sorted(grouped)}, dropped


def make_grid(bbox: list, geometry: dict, crs: str) -> tuple[dict, np.ndarray]:
    west, south, east, north = transform_bounds("EPSG:4326", crs, *bbox, densify_pts=21)
    west, south = math.floor(west / 20) * 20, math.floor(south / 20) * 20
    east, north = math.ceil(east / 20) * 20, math.ceil(north / 20) * 20
    grid = {"crs": crs, "resolution_m": 20, "width": int((east - west) / 20),
            "height": int((north - south) / 20),
            "transform": list(from_origin(west, north, 20, 20))[:6]}
    mask = geometry_mask([transform_geom("EPSG:4326", crs, geometry)],
                         out_shape=(grid["height"], grid["width"]),
                         transform=Affine(*grid["transform"]), invert=True, all_touched=False)
    if not mask.any():
        raise PipelineError("Tanager footprint has no pixels on the Sentinel grid.")
    return grid, mask


def parse_calibration(xml: bytes) -> dict:
    """Extract product-specific BOA scaling, including post-baseline-04 offsets."""
    root = ET.fromstring(xml)
    elements = list(root.iter())
    local = lambda e: e.tag.rsplit("}", 1)[-1]
    quantification = [float(e.text) for e in elements if local(e) == "BOA_QUANTIFICATION_VALUE"]
    offsets = {e.attrib["band_id"]: float(e.text) for e in elements if local(e) == "BOA_ADD_OFFSET"}
    band_ids = {}
    for e in elements:
        if local(e) == "Spectral_Information":
            name = e.attrib["physicalBand"]
            name = "B" + name[1:].zfill(2) if name[1:].isdigit() else name
            band_ids[name] = e.attrib["bandId"]
    # These 2025 products must explicitly supply offsets; do not guess zero.
    if len(quantification) != 1 or not math.isfinite(quantification[0]) or quantification[0] <= 0:
        raise PipelineError("Missing/invalid BOA_QUANTIFICATION_VALUE in official product XML.")
    result = {}
    for band in SPECTRAL_BANDS.values():
        if band not in band_ids or band_ids[band] not in offsets:
            raise PipelineError(f"Missing official BOA offset for {band}; refusing uncalibrated ratios.")
        offset = offsets[band_ids[band]]
        if not math.isfinite(offset):
            raise PipelineError(f"Nonfinite BOA offset for {band}.")
        result[band] = {"quantification_value": quantification[0], "add_offset_dn": offset,
                        "formula": "(DN + add_offset_dn) / quantification_value"}
    return result


def band_metadata(item: dict) -> dict:
    result = {}
    for role, band in SPECTRAL_BANDS.items():
        asset = item["assets"][band]
        spectral = asset["eo:bands"][0]
        center = float(spectral["center_wavelength"]) * 1000
        if not 400 <= center <= 1700:
            raise PipelineError(f"{band} center wavelength {center} outside 400-1700 nm.")
        result[band] = {"role": role, "center_wavelength_nm": center,
                        "full_width_half_max_nm": float(spectral["full_width_half_max"]) * 1000,
                        "native_resolution_m": asset["gsd"], "analysis_resolution_m": 20}
    return result


def read_cog_window(url: str, grid: dict, categorical: bool = False) -> np.ndarray:
    """Read native-resolution intersecting blocks, then resample only that ROI.

    B04 is area-averaged from 10 m to 20 m without using prebuilt overviews.
    Other inputs use nearest sampling. Any nodata fraction invalidates a cell.
    """
    transform = Affine(*grid["transform"])
    shape = (grid["height"], grid["width"])
    bounds = array_bounds(*shape, transform)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY=3,
                      GDAL_HTTP_RETRY_DELAY=2, GDAL_HTTP_TIMEOUT=90,
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", VSI_CACHE=False):
        with rasterio.open(planetary_computer.sign(url)) as dataset:
            local_bounds = transform_bounds(grid["crs"], dataset.crs, *bounds, densify_pts=21)
            window = from_bounds(*local_bounds, transform=dataset.transform)
            left, top = math.floor(window.col_off) - 1, math.floor(window.row_off) - 1
            right = math.ceil(window.col_off + window.width) + 1
            bottom = math.ceil(window.row_off + window.height) + 1
            left, top, right, bottom = max(0, left), max(0, top), min(dataset.width, right), min(dataset.height, bottom)
            if right <= left or bottom <= top:
                return np.zeros(shape, dtype=np.float32)
            window = Window(left, top, right - left, bottom - top)
            source = dataset.read(1, window=window)
            source_transform = dataset.window_transform(window)
            if dataset.nodata != 0 or dataset.scales != (1.0,) or dataset.offsets != (0.0,):
                raise PipelineError("Unexpected COG nodata/scaling; inspect calibration before continuing.")
            sampling = (Resampling.average if not categorical and abs(dataset.res[0]) < 20
                        else Resampling.nearest)
            destination = np.zeros(shape, dtype=np.float32)
            common = dict(src_transform=source_transform, src_crs=dataset.crs,
                          dst_transform=transform, dst_crs=grid["crs"], resampling=sampling)
            reproject(source, destination, src_nodata=0, dst_nodata=0, **common)
            coverage = np.zeros(shape, dtype=np.float32)
            reproject((source != 0).astype(np.float32), coverage, src_nodata=None, dst_nodata=0, **common)
            destination[coverage < 1 - 1e-6] = 0
            return destination


def window_identity(item: dict, grid: dict) -> dict:
    keys = list(SPECTRAL_BANDS.values()) + ["SCL", "product-metadata"]
    return {"version": CACHE_VERSION, "item_id": item["id"], "grid": grid,
            "assets": {key: item["assets"][key]["href"] for key in keys},
            "resampling": "native-window; B04 average, others nearest; any nodata fraction excluded"}


def load_scene(item: dict, grid: dict, directory: Path, *, offline: bool = False) -> tuple[dict, dict]:
    identity = window_identity(item, grid)
    stem = f"{item['id']}_{fingerprint(identity)[:16]}"
    path, receipt_path = directory / f"{stem}.npz", directory / f"{stem}.json"
    if path.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt["identity"] != identity or receipt["sha256"] != sha256(path):
            raise PipelineError(f"Window cache integrity failure: {path}")
        xml_path = Path(receipt["product_metadata_xml"])
        if (not xml_path.exists() or sha256(xml_path) != receipt["product_metadata_sha256"]
                or parse_calibration(xml_path.read_bytes()) != receipt["calibration"]
                or band_metadata(item) != receipt["bands"]):
            raise PipelineError(f"Window cache calibration/metadata integrity failure: {receipt_path}")
        with np.load(path, allow_pickle=False) as saved:
            arrays = {key: saved[key] for key in (*SPECTRAL_BANDS.values(), "SCL")}
        if any(a.shape != (grid["height"], grid["width"]) for a in arrays.values()):
            raise PipelineError(f"Window cache dimensions disagree with the saved grid: {path}")
        return arrays, receipt
    if offline:
        raise PipelineError(f"Missing real Sentinel window cache: {path}")
    spectral = band_metadata(item)
    response = requests.get(planetary_computer.sign(item["assets"]["product-metadata"]["href"]), timeout=90)
    response.raise_for_status()
    calibration = parse_calibration(response.content)
    xml_path = directory / f"{stem}.xml"
    xml_path.write_bytes(response.content)
    # Independent datasets/read handles; cap network concurrency at four.
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {key: pool.submit(read_cog_window, item["assets"][key]["href"], grid, key == "SCL")
                   for key in (*SPECTRAL_BANDS.values(), "SCL")}
        arrays = {key: future.result() for key, future in pending.items()}
    arrays["SCL"] = arrays["SCL"].astype(np.uint8)
    temporary = path.with_suffix(".npz.part")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    temporary.replace(path)
    receipt = {"identity": identity, "sha256": sha256(path), "path": str(path),
               "calibration": calibration, "bands": spectral,
               "product_metadata_xml": str(xml_path), "product_metadata_sha256": sha256(xml_path)}
    write_json(receipt_path, receipt)
    return arrays, receipt


def scene_indices(arrays: dict, calibration: dict, footprint: np.ndarray) -> tuple[dict, np.ndarray]:
    valid = footprint & np.isin(arrays["SCL"], ACCEPTED_SCL)
    reflectance = {}
    for role, band in SPECTRAL_BANDS.items():
        dn = arrays[band]
        scale = calibration[band]
        # Reflectance is the surface-reflected fraction, after atmospheric correction.
        # DN=0 is nodata BEFORE applying the product-specific additive offset.
        value = (dn.astype(np.float64) + scale["add_offset_dn"]) / scale["quantification_value"]
        valid &= (dn > 0) & np.isfinite(value) & (value >= 0)
        reflectance[role] = value
    # Reuse Stage 1 formulas: Red Edge supports canopy condition; SWIR is
    # moisture-sensitive, but NDMI alone cannot identify the cause of a decline.
    indices = compute_indices(reflectance, valid)
    valid &= np.logical_and.reduce([np.isfinite(indices[name]) for name in INDICES])
    for values in indices.values():
        values[~valid] = np.nan
        if np.any(np.abs(values[valid]) > 1 + 1e-12):
            raise PipelineError("Calibrated normalized index outside [-1, 1].")
    return indices, valid


def merge_clear_pixels(mosaic: dict, occupied: np.ndarray, indices: dict, valid: np.ndarray) -> int:
    """Copy a coherent index vector from one acquisition, without double counting."""
    take = valid & ~occupied
    for name in INDICES:
        mosaic[name][take] = indices[name][take]
    occupied[take] = True
    return int(take.sum())


def vegetation_statistics(indices: dict, valid: np.ndarray, threshold: float) -> tuple[np.ndarray, dict]:
    vegetation = valid & (indices["NDVI"] >= threshold)
    vegetation &= np.logical_and.reduce([np.isfinite(indices[name]) for name in INDICES])
    statistics = {}
    if vegetation.any():
        for name in INDICES:
            values = indices[name][vegetation]
            p25, median, p75 = np.percentile(values, [25, 50, 75])
            statistics[name] = {"min": float(values.min()), "max": float(values.max()),
                                "median": float(median), "p25": float(p25), "p75": float(p75)}
    return vegetation, statistics


def process_day(day: str, items: list[dict], grid: dict, footprint: np.ndarray,
                directory: Path, threshold: float, *, offline: bool = False) -> tuple[dict, dict, np.ndarray]:
    shape = footprint.shape
    mosaic = {name: np.full(shape, np.nan) for name in INDICES}
    occupied = np.zeros(shape, dtype=bool)
    scenes = []
    for item in items:
        arrays, receipt = load_scene(item, grid, directory, offline=offline)
        indices, valid = scene_indices(arrays, receipt["calibration"], footprint)
        contribution = merge_clear_pixels(mosaic, occupied, indices, valid)
        scenes.append({"scene_id": item["id"], "acquisition_datetime": item["properties"]["datetime"],
                       "scene_cloud_percent": item["properties"]["eo:cloud_cover"],
                       "platform": item["properties"]["platform"],
                       "processing_baseline": item["properties"]["s2:processing_baseline"],
                       "valid_pixels_in_footprint": int(valid.sum()), "contributing_pixels": contribution,
                       "window_cache": receipt["path"], "window_sha256": receipt["sha256"],
                       "bands": receipt["bands"], "calibration": receipt["calibration"]})
    vegetation, statistics = vegetation_statistics(mosaic, occupied, threshold)
    times = sorted({scene["acquisition_datetime"] for scene in scenes}, key=utc)
    contributing = [scene["acquisition_datetime"] for scene in scenes if scene["contributing_pixels"]]
    # A daily mosaic has a time range; this representative timestamp is explicit,
    # never falsely presented as the only acquisition when several contributed.
    representative = min(contributing, key=utc) if contributing else times[0]
    valid_count, vegetation_count = int(occupied.sum()), int(vegetation.sum())
    observation = {"date": day, "acquisition_datetime": representative,
                   "acquisition_datetimes": times, "sources": scenes,
                   "valid_pixel_count": valid_count, "vegetation_pixel_count": vegetation_count,
                   "footprint_pixel_count": int(footprint.sum()),
                   "valid_footprint_percentage": 100 * valid_count / int(footprint.sum()),
                   "vegetation_percentage_of_valid": 100 * vegetation_count / valid_count if valid_count else 0.0,
                   "statistics": statistics}
    return observation, mosaic, vegetation


def robust_trend(dates: list[str], values: list[float], stable_tolerance: float = 0.02) -> dict:
    """Theil-Sen: median of all pairwise slopes, using elapsed calendar days."""
    if len(dates) != len(values) or not np.isfinite(values).all():
        raise PipelineError("Trend inputs must be paired finite daily observations.")
    days = np.array([date.fromisoformat(day).toordinal() for day in dates], dtype=float)
    if len(days) > 1 and np.any(np.diff(days) <= 0):
        raise PipelineError("Trend dates must be unique and strictly chronological.")
    result = {"method": "Theil-Sen median of pairwise slopes over elapsed days",
              "observation_count": len(dates), "stable_total_change_tolerance": stable_tolerance,
              "slope_per_day": None, "slope_per_30_days": None, "fitted_change_over_span": None,
              "direction": "insufficient observations"}
    if len(days) < 3:
        return result
    values = np.asarray(values, dtype=float)
    slopes = np.concatenate([(values[i + 1:] - values[i]) / (days[i + 1:] - days[i])
                             for i in range(len(days) - 1)])
    slope = float(np.median(slopes))
    change = slope * float(days[-1] - days[0])
    result.update(slope_per_day=slope, slope_per_30_days=30 * slope,
                  fitted_change_over_span=change, span_days=float(days[-1] - days[0]),
                  direction=("broadly stable" if abs(change) <= stable_tolerance else
                             "increasing" if change > 0 else "decreasing"))
    return result


def closest_observation(observations: list[dict], acquisition: str) -> dict:
    target = utc(acquisition)
    # Compare actual contributing acquisitions, not midnight/date labels.
    candidates = [(abs((utc(scene["acquisition_datetime"]) - target).total_seconds()),
                   scene["acquisition_datetime"], observation, scene)
                  for observation in observations for scene in observation["sources"]
                  if scene["contributing_pixels"] > 0]
    gap, timestamp, observation, scene = min(candidates, key=lambda x: (x[0], x[1], x[3]["scene_id"]))
    return {"date": observation["date"], "acquisition_datetime": timestamp,
            "source_scene_id": scene["scene_id"], "platform": scene["platform"],
            "absolute_gap_days": gap / 86400,
            "signed_gap_days": (utc(timestamp) - target).total_seconds() / 86400,
            "all_daily_acquisition_datetimes": observation["acquisition_datetimes"],
            "daily_vegetation_statistics": observation["statistics"],
            "valid_footprint_percentage": observation["valid_footprint_percentage"],
            "vegetation_pixel_count": observation["vegetation_pixel_count"]}


def baseline_comparison(observations: list[dict], acquisition: str, closest: dict,
                        lookback_days: int = 60, minimum_dates: int = 5,
                        maximum_gap_days: float = 7) -> dict:
    target = utc(acquisition)
    start = target - timedelta(days=lookback_days)
    # Require every acquisition to predate Tanager and remove the compared date
    # if it is itself pre-Tanager; the baseline must not contain its target.
    baseline = [o for o in observations if o["date"] != closest["date"]
                and all(start <= utc(t) < target for t in o["acquisition_datetimes"])]
    result = {"lookback_days": lookback_days, "minimum_dates": minimum_dates,
              "maximum_target_gap_days": maximum_gap_days,
              "window_start": start.isoformat(), "window_end_exclusive": acquisition,
              "dates": [o["date"] for o in baseline], "observation_count": len(baseline),
              "target_date": closest["date"], "available": False,
              "method": "Equal-weight daily vegetation medians; baseline median, unscaled MAD, target-minus-baseline and tie-aware empirical percentile. Excludes target date; no probability."}
    if len(baseline) < minimum_dates or closest["absolute_gap_days"] > maximum_gap_days:
        result["reason"] = "Too few prior dates or nearest usable acquisition is more than the allowed gap away."
        return result
    result["available"] = True
    result["indices"] = {}
    for name in INDICES:
        values = np.array([o["statistics"][name]["median"] for o in baseline])
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        value = closest["daily_vegetation_statistics"][name]["median"]
        percentile = 100 * float((values < value).sum() + 0.5 * (values == value).sum()) / values.size
        result["indices"][name] = {"baseline_median": median, "baseline_mad": mad,
                                  "target_median": value, "target_minus_baseline": value - median,
                                  "target_empirical_percentile": percentile,
                                  "target_distance_in_unscaled_mad": (value - median) / mad if mad > 0 else None,
                                  "mad_distance_defined": mad > 0}
    return result


def save_timeseries(observations: list[dict], output: Path) -> None:
    write_json(output / "sentinel_timeseries.json", {"schema_version": 1, "observations": observations})
    fields = ["date", "acquisition_datetime", "acquisition_datetimes", "scene_ids", "scene_cloud_percent",
              "valid_pixel_count", "vegetation_pixel_count", "footprint_pixel_count",
              "valid_footprint_percentage", "vegetation_percentage_of_valid"]
    fields += [f"{name.lower()}_{stat}" for name in INDICES for stat in ("median", "p25", "p75")]
    temporary = output / "sentinel_timeseries.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for observation in observations:
            row = {key: observation[key] for key in fields if key in observation}
            # Keep parallel CSV source lists aligned; JSON also supplies the
            # distinct chronological acquisition-time list for the daily mosaic.
            row["acquisition_datetimes"] = ";".join(s["acquisition_datetime"] for s in observation["sources"])
            row["scene_ids"] = ";".join(s["scene_id"] for s in observation["sources"])
            row["scene_cloud_percent"] = ";".join(str(s["scene_cloud_percent"]) for s in observation["sources"])
            row.update({f"{name.lower()}_{stat}": observation["statistics"][name][stat]
                        for name in INDICES for stat in ("median", "p25", "p75")})
            writer.writerow(row)
    temporary.replace(output / "sentinel_timeseries.csv")


def plot_timeseries(observations: list[dict], summary: dict, output: Path) -> None:
    os.environ["MPLCONFIGDIR"] = str(output / ".matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    dates = [utc(o["acquisition_datetime"]) for o in observations]
    target = utc(summary["tanager_acquisition_date"])
    years = str(dates[0].year) if dates[0].year == dates[-1].year else f"{dates[0].year}-{dates[-1].year}"
    colors = {"NDVI": "#277044", "NDRE": "#996526", "NDMI": "#246b9b"}

    def finish(fig, filename, dpi=160):
        fig.supxlabel("Copernicus Sentinel-2 L2A | Microsoft Planetary Computer", fontsize=8)
        path = output / filename
        temporary = path.with_suffix(".png.tmp")
        fig.savefig(temporary, format="png", dpi=dpi)
        plt.close(fig)
        temporary.replace(path)

    def draw(axis, name):
        median = [o["statistics"][name]["median"] for o in observations]
        lower = [o["statistics"][name]["p25"] for o in observations]
        upper = [o["statistics"][name]["p75"] for o in observations]
        axis.fill_between(dates, lower, upper, color=colors[name], alpha=0.17,
                          label="Vegetation spatial P25-P75 (not confidence interval)")
        axis.plot(dates, median, "o-", color=colors[name], markersize=3, linewidth=1.1,
                  label="Daily vegetation median (lines guide the eye)")
        axis.axvline(target, color="#813c67", linestyle="--", linewidth=1.4, label=f"Tanager: {target.date().isoformat()}")
        axis.set_ylabel(name)
        axis.set_ylim(-1, 1)
        axis.grid(alpha=0.2)
        trend = summary["temporal_statistics"][name]["trend"]
        slope = trend["slope_per_day"]
        label = f"{trend['direction']}; slope {slope:+.5f}/day" if slope is not None else trend["direction"]
        axis.set_title(f"{name}: {label}", loc="left", fontsize=11)
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

    for name in INDICES:
        fig, axis = plt.subplots(figsize=(11, 4.7), layout="constrained")
        draw(axis, name)
        axis.legend(fontsize=8, loc="lower left")
        fig.suptitle("Sentinel-2 temporal spectral evidence | not a drought diagnosis", fontsize=12)
        axis.set_xlabel(f"{years} acquisition date (UTC); vegetation/clear coverage varies by date")
        finish(fig, f"{name.lower()}_timeseries.png")
    fig, axes = plt.subplots(4, 1, figsize=(12, 12), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1, 1, 0.55]}, layout="constrained")
    for axis, name in zip(axes[:3], INDICES):
        draw(axis, name)
    axes[0].legend(loc="lower left", fontsize=8)
    coverage = [o["valid_footprint_percentage"] for o in observations]
    vegetation = [100 * o["vegetation_pixel_count"] / o["footprint_pixel_count"] for o in observations]
    axes[3].plot(dates, coverage, "o-", markersize=3, label="Valid clear land / footprint")
    axes[3].plot(dates, vegetation, "o-", markersize=3, label="Screened vegetation / footprint")
    axes[3].axvline(target, color="#813c67", linestyle="--")
    axes[3].set_ylim(0, 105)
    axes[3].set_ylabel("Coverage (%)")
    axes[3].set_xlabel(f"{years} acquisition date (UTC) | Changing populations; no fixed crop cohort")
    axes[3].grid(alpha=0.2)
    axes[3].legend(fontsize=8, loc="lower left")
    fig.suptitle("Spectral + temporal evidence over the Tanager footprint\n"
                 "Sentinel-2 vegetation medians and spatial IQR | no ground-truth drought confirmation", fontsize=14)
    finish(fig, "temporal_evidence.png", dpi=170)


def run(args: argparse.Namespace) -> dict:
    summary, geometry = source_area()
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    print(f"Tanager {summary['scene_id']} | {summary['acquisition_date']} | bbox {summary['bbox']}", flush=True)
    print(f"Sentinel window cache: {directory}", flush=True)
    items, catalog = query_catalog(summary["bbox"], args.start_date, args.end_date,
                                   args.cloud_max, directory, args.refresh_catalog)
    grouped, dropped = group_daily(items)
    print(f"STAC scenes: {len(items)}; candidate dates: {len(grouped)}; reprocessing duplicates: {len(dropped)}", flush=True)
    grid, footprint = make_grid(summary["bbox"], geometry, summary["projection"])
    observations, excluded = [], []
    for index, (day, daily_items) in enumerate(grouped.items(), 1):
        print(f"[{index}/{len(grouped)}] {day}: reading {len(daily_items)} scene window(s)", flush=True)
        observation, _, _ = process_day(day, daily_items, grid, footprint, directory, args.ndvi_threshold)
        reasons = []
        if observation["valid_footprint_percentage"] < 100 * args.min_valid_fraction:
            reasons.append("insufficient clear valid footprint coverage")
        if observation["vegetation_pixel_count"] < args.min_vegetation_pixels:
            reasons.append("too few vegetation pixels")
        if reasons:
            excluded.append({**observation, "exclusion_reasons": reasons})
        else:
            observations.append(observation)
        print(f"  {'excluded' if reasons else 'retained'}: clear valid {observation['valid_footprint_percentage']:.1f}%, "
              f"vegetation {observation['vegetation_pixel_count']:,}", flush=True)
    if not observations:
        raise PipelineError("No real dates passed the documented coverage/vegetation filters; no outputs substituted.")
    dates = [o["date"] for o in observations]
    temporal = {}
    for name in INDICES:
        medians = [o["statistics"][name]["median"] for o in observations]
        temporal[name] = {"daily_medians": medians, "median_of_daily_medians": float(np.median(medians)),
                          "min_daily_median": min(medians), "max_daily_median": max(medians),
                          "trend": robust_trend(dates, medians, args.stable_change_tolerance)}
    closest = closest_observation(observations, summary["acquisition_date"])
    bands = observations[0]["sources"][0]["bands"]
    result = {
        "schema_version": 1, "source_scene_id": summary["scene_id"], "bbox": summary["bbox"],
        "footprint_geometry": geometry, "grid": grid, "footprint_pixel_count": int(footprint.sum()),
        "requested_date_range": {"start": args.start_date, "end_inclusive": args.end_date},
        "stac_scenes_found": len(items), "candidate_dates": len(grouped),
        "usable_temporal_observations": len(observations), "dates_used": dates,
        "catalog_snapshot": catalog, "raw_window_directory": str(directory),
        "reprocessing_duplicates_dropped": dropped, "excluded_dates": excluded,
        "tanager_acquisition_date": summary["acquisition_date"], "closest_sentinel_observation": closest,
        "vegetation_threshold": args.ndvi_threshold,
        "vegetation_definition": "Common finite NDVI/NDRE/NDMI, valid clear-land pixel and NDVI >= threshold; uncalibrated PoC, recalculated on each date.",
        "date_quality_filters": {"minimum_valid_footprint_fraction": args.min_valid_fraction,
                                 "minimum_vegetation_pixels": args.min_vegetation_pixels,
                                 "interpretation": "PoC coverage filters, not disease/stress thresholds"},
        "cloud_masking_methodology": {
            "scene_cloud_percent_lt": args.cloud_max, "accepted_scl_classes": list(ACCEPTED_SCL),
            "excluded_scl_classes": {str(k): v for k, v in SCL_CLASSES.items() if k not in ACCEPTED_SCL},
            "pixel_validity": "Pixel center inside actual Tanager polygon AND SCL in {4,5} AND all four reflectances finite/nonnegative AND DN nonzero AND all index denominators > 0; unknown SCL excluded.",
            "denominators": "Valid coverage uses all polygon pixels. Vegetation percentage uses daily valid pixels. Index statistics use daily screened vegetation only."},
        "sentinel_bands": bands, "quality_band": {"name": "SCL", "native_resolution_m": 20},
        "analysis_center_wavelength_window_nm": [400, 1700],
        "calibration": "Each product's official XML BOA_QUANTIFICATION_VALUE and band-specific BOA_ADD_OFFSET; nodata before offset, negative reflectances excluded, not clipped. Per-scene values saved in time series.",
        "spatial_method": "Fixed 20 m UTM grid; exact query bbox, pixel-center clip to actual Tanager STAC polygon. Native COG windows only. B04 10 m area average; other bands/SCL nearest. Any source nodata fraction excluded; no overview substitution.",
        "duplicate_method": "Latest generation per platform/tile/acquisition/orbit. One clear-pixel mosaic per UTC date, sources ordered by scene cloud percentage then ID. First valid coherent band/index vector wins overlaps; each pixel counted once; all acquisition times retained.",
        "trend_methodology": "Equal-weight retained daily medians; Theil-Sen median pairwise slope per elapsed day. Broadly stable if absolute slope times observed span <= configurable 0.02 index units by default; otherwise sign determines direction. At least 3 dates. Descriptive PoC tolerance, no significance test.",
        "temporal_statistics": temporal,
        "baseline_comparison": baseline_comparison(observations, summary["acquisition_date"], closest),
        "interpretation": ("Temporal moisture-related decline evidence over the requested period; causes unconfirmed."
                           if temporal["NDMI"]["trend"]["direction"] == "decreasing" else
                           "No decreasing NDMI trend established over the requested period; this does not rule out local or short-term stress."),
        "limitations": LIMITATIONS,
        "reference_notebook": "references/00_EO_data_quickstart_notebook.ipynb",
        "reference_notebook_sha256": sha256(REPO_ROOT / "references/00_EO_data_quickstart_notebook.ipynb"),
        "software_versions": {name: importlib.metadata.version(name) for name in
                              ("numpy", "rasterio", "pystac-client", "planetary-computer", "matplotlib", "requests")},
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_timeseries(observations, OUTPUT_DIR)
    plot_timeseries(observations, result, OUTPUT_DIR)
    write_json(OUTPUT_DIR / "temporal_summary.json", result)
    print(f"Completed: {len(observations)} usable dates; closest {closest['acquisition_datetime']}; outputs {OUTPUT_DIR}", flush=True)
    for name in INDICES:
        print(f"{name}: {temporal[name]['trend']}", flush=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2025-04-01")
    parser.add_argument("--end-date", default="2025-07-31")
    parser.add_argument("--cloud-max", type=float, default=30)
    parser.add_argument("--ndvi-threshold", type=float, default=0.30)
    parser.add_argument("--min-valid-fraction", type=float, default=0.20)
    parser.add_argument("--min-vegetation-pixels", type=int, default=100)
    parser.add_argument("--stable-change-tolerance", type=float, default=0.02)
    parser.add_argument("--refresh-catalog", action="store_true", help="Query STAC again instead of using the saved query snapshot")
    args = parser.parse_args(argv)
    try:
        if date.fromisoformat(args.start_date) > date.fromisoformat(args.end_date):
            parser.error("start-date must precede end-date")
    except ValueError:
        parser.error("dates must use YYYY-MM-DD")
    if not 0 < args.ndvi_threshold < 1 or not 0 < args.cloud_max <= 100:
        parser.error("ndvi-threshold must be in (0,1); cloud-max in (0,100]")
    if not 0 < args.min_valid_fraction <= 1 or args.min_vegetation_pixels < 1:
        parser.error("min-valid-fraction must be in (0,1]; min-vegetation-pixels must be positive")
    if not math.isfinite(args.stable_change_tolerance) or args.stable_change_tolerance < 0:
        parser.error("stable-change-tolerance must be finite and nonnegative")
    try:
        run(args)
    except (PipelineError, requests.RequestException, rasterio.errors.RasterioError,
            pystac_client.exceptions.APIError, OSError, KeyError, ValueError) as error:
        # Strip SAS query strings from errors; the progress log identifies the
        # last successful date. Never silently skip a data-access failure.
        message = str(error)
        import re
        message = re.sub(r"(https?://[^\s?'\"]+)\?[^\s'\"]+", r"\1?[credentials omitted]", message)
        print(f"Stage 3 stopped: {type(error).__name__}: {message}", file=sys.stderr, flush=True)
        return 1
    return 0

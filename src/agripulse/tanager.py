"""Reproduce the official agriculture notebook's Tanager workflow.

Source: references/01_agriculture_crop_intelligence.ipynb, cells 5, 12,
14, 16, 18, 20, 22, 24, 26. References are read-only source material.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
from threading import Event
import time
from typing import Callable
from urllib.parse import urljoin, urlsplit

import h5py
import numpy as np
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "outputs" / "tanager"

# Exact collection, active scene list, asset keys and HDF5 paths from cells above.
STAC_BASE = "https://www.planet.com/data/stac/tanager-core-imagery/agriculture"
SCENE_IDS = (
    "20250608_091605_90_4001",
    "20250331_113403_16_4001",
    "20250407_035527_47_4001",
)
HDF_ROOT = "HDFEOS/GRIDS/HYP/Data Fields"
MASK_NAMES = ("nodata_pixels", "beta_cloud_mask", "beta_cirrus_mask")
TARGETS_NM = {"red": 665.0, "red_edge": 705.0, "nir": 860.0, "swir": 1650.0}
# Restrict analysis to the requested Arab Satellite 813 compatibility window.
# This is a wavelength constraint, not a simulation of 813's spectral response.
ANALYSIS_RANGE_NM = (400.0, 1700.0)


class PipelineError(RuntimeError):
    """Actionable data-access or validation failure; never use substitute data."""


def raw_data_dir() -> Path:
    """AGRIPULSE_DATA_DIR is the final raw-data directory, not its parent."""
    configured = os.environ.get("AGRIPULSE_DATA_DIR", "").strip()
    if configured:
        directory = Path(configured).expanduser()
        if not directory.is_absolute():
            directory = REPO_ROOT / directory
    elif os.name == "nt":
        directory = Path("C:/AgriPulseData/tanager")
    else:
        directory = REPO_ROOT / "data" / "raw" / "tanager"
    return directory.resolve()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def range_identity(url: str, start: int, stop: int, size: int, etag: str) -> dict:
    return {"url": url, "etag": etag, "content_length_bytes": size,
            "range_start": start, "range_stop": stop}


def saved_range_bytes(path: Path, identity: dict) -> int:
    """Reuse only bytes with matching remote identity, length and local checksum."""
    checkpoint = path.with_suffix(path.suffix + ".json")
    if not path.exists() or not checkpoint.exists():
        return 0
    try:
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        count = path.stat().st_size
        if (all(saved.get(key) == value for key, value in identity.items())
                and 0 < count <= identity["range_stop"] - identity["range_start"] + 1
                and saved.get("downloaded_bytes") == count and saved.get("sha256") == sha256(path)):
            return count
    except (OSError, ValueError):
        pass
    return 0


def download_range(url: str, path: Path, start: int, stop: int, size: int, etag: str,
                   received: int, cancelled: Event) -> Path:
    """Resume an inclusive HTTP range, retaining a checksum checkpoint on failure."""
    expected = stop - start + 1
    request_start = start + received
    headers = {"Accept-Encoding": "identity", "Range": f"bytes={request_start}-{stop}", "If-Match": etag}
    identity = range_identity(url, start, stop, size, etag)
    digest = hashlib.sha256()
    if received:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    last_report = time.monotonic()
    with requests.get(url, headers=headers, stream=True, timeout=(15, 60)) as response:
        response.raise_for_status()
        if (response.status_code != 206
                or response.headers.get("Content-Range") != f"bytes {request_start}-{stop}/{size}"
                or response.headers.get("Content-Length") != str(expected - received)):
            raise PipelineError(f"Server did not honor verified byte range {request_start}-{stop}")
        with path.open("ab" if received else "wb") as stream:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if cancelled.is_set():
                    raise PipelineError("Range request stopped after another download request failed")
                if not chunk:
                    continue
                if received + len(chunk) > expected:
                    raise PipelineError(f"Server sent excess data for byte range {start}-{stop}")
                stream.write(chunk)
                stream.flush()
                digest.update(chunk)
                received += len(chunk)
                # Save after each flushed MiB so an interrupted run can continue safely.
                write_json(path.with_suffix(path.suffix + ".json"),
                           {**identity, "downloaded_bytes": received, "sha256": digest.hexdigest()})
                if time.monotonic() - last_report >= 30:
                    print(f"Range {start}-{stop}: {received / 1024**2:.1f}/{expected / 1024**2:.1f} MiB",
                          flush=True)
                    last_report = time.monotonic()
    if received != expected:
        raise PipelineError(f"Incomplete byte range {start}-{stop}: received {received}/{expected}")
    return path


def download_source(session: requests.Session, url: str, path: Path,
                    checkpoint: Callable[[str], None]) -> dict:
    """Check remote size first; stream atomically and validate cached bytes."""
    with session.head(url, allow_redirects=True, timeout=(15, 60)) as response:
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        if length is None or not length.isdigit() or int(length) <= 0:
            raise PipelineError(f"HEAD did not return a positive Content-Length: {url}")
        size = int(length)
        etag = response.headers.get("ETag")
        supports_ranges = response.headers.get("Accept-Ranges") == "bytes"
    print(f"Remote Content-Length: {size:,} bytes ({size / 1024**2:.2f} MiB)", flush=True)
    checkpoint(f"checked remote Content-Length ({size:,} bytes) and ETag")
    receipt_path = path.with_suffix(path.suffix + ".download.json")
    if path.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (receipt.get("url") == url and receipt.get("content_length_bytes") == size
                and receipt.get("etag") == etag and path.stat().st_size == size
                and receipt.get("sha256") == sha256(path) and h5py.is_hdf5(path)):
            print(f"Reusing verified source: {path.name}", flush=True)
            return receipt
    if shutil.disk_usage(path.parent).free < 2 * size + 100 * 1024**2:
        raise PipelineError(f"Insufficient disk space for {size:,} source bytes plus assembly space")
    partial = path.with_suffix(path.suffix + ".part")
    received = 0
    digest = hashlib.sha256()
    last_report = time.monotonic()
    headers = {"If-Match": etag} if etag else {}
    print(f"Downloading official HDF5 to {path}", flush=True)
    fragments = []
    if supports_ranges and etag:
        chunk_size = 16 * 1024**2
        ranges = [(start, min(start + chunk_size, size) - 1) for start in range(0, size, chunk_size)]
        fragments = [path.with_suffix(f".h5.range-{i:04d}.part") for i in range(len(ranges))]
        pending = []
        resumed_bytes = 0
        for fragment, (start, stop) in zip(fragments, ranges):
            saved = saved_range_bytes(fragment, range_identity(url, start, stop, size, etag))
            if saved == stop - start + 1:
                received += saved
            else:
                resumed_bytes += saved
                pending.append((fragment, start, stop, saved))
        print(f"Reusing {received / 1024**2:.1f} MiB in completed ranges; "
              f"resuming {resumed_bytes / 1024**2:.1f} MiB in partial ranges.", flush=True)
        checkpoint(f"verified {received:,} completed source bytes and {resumed_bytes:,} resumable bytes")
        print("Downloading with four verified HTTP range connections.", flush=True)
        cancelled = Event()
        with ThreadPoolExecutor(max_workers=4) as executor:
            jobs = {executor.submit(download_range, url, fragment, start, stop, size, etag, saved, cancelled):
                    stop - start + 1 for fragment, start, stop, saved in pending}
            try:
                for job in as_completed(jobs):
                    job.result()
                    received += jobs[job]
                    checkpoint(f"verified {received:,} of {size:,} source bytes")
                    print(f"Verified {received / 1024**2:.1f}/{size / 1024**2:.1f} MiB"
                          f" ({received / size:.1%})", flush=True)
            except Exception as exc:
                print(f"Download blocked: {type(exc).__name__}: {exc}\n"
                      "Stopping remaining requests; keeping resume checkpoints.", file=sys.stderr, flush=True)
                cancelled.set()
                for job in jobs:
                    job.cancel()
                raise
        with partial.open("wb") as stream:
            for fragment in fragments:
                with fragment.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        stream.write(chunk)
                        digest.update(chunk)
    else:
        with session.get(url, headers=headers, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise PipelineError(f"Expected full HTTP 200 download, received {response.status_code}")
            if response.headers.get("Content-Length") != str(size):
                raise PipelineError("GET Content-Length differs from HEAD; source may have changed")
            with partial.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    stream.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if time.monotonic() - last_report >= 10:
                        print(f"Downloaded {received / 1024**2:.1f}/{size / 1024**2:.1f} MiB"
                              f" ({received / size:.1%})", flush=True)
                        last_report = time.monotonic()
    if received != size:
        raise PipelineError(f"Incomplete download: {received:,} of {size:,} bytes; retained {partial}")
    if not h5py.is_hdf5(partial):
        raise PipelineError(f"Downloaded asset is not HDF5: {partial}")
    partial.replace(path)
    receipt = {"url": url, "content_length_bytes": size, "etag": etag,
               "sha256": digest.hexdigest()}
    write_json(receipt_path, receipt)
    for fragment in fragments:
        fragment.unlink()
        fragment.with_suffix(fragment.suffix + ".json").unlink(missing_ok=True)
    print("Source download complete and byte count verified.", flush=True)
    return receipt


def select_bands(asset: dict) -> tuple[np.ndarray, dict, list[dict]]:
    spectral = [b for b in asset.get("bands", []) if "eo:center_wavelength" in b]
    wavelengths = np.array([b["eo:center_wavelength"] for b in spectral], dtype=np.float64) * 1000
    if wavelengths.size == 0 or not np.isfinite(wavelengths).all():
        raise PipelineError("Missing or invalid exact STAC bands/eo:center_wavelength metadata")
    if not np.all(np.diff(wavelengths) > 0):
        raise PipelineError("STAC spectral wavelengths are not strictly increasing")
    eligible = np.flatnonzero((wavelengths >= ANALYSIS_RANGE_NM[0])
                             & (wavelengths <= ANALYSIS_RANGE_NM[1]))
    if eligible.size == 0:
        raise PipelineError("No STAC spectral bands inside 400-1700 nm")
    selected = {}
    for name, target in TARGETS_NM.items():
        idx = int(eligible[np.argmin(np.abs(wavelengths[eligible] - target))])
        selected[name] = {"target_nm": target, "wavelength_nm": float(wavelengths[idx]),
                          "band_index_zero_based": idx, "stac_band_name": spectral[idx].get("name")}
        print(f"{name}: target {target:g} nm -> {wavelengths[idx]:.5f} nm (band {idx})", flush=True)
    return wavelengths, selected, spectral


def load_reflectance(path: Path, wavelengths: np.ndarray, selected: dict,
                     spectral: list[dict]) -> tuple[dict, np.ndarray, dict]:
    with h5py.File(path, "r") as source:
        sr = source[f"{HDF_ROOT}/surface_reflectance"]
        if sr.ndim != 3 or sr.shape[0] != len(wavelengths):
            raise PipelineError(f"HDF5 cube shape {sr.shape} does not match STAC spectral bands")
        masks = {name: source[f"{HDF_ROOT}/{name}"][:] for name in MASK_NAMES}
        if any(mask.shape != sr.shape[1:] for mask in masks.values()):
            raise PipelineError("Official masks do not match the surface-reflectance pixel grid")
        valid = np.logical_and.reduce([mask == 0 for mask in masks.values()])
        quality = {"cube_shape_bands_rows_columns": list(sr.shape),
                   "valid_pixel_count": int(valid.sum()), "total_pixel_count": int(valid.size),
                   "valid_pixel_percentage": float(valid.mean() * 100),
                   "mask_flagged_percentages": {
                       name: float((mask != 0).mean() * 100) for name, mask in masks.items()}}
        if not valid.any():
            raise PipelineError("Official quality masks leave no valid pixels")
        reflectance = {}
        for name, selection in selected.items():
            idx = selection["band_index_zero_based"]
            # Reflectance is the fraction of incident sunlight reflected by the surface.
            # This official SR asset stores physical floats directly, with no scale/offset.
            arr = sr[idx, :, :].astype(np.float64)
            nodata = spectral[idx].get("nodata")
            invalid = ~valid | ~np.isfinite(arr) | (arr < 0)
            if isinstance(nodata, (int, float)):
                invalid |= arr == nodata
            arr[invalid] = np.nan
            reflectance[name] = arr
    print(f"Quality-mask valid pixels: {quality['valid_pixel_percentage']:.6f}%", flush=True)
    return reflectance, valid, quality


def normalized_difference(first: np.ndarray, second: np.ndarray, valid: np.ndarray) -> np.ndarray:
    denominator = first + second
    usable = valid & np.isfinite(first) & np.isfinite(second) & (denominator > 0)
    result = np.full(first.shape, np.nan, dtype=np.float64)
    # Preserve the requested formula exactly; mask zero sums instead of adding epsilon.
    np.divide(first - second, denominator, out=result, where=usable)
    return result


def summarize(values: np.ndarray) -> dict:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise PipelineError("No finite valid pixels remain for an index")
    return {"min": float(finite.min()), "max": float(finite.max()),
            "mean": float(finite.mean()), "median": float(np.median(finite)),
            "standard_deviation": float(finite.std(ddof=0)),
            "valid_pixel_count": int(finite.size),
            "valid_pixel_percentage": float(finite.size / values.size * 100)}


def save_plot(path: Path, name: str, values: np.ndarray, scene_id: str) -> None:
    # Keep Matplotlib's cache inside the repository and support headless execution.
    os.environ["MPLCONFIGDIR"] = str(OUTPUT_DIR / ".matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap("BrBG" if name == "NDMI" else "RdYlGn").copy()
    cmap.set_bad("#d9d9d9")
    fig, ax = plt.subplots(figsize=(9, 8), constrained_layout=True)
    plotted = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, vmin=-1, vmax=1,
                        interpolation="nearest")
    ax.set_title(f"{name} | {scene_id}\nGray = excluded pixels")
    ax.set_xlabel("Image column (pixel)")
    ax.set_ylabel("Image row (pixel)")
    fig.colorbar(plotted, ax=ax, label=f"{name} (unitless)", shrink=0.8)
    fig.text(0.5, 0.005, "Planet Labs PBC | CC-BY-4.0", ha="center", fontsize=8)
    temporary = path.with_suffix(".png.tmp")
    fig.savefig(temporary, format="png", dpi=160)
    plt.close(fig)
    temporary.replace(path)


def run_pipeline(scene_id: str) -> None:
    last_success = "initialized pipeline"
    stage = "create source and output directories"

    def checkpoint(message: str) -> None:
        nonlocal last_success
        last_success = message

    try:
        raw_dir = raw_data_dir()
        raw_dir.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Raw satellite data directory: {raw_dir}", flush=True)
        last_success = "created source and output directories"
        stage = "fetch official STAC item"
        stac_url = f"{STAC_BASE}/{scene_id}/{scene_id}.json"
        with requests.Session() as session:
            session.headers.update({"User-Agent": "AgriPulse-813/0.1", "Accept-Encoding": "identity"})
            with session.get(stac_url, timeout=(15, 60)) as response:
                response.raise_for_status()
                item = response.json()
            if item["id"] != scene_id:
                raise PipelineError("Returned STAC scene ID differs from requested official scene")
            stac_path = raw_dir / f"{scene_id}.json"
            write_json(stac_path, item)
            last_success = "fetched and saved official STAC item"
            stage = "validate scene and spectral metadata"
            properties = item["properties"]
            key = "ortho_sr_hdf5" if "ortho_sr_hdf5" in item["assets"] else "basic_sr_hdf5"
            asset = item["assets"][key]
            url = urljoin(stac_url, asset["href"])
            print(f"Scene ID: {scene_id}\nAcquisition date: {properties['datetime']}\n"
                  f"Bbox: {item['bbox']}\nCloud percentage (STAC): {properties.get('cloud_percent')}\n"
                  f"Ground sample distance (STAC gsd): {properties.get('gsd')} m\n"
                  f"Surface-reflectance asset: {key}\nAsset URL: {url}", flush=True)
            wavelengths, selected, spectral = select_bands(asset)
            resolutions = sorted({float(b["raster:spatial_resolution"]) for b in spectral
                                  if "raster:spatial_resolution" in b})
            print(f"Spectral asset pixel resolution: {resolutions} m", flush=True)
            last_success = "validated STAC metadata and selected exact wavelengths"
            stage = "check remote Content-Length and download official surface-reflectance HDF5"
            filename = Path(urlsplit(url).path).name
            if not filename:
                raise PipelineError("Official asset URL has no filename")
            source_path = raw_dir / filename
            receipt = download_source(session, url, source_path, checkpoint)
        last_success = "downloaded or verified full official surface-reflectance HDF5"
        stage = "read official masks and surface-reflectance bands"
        reflectance, valid, quality = load_reflectance(source_path, wavelengths, selected, spectral)
        last_success = "read official quality masks and four real reflectance bands"
        stage = "compute masked indices and valid-pixel statistics"
        # Red Edge responds to canopy chlorophyll changes; it is useful beyond NDVI greenness.
        # SWIR is sensitive to vegetation water absorption, giving NDMI moisture sensitivity.
        indices = {"NDVI": normalized_difference(reflectance["nir"], reflectance["red"], valid),
                   "NDRE": normalized_difference(reflectance["nir"], reflectance["red_edge"], valid),
                   "NDMI": normalized_difference(reflectance["nir"], reflectance["swir"], valid)}
        statistics = {name: summarize(arr) for name, arr in indices.items()}
        summary = {
            "scene_id": scene_id, "acquisition_date": properties["datetime"], "bbox": item["bbox"],
            "location_description": properties.get("location_description"),
            "cloud_percent": properties.get("cloud_percent"),
            "ground_sample_distance_m": properties.get("gsd"),
            "spatial_resolution_m": resolutions, "projection": asset.get("proj:code"),
            "total_spectral_bands": int(wavelengths.size),
            "number_of_bands_inside_400_1700_nm": int(np.count_nonzero(
                (wavelengths >= ANALYSIS_RANGE_NM[0]) & (wavelengths <= ANALYSIS_RANGE_NM[1]))),
            "analysis_wavelength_range_nm": list(ANALYSIS_RANGE_NM),
            "exact_selected_wavelengths": {name: band["wavelength_nm"] for name, band in selected.items()},
            "wavelength_units": "nm", "selected_bands": selected, **quality,
            "valid_pixel_definition": "nodata_pixels == 0 AND beta_cloud_mask == 0 AND beta_cirrus_mask == 0",
            "index_pixel_definition": "quality-valid AND both reflectances finite and nonnegative AND sum > 0",
            "standard_deviation_convention": "population (ddof=0)",
            "surface_reflectance_asset": key, "stac_item_url": stac_url,
            "source_download": receipt, "stac_snapshot_sha256": sha256(stac_path),
            "reference_notebook": "references/01_agriculture_crop_intelligence.ipynb",
            "reference_notebook_sha256": sha256(REPO_ROOT / "references/01_agriculture_crop_intelligence.ipynb"),
            "software_versions": {name: importlib.metadata.version(name)
                                  for name in ("numpy", "h5py", "matplotlib", "requests")},
            "python_version": sys.version.split()[0],
            "data_attribution": "Planet Labs PBC", "license": properties.get("license"),
        }
        last_success = "computed NDVI, NDRE, NDMI and valid-pixel statistics"
        stage = "save result JSON and index PNGs"
        for name, values in indices.items():
            save_plot(OUTPUT_DIR / f"{name.lower()}.png", name, values, scene_id)
        write_json(OUTPUT_DIR / "index_statistics.json", statistics)
        write_json(OUTPUT_DIR / "scene_summary.json", summary)
        print(json.dumps(statistics, indent=2, allow_nan=False), flush=True)
        print(f"SUCCESS: all five results saved under {OUTPUT_DIR}", flush=True)
    except (requests.RequestException, OSError, ValueError, KeyError, PipelineError) as exc:
        raise PipelineError(f"Failed step: {stage}\nLast successful step: {last_success}\n"
                            f"Exact blocker: {type(exc).__name__}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-id", choices=SCENE_IDS, default=SCENE_IDS[0],
                        help="Official agriculture notebook scene (default: its first scene)")
    args = parser.parse_args(argv)
    try:
        run_pipeline(args.scene_id)
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

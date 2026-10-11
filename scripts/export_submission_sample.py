"""Maintainer-only real-data export; the evaluator runs the notebook, not this script.

Requires the existing verified local Stage 1-4.6 artifacts. Never downloads data,
creates substitute measurements, changes upstream outputs, or fits a model.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agripulse import ml, stress, tanager

SAMPLE_SIZE = 2048
SEED = 813


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def select_pixels(mask, count=SAMPLE_SIZE):
    population = np.flatnonzero(mask)
    require(len(population) >= count, "Too few real quality-valid pixels; no fallback")
    rng = np.random.Generator(np.random.PCG64(SEED))
    return np.sort(rng.choice(population, count, replace=False))


def deterministic_npz(arrays):
    """Fixed ZIP timestamps, sorted members, native values in explicit little endian."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for key, value in sorted(arrays.items()):
            array = np.asarray(value)
            array = array.astype(array.dtype.newbyteorder("<"), copy=False)
            member = io.BytesIO()
            np.lib.format.write_array(member, array, allow_pickle=False)
            info = zipfile.ZipInfo(key + ".npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(info, member.getvalue(), compresslevel=9)
    return buffer.getvalue()


def build_package():
    # Authoritative loader verifies HDF5 size/hash, STAC, Stage 1/2 lineage and masks.
    inputs = ml.load_inputs()
    scene = inputs.phase1.summary
    require(scene["license"] == "CC-BY-4.0", "Unexpected source license; stop export")
    summary_path = ROOT / "outputs/ml/ml_summary.json"
    summary = json.loads(summary_path.read_bytes())
    require(summary["scene_id"] == scene["scene_id"], "ML scene mismatch")
    for key, record in inputs.provenance.items():
        require(record["sha256"] == summary["input_provenance"][key]["sha256"],
                f"Stale ML source lineage: {key}")
    evidence_path = ROOT / "outputs/ml/anomaly_pixel_evidence.npz"
    with np.load(evidence_path, allow_pickle=False) as evidence:
        eligible = evidence["eligible_mask"]
        bands = evidence["usable_source_band_indices"]
        require(evidence["scene_id"].item() == scene["scene_id"], "ML evidence scene mismatch")
    require(ml.membership_hash(np.flatnonzero(eligible)) == summary["eligible_membership_sha256"],
            "ML eligibility checksum mismatch")
    require(bands.tolist() == summary["usable_source_band_indices_zero_based"], "ML band mismatch")
    wave = inputs.wavelengths_nm[bands]
    require(not np.any((wave >= 1350) & (wave <= 1450)), "Atmospheric caution bands retained")
    flat = select_pixels(inputs.phase1.quality_mask)
    with h5py.File(inputs.phase1.source_path, "r") as source:
        cube = source[f"{tanager.HDF_ROOT}/surface_reflectance"]
        spectra = np.empty((len(flat), len(bands)), dtype=cube.dtype)
        for column, band in enumerate(bands):
            spectra[:, column] = cube[int(band)].ravel()[flat]
    arrays = dict(spectra=spectra, wavelength_nm=wave, source_band_indices=bands,
                  source_flat_indices=flat, source_shape=np.array(eligible.shape),
                  valid_mask=inputs.phase1.quality_mask.ravel()[flat],
                  scene_id=np.array(scene["scene_id"]))
    for name, selection in scene["selected_bands"].items():
        column = int(np.flatnonzero(bands == selection["band_index_zero_based"])[0])
        values = spectra[:, column].astype(np.float64)
        nodata = inputs.band_metadata[selection["band_index_zero_based"]].get("nodata")
        invalid = ~np.isfinite(values) | (values < 0)
        if isinstance(nodata, (float, int)):
            invalid |= values == nodata
        values[invalid] = np.nan
        arrays[name] = values
    indices = tanager.compute_indices(arrays, arrays["valid_mask"])
    for name in stress.INDEX_NAMES:
        require(np.array_equal(indices[name], inputs.phase1.indices[name].ravel()[flat], equal_nan=True),
                f"Sample {name} does not match authoritative source calculation")
    arrays["vegetation_mask"] = arrays["valid_mask"] & np.isfinite(indices["NDVI"]) & (indices["NDVI"] >= .3)
    complete = np.ones(len(flat), dtype=bool)
    for column, band in enumerate(bands):
        valid, _ = ml.audit_band(spectra[:, column], wave[column], inputs.band_metadata[band].get("nodata"))
        complete &= valid
    arrays["ml_eligible_mask"] = (arrays["vegetation_mask"] & complete
                                  & np.logical_and.reduce([np.isfinite(v) for v in indices.values()]))
    require(np.array_equal(arrays["ml_eligible_mask"], eligible.ravel()[flat]), "Sample ML eligibility mismatch")

    contract = json.loads((ROOT / "examples/product_contract_konya.json").read_bytes())
    fusion = json.loads((ROOT / "dashboard/public/data/konya/fusion.json").read_bytes())
    require(contract["decision_state"] == fusion["decision"] == "GROUND_VERIFICATION_REQUIRED"
            and contract["automation_allowed"] is fusion["automation_allowed"] is False,
            "Validated decision changed")
    cutoff = datetime.fromisoformat(contract["decision_as_of"])
    csv_path = ROOT / "outputs/sentinel/sentinel_timeseries.csv"
    reader = csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8")))
    fields = reader.fieldnames + ["eligible_at_decision_cutoff", "after_decision_cutoff", "operational_availability"]
    rows = list(reader)
    # Cross-check the saved Stage 3 JSON; medians and coverage are never fabricated.
    source_json = ROOT / "outputs/sentinel/sentinel_timeseries.json"
    observations = json.loads(source_json.read_bytes())["observations"]
    require(len(rows) == len(observations), "CSV/JSON observation count mismatch")
    for row, observation in zip(rows, observations):
        require(row["date"] == observation["date"]
                and sorted(row["acquisition_datetimes"].split(";")) == sorted(observation["acquisition_datetimes"]),
                "CSV acquisition provenance mismatch")
        for name in stress.INDEX_NAMES:
            for statistic in ("median", "p25", "p75"):
                require(float(row[f"{name.lower()}_{statistic}"]) == observation["statistics"][name][statistic],
                        "CSV/JSON scientific values differ")
        before = all(datetime.fromisoformat(t) <= cutoff for t in row["acquisition_datetimes"].split(";"))
        row.update(eligible_at_decision_cutoff=str(before).lower(), after_decision_cutoff=str(not before).lower(),
                   operational_availability="not_established")
    decision_dates = [row["date"] for row in rows if row["eligible_at_decision_cutoff"] == "true"]
    require(decision_dates == fusion["temporal_evidence"]["dates_used"], "Decision-time dates differ from validated result")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    package = {"tanager_sample.npz": deterministic_npz(arrays),
               "sentinel_timeseries_sample.csv": stream.getvalue().encode("utf-8")}
    sources = {key: {"file": (Path(record["path"]).name if key in ("source_hdf5", "stac_snapshot")
                              else Path(record["path"]).relative_to(ROOT).as_posix()),
                     "sha256": record["sha256"]} for key, record in inputs.provenance.items()}
    for name, path in [("ml_summary", summary_path), ("ml_pixels", evidence_path),
                       ("sentinel_csv", csv_path), ("sentinel_json", source_json)]:
        sources[name] = {"file": path.relative_to(ROOT).as_posix(), "sha256": tanager.sha256(path)}
    metadata = {
        "schema_version": "submission-A.1", "scene_id": scene["scene_id"],
        "source_date": scene["acquisition_date"], "location": "Konya / Çumra, Türkiye", "bbox": scene["bbox"],
        "attribution": "Planet Labs PBC, CC-BY-4.0; Sentinel-2: Copernicus / ESA via Microsoft Planetary Computer. Reference notebooks: Dr. Vincent Markiet / Space42.",
        "sources": sources, "raw_source_bytes": scene["source_download"]["content_length_bytes"],
        "selection": "Uniform sampling without replacement from sorted quality-valid flat pixel indices, PCG64(813), then sort selected indices. No risk-class stratification.",
        "random_seed": SEED, "sample_size": len(flat), "quality_valid_source_population": int(inputs.phase1.quality_mask.sum()),
        "vegetation_sample_size": int(arrays["vegetation_mask"].sum()),
        "ml_sample_size": int(arrays["ml_eligible_mask"].sum()), "spectral_band_count": len(bands),
        "wavelength_range_nm": [float(wave.min()), float(wave.max())],
        "index_band_centers_nm": scene["exact_selected_wavelengths"],
        "spectra_units": "Physical surface reflectance; unchanged source float32 values, no scaling, smoothing or imputation.",
        "exclusions": "Official nodata/cloud/cirrus mask failures excluded before sampling. Retain existing Stage 4.6 usable bands, excluding 1350-1450 nm inclusive (20 bands). ML additionally requires screened vegetation with finite nonnegative non-nodata spectra at every retained band.",
        "spatial_interpretation": "Noncontiguous pixel sample. Flat indices identify original pixels; array order is not a spatial map.",
        "sentinel_rows": len(rows), "decision_time_rows": len(decision_dates), "retrospective_rows": len(rows)-len(decision_dates),
        "decision_as_of": contract["decision_as_of"],
        "temporal_rule": fusion["temporal_evidence"]["cutoff_rule"],
        "availability_caution": "Acquisition-time eligibility only; historical publication/processing/operational availability is not established.",
        "scope": "Compact calculations reproduce the workflow, not all full-scene statistics. The validated full-scene decision is loaded separately from the committed product contract and evidence package.",
        "artifacts": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in package.items()},
    }
    package["provenance.json"] = encode(metadata)
    return package


def export(destination, check=False):
    package = build_package()
    if check:
        for name, data in package.items():
            saved = (destination / name).read_bytes()
            # New NPZ is byte stable; tolerate checkout newline conversion in text.
            require(saved == data if name.endswith(".npz") else saved.replace(b"\r\n", b"\n") == data,
                    f"Stale sample: {name}")
    else:
        destination.mkdir(parents=True, exist_ok=True)
        for name, data in package.items():
            (destination / name).write_bytes(data)
    print(json.dumps({name: {"bytes": len(data), "sha256": digest(data)} for name, data in package.items()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/sample_input")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    export(args.output_dir, args.check)

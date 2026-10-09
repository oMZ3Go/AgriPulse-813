"""Deterministic, acquisition-time-gated evidence fusion from saved Stages 2/3.

No satellite download, raw raster processing, ground simulation, or actuation.
The decision is a review priority, never a probability or a drought diagnosis.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys

import numpy as np

from . import sentinel, stress, tanager

OUTPUT_DIR = tanager.REPO_ROOT / "outputs/fusion"
DEFAULT_DECISION_AS_OF = "2025-06-09T08:35:59.024Z"  # Explicit user-selected cutoff.
ENGINE_VERSION = "fusion-poc-v1"
INPUT_FILES = {
    "stress_summary": "outputs/stress/stress_summary.json",
    "stress_statistics": "outputs/stress/stress_statistics.json",
    "pixel_evidence": "outputs/stress/pixel_evidence.npz",
    "temporal_summary": "outputs/sentinel/temporal_summary.json",
    "sentinel_timeseries": "outputs/sentinel/sentinel_timeseries.json",
}
SPECTRAL_STATES = ("RELATIVE_HOTSPOTS_PRESENT", "NO_HIGH_RANKED_HOTSPOTS",
                   "NO_MEASURABLE_CONTRAST", "INSUFFICIENT")
TEMPORAL_STATES = ("DECLINE_SUPPORT", "NEUTRAL_OR_MIXED", "RECOVERY_OR_WETTER", "INSUFFICIENT")
GROUND_STATES = ("UNAVAILABLE", "VERIFIED_LOW", "VERIFIED_NORMAL")
LIMITATIONS = [
    "Decision support only: no confirmed water stress/drought, calibrated probability, ML confidence, irrigation prescription or automatic actuation.",
    "Stage 2 ranks are relative within one scene. Hotspot counts/percentages are not drought prevalence or calibrated severity.",
    "NDMI is a moisture-related spectral proxy; phenology, harvest, soil, canopy structure and residual atmosphere can also change it. NDVI/NDRE are supporting context only.",
    "No ground observations exist in this decision. Future low/normal ground states require site/crop/soil/depth calibration, quality checks, temporal validity and spatial relevance.",
    "This is an acquisition-time-gated retrospective reconstruction. Historical publication, processing and operational availability of these archived products are not established; no claim of a live decision made in June 2025.",
    "A same-day mosaic straddling the cutoff is excluded in full; aggregate statistics cannot safely remove its later pixels without reprocessing raw products.",
    "Clear coverage and vegetation populations vary by date. The regional Sentinel median does not validate individual Tanager hotspots or track a fixed crop cohort.",
    "The 60-day baseline is a short seasonal reference, not a climatology. Percentile categories and the 0.02 trend stability tolerance are uncalibrated PoC choices, not significance tests or drought thresholds.",
    "The whole eligible-window slope can hide recent dips; neutral/mixed evidence neither confirms nor rules out local or short-term stress.",
    "Tanager and Sentinel differ in resolution, spectral response and acquisition time. Their shared spectral proxies are correlated; fusion does not create independent ground truth.",
    "Source spectral centers remain inside 400-1700 nm. This is not an Arab Satellite 813 response simulation.",
    "File hashes provide reproducibility and change detection, not source authenticity or verification of all upstream processing. Stage 4 validates saved evidence without reopening raw satellite assets.",
]


@dataclass(frozen=True)
class FusionConfig:
    decision_as_of: str = DEFAULT_DECISION_AS_OF
    stable_change_tolerance: float = 0.02
    baseline_lookback_days: int = 60
    baseline_minimum_dates: int = 5
    maximum_target_gap_days: float = 7.0


@dataclass
class EvidenceInputs:
    stress_summary: dict
    stress_statistics: dict
    pixels: dict[str, np.ndarray]
    temporal_summary: dict
    observations: list[dict]
    provenance: dict


def require(condition: bool, message: str) -> None:
    if not condition:
        raise tanager.PipelineError(f"Evidence validation failed: {message}")


def close(actual, expected, label: str, tolerance: float = 1e-9) -> None:
    require(isinstance(actual, (int, float)) and not isinstance(actual, bool)
            and math.isfinite(actual) and math.isclose(actual, expected, abs_tol=tolerance, rel_tol=1e-10), label)


def same_tree(actual, expected, label: str) -> None:
    """Compare documented saved statistics, with explicit numerical tolerance."""
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and expected.keys() <= actual.keys(), f"{label}: missing fields")
        for key, value in expected.items():
            same_tree(actual[key], value, f"{label}.{key}")
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        close(actual, expected, label)
    else:
        require(actual == expected, label)


def finite_json(value, label: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            finite_json(child, f"{label}.{key}")
    elif isinstance(value, list):
        for child in value:
            finite_json(child, label)
    elif isinstance(value, float):
        require(math.isfinite(value), f"Nonfinite JSON number: {label}")


def load_inputs(root: Path = tanager.REPO_ROOT) -> EvidenceInputs:
    """Hash exactly the bytes parsed; only the five saved evidence files are needed."""
    loaded, provenance = {}, {}
    for name, relative in INPUT_FILES.items():
        path = root / relative
        require(path.is_file(), f"Required input is missing: {path}")
        data = path.read_bytes()
        provenance[name] = {"path": relative, "size_bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest()}
        if name == "pixel_evidence":
            with np.load(io.BytesIO(data), allow_pickle=False) as archive:
                loaded[name] = {key: archive[key] for key in archive.files}
        else:
            loaded[name] = json.loads(data)
            finite_json(loaded[name], relative)
    require(loaded["sentinel_timeseries"].get("schema_version") == 1, "Unknown time-series schema")
    return EvidenceInputs(loaded["stress_summary"], loaded["stress_statistics"], loaded["pixel_evidence"],
                          loaded["temporal_summary"], loaded["sentinel_timeseries"]["observations"], provenance)


def validate_pixels(inputs: EvidenceInputs) -> None:
    """Check the saved explanations against their summaries, without reading HDF5."""
    summary, stats, pixels = inputs.stress_summary, inputs.stress_statistics, inputs.pixels
    required = {"scene_id", "quality_mask", "vegetation_mask", "classified_mask", "risk_score", "risk_class",
                "ndmi_deficit", "support_factor", "ndvi_condition", "ndre_condition"}
    required |= {name.lower() + suffix for name in sentinel.INDICES for suffix in ("", "_percentile")}
    require(required <= pixels.keys(), "Missing Stage 2 pixel evidence layers")
    require(pixels["scene_id"].shape == () and str(pixels["scene_id"].item()) == summary["source_scene_id"],
            "NPZ scene ID does not match Stage 2")
    classified = pixels["classified_mask"]
    require(classified.ndim == 2, "Expected original two-dimensional Tanager grid")
    for key in required - {"scene_id"}:
        require(pixels[key].shape == classified.shape, f"Pixel grid mismatch: {key}")
    quality, vegetation = pixels["quality_mask"], pixels["vegetation_mask"]
    require(all(a.dtype == np.bool_ for a in (classified, quality, vegetation)), "Masks must be boolean")
    require(not (classified & ~vegetation).any() and not (vegetation & ~quality).any(), "Inconsistent mask subsets")
    count = int(classified.sum())
    for key, value in {"total_image_pixels": classified.size, "total_valid_pixels": int(quality.sum()),
                       "vegetation_pixels": int(vegetation.sum()), "classified_vegetation_pixels": count,
                       "vegetation_pixels_missing_index_evidence": int(vegetation.sum()) - count}.items():
        close(summary[key], value, f"Stage 2 {key}", tolerance=0)
    require(quality.any(), "No quality-valid Tanager pixels")
    close(summary["vegetation_percentage"], 100 * vegetation.sum() / quality.sum(), "Stage 2 vegetation percentage")
    threshold = summary["vegetation_threshold"]
    require(0 < threshold < 1, "Invalid Stage 2 vegetation threshold")
    float_layers = [key for key in required if key not in
                    {"scene_id", "quality_mask", "vegetation_mask", "classified_mask", "risk_class", "ndvi_condition", "ndre_condition"}]
    for key in float_layers:
        values = pixels[key]
        require(values.dtype.kind == "f" and np.isfinite(values[classified]).all()
                and np.isnan(values[~classified]).all(), f"Invalid/mis-masked float evidence: {key}")
    require((pixels["ndvi"][classified] >= threshold).all(), "Classified pixels fail the NDVI screen")
    # Successful v1 Stage 2 outputs necessarily have a finite contrast population.
    require(count >= 2, "Stage 2 summary claims a completed ranking with fewer than two classified pixels")
    for name in sentinel.INDICES:
        values = pixels[name.lower()][classified]
        require((np.abs(values) <= 1 + 1e-12).all(), f"{name} outside normalized-index bounds")
        ranks = stress.percentile_ranks(values)
        require(np.allclose(pixels[name.lower() + "_percentile"][classified], ranks, atol=1e-9, rtol=0),
                f"Saved {name} ranks disagree with saved index population")
        same_tree(stats["vegetation_indices"][name], stress.robust_statistics(values), f"Stage 2 {name} statistics")
    deficit = 100 - pixels["ndmi_percentile"][classified]
    factor = (0.8 + 0.1 * (1 - pixels["ndvi_percentile"][classified] / 100)
              + 0.1 * (1 - pixels["ndre_percentile"][classified] / 100))
    for key, expected in (("ndmi_deficit", deficit), ("support_factor", factor), ("risk_score", deficit * factor)):
        require(np.allclose(pixels[key][classified], expected, atol=1e-9, rtol=0), f"Stage 2 formula mismatch: {key}")
    for name in ("ndvi", "ndre"):
        expected = np.zeros(classified.shape, dtype=np.uint8)
        expected[classified] = np.searchsorted((25.0, 75.0), pixels[name + "_percentile"][classified], side="right") + 1
        require(np.array_equal(pixels[name + "_condition"], expected), f"Stage 2 condition mismatch: {name}")
    require(np.array_equal(pixels["risk_class"], stress.classify_scores(pixels["risk_score"])), "Stage 2 class/score mismatch")
    same_tree(stats["risk_score"], stress.robust_statistics(pixels["risk_score"][classified]), "Stage 2 score statistics")
    counts = {name: int((pixels["risk_class"] == code).sum()) for code, name in enumerate(stress.CLASS_NAMES, 1)}
    percentages = {name: 100 * value / count for name, value in counts.items()}
    same_tree(stats["risk_class_counts"], counts, "Stage 2 class counts")
    same_tree(stats["risk_class_percentages"], percentages, "Stage 2 class percentages")
    same_tree(summary["risk_class_percentages"], percentages, "Stage 2 summary class percentages")


def validate_observation(observation: dict, summary: dict) -> None:
    day, sources = observation["date"], observation["sources"]
    require(bool(sources), f"No source acquisitions for {day}")
    times = sorted({s["acquisition_datetime"] for s in sources}, key=sentinel.utc)
    require(observation["acquisition_datetimes"] == times, f"Incomplete acquisition-time list for {day}")
    require(all(sentinel.utc(t).date().isoformat() == day for t in times), f"Mixed UTC days in {day}")
    require(len({s["scene_id"] for s in sources}) == len(sources), f"Duplicate source ID in {day}")
    footprint, valid, vegetation = (observation[k] for k in
                                  ("footprint_pixel_count", "valid_pixel_count", "vegetation_pixel_count"))
    require(all(type(n) is int for n in (footprint, valid, vegetation)) and 0 < vegetation <= valid <= footprint,
            f"Invalid pixel counts for {day}")
    require(footprint == summary["footprint_pixel_count"], f"Changed footprint population on {day}")
    contributions = []
    for source in sources:
        require(source["platform"] in ("Sentinel-2A", "Sentinel-2B", "Sentinel-2C")
                and source["scene_id"].startswith(("S2A_MSIL2A_", "S2B_MSIL2A_", "S2C_MSIL2A_")),
                f"Unexpected non-Sentinel-2 L2A source on {day}")
        require(source["scene_id"][2] == source["platform"][-1]
                and source["scene_id"].split("_")[2] == sentinel.utc(source["acquisition_datetime"]).strftime("%Y%m%dT%H%M%S"),
                f"Sentinel product identity and platform/acquisition timestamp disagree on {day}")
        require(re.fullmatch(r"[0-9a-f]{64}", source["window_sha256"]) is not None,
                f"Invalid source-window hash on {day}")
        n, available = source["contributing_pixels"], source["valid_pixels_in_footprint"]
        require(type(n) is int and type(available) is int and 0 <= n <= available <= footprint,
                f"Invalid source contributions on {day}")
        contributions.append(n)
        require(0 <= source["scene_cloud_percent"] < summary["cloud_masking_methodology"]["scene_cloud_percent_lt"],
                f"Scene cloud filter mismatch on {day}")
        same_tree(source["bands"], summary["sentinel_bands"], f"Sentinel bands on {day}")
    require(sum(contributions) == valid, f"Overlap/contribution counts inconsistent on {day}")
    earliest = min((s["acquisition_datetime"] for s in sources if s["contributing_pixels"]), key=sentinel.utc)
    require(sentinel.utc(observation["acquisition_datetime"]) == sentinel.utc(earliest), f"Representative timestamp mismatch on {day}")
    close(observation["valid_footprint_percentage"], 100 * valid / footprint, f"Valid coverage on {day}")
    close(observation["vegetation_percentage_of_valid"], 100 * vegetation / valid, f"Vegetation coverage on {day}")
    filters = summary["date_quality_filters"]
    require(valid / footprint >= filters["minimum_valid_footprint_fraction"]
            and vegetation >= filters["minimum_vegetation_pixels"], f"Retained date fails Stage 3 coverage filters: {day}")
    for name in sentinel.INDICES:
        stats = observation["statistics"][name]
        values = [stats[k] for k in ("min", "p25", "median", "p75", "max")]
        require(all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
                and -1 - 1e-12 <= values[0] <= values[1] <= values[2] <= values[3] <= values[4] <= 1 + 1e-12,
                f"Invalid {name} distribution on {day}")
    require(observation["statistics"]["NDVI"]["min"] >= summary["vegetation_threshold"], f"NDVI screen mismatch on {day}")


def validate_inputs(inputs: EvidenceInputs) -> None:
    a, b = inputs.stress_summary, inputs.temporal_summary
    for value in (a, inputs.stress_statistics, b, inputs.observations):
        finite_json(value, "saved evidence")
    require(a["source_scene_id"] in tanager.SCENE_IDS and a["source_scene_id"] == b["source_scene_id"],
            "Tanager source scene IDs are incompatible")
    require(sentinel.utc(a["acquisition_date"]) == sentinel.utc(b["tanager_acquisition_date"]),
            "Tanager acquisition datetimes are incompatible")
    require(len(a["bbox"]) == 4 and a["bbox"] == b["bbox"], "Incompatible Stage 2/Stage 3 bbox")
    west, south, east, north = a["bbox"]
    require(-180 <= west < east <= 180 and -90 <= south < north <= 90, "Invalid geographic bbox")
    require(a["methodology"]["name"] == "Scene-relative spectral moisture-stress risk, PoC v1"
            and a["methodology"]["score_is_probability"] is False
            and a["methodology"]["score_range"] == [0, 100], "Unsupported Stage 2 methodology")
    require(a["methodology"]["formula"] ==
            "risk = (100 - P_NDMI) * (0.8 + 0.1*(1 - P_NDVI/100) + 0.1*(1 - P_NDRE/100))",
            "Unsupported Stage 2 score formula")
    require(a["pixel_evidence"]["file"] == "pixel_evidence.npz", "Unexpected Stage 2 evidence source")
    require(a["analysis_wavelength_range_nm"] == [400, 1700]
            and b["analysis_center_wavelength_window_nm"] == [400, 1700], "Incompatible spectral window")
    require(all(400 <= w <= 1700 for w in a["exact_selected_wavelengths_nm"].values()), "Tanager wavelength outside compatibility window")
    require(b["schema_version"] == 1 and b["grid"]["resolution_m"] == 20, "Unsupported Stage 3 schema/grid")
    query = b["catalog_snapshot"]["query"]
    require(query["endpoint"] == sentinel.STAC_URL and query["collection"] == sentinel.COLLECTION
            and query["bbox"] == a["bbox"], "Unexpected Stage 3 catalog/collection/bbox")
    require(set(b["sentinel_bands"]) == set(sentinel.SPECTRAL_BANDS.values()), "Unexpected Sentinel analysis bands")
    for role, band in sentinel.SPECTRAL_BANDS.items():
        require(b["sentinel_bands"][band]["role"] == role
                and 400 <= b["sentinel_bands"][band]["center_wavelength_nm"] <= 1700, f"Invalid Sentinel band {band}")
    require(b["quality_band"]["name"] == "SCL" and b["cloud_masking_methodology"]["accepted_scl_classes"] == [4, 5],
            "Unsupported Stage 3 quality-mask method")
    require(a["vegetation_threshold"] == b["vegetation_threshold"], "Vegetation screens differ; explicit scientific review needed")
    grid, footprint = sentinel.make_grid(b["bbox"], b["footprint_geometry"], b["grid"]["crs"])
    same_tree(b["grid"], grid, "Stage 3 footprint grid")
    close(b["footprint_pixel_count"], int(footprint.sum()), "Stage 3 footprint pixel count", tolerance=0)
    for digest in (a["phase1_summary_sha256"], a["source_hdf5_sha256"], b["catalog_snapshot"]["sha256"]):
        require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "Invalid upstream provenance hash")
    require(0 < b["date_quality_filters"]["minimum_valid_footprint_fraction"] <= 1
            and b["date_quality_filters"]["minimum_vegetation_pixels"] >= 1, "Invalid Stage 3 coverage filters")
    validate_pixels(inputs)
    observations = inputs.observations
    dates = [o["date"] for o in observations]
    require(bool(dates) and dates == sorted(set(dates)), "Sentinel daily observations must be unique and chronological")
    require(dates == b["dates_used"] and len(dates) == b["usable_temporal_observations"], "Stage 3 date/count mismatch")
    require(b["candidate_dates"] == len(dates) + len(b["excluded_dates"]), "Stage 3 candidate-date count mismatch")
    source_count = sum(len(o["sources"]) for o in observations + b["excluded_dates"])
    require(b["stac_scenes_found"] == source_count + len(b["reprocessing_duplicates_dropped"]), "Stage 3 scene count mismatch")
    period = b["requested_date_range"]
    require(all(period["start"] <= day <= period["end_inclusive"] for day in dates), "Observation outside requested date range")
    for observation in observations:
        validate_observation(observation, b)
    # Full-season fields are checked for consistency here, NEVER used in the
    # decision-time classification. Tampered inputs fail instead of being fused.
    for name in sentinel.INDICES:
        medians = [o["statistics"][name]["median"] for o in observations]
        saved = b["temporal_statistics"][name]
        require(saved["daily_medians"] == medians, f"Stage 3 saved {name} medians disagree with the time series")
        same_tree(saved, {"median_of_daily_medians": float(np.median(medians)),
                          "min_daily_median": min(medians), "max_daily_median": max(medians)}, f"Stage 3 {name} summary")
        tolerance = saved["trend"]["stable_total_change_tolerance"]
        require(math.isfinite(tolerance) and tolerance >= 0, "Invalid retrospective trend tolerance")
        same_tree(saved["trend"], sentinel.robust_trend(dates, medians, tolerance), f"Retrospective {name} trend")
    closest = sentinel.closest_observation(observations, a["acquisition_date"])
    same_tree(b["closest_sentinel_observation"], closest, "Stage 3 closest observation")
    baseline = b["baseline_comparison"]
    same_tree(baseline, sentinel.baseline_comparison(observations, a["acquisition_date"], closest,
              baseline["lookback_days"], baseline["minimum_dates"], baseline["maximum_target_gap_days"]), "Stage 3 baseline")


def spectral_evidence(inputs: EvidenceInputs, as_of: str) -> dict:
    summary, stats, pixels = inputs.stress_summary, inputs.stress_statistics, inputs.pixels
    classified = pixels["classified_mask"]
    contrast = float(np.ptp(pixels["ndmi"][classified]))
    present = bool(((pixels["risk_class"] >= 3) & classified).any())
    if sentinel.utc(summary["acquisition_date"]) > sentinel.utc(as_of):
        state = "INSUFFICIENT"
        return {"state": state, "reason": "Tanager acquisition is after decision_as_of; its spectral evidence is excluded."}
    state = ("NO_MEASURABLE_CONTRAST" if contrast <= 1e-12 else
             "RELATIVE_HOTSPOTS_PRESENT" if present else "NO_HIGH_RANKED_HOTSPOTS")
    return {"state": state, "source_scene_id": summary["source_scene_id"],
            "acquisition_datetime": summary["acquisition_date"],
            "classified_vegetation_pixels": summary["classified_vegetation_pixels"],
            "vegetation_threshold": summary["vegetation_threshold"],
            "relative_score_median": stats["risk_score"]["median"],
            "relative_score_maximum": stats["risk_score"]["max"], "score_is_probability": False,
            "relative_hotspots_present": present, "ndmi_spatial_range": contrast,
            "methodology": summary["methodology"]["name"],
            "interpretation": "Saved High/Very High relative ranks (score >= 50) prioritize ground sampling; their extent is NOT drought prevalence or calibrated severity."}


def temporal_category(percentile: float | None, trend_direction: str, *, baseline_available: bool) -> tuple[str, str, str]:
    """Require agreement of low/high NDMI position and a directional NDMI trend."""
    require(trend_direction in ("increasing", "decreasing", "broadly stable", "insufficient observations"), "Unknown temporal direction")
    if not baseline_available or percentile is None or trend_direction == "insufficient observations":
        return "INSUFFICIENT", "UNAVAILABLE", "A usable baseline and at least three historical dates are required."
    require(math.isfinite(percentile) and 0 <= percentile <= 100, "NDMI baseline percentile outside [0,100]")
    position = "RELATIVELY_LOW" if percentile < 25 else "RELATIVELY_HIGH" if percentile > 75 else "BROAD_HISTORICAL_RANGE"
    if position == "RELATIVELY_LOW" and trend_direction == "decreasing":
        return "DECLINE_SUPPORT", position, "Low NDMI baseline rank and decreasing historical NDMI agree; moisture-related decline evidence only."
    if position == "RELATIVELY_HIGH" and trend_direction == "increasing":
        return "RECOVERY_OR_WETTER", position, "High NDMI baseline rank and increasing historical NDMI agree; a relative spectral state, not measured recovery."
    return "NEUTRAL_OR_MIXED", position, "NDMI baseline position and trend do not jointly support a directional state; central, stable or conflicting evidence remains neutral/mixed."


def temporal_evidence(observations: list[dict], tanager_datetime: str, config: FusionConfig) -> tuple[dict, dict]:
    cutoff = sentinel.utc(config.decision_as_of)
    eligible, excluded = [], []
    for observation in observations:
        latest = max(sentinel.utc(t) for t in observation["acquisition_datetimes"])
        if latest <= cutoff:
            eligible.append(observation)
        else:
            excluded.append({"date": observation["date"], "latest_acquisition_datetime": latest.isoformat(),
                             "reason": "At least one source acquisition is after decision_as_of; whole daily mosaic excluded."})
    dates = [o["date"] for o in eligible]
    trends = {name: sentinel.robust_trend(dates, [o["statistics"][name]["median"] for o in eligible],
                                        config.stable_change_tolerance) for name in sentinel.INDICES}
    result = {"historical_observations_used": len(eligible),
              "observations_strictly_before_cutoff": sum(max(sentinel.utc(t) for t in o["acquisition_datetimes"]) < cutoff for o in eligible),
              "dates_used": dates, "decision_time_trends": trends,
              "cutoff_rule": "All listed source acquisitions of a daily mosaic must be <= decision_as_of; straddling mosaics excluded in full.",
              "closest_observation": None, "baseline": {"available": False, "reason": "No eligible observations"}}
    if eligible:
        closest = sentinel.closest_observation(eligible, tanager_datetime)
        baseline = sentinel.baseline_comparison(eligible, tanager_datetime, closest, config.baseline_lookback_days,
                                                config.baseline_minimum_dates, config.maximum_target_gap_days)
        result["closest_observation"] = {key: closest[key] for key in
                ("date", "acquisition_datetime", "source_scene_id", "absolute_gap_days", "daily_vegetation_statistics")}
        result["baseline"] = baseline
    baseline = result["baseline"]
    percentile = baseline["indices"]["NDMI"]["target_empirical_percentile"] if baseline["available"] else None
    state, position, reason = temporal_category(percentile, trends["NDMI"]["direction"], baseline_available=baseline["available"])
    result.update(state=state, ndmi_baseline_position=position, category_reason=reason,
                  ndmi_baseline_percentile=percentile,
                  supporting_context="NDVI/NDRE trends and baseline comparisons describe vegetation condition only; they do not select the moisture state.")
    return result, {"eligible_dates": dates, "excluded_observations": excluded,
                    "excluded_count": len(excluded), "excluded_data_used_in_decision": False}


# Ordered, exhaustive categorical rules. Every branch requires human oversight.
# VERIFIED_* states are future contracts, exercised only by unit tests today.
RULES = [
    {"id": "D01", "any_insufficient_satellite": True, "decision": "INSUFFICIENT_EVIDENCE",
     "reason": "At least one required satellite evidence component is insufficient.",
     "next_step": "Resolve missing or temporally ineligible satellite evidence, then rerun the review; do not infer stress from missing data."},
    {"id": "D02", "spectral": ["RELATIVE_HOTSPOTS_PRESENT"], "temporal": ["DECLINE_SUPPORT"], "ground": ["VERIFIED_LOW"],
     "decision": "ACTION_REVIEW_REQUIRED", "reason": "Relative hotspots, temporal decline support and site-verified low ground moisture agree.",
     "next_step": "Request human agronomic review of the corroborated evidence, crop/soil context and sensor representativeness before considering any action."},
    {"id": "D03", "ground": ["VERIFIED_LOW"], "decision": "ELEVATED_CONCERN",
     "reason": "Site-verified low ground moisture warrants local review, while satellite evidence does not fully agree.",
     "next_step": "Review local ground conditions and calibration with an agronomist; investigate the spatial or temporal disagreement."},
    {"id": "D04", "ground": ["VERIFIED_NORMAL"], "temporal": ["DECLINE_SUPPORT"],
     "decision": "GROUND_VERIFICATION_REQUIRED", "reason": "Temporal decline evidence conflicts with the site-normal ground interpretation.",
     "next_step": "Check sensor calibration, timing and field representativeness; repeat representative measurements to resolve the disagreement."},
    {"id": "D05", "ground": ["VERIFIED_NORMAL"], "decision": "MONITOR",
     "reason": "Site-normal ground evidence and absence of temporal decline support do not justify escalation.",
     "next_step": "Continue observation and review local conditions if evidence changes; no irrigation escalation is authorized."},
    {"id": "D06", "spectral": ["RELATIVE_HOTSPOTS_PRESENT"], "ground": ["UNAVAILABLE"],
     "decision": "GROUND_VERIFICATION_REQUIRED", "reason": "Relative hyperspectral hotspots offer sampling priorities, but ground verification is unavailable.",
     "next_step": "Review the hotspot map against field boundaries; obtain quality-checked, site-calibrated soil-moisture observations in representative hotspot and comparison areas before considering an intervention."},
    {"id": "D07", "temporal": ["DECLINE_SUPPORT"], "ground": ["UNAVAILABLE"],
     "decision": "GROUND_VERIFICATION_REQUIRED", "reason": "Temporal moisture-related decline evidence requires local verification of its cause.",
     "next_step": "Arrange representative ground verification and inspect crop/soil context; do not treat the spectral decline as confirmed water stress."},
    {"id": "D08", "decision": "MONITOR", "reason": "Available evidence supplies neither relative high-ranked hotspots nor temporal decline support.",
     "next_step": "Continue monitoring and seek ground context when available; absence of these signals does not establish absence of stress."},
]


def select_rule(spectral_state: str, temporal_state: str, ground_state: str) -> dict:
    require(spectral_state in SPECTRAL_STATES and temporal_state in TEMPORAL_STATES and ground_state in GROUND_STATES,
            "Unknown evidence state; refusing a permissive fallback")
    for rule in RULES:
        if rule.get("any_insufficient_satellite"):
            if "INSUFFICIENT" not in (spectral_state, temporal_state):
                continue
        if any(value not in rule.get(key, [value]) for key, value in
               (("spectral", spectral_state), ("temporal", temporal_state), ("ground", ground_state))):
            continue
        return {"rule_id": rule["id"], "decision": rule["decision"], "automation_allowed": False,
                "recommended_next_step": rule["next_step"], "reason": rule["reason"]}
    raise tanager.PipelineError("Decision matrix is incomplete")


def reasoning_trace(spectral: dict, temporal: dict, ground: dict, rule: dict) -> list[dict]:
    trace = [{"rule_id": "SPECTRAL_" + spectral["state"],
              "explanation": (f"Relative hyperspectral hotspots are available within {spectral['classified_vegetation_pixels']:,} classified vegetation pixels. Their extent is not drought prevalence."
                              if spectral["state"] == "RELATIVE_HOTSPOTS_PRESENT" else spectral.get("reason", spectral.get("interpretation", spectral["state"])))}]
    if temporal["baseline"]["available"]:
        ndmi = temporal["baseline"]["indices"]["NDMI"]
        explanation = (f"Closest eligible Sentinel NDMI is {ndmi['target_median']:.4f}, at percentile "
                       f"{ndmi['target_empirical_percentile']:.2f} of {temporal['baseline']['observation_count']} prior daily medians: "
                       f"{temporal['ndmi_baseline_position']}. This rank is not a probability.")
    else:
        explanation = "A usable decision-time NDMI baseline comparison is unavailable."
    trace.append({"rule_id": "TEMPORAL_BASELINE_" + temporal["ndmi_baseline_position"], "explanation": explanation})
    trend = temporal["decision_time_trends"]["NDMI"]
    slope = trend["slope_per_day"]
    text = (f"Using {temporal['historical_observations_used']} eligible daily observations, the historical NDMI slope is "
            f"{slope:+.6f} index units/day ({trend['direction']})." if slope is not None else
            "Fewer than three eligible daily observations: no decision-time NDMI trend can be estimated.")
    trace.extend([
        {"rule_id": "TEMPORAL_TREND", "explanation": text + " Observations after the cutoff are not used."},
        {"rule_id": "TEMPORAL_" + temporal["state"], "explanation": temporal["category_reason"]},
        {"rule_id": "GROUND_" + ground["state"], "explanation": ground["reason"]},
        {"rule_id": rule["rule_id"], "explanation": rule["reason"] + " Result: " + rule["decision"] + "."},
        {"rule_id": "AUTOMATION_DISABLED", "explanation": "Stage 4 permits decision support and human review only. Automatic irrigation and pump activation are blocked in every rule."},
    ])
    return trace


def fuse(inputs: EvidenceInputs, config: FusionConfig = FusionConfig()) -> tuple[dict, dict]:
    validate_inputs(inputs)
    sentinel.utc(config.decision_as_of)
    require(math.isfinite(config.stable_change_tolerance) and config.stable_change_tolerance >= 0,
            "Invalid decision-time stability tolerance")
    require(config.baseline_lookback_days > 0 and config.baseline_minimum_dates >= 1
            and math.isfinite(config.maximum_target_gap_days) and config.maximum_target_gap_days > 0, "Invalid baseline configuration")
    spectral = spectral_evidence(inputs, config.decision_as_of)
    temporal, audit = temporal_evidence(inputs.observations, inputs.stress_summary["acquisition_date"], config)
    # No ground file, dummy measurement, hardware adapter or CLI override exists.
    ground = {"state": "UNAVAILABLE", "observations": [], "reason": "No real ground measurements are available; none have been simulated or inferred from satellite indices."}
    rule = select_rule(spectral["state"], temporal["state"], ground["state"])
    decision = {"schema_version": 1, "engine_version": ENGINE_VERSION,
                "decision_as_of": config.decision_as_of,
                "source_scene_id": inputs.stress_summary["source_scene_id"], "bbox": inputs.stress_summary["bbox"],
                "decision": rule["decision"], "matched_rule_id": rule["rule_id"], "automation_allowed": False,
                "recommended_next_step": rule["recommended_next_step"], "spectral_evidence": spectral,
                "temporal_evidence": temporal, "ground_evidence": ground,
                "reasoning_trace": reasoning_trace(spectral, temporal, ground, rule), "limitations": LIMITATIONS}
    summary = {"schema_version": 1, "engine_version": ENGINE_VERSION, "configuration": asdict(config),
               "decision": decision["decision"], "matched_rule_id": rule["rule_id"], "automation_allowed": False,
               "input_provenance": inputs.provenance,
               "validation": "Cross-checked scene/time/bbox, Stage 2 saved pixel masks/ranks/formula/statistics, Stage 3 dates/sources/counts/distributions/summary statistics. No raw assets reopened.",
               "upstream_lineage": {"phase1_summary_sha256": inputs.stress_summary["phase1_summary_sha256"],
                                    "source_hdf5_sha256": inputs.stress_summary["source_hdf5_sha256"],
                                    "sentinel_catalog_sha256": inputs.temporal_summary["catalog_snapshot"]["sha256"],
                                    "note": "Upstream hashes retained as reported; Stage 4 does not rehash raw assets or the external catalog."},
               "temporal_selection_audit": audit,
               "decision_time_evidence": {"spectral": spectral, "temporal": temporal, "ground": ground},
               "methodology": {"spectral_role": "Spatial prioritization only; hotspot fraction never selects severity.",
                               "temporal_rule": "NDMI percentile <25 AND decreasing trend => DECLINE_SUPPORT; >75 AND increasing => RECOVERY_OR_WETTER; other sufficient combinations => NEUTRAL_OR_MIXED; missing baseline/trend => INSUFFICIENT. Boundaries 25 and 75 are central.",
                               "trend": "Stage 3 Theil-Sen method applied anew to eligible daily medians only, including the cutoff acquisition. Absolute fitted change <= stability tolerance is broadly stable.",
                               "baseline": "Recomputed from eligible daily medians in the configured lookback strictly before Tanager, excluding the compared date; no future seasonal baseline field drives the decision.",
                               "ground": "Unavailable in the production entry point. VERIFIED_* branches are future contracts, without universal soil-moisture thresholds.",
                               "automation": "Always false, including future-rule scenarios with ground evidence."},
               "retrospective_context_not_used_for_decision": {
                   "used_in_decision": False, "requested_date_range": inputs.temporal_summary["requested_date_range"],
                   "observation_count": len(inputs.observations),
                   "full_season_trends": {name: inputs.temporal_summary["temporal_statistics"][name]["trend"] for name in sentinel.INDICES},
                   "warning": "These full-season trends can include later observations. They are retained for audit/context only, never as information available at decision_as_of."},
               "limitations": LIMITATIONS}
    return decision, summary


def decision_matrix() -> dict:
    return {"engine_version": ENGINE_VERSION, "evaluation": "First matching rule, in listed order; all valid states covered.",
            "automation_allowed_for_every_rule": False,
            "spectral_states": list(SPECTRAL_STATES), "temporal_states": list(TEMPORAL_STATES), "ground_states": list(GROUND_STATES),
            "rules": [{**rule, "automation_allowed": False} for rule in RULES],
            "future_ground_contract": {
                "implemented_in_stage4": False,
                "current_production_state": "UNAVAILABLE",
                "verified_state_requirements": "A future validator must check sensor identity, timestamp <= decision_as_of, calibrated freshness, spatial relevance, valid quality, depth/crop/soil context and site-specific interpretation. Missing/invalid/uninterpretable readings remain UNAVAILABLE. No universal moisture threshold is defined.",
                "interpretation_to_state": {"LOW_FOR_SITE": "VERIFIED_LOW", "WITHIN_SITE_RANGE": "VERIFIED_NORMAL", "UNDETERMINED": "UNAVAILABLE"},
                "observation_schema": {
                    "type": "object", "additionalProperties": False,
                    "required": ["sensor_id", "sensor_timestamp", "soil_moisture_value", "soil_moisture_unit", "location", "quality_valid", "calibration_reference", "interpretation", "interpretation_authority"],
                    "properties": {
                        "sensor_id": {"type": "string", "minLength": 1},
                        "sensor_timestamp": {"type": "string", "format": "date-time"},
                        "soil_moisture_value": {"type": "number"},
                        "soil_moisture_unit": {"type": "string", "minLength": 1},
                        "location": {"type": "object", "required": ["latitude", "longitude"], "additionalProperties": False,
                                     "properties": {"latitude": {"type": "number", "minimum": -90, "maximum": 90},
                                                    "longitude": {"type": "number", "minimum": -180, "maximum": 180}}},
                        "quality_valid": {"type": "boolean"},
                        "measurement_depth_cm": {"type": "number", "minimum": 0},
                        "calibration_reference": {"type": "string", "minLength": 1},
                        "interpretation": {"enum": ["LOW_FOR_SITE", "WITHIN_SITE_RANGE", "UNDETERMINED"]},
                        "interpretation_authority": {"type": "string", "minLength": 1},
                    }}}}


def save_report(decision: dict, summary: dict, output: Path) -> None:
    spectral, temporal = decision["spectral_evidence"], decision["temporal_evidence"]
    lines = ["# Stage 4 - Evidence Fusion & Decision Engine", "",
             f"**Decision: {decision['decision']}**", "", f"Decision as of: `{decision['decision_as_of']}` (acquisition-time cutoff).",
             f"Source scene: `{decision['source_scene_id']}`.", "", "**Automation allowed: false. No irrigation or pump action is authorized.**", "",
             "## Evidence available at the cutoff", "", f"- Spectral evidence: `{spectral['state']}`.",
             f"- Temporal evidence: `{temporal['state']}`.", f"- Ground evidence: `{decision['ground_evidence']['state']}`; no measurements provided.",
             f"- Eligible daily Sentinel observations: **{temporal['historical_observations_used']}** ({temporal['observations_strictly_before_cutoff']} strictly before the cutoff).",
             f"- Later/straddling daily observations excluded: **{summary['temporal_selection_audit']['excluded_count']}**.", ""]
    if "classified_vegetation_pixels" in spectral:
        lines += [f"Tanager provides {spectral['classified_vegetation_pixels']:,} classified vegetation pixels. Relative score median: {spectral['relative_score_median']:.4f}; maximum: {spectral['relative_score_maximum']:.4f}.",
                  "These scores rank spatial sampling priorities; they are not probabilities, and hotspot extent is not drought prevalence.", ""]
    trend = temporal["decision_time_trends"]["NDMI"]
    if trend["slope_per_day"] is not None:
        lines += [f"Decision-time NDMI Theil-Sen slope: **{trend['slope_per_day']:+.9f} index units/day**, {trend['direction']}, using {trend['observation_count']} dates over {trend['span_days']:g} days.", ""]
    if temporal["baseline"]["available"]:
        lines += [f"The baseline uses {temporal['baseline']['observation_count']} eligible daily medians in the preceding {temporal['baseline']['lookback_days']} days strictly before Tanager. The compared date is excluded.", "",
                  "| Index | Baseline median | Unscaled MAD | Closest median | Baseline percentile |", "| --- | ---: | ---: | ---: | ---: |"]
        for name, values in temporal["baseline"]["indices"].items():
            lines.append(f"| {name} | {values['baseline_median']:.6f} | {values['baseline_mad']:.6f} | {values['target_median']:.6f} | {values['target_empirical_percentile']:.2f} |")
        lines += ["", f"Closest eligible Sentinel acquisition: `{temporal['closest_observation']['acquisition_datetime']}`.",
                  "Percentiles are empirical ranks, not probabilities. NDVI/NDRE are supporting vegetation context, not independent moisture diagnoses.", ""]
    lines += ["## Why this decision was produced", ""]
    lines += [f"{i}. **{entry['rule_id']}**: {entry['explanation']}" for i, entry in enumerate(decision["reasoning_trace"], 1)]
    lines += ["", "## Recommended next step", "", decision["recommended_next_step"], "",
              "## Rules and temporal separation", "",
              summary["methodology"]["temporal_rule"], "",
              "Trend uses the median pairwise slope per elapsed day. An absolute fitted change <= 0.02 across the eligible span is broadly stable by default. These are uncalibrated descriptive PoC categories.", "",
              "The full April-July seasonal analysis remains only in fusion_summary.json under retrospective_context_not_used_for_decision. No later observations enter the decision-time trend, target selection or baseline.", "",
              "The future ground schema and ordered rule matrix are in decision_matrix.json. VERIFIED_LOW/NORMAL require future site-calibrated validation; Stage 4 supplies no ground measurement. Every rule blocks automatic action.", "",
              "## Provenance", "", "| Input | SHA-256 |", "| --- | --- |"]
    lines += [f"| {record['path']} | `{record['sha256']}` |" for record in summary["input_provenance"].values()]
    lines += ["", "## Limitations", ""] + [f"- {text}" for text in LIMITATIONS]
    path = output / "decision_report.md"
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_figure(decision: dict, output: Path) -> None:
    os.environ["MPLCONFIGDIR"] = str(output / ".matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    import textwrap

    spectral, temporal = decision["spectral_evidence"], decision["temporal_evidence"]
    spectral_text = spectral.get("reason", "")
    if "classified_vegetation_pixels" in spectral:
        spectral_text = (f"{spectral['classified_vegetation_pixels']:,} classified vegetation pixels | relative score median "
                         f"{spectral['relative_score_median']:.2f}, maximum {spectral['relative_score_maximum']:.2f}.\n"
                         "Spatial priorities for verification; hotspot extent is not drought prevalence.")
    temporal_text = f"{temporal['historical_observations_used']} daily observations at or before the cutoff. "
    if temporal["baseline"]["available"]:
        n = temporal["baseline"]["indices"]["NDMI"]
        temporal_text += (f"NDMI {n['target_median']:.4f}; prior-baseline percentile {n['target_empirical_percentile']:.2f}.\n"
                          f"Decision-time NDMI slope {temporal['decision_time_trends']['NDMI']['slope_per_day']:+.6f}/day. "
                          "Later seasonal observations are excluded.")
    else:
        temporal_text += "A usable baseline or trend is missing."
    cards = [
        ("Tanager | spatial / spectral prioritization", spectral["state"], spectral_text, "#eaf1f6", "#235370"),
        ("Sentinel-2 | decision-time temporal context", temporal["state"], temporal_text, "#edf4f3", "#23645a"),
        ("Ground observations | local verification", "UNAVAILABLE", "No real ground reading is available. No values were simulated.\nFuture verification requires site calibration, quality checks and relevant location/timing.", "#fff3db", "#7a5600"),
        ("Decision | human review", decision["decision"], "AUTOMATION BLOCKED | automation_allowed = false\n" + decision["recommended_next_step"], "#f1eef8", "#5a427f"),
    ]
    fig, axis = plt.subplots(figsize=(12, 13))
    fig.subplots_adjust(left=0.035, right=0.965, bottom=0.035, top=0.88)
    axis.set(xlim=(0, 1), ylim=(0, 1))
    axis.axis("off")
    fig.suptitle("AgriPulse | Evidence fusion & decision support", fontsize=19, y=0.975)
    fig.text(0.5, 0.935, f"Decision as of {decision['decision_as_of']}\nSatellite concern is not ground truth | no probability or irrigation prescription", ha="center", fontsize=11)
    for i, (title, state, body, background, edge) in enumerate(cards):
        top = 0.985 - i * 0.25
        axis.add_patch(FancyBboxPatch((0.025, top - 0.205), 0.95, 0.205, boxstyle="round,pad=0.012", linewidth=1.4, edgecolor=edge, facecolor=background))
        axis.text(0.055, top - 0.025, title, color=edge, fontsize=13, weight="bold", va="top")
        axis.text(0.055, top - 0.067, state, fontsize=14, weight="bold", va="top", color=edge)
        wrapped = "\n".join(textwrap.fill(line, width=111) for line in body.splitlines())
        axis.text(0.055, top - 0.108, wrapped, fontsize=10.5, va="top", linespacing=1.45)
        if i < 3:
            axis.annotate("", xy=(0.5, top - 0.235), xytext=(0.5, top - 0.219),
                          arrowprops={"arrowstyle": "-|>", "color": "#536170", "lw": 1.8})
    path = output / "evidence_fusion.png"
    temporary = path.with_suffix(".png.tmp")
    fig.savefig(temporary, format="png", dpi=170)
    plt.close(fig)
    temporary.replace(path)


def run_pipeline(config: FusionConfig = FusionConfig(), *, output: Path = OUTPUT_DIR) -> dict:
    inputs = load_inputs()
    decision, summary = fuse(inputs, config)
    output.mkdir(parents=True, exist_ok=True)
    tanager.write_json(output / "decision.json", decision)
    tanager.write_json(output / "fusion_summary.json", summary)
    tanager.write_json(output / "decision_matrix.json", decision_matrix())
    save_report(decision, summary, output)
    save_figure(decision, output)
    print(f"Decision as of: {decision['decision_as_of']}")
    print(f"Spectral: {decision['spectral_evidence']['state']}; temporal: {decision['temporal_evidence']['state']}; ground: UNAVAILABLE")
    print(f"Historical dates used: {decision['temporal_evidence']['historical_observations_used']}; later/straddling dates excluded: {summary['temporal_selection_audit']['excluded_count']}")
    print(f"Decision: {decision['decision']} (rule {decision['matched_rule_id']}); automation_allowed = false")
    print(f"Outputs: {output}")
    return decision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-as-of", default=DEFAULT_DECISION_AS_OF,
                        help="Timezone-aware acquisition cutoff; the current PoC defaults to the June 9 Sentinel acquisition")
    args = parser.parse_args(argv)
    try:
        run_pipeline(FusionConfig(decision_as_of=args.decision_as_of))
    except (tanager.PipelineError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Stage 4 stopped: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0

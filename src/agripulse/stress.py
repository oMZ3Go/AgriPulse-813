"""Scene-relative spectral moisture-stress risk, without ground-truth labels.

Only the completed local Phase 1 scene is used. All exclusions remain unclassified.
The score is an explainable PoC ranking, not a probability or drought diagnosis.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from urllib.parse import urljoin, urlsplit

import numpy as np

from . import tanager

OUTPUT_DIR = tanager.REPO_ROOT / "outputs" / "stress"
DEFAULT_NDVI_THRESHOLD = 0.30
INDEX_NAMES = ("NDVI", "NDRE", "NDMI")
CLASS_NAMES = ("Low", "Moderate", "High", "Very High")
CLASS_EDGES = (25.0, 50.0, 75.0)
CONDITION_LABELS = {0: "excluded", 1: "lower quarter", 2: "middle half", 3: "upper quarter"}
SCIENTIFIC_REFERENCES = {
    "ndvi_screening_background": "https://science.nasa.gov/earth/earth-observatory/measuring-vegetation-ndvi-evi/",
    "ndmi_background": "https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index",
    "land_cover_and_soil_confounding": "https://pubs.usgs.gov/publication/70032687",
}
LIMITATIONS = [
    "Spectral risk/proxy only: neither ground-truth-confirmed water stress nor a drought diagnosis; scores are not probabilities.",
    "A single scene provides no temporal anomaly or seasonal baseline. A uniformly wet or dry scene can still have relative ranks; class percentages are not stress prevalence.",
    "The NDVI threshold is a configurable, uncalibrated PoC screen, not a crop classifier or guaranteed separation of vegetation, soil, and water.",
    "Sparse, senescent, harvested, or severely affected vegetation may be excluded. Excluded pixels are unassessed, not low risk.",
    "Crop type, phenology, canopy density, soil background, shadows, mixed pixels and residual atmospheric effects can confound these indices.",
    "NDVI, NDRE, and NDMI share NIR and are correlated; supporting terms are not independent confirmation of water stress.",
    "Ranks and score modifiers are uncalibrated design choices, without ground-truth accuracy, confidence estimates, disease labels or irrigation prescriptions.",
    "Scene-wide ranks mix vegetation types and fields; changing the vegetation threshold changes the reference population and scores.",
    "The 400-1700 nm restriction is a compatibility window, not a simulation of Satellite 813 spectral response or resolution.",
    "Future ground sensors and temporal Sentinel-2 evidence will be needed to increase confidence; neither is used in Phase 2.",
]


@dataclass
class Phase1Inputs:
    indices: dict[str, np.ndarray]
    quality_mask: np.ndarray
    summary: dict
    source_path: Path
    summary_sha256: str


@dataclass
class StressResult:
    vegetation_mask: np.ndarray
    classified_mask: np.ndarray
    percentiles: dict[str, np.ndarray]
    conditions: dict[str, np.ndarray]
    moisture_deficit: np.ndarray
    support_factor: np.ndarray
    risk_score: np.ndarray
    risk_class: np.ndarray
    statistics: dict
    summary: dict


def load_phase1_inputs() -> Phase1Inputs:
    """Read and verify the existing source offline, reusing Phase 1 processing."""
    summary_path = tanager.OUTPUT_DIR / "scene_summary.json"
    if not summary_path.is_file():
        raise tanager.PipelineError("Phase 1 scene_summary.json is missing; complete Phase 1 first")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    scene_id = summary["scene_id"]
    if scene_id not in tanager.SCENE_IDS:
        raise tanager.PipelineError("Phase 1 summary does not identify an official agriculture scene")
    stac_path = tanager.raw_data_dir() / f"{scene_id}.json"
    if tanager.sha256(stac_path) != summary["stac_snapshot_sha256"]:
        raise tanager.PipelineError("Local STAC snapshot differs from the completed Phase 1 run")
    item = json.loads(stac_path.read_text(encoding="utf-8"))
    if item["id"] != scene_id:
        raise tanager.PipelineError("Scene ID mismatch between Phase 1 and local STAC")
    asset = item["assets"][summary["surface_reflectance_asset"]]
    url = urljoin(summary["stac_item_url"], asset["href"])
    source = tanager.raw_data_dir() / Path(urlsplit(url).path).name
    receipt = summary["source_download"]
    if (url != receipt["url"] or source.stat().st_size != receipt["content_length_bytes"]
            or tanager.sha256(source) != receipt["sha256"]):
        raise tanager.PipelineError("Local HDF5 does not match the completed Phase 1 source checksum/size")
    wavelengths, selected, spectral = tanager.select_bands(asset)
    if (list(tanager.ANALYSIS_RANGE_NM) != summary["analysis_wavelength_range_nm"]
            or selected != summary["selected_bands"]):
        raise tanager.PipelineError("Spectral selection differs from the completed 400-1700 nm Phase 1 analysis")
    reflectance, valid, quality = tanager.load_reflectance(source, wavelengths, selected, spectral)
    if quality["valid_pixel_count"] != summary["valid_pixel_count"]:
        raise tanager.PipelineError("Quality-mask coverage differs from Phase 1")
    indices = tanager.compute_indices(reflectance, valid)
    return Phase1Inputs(indices, valid, summary, source, tanager.sha256(summary_path))


def percentile_ranks(values: np.ndarray) -> np.ndarray:
    """Tie-aware empirical midranks: 100 * (number below + half equal) / N.

    No forced stretching to 0/100, and equal values always receive equal ranks.
    """
    if values.ndim != 1 or not values.size or not np.isfinite(values).all():
        raise tanager.PipelineError("Percentile ranks require a nonempty finite one-dimensional population")
    _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    middle = np.cumsum(counts) - 0.5 * counts
    return 100.0 * middle[inverse] / values.size


def robust_statistics(values: np.ndarray) -> dict:
    values = values[np.isfinite(values)]
    if not values.size:
        raise tanager.PipelineError("No finite values available for statistics")
    levels = (5, 10, 25, 50, 75, 90, 95)
    quantiles = np.percentile(values, levels, method="linear")
    return {"count": int(values.size), "min": float(values.min()), "max": float(values.max()),
            "mean": float(values.mean()), "median": float(np.median(values)),
            "standard_deviation": float(values.std(ddof=0)),
            "median_absolute_deviation": float(np.median(np.abs(values - np.median(values)))),
            "interquartile_range": float(quantiles[4] - quantiles[2]),
            "percentiles": {f"p{level:02d}": float(value) for level, value in zip(levels, quantiles)}}


def classify_scores(scores: np.ndarray) -> np.ndarray:
    """0 = excluded; 1..4 follow [0,25), [25,50), [50,75), [75,100]."""
    finite = np.isfinite(scores)
    if np.any((scores[finite] < 0) | (scores[finite] > 100)):
        raise tanager.PipelineError("Risk score outside the 0-100 range")
    classes = np.zeros(scores.shape, dtype=np.uint8)
    classes[finite] = np.searchsorted(CLASS_EDGES, scores[finite], side="right") + 1
    return classes


def assess_stress(indices: dict[str, np.ndarray], quality_mask: np.ndarray,
                  ndvi_threshold: float = DEFAULT_NDVI_THRESHOLD) -> StressResult:
    """Rank vegetation only; NDMI drives risk and greenness terms only support it."""
    if not np.isfinite(ndvi_threshold) or not 0 < ndvi_threshold < 1:
        raise tanager.PipelineError("NDVI vegetation threshold must be finite and strictly between 0 and 1")
    shape = quality_mask.shape
    if quality_mask.dtype != np.bool_ or len(shape) != 2:
        raise tanager.PipelineError("Quality mask must be a two-dimensional boolean array")
    if any(indices[name].shape != shape for name in INDEX_NAMES):
        raise tanager.PipelineError("Index grids and the quality mask must have matching shapes")
    vegetation = quality_mask & np.isfinite(indices["NDVI"]) & (indices["NDVI"] >= ndvi_threshold)
    classified = vegetation & np.logical_and.reduce([np.isfinite(indices[name]) for name in INDEX_NAMES])
    count = int(classified.sum())
    if count < 2:
        raise tanager.PipelineError("Fewer than two vegetation pixels have all three finite indices; no relative risk map can be computed")
    if np.ptp(indices["NDMI"][classified]) <= 1e-12:
        raise tanager.PipelineError("Vegetation NDMI has no measurable scene contrast; declining to invent a relative risk ranking")

    percentiles = {}
    conditions = {}
    for name in INDEX_NAMES:
        percentile = np.full(shape, np.nan, dtype=np.float64)
        percentile[classified] = percentile_ranks(indices[name][classified])
        percentiles[name] = percentile
        condition = np.zeros(shape, dtype=np.uint8)
        condition[classified] = np.searchsorted((25.0, 75.0), percentile[classified], side="right") + 1
        conditions[name] = condition

    # NDMI is the necessary driver. NDVI/NDRE only modulate this base by 0.8-1.0.
    # Coefficients are declared PoC choices, not learned or field-calibrated weights.
    moisture_deficit = 100.0 - percentiles["NDMI"]
    support_factor = (0.8 + 0.1 * (1.0 - percentiles["NDVI"] / 100.0)
                      + 0.1 * (1.0 - percentiles["NDRE"] / 100.0))
    risk = np.clip(moisture_deficit * support_factor, 0.0, 100.0)
    classes = classify_scores(risk)
    class_counts = {name: int(np.count_nonzero(classes == code))
                    for code, name in enumerate(CLASS_NAMES, start=1)}
    class_percentages = {name: value / count * 100.0 for name, value in class_counts.items()}
    valid_count = int(quality_mask.sum())
    vegetation_count = int(vegetation.sum())
    statistics = {
        "reference_population": "NDVI-screened, quality-valid vegetation with finite NDVI, NDRE and NDMI",
        "vegetation_indices": {name: robust_statistics(indices[name][classified]) for name in INDEX_NAMES},
        "risk_score": robust_statistics(risk[classified]),
        "risk_class_counts": class_counts,
        "risk_class_percentages": class_percentages,
        "statistics_conventions": "Population standard deviation; unscaled MAD; linear interpolated quantiles",
    }
    summary = {
        "vegetation_threshold": float(ndvi_threshold), "vegetation_criterion": "quality-valid AND finite NDVI >= threshold",
        "total_image_pixels": int(quality_mask.size), "total_valid_pixels": valid_count,
        "vegetation_pixels": vegetation_count,
        "vegetation_percentage": vegetation_count / valid_count * 100.0,
        "vegetation_percentage_denominator": "total_valid_pixels (official Phase 1 quality mask)",
        "vegetation_percentage_of_image": vegetation_count / quality_mask.size * 100.0,
        "classified_vegetation_pixels": count,
        "vegetation_pixels_missing_index_evidence": vegetation_count - count,
        "risk_class_percentages": class_percentages,
        "risk_class_percentage_denominator": "classified_vegetation_pixels",
        "methodology": {
            "name": "Scene-relative spectral moisture-stress risk, PoC v1",
            "reference_population": statistics["reference_population"],
            "percentile_definition": "P_X = 100 * (count(X < x) + 0.5 * count(X == x)) / N; ties share midranks",
            "formula": "risk = (100 - P_NDMI) * (0.8 + 0.1*(1 - P_NDVI/100) + 0.1*(1 - P_NDRE/100))",
            "score_range": [0, 100], "score_is_probability": False,
            "support_factor_range": [0.8, 1.0],
            "interpretation": "Lower NDMI rank drives risk. Lower NDVI/NDRE ranks strengthen supporting evidence, without adding an independent stress term.",
            "calibration": "Threshold and supporting coefficients are unvalidated PoC design choices, not fitted weights or disease thresholds.",
            "condition_categories": {"lower quarter": "P < 25", "middle half": "25 <= P < 75", "upper quarter": "P >= 75"},
            "risk_classes": {"Low": "0 <= score < 25", "Moderate": "25 <= score < 50",
                             "High": "50 <= score < 75", "Very High": "75 <= score <= 100"},
            "boundary_note": "Requested 0-24/25-49/50-74/75-100 classes expressed as continuous intervals; no rounding before classification.",
        },
        "limitations": LIMITATIONS,
        "scientific_references": SCIENTIFIC_REFERENCES,
    }
    return StressResult(vegetation, classified, percentiles, conditions, moisture_deficit,
                        support_factor, risk, classes, statistics, summary)


def save_evidence(path: Path, inputs: Phase1Inputs, result: StressResult) -> None:
    """Preserve numeric and categorical explanations on the original pixel grid."""
    arrays = {name.lower(): np.where(result.classified_mask, inputs.indices[name], np.nan) for name in INDEX_NAMES}
    arrays.update({f"{name.lower()}_percentile": result.percentiles[name] for name in INDEX_NAMES})
    arrays.update({f"{name.lower()}_condition": result.conditions[name] for name in ("NDVI", "NDRE")})
    arrays.update(quality_mask=inputs.quality_mask, vegetation_mask=result.vegetation_mask,
                  classified_mask=result.classified_mask, ndmi_deficit=result.moisture_deficit,
                  support_factor=result.support_factor, risk_score=result.risk_score, risk_class=result.risk_class,
                  scene_id=np.array(inputs.summary["scene_id"]))
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    temporary.replace(path)


def save_figures(inputs: Phase1Inputs, result: StressResult) -> None:
    os.environ["MPLCONFIGDIR"] = str(tanager.OUTPUT_DIR / ".matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    excluded = "#d9d9d9"
    scene_id = inputs.summary["scene_id"]
    note = "Scene-relative spectral proxy; not confirmed water stress or drought.\nGray: excluded pixels. Image coordinates; no field boundaries."
    risk_cmap = plt.get_cmap("magma").copy()
    risk_cmap.set_bad(excluded)

    def finish(fig, filename):
        fig.supxlabel(note, fontsize=9)
        path = OUTPUT_DIR / filename
        temporary = path.with_suffix(path.suffix + ".tmp")
        fig.savefig(temporary, format="png", dpi=150)
        plt.close(fig)
        temporary.replace(path)

    fig, ax = plt.subplots(figsize=(10, 9), constrained_layout=True)
    im = ax.imshow(np.ma.masked_invalid(result.risk_score), cmap=risk_cmap, vmin=0, vmax=100, interpolation="nearest")
    ax.set_title(f"Spectral moisture-stress risk | {scene_id}\nVegetation screen: NDVI >= {result.summary['vegetation_threshold']:g}")
    ax.set(xlabel="Image column (pixel)", ylabel="Image row (pixel)")
    fig.colorbar(im, ax=ax, label="Relative risk score (0-100; not a probability)", shrink=0.8)
    finish(fig, "moisture_stress_risk.png")

    fig, ax = plt.subplots(figsize=(10, 9), constrained_layout=True)
    cmap = ListedColormap(["#4575b4", "#fee090", "#f46d43", "#a50026"])
    cmap.set_bad(excluded)
    im = ax.imshow(np.ma.masked_where(result.risk_class == 0, result.risk_class), cmap=cmap,
                   norm=BoundaryNorm([0.5, 1.5, 2.5, 3.5, 4.5], 4), interpolation="nearest")
    ax.set_title(f"Spectral moisture-stress risk classes\n{scene_id}")
    ax.set(xlabel="Image column (pixel)", ylabel="Image row (pixel)")
    bar = fig.colorbar(im, ax=ax, ticks=[1, 2, 3, 4], shrink=0.8)
    bar.ax.set_yticklabels(["Low [0,25)", "Moderate [25,50)", "High [50,75)", "Very High [75,100]"])
    finish(fig, "moisture_stress_classes.png")

    fig, axes = plt.subplots(2, 2, figsize=(15, 13), constrained_layout=True)
    titles = {"NDVI": "NDVI: supporting greenness evidence", "NDRE": "NDRE: supporting red-edge evidence",
              "NDMI": "NDMI: primary moisture proxy"}
    for ax, name in zip(axes.flat, INDEX_NAMES):
        cmap = plt.get_cmap("BrBG" if name == "NDMI" else "YlGn").copy()
        cmap.set_bad(excluded)
        values = np.ma.masked_where(~result.classified_mask, inputs.indices[name])
        im = ax.imshow(values, cmap=cmap, vmin=-1, vmax=1, interpolation="nearest")
        ax.set_title(titles[name])
        fig.colorbar(im, ax=ax, label=f"{name} (unitless)", shrink=0.8)
    ax = axes[1, 1]
    im = ax.imshow(np.ma.masked_invalid(result.risk_score), cmap=risk_cmap, vmin=0, vmax=100, interpolation="nearest")
    ax.set_title("Result: spectral moisture-stress risk")
    fig.colorbar(im, ax=ax, label="Relative score (0-100)", shrink=0.8)
    for ax in axes.flat:
        ax.set(xlabel="Image column", ylabel="Image row")
    fig.suptitle(f"Expert evidence | {scene_id}\nSame screened vegetation in every panel; NDMI drives the score", fontsize=14)
    finish(fig, "expert_evidence.png")


def run_pipeline(ndvi_threshold: float = DEFAULT_NDVI_THRESHOLD) -> StressResult:
    inputs = load_phase1_inputs()
    result = assess_stress(inputs.indices, inputs.quality_mask, ndvi_threshold)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = result.summary
    summary.update(
        source_scene_id=inputs.summary["scene_id"], acquisition_date=inputs.summary["acquisition_date"],
        bbox=inputs.summary["bbox"], source_hdf5_path=str(inputs.source_path),
        source_hdf5_sha256=inputs.summary["source_download"]["sha256"], phase1_summary_sha256=inputs.summary_sha256,
        exact_selected_wavelengths_nm=inputs.summary["exact_selected_wavelengths"],
        analysis_wavelength_range_nm=inputs.summary["analysis_wavelength_range_nm"],
        data_attribution="Planet Labs PBC; CC-BY-4.0", numpy_version=np.__version__,
        pixel_evidence={
            "file": "pixel_evidence.npz", "layout": "Original HDF5 (row, column) grid; zero-based indices",
            "float_layers": "ndvi, ndre, ndmi, their *_percentile layers (0-100), ndmi_deficit, support_factor, risk_score; NaN means unclassified",
            "condition_layers": {"ndvi_condition": "relative greenness", "ndre_condition": "relative red-edge index"},
            "condition_codes": CONDITION_LABELS,
            "risk_class_codes": {0: "excluded", **dict(enumerate(CLASS_NAMES, start=1))},
            "mask_layers": "quality_mask, vegetation_mask, classified_mask (boolean)",
            "interpretation": "Conditions describe relative index ranks only; they are not Healthy/Stress ground-truth labels.",
        },
    )
    save_evidence(OUTPUT_DIR / "pixel_evidence.npz", inputs, result)
    save_figures(inputs, result)
    tanager.write_json(OUTPUT_DIR / "stress_statistics.json", result.statistics)
    tanager.write_json(OUTPUT_DIR / "stress_summary.json", summary)
    print(f"Vegetation: {summary['vegetation_pixels']:,}/{summary['total_valid_pixels']:,} valid pixels "
          f"({summary['vegetation_percentage']:.6f}%)", flush=True)
    print(json.dumps(result.statistics, indent=2, allow_nan=False), flush=True)
    print(f"SUCCESS: Phase 2 outputs saved under {OUTPUT_DIR}", flush=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndvi-threshold", type=float, default=DEFAULT_NDVI_THRESHOLD,
                        help="Uncalibrated PoC vegetation screen: NDVI >= threshold (default: 0.30)")
    args = parser.parse_args(argv)
    try:
        run_pipeline(args.ndvi_threshold)
    except (tanager.PipelineError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}\nNo substitute data or labels were generated.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

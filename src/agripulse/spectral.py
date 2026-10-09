"""Stage 4.5: exploratory spectral detail from the existing real Tanager scene.

Risk defines sampling groups only. Spectral contrasts are not independent
validation of water stress, biomarkers, or an accuracy benchmark.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import sys

import h5py
import numpy as np

from . import stress, tanager

OUTPUT_DIR = tanager.REPO_ROOT / "outputs/spectral"
SCENE_ID = "20250608_091605_90_4001"
GROUP_LABELS = {"lower": "LOW relative-risk vegetation", "higher": "VERY HIGH relative-risk vegetation"}
COLORS = {"lower": "#167568", "higher": "#ae4c26"}
WINDOW_NM = (400.0, 1700.0)
# Fixed descriptive display conventions, not fitted thresholds or sensor bandpasses.
CONTRAST_BIN_WIDTH_NM = 25.0
INDEX_EXCLUSION_RADIUS_NM = 15.0
CONTRAST_CENTER_SEPARATION_NM = 100.0
MAX_CONTRAST_REGIONS = 3
ATMOSPHERIC_CAUTION_NM = (1350.0, 1450.0)  # Already documented in Stage 1.
CONFOUNDING = (
    "Stage 2 risk uses NDVI/NDRE/NDMI from the same cube. Differences near their "
    "Red, Red Edge, NIR and SWIR wavelengths are partly expected by construction. "
    "Contrasts elsewhere are also correlated spectral evidence, not independent validation of water stress."
)
CONCLUSION = (
    "Indices provide a compact interpretable baseline. Hyperspectral data preserves fine spectral "
    "structure that can support future calibrated crop-specific models when ground truth becomes available."
)
LIMITATIONS = [
    CONFOUNDING,
    "Exploratory information-content demonstration, not proof that hyperspectral data improves drought-detection accuracy. No ground truth, accuracy benchmark, significance test or causal validation is available.",
    "The 400-1700 nm compatibility window does NOT simulate Satellite 813 spectral response functions or spatial resolution. The four-point baseline uses Tanager narrow bands, not convolved multispectral sensor bands.",
    "Risk groups are scene-relative sampling priorities, not healthy/drought labels or calibrated stress severity. Group definitions and contrast display rules are fixed, not tuned to maximize separation.",
    "Crop type, phenology, canopy density, soil, mixed pixels, shadows and remaining atmospheric effects can explain group contrasts. No field/crop matching or independent replicates are established.",
    "The existing NDVI vegetation screen and beta quality masks are imperfect and may omit sparse or affected vegetation; the selected tails do not represent all vegetation.",
    "Missing, nonfinite, negative and STAC-nodata reflectances are excluded per band without imputation or clipping. Per-band populations can differ; empty bands have null statistics and gaps in figures. Reflectance above one is retained and counted, not silently clipped.",
    "The 1350-1450 nm atmospheric water-vapor region flagged in Stage 1 remains visible with a caution but is excluded from contrast-region ranking. Finite values elsewhere are not a guarantee of reliable atmospheric correction.",
    "P25-P75 describes within-group spatial spread, not a confidence interval. The difference of medians is descriptive; spectra are not smoothed, normalized or treated as independent tests.",
    "Exploratory narrow-band contrast regions are ranked display windows, not biomarkers or drought bands. Nearby/correlated wavelengths do not provide 260 independent pieces of evidence.",
]


@dataclass
class SpectralInputs:
    phase1: stress.Phase1Inputs
    stage2_summary: dict
    pixels: dict[str, np.ndarray]
    wavelengths_nm: np.ndarray
    band_metadata: list[dict]
    provenance: dict


def require(condition: bool, message: str) -> None:
    if not condition:
        raise tanager.PipelineError(f"Stage 4.5: {message}")


def window_band_indices(wavelengths: np.ndarray) -> np.ndarray:
    wavelengths = np.asarray(wavelengths)
    require(wavelengths.ndim == 1 and wavelengths.size > 0
            and np.isfinite(wavelengths).all(), "Wavelengths must be a finite nonempty vector")
    require(np.all(np.diff(wavelengths) > 0), "Wavelengths must be strictly increasing")
    selected = np.flatnonzero((wavelengths >= WINDOW_NM[0]) & (wavelengths <= WINDOW_NM[1]))
    require(selected.size > 0, "No bands inside 400-1700 nm")
    return selected


def validate_stage2(phase1: stress.Phase1Inputs, summary: dict, pixels: dict) -> None:
    """Verify saved evidence against the unchanged Stage 2 implementation, read-only."""
    require(summary["source_scene_id"] == phase1.summary["scene_id"] == SCENE_ID,
            "This demonstration requires scene 20250608_091605_90_4001")
    require(summary["phase1_summary_sha256"] == phase1.summary_sha256
            and summary["source_hdf5_sha256"] == phase1.summary["source_download"]["sha256"],
            "Stage 2 lineage differs from the verified Stage 1 inputs")
    require(summary["exact_selected_wavelengths_nm"] == phase1.summary["exact_selected_wavelengths"]
            and summary["analysis_wavelength_range_nm"] == list(WINDOW_NM),
            "Stage 2 wavelength metadata differs from Stage 1")
    require(summary["acquisition_date"] == phase1.summary["acquisition_date"]
            and summary["bbox"] == phase1.summary["bbox"], "Stage 2 scene metadata differs from Stage 1")
    require(pixels["scene_id"].shape == () and pixels["scene_id"].item() == SCENE_ID,
            "Saved pixel evidence has the wrong scene ID")
    expected = stress.assess_stress(phase1.indices, phase1.quality_mask, summary["vegetation_threshold"])
    layers = {"quality_mask": phase1.quality_mask, "vegetation_mask": expected.vegetation_mask,
              "classified_mask": expected.classified_mask, "risk_score": expected.risk_score,
              "risk_class": expected.risk_class}
    layers.update({name.lower(): np.where(expected.classified_mask, values, np.nan)
                   for name, values in phase1.indices.items()})
    for key, values in layers.items():
        require(key in pixels and pixels[key].dtype == values.dtype
                and np.array_equal(pixels[key], values, equal_nan=True),
                f"Saved Stage 2 {key} differs from the verified real source")
    for key in ("total_image_pixels", "total_valid_pixels", "vegetation_pixels", "classified_vegetation_pixels"):
        require(summary[key] == expected.summary[key], f"Stage 2 count mismatch: {key}")


def load_inputs() -> SpectralInputs:
    """Offline only: reuse source checksum, masks, wavelength and index readers."""
    phase1 = stress.load_phase1_inputs()
    provenance = {"stage1_summary": {"sha256": phase1.summary_sha256},
                  "source_hdf5": {"path": str(phase1.source_path),
                                  "sha256": phase1.summary["source_download"]["sha256"]}}
    loaded = {}
    for key, filename in (("stage2_summary", "stress_summary.json"), ("pixels", "pixel_evidence.npz")):
        path = stress.OUTPUT_DIR / filename
        require(path.is_file(), f"Missing existing Stage 2 input: {path}")
        data = path.read_bytes()
        provenance[key] = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}
        if key == "pixels":
            with np.load(io.BytesIO(data), allow_pickle=False) as archive:
                loaded[key] = {name: archive[name] for name in archive.files}
        else:
            loaded[key] = json.loads(data)
    validate_stage2(phase1, loaded["stage2_summary"], loaded["pixels"])
    stac_path = tanager.raw_data_dir() / f"{SCENE_ID}.json"
    data = stac_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    require(digest == phase1.summary["stac_snapshot_sha256"], "STAC changed while loading inputs")
    item = json.loads(data)
    wavelengths, selected, metadata = tanager.select_bands(item["assets"][phase1.summary["surface_reflectance_asset"]])
    require(selected == phase1.summary["selected_bands"], "Index baseline metadata mismatch")
    provenance["stac_snapshot"] = {"path": str(stac_path), "sha256": digest}
    return SpectralInputs(phase1, loaded["stage2_summary"], loaded["pixels"], wavelengths, metadata, provenance)


def select_groups(pixels: dict) -> tuple[dict[str, np.ndarray], dict]:
    """Use every pixel in fixed quartile tails intersected with the named classes.

    No random draws, hand-picked examples, spectral fitting or sample-size cap.
    Quantiles use the entire original classified vegetation population.
    """
    quality, vegetation, classified = (pixels[key] for key in
                                      ("quality_mask", "vegetation_mask", "classified_mask"))
    scores = pixels["risk_score"]
    require(quality.ndim == 2 and all(a.shape == quality.shape and a.dtype == np.bool_
                                    for a in (quality, vegetation, classified)), "Invalid mask grid")
    require(scores.shape == quality.shape, "Risk score grid does not match masks")
    eligible = quality & vegetation & classified & np.isfinite(scores)
    values = scores[eligible]
    require(values.size >= 2 and ((values >= 0) & (values <= 100)).all(), "Invalid sampling score population")
    q25, q75 = np.percentile(values, [25, 75], method="linear")
    groups = {"lower": eligible & (scores <= q25) & (scores < stress.CLASS_EDGES[0]),
              "higher": eligible & (scores >= q75) & (scores >= stress.CLASS_EDGES[-1])}
    require(all(group.any() for group in groups.values()), "One or both fixed risk groups are empty; no fallback threshold is fitted")
    require(not (groups["lower"] & groups["higher"]).any(), "Sampling groups overlap")
    definitions = {
        "reference_population_pixels": int(eligible.sum()),
        "score_quantiles": {"p25": float(q25), "p75": float(q75)},
        "quantile_method": "numpy linear; include all boundary ties; no random sampling or manual pixel selection",
        "lower": "quality-valid AND Stage 2 classified vegetation AND score <= population P25 AND score < 25 (Low)",
        "higher": "quality-valid AND Stage 2 classified vegetation AND score >= population P75 AND score >= 75 (Very High)",
        "note": "Class intersections preserve the exact Stage 2 labels; counts need not be equal or exactly 25%. Scores are used only for sampling.",
    }
    return groups, definitions


def band_statistics(values: np.ndarray, nodata: float | None = None) -> dict:
    """No invalid values enter percentiles; an empty band is explicitly missing."""
    usable = np.isfinite(values) & (values >= 0)
    if isinstance(nodata, (float, int)):
        usable &= values != nodata
    finite = values[usable].astype(np.float64)
    stats = {"valid_pixel_count": int(finite.size), "excluded_pixel_count": int(values.size - finite.size),
             "above_one_pixel_count": int((finite > 1).sum()), "p25": None, "median": None, "p75": None}
    if finite.size:
        p25, median, p75 = np.percentile(finite, [25, 50, 75], method="linear")
        stats.update(p25=float(p25), median=float(median), p75=float(p75))
    return stats


def collect_spectra(inputs: SpectralInputs, groups: dict) -> tuple[np.ndarray, dict]:
    """Read small contiguous band blocks to respect the HDF5 chunk layout.

    Fixed spatial groups are retained; per-band exclusions are counted explicitly.
    This avoids dropping every pixel because of the source's missing bands.
    """
    indices = window_band_indices(inputs.wavelengths_nm)
    curves = {key: [] for key in groups}
    with h5py.File(inputs.phase1.source_path, "r") as source:
        cube = source[f"{tanager.HDF_ROOT}/surface_reflectance"]
        require(cube.shape == (len(inputs.wavelengths_nm), *inputs.phase1.quality_mask.shape),
                "Source cube does not match metadata/mask grid")
        # 14 planes is about 29 MiB for this scene, rather than the full cube.
        for offset in range(0, len(indices), 14):
            block_indices = indices[offset:offset + 14]
            block = cube[int(block_indices[0]):int(block_indices[-1]) + 1]
            for band_index, plane in zip(block_indices, block):
                for key, mask in groups.items():
                    curves[key].append(band_statistics(plane[mask], inputs.band_metadata[band_index].get("nodata")))
            print(f"Read {min(offset + 14, len(indices))}/{len(indices)} in-window bands", flush=True)
    return indices, curves


def exploratory_regions(wavelengths: np.ndarray, difference: list, baseline_nm: list) -> dict:
    """Rank fixed windows by mean absolute difference, with fixed exclusions.

    Spacing avoids reporting only adjacent windows of the same broad contrast;
    it does not establish spectrally independent regions.
    """
    delta = np.array([np.nan if value is None else value for value in difference], dtype=float)
    require(delta.shape == wavelengths.shape, "Contrast and wavelength shapes differ")
    candidates = []
    for start in np.arange(WINDOW_NM[0], WINDOW_NM[1], CONTRAST_BIN_WIDTH_NM):
        stop = start + CONTRAST_BIN_WIDTH_NM
        selected = (wavelengths >= start) & (wavelengths < stop)
        w, d = wavelengths[selected], delta[selected]
        # Require the whole window to be usable and outside caution/index neighborhoods.
        if (len(w) < 3 or not np.isfinite(d).all()
                or np.any((w >= ATMOSPHERIC_CAUTION_NM[0]) & (w <= ATMOSPHERIC_CAUTION_NM[1]))
                or np.any(np.abs(w[:, None] - np.asarray(baseline_nm)) <= INDEX_EXCLUSION_RADIUS_NM)):
            continue
        peak = int(np.argmax(np.abs(d)))
        candidates.append({"window_nm": [float(start), float(stop)],
                           "sampled_wavelength_range_nm": [float(w[0]), float(w[-1])],
                           "band_count": len(w), "mean_absolute_median_difference": float(np.mean(np.abs(d))),
                           "mean_signed_median_difference": float(np.mean(d)),
                           "peak_wavelength_nm": float(w[peak]), "peak_signed_median_difference": float(d[peak])})
    candidates.sort(key=lambda row: (-row["mean_absolute_median_difference"], row["window_nm"][0]))
    selected = []
    for row in candidates:
        if all(abs(row["window_nm"][0] - old["window_nm"][0]) >= CONTRAST_CENTER_SEPARATION_NM for old in selected):
            selected.append(row)
            if len(selected) == MAX_CONTRAST_REGIONS:
                break
    return {"label": "exploratory narrow-band contrast regions", "regions": selected,
            "all_eligible_windows_ranked": candidates,
            "method": "Fixed 25 nm half-open windows anchored at 400 nm; >=3 bands, all usable in both groups. Rank mean absolute (higher minus lower) median reflectance; ties favor lower wavelength. Select up to 3 with centers >=100 nm apart.",
            "index_exclusion_radius_nm": INDEX_EXCLUSION_RADIUS_NM,
            "atmospheric_caution_excluded_nm": list(ATMOSPHERIC_CAUTION_NM),
            "interpretation": "Descriptive display selection only. Window widths, exclusions and spacing are fixed conventions, not tuned thresholds, independent tests or sensor response functions."}


def analyze(inputs: SpectralInputs) -> dict:
    groups, definitions = select_groups(inputs.pixels)
    indices, curves = collect_spectra(inputs, groups)
    wavelengths = inputs.wavelengths_nm[indices]
    difference = [None if a["median"] is None or b["median"] is None else b["median"] - a["median"]
                  for a, b in zip(curves["lower"], curves["higher"])]
    baseline = inputs.phase1.summary["selected_bands"]
    region_report = exploratory_regions(wavelengths, difference, [meta["wavelength_nm"] for meta in baseline.values()])
    group_report = {}
    for key, mask in groups.items():
        # Portable membership checksum of zero-based flat C-order pixel indices.
        members = np.flatnonzero(mask).astype("<i8")
        counts = [row["valid_pixel_count"] for row in curves[key]]
        group_report[key] = {"label": GROUP_LABELS[key], "definition": definitions[key],
                             "selected_pixel_count": int(mask.sum()),
                             "membership_flat_indices_sha256": hashlib.sha256(members.tobytes()).hexdigest(),
                             "membership_encoding": "sorted zero-based row-major flat indices as little-endian int64",
                             "valid_count_min_max": [min(counts), max(counts)],
                             "bands_with_statistics": sum(count > 0 for count in counts),
                             "band_statistics": curves[key]}
    available = sum(value is not None for value in difference)
    return {
        "schema_version": 1, "stage": "4.5", "source_scene": SCENE_ID,
        "acquisition_date": inputs.phase1.summary["acquisition_date"],
        "wavelength_range_nm": list(WINDOW_NM), "number_of_bands_in_range": len(indices),
        "actual_band_center_range_nm": [float(wavelengths[0]), float(wavelengths[-1])],
        "bands_with_statistics_in_both_groups": available,
        "bands_without_comparable_statistics_nm": [float(w) for w, d in zip(wavelengths, difference) if d is None],
        "wavelengths_nm": wavelengths.tolist(), "source_band_indices_zero_based": indices.tolist(),
        "vegetation_population": {key: inputs.stage2_summary[key] for key in
                                  ("total_image_pixels", "total_valid_pixels", "vegetation_threshold",
                                   "vegetation_pixels", "classified_vegetation_pixels")},
        "group_definitions": definitions, "groups": group_report,
        "existing_index_bands": baseline, "median_difference_higher_minus_lower": difference,
        "exploratory_contrast_regions": region_report,
        "information_comparison": {
            "compact_baseline": "Four Tanager narrow-band reflectances: Red, Red Edge, NIR, SWIR; NDVI, NDRE and NDMI are derived from these same four, not three extra independent measurements.",
            "profile": f"{len(indices)} in-window band centers; {available} with group statistics in both groups. Richer spectral sampling around and between the baseline wavelengths; missing bands are gaps.",
            "independent_band_count_claimed": False, "prediction_accuracy_evaluated": False,
            "satellite_813_response_simulated": False, "conclusion": CONCLUSION},
        "methodology": {
            "source_verification": "Reuse Stage 2 offline Stage 1 loader: HDF5 size/SHA-256, STAC SHA-256, wavelength selection and official quality masks. Validate saved Stage 2 masks/indices/scores/classes against the unchanged implementation; use saved scores only to select groups.",
            "group_sampling": "All fixed quartile/class intersection members; no random subsampling, manual representatives, class balancing or spectral separation fitting. Quantiles precede per-band exclusions.",
            "reflectance": "Physical surface-reflectance floats; no scaling, smoothing, normalization, clipping or imputation. Reuse Stage 1 finite/nonnegative/STAC-nodata convention for each band.",
            "statistics": "Per-band linear P25/P50/P75 from usable group members only. Null when no usable members; valid/excluded/above-one counts accompany every band. P25-P75 is spatial spread, not uncertainty of the median.",
            "difference": "Higher relative-risk group median minus lower relative-risk group median, in surface-reflectance units, only where both medians exist.",
            "confounding": CONFOUNDING},
        "limitations": LIMITATIONS, "input_provenance": inputs.provenance,
        "data_attribution": {"provider": inputs.phase1.summary["data_attribution"],
                             "license": inputs.phase1.summary["license"],
                             "stac_item_url": inputs.phase1.summary["stac_item_url"],
                             "reference_notebooks": "Dr. Vincent Markiet / Space42; existing repository references"},
        "software_versions": {"numpy": np.__version__, "h5py": h5py.__version__},
    }


def save_figures(summary: dict, output: Path) -> None:
    os.environ["MPLCONFIGDIR"] = str(output / ".matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    w = np.array(summary["wavelengths_nm"])
    baseline = summary["existing_index_bands"]
    baseline_nm = [meta["wavelength_nm"] for meta in baseline.values()]
    positions = [int(np.argmin(np.abs(w - x))) for x in baseline_nm]
    regions = summary["exploratory_contrast_regions"]["regions"]
    arrays = {key: {stat: np.array([row[stat] for row in group["band_statistics"]], dtype=float)
                    for stat in ("p25", "median", "p75")} for key, group in summary["groups"].items()}
    count_text = " | ".join(f"{key.capitalize()} group n = {group['selected_pixel_count']:,}"
                            for key, group in summary["groups"].items())
    footer = ("Risk groups share the index bands: separation is partly expected by construction; no independent water-stress validation.\n"
              "400–1700 nm is a compatibility window, not a Satellite 813 response simulation. Planet Labs PBC · CC-BY-4.0")

    def decorate(axis):
        axis.set(xlim=WINDOW_NM, xlabel="Wavelength (nm)")
        axis.grid(alpha=0.18)
        axis.spines[["top", "right"]].set_visible(False)
        axis.axvspan(*ATMOSPHERIC_CAUTION_NM, color="#d8dde5", alpha=0.6, zorder=0)
        axis.text(1400, 0.98, "Atmospheric\ncaution", transform=axis.get_xaxis_transform(),
                  ha="center", va="top", fontsize=8, color="#596275")
        for center in baseline_nm:
            axis.axvline(center, color="#626d79", ls=":", lw=0.85, alpha=0.7)

    def plot_curves(axis, spread=True):
        for key, values in arrays.items():
            axis.plot(w, values["median"], color=COLORS[key], lw=1.9, label=GROUP_LABELS[key])
            if spread:
                axis.fill_between(w, values["p25"], values["p75"], color=COLORS[key], alpha=0.16)
        axis.set_ylabel("Surface reflectance")

    def save(fig, filename):
        temporary = (output / filename).with_suffix(".png.tmp")
        fig.savefig(temporary, format="png", dpi=170, facecolor="white")
        plt.close(fig)
        temporary.replace(output / filename)

    with plt.rc_context({"font.size": 10, "axes.titlesize": 12, "axes.labelsize": 11}):
        fig, ax = plt.subplots(figsize=(12, 7))
        fig.subplots_adjust(left=0.08, right=0.98, top=0.80, bottom=0.22)
        fig.suptitle("Real Tanager vegetation | group spectral signatures", fontsize=18, y=0.97)
        fig.text(0.5, 0.90, f"{SCENE_ID} · {count_text}\nMedian and shaded P25–P75 spatial spread; valid counts vary by band", ha="center", va="top")
        decorate(ax)
        plot_curves(ax)
        ax.legend(loc="upper left", fontsize=9, frameon=False)
        fig.text(0.08, 0.12, "Dotted lines: index baseline wavelengths. Missing bands remain gaps; no interpolation or smoothing.", fontsize=9)
        fig.text(0.08, 0.035, footer, fontsize=9, linespacing=1.7)
        save(fig, "group_spectral_signatures.png")

        fig, ax = plt.subplots(figsize=(12, 7))
        fig.subplots_adjust(left=0.09, right=0.98, top=0.77, bottom=0.28)
        fig.suptitle("Exploratory narrow-band contrast regions", fontsize=18, y=0.97)
        fig.text(0.5, 0.90, "Higher minus lower relative-risk group median reflectance\nFixed 25 nm windows, outside index neighborhoods and atmospheric caution; descriptive ranking only", ha="center", va="top")
        decorate(ax)
        ax.axhline(0, color="#5b6570", lw=0.8)
        ax.plot(w, np.array(summary["median_difference_higher_minus_lower"], dtype=float), color="#465b8c", lw=1.8)
        ax.set_ylabel("Difference in surface reflectance")
        for i, region in enumerate(regions, 1):
            start, end = region["window_nm"]
            ax.axvspan(start, end, color="#e5bb55", alpha=0.3)
            ax.text((start + end) / 2, 0.97, str(i), transform=ax.get_xaxis_transform(), ha="center", va="top", weight="bold")
        region_text = " | ".join(f"{i}. {r['window_nm'][0]:.0f}–{r['window_nm'][1]:.0f} nm" for i, r in enumerate(regions, 1))
        fig.text(0.09, 0.16, region_text + "\nNumbered windows are display contrasts, not biomarkers, drought bands or independent tests.", fontsize=10, linespacing=1.7, va="top")
        fig.text(0.09, 0.035, footer, fontsize=9, linespacing=1.7)
        save(fig, "spectral_difference.png")

        fig, axes = plt.subplots(1, 2, figsize=(14, 9), sharey=True)
        fig.subplots_adjust(left=0.07, right=0.98, top=0.74, bottom=0.385, wspace=0.12)
        fig.suptitle("Why hyperspectral? More spectral detail to investigate", fontsize=20, y=0.975)
        fig.text(0.5, 0.915, "Same real scene · same vegetation groups · same reflectance scale\nExploratory information content — prediction accuracy has not been evaluated", ha="center", va="top", fontsize=12)
        for axis in axes:
            decorate(axis)
        axes[0].set_title("A  |  Compact index baseline: four sampled wavelengths", pad=15)
        axes[0].set_ylabel("Surface reflectance")
        for key, values in arrays.items():
            med = values["median"][positions]
            axes[0].errorbar(baseline_nm, med, yerr=[med - values["p25"][positions], values["p75"][positions] - med],
                            fmt="o", ms=5, capsize=3, color=COLORS[key], alpha=0.9)
        axes[1].set_title(f"B  |  Full profile: {len(w)} narrow-band centers", pad=15)
        plot_curves(axes[1])
        axes[1].set_ylabel("")
        for r in regions:
            axes[1].axvspan(*r["window_nm"], color="#e5bb55", alpha=0.17, zorder=0)
        fig.legend(handles=[Line2D([0], [0], color=COLORS[key], lw=2, label=GROUP_LABELS[key]) for key in GROUP_LABELS],
                   loc="upper center", bbox_to_anchor=(0.5, 0.845), ncol=2, frameon=False)
        names = ("Red", "Red Edge", "NIR", "SWIR")
        baseline_text = " · ".join(f"{name} {center:.2f}" for name, center in zip(names, baseline_nm)) + " nm"
        fig.text(0.07, 0.30, baseline_text + "\nNDVI / NDRE / NDMI summarize these four measurements.", fontsize=10, linespacing=1.7, va="top")
        fig.text(0.56, 0.30, f"{summary['bands_with_statistics_in_both_groups']} bands with group statistics; missing bands remain gaps.\nGold: contrast windows outside index neighborhoods.", fontsize=10, linespacing=1.7, va="top")
        fig.text(0.5, 0.215, "Indices = interpretable baseline\nHyperspectral = richer spectral detail for future calibrated crop-specific models", ha="center", fontsize=14, weight="bold", linespacing=1.5, va="top")
        fig.text(0.5, 0.105, "Ground truth is needed to test any benefit. P25–P75 is spatial spread, not a confidence interval.", ha="center", fontsize=10)
        fig.text(0.07, 0.025, footer, fontsize=9, linespacing=1.7)
        save(fig, "hyperspectral_value.png")


def run_pipeline(*, output: Path = OUTPUT_DIR) -> dict:
    output = output.resolve()
    # Protect established outputs even when this function is called directly.
    for name in ("tanager", "stress", "sentinel", "fusion"):
        protected = (tanager.REPO_ROOT / "outputs" / name).resolve()
        require(output != protected and protected not in output.parents,
                "Stage 4.5 output must not be inside an existing stage output directory")
    inputs = load_inputs()
    summary = analyze(inputs)
    output.mkdir(parents=True, exist_ok=True)
    save_figures(summary, output)
    tanager.write_json(output / "spectral_summary.json", summary)
    print(f"Bands: {summary['number_of_bands_in_range']} in 400-1700 nm; "
          f"{summary['bands_with_statistics_in_both_groups']} with statistics in both groups")
    for group in summary["groups"].values():
        print(f"{group['label']}: {group['selected_pixel_count']:,} selected pixels")
    print(f"SUCCESS: Stage 4.5 outputs saved under {output}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        run_pipeline()
    except (tanager.PipelineError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Stage 4.5 stopped: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0

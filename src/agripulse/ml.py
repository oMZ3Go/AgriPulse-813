"""Stage 4.6: experimental within-scene unsupervised spectral anomaly ML.

Model fitting accepts spectra only, never Stage 2 risk scores or classes.
This is not a calibrated agronomic classifier, probability or diagnosis.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import platform
import sys
import time

import h5py
import numpy as np
from scipy.stats import rankdata
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from . import stress, tanager

OUTPUT_DIR = tanager.REPO_ROOT / "outputs/ml"
SCENE_ID = "20250608_091605_90_4001"
WINDOW_NM = (400.0, 1700.0)
# Conservative exclusion of the existing Stage 1 / 4.5 atmospheric caution region.
# Includes the ten wholly unusable bands documented by Stage 4.5. No risk-group
# statistics or risk-dependent contrast windows are used to select features.
ATMOSPHERIC_EXCLUSION_NM = (1350.0, 1450.0)
SEED = 813
FIT_SAMPLE_CAP = 20_000
PCA_VARIANCE = 0.99
SCORE_BATCH_SIZE = 8192
READ_BANDS = 14
FOREST_CONFIG = dict(n_estimators=200, max_samples=256, contamination="auto",
                     max_features=1.0, bootstrap=False, n_jobs=1,
                     random_state=SEED, verbose=0, warm_start=False)
SCORE_DEFINITION = (
    "-IsolationForest.score_samples(PCA(StandardScaler(reflectance))); "
    "higher means more spectrally unusual relative to this scene's eligible vegetation. "
    "Raw continuous score, not a probability; no predict/decision threshold is used."
)
LIMITATIONS = [
    "Scene-relative, unsupervised, exploratory and not field-calibrated. This is not a calibrated agronomic classifier.",
    "The anomaly layer identifies vegetation spectra that are unusual relative to the current scene. It is not a drought, disease, or crop-stress classifier, a diagnosis, or proof of moisture stress or agronomic damage.",
    "Scores are not probabilities or prevalence estimates and are not directly comparable across scenes or fitted models. No binary anomaly threshold or known anomaly fraction is asserted.",
    "Independent ground truth is insufficient for defensible supervised learning. No fabricated labels, classification accuracy, F1, precision, recall or ROC-AUC are used.",
    "Agreement with Stage 2 does not prove moisture stress; disagreement does not prove either method wrong. Both originate from the same scene, so comparison is not independent validation.",
    "Crop type, canopy structure/density, phenology, soil/background, mixed pixels, shadows and residual atmospheric effects can explain spectral differences.",
    "The NDVI screen and beta quality masks are imperfect; sparse, senescent or severely affected vegetation may be omitted. Pixels missing any retained band remain unassessed, not assigned a low score.",
    "Uniform pixel sampling represents area, not balanced fields/crops or independent field replicates; rare vegetation types may be underrepresented. Fit-sample scores are descriptive in-sample scores, not held-out evaluation.",
    "Standardization can emphasize noisy low-variance bands. PCA retains sample variance, not physical importance, and discarded low-variance directions may contain unusual spectra. PCs are not physical drought indicators.",
    "The 1350-1450 nm atmospheric caution region is excluded in full. Other finite reflectances may still contain atmospheric artifacts; values above one are retained and counted, not clipped.",
    "400-1700 nm is a compatibility window only, not a Satellite 813 spectral response or spatial-resolution simulation. No missing bands are interpolated, imputed or smoothed.",
]


@dataclass
class MLInputs:
    phase1: stress.Phase1Inputs
    stage2_summary: dict
    candidate_mask: np.ndarray
    wavelengths_nm: np.ndarray
    band_metadata: list[dict]
    provenance: dict


@dataclass
class Spectra:
    values: np.ndarray
    flat_indices: np.ndarray
    eligible_mask: np.ndarray
    band_indices: np.ndarray
    audit: list[dict]
    candidate_count: int


@dataclass
class ModelResult:
    scores: np.ndarray
    fit_rows: np.ndarray
    scaler: StandardScaler
    pca: PCA
    forest: IsolationForest


def require(condition: bool, message: str) -> None:
    if not condition:
        raise tanager.PipelineError(f"Stage 4.6: {message}")


def membership_hash(indices: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(indices, dtype="<i8").tobytes()).hexdigest()


def read_required(path: Path) -> bytes:
    require(path.is_file(), f"Missing required local input: {path}; no download will be attempted")
    return path.read_bytes()


def validate_eligibility(phase1: stress.Phase1Inputs, summary: dict, masks: dict) -> np.ndarray:
    """Reconstruct only Stage 2's eligibility screen; do not call assess_stress.

    Risk fields may change or be absent without influencing this function.
    The classified mask means finite NDVI/NDRE/NDMI, not any risk class.
    """
    source = phase1.summary
    require(summary["source_scene_id"] == source["scene_id"] == SCENE_ID, "Scene ID mismatch")
    require(summary["phase1_summary_sha256"] == phase1.summary_sha256
            and summary["source_hdf5_sha256"] == source["source_download"]["sha256"],
            "Stage 2 input lineage differs from Stage 1")
    require(summary["acquisition_date"] == source["acquisition_date"]
            and summary["bbox"] == source["bbox"], "Scene acquisition/bbox mismatch")
    require(summary["analysis_wavelength_range_nm"] == list(WINDOW_NM)
            and summary["exact_selected_wavelengths_nm"] == source["exact_selected_wavelengths"],
            "Stage 2 wavelength mismatch")
    require(masks["scene_id"].shape == () and masks["scene_id"].item() == SCENE_ID,
            "Pixel evidence scene ID mismatch")
    threshold = summary["vegetation_threshold"]
    require(np.isfinite(threshold) and 0 < threshold < 1, "Invalid vegetation threshold")
    quality = phase1.quality_mask
    require(quality.dtype == np.bool_ and quality.ndim == 2, "Invalid quality mask")
    require(all(phase1.indices[name].shape == quality.shape for name in stress.INDEX_NAMES),
            "Index grid mismatch")
    ndvi = phase1.indices["NDVI"]
    vegetation = quality & np.isfinite(ndvi) & (ndvi >= threshold)
    candidate = vegetation & np.logical_and.reduce([np.isfinite(phase1.indices[n]) for n in stress.INDEX_NAMES])
    for name, expected in (("quality_mask", quality), ("vegetation_mask", vegetation),
                           ("classified_mask", candidate)):
        require(name in masks and masks[name].dtype == np.bool_
                and np.array_equal(masks[name], expected), f"Saved {name} differs from real-source eligibility")
    counts = dict(total_image_pixels=quality.size, total_valid_pixels=int(quality.sum()),
                  vegetation_pixels=int(vegetation.sum()), classified_vegetation_pixels=int(candidate.sum()))
    require(all(summary[name] == count for name, count in counts.items()), "Stage 2 eligibility count mismatch")
    require(candidate.sum() >= 3, "Fewer than three candidate vegetation pixels")
    return candidate


def load_inputs() -> MLInputs:
    """Read only local files; existing Stage 1 loader verifies HDF5 and STAC hashes."""
    phase1 = stress.load_phase1_inputs()
    require(phase1.summary["scene_id"] == SCENE_ID, "Scene ID mismatch")
    summary_path = stress.OUTPUT_DIR / "stress_summary.json"
    pixel_path = stress.OUTPUT_DIR / "pixel_evidence.npz"
    summary_bytes, pixel_bytes = read_required(summary_path), read_required(pixel_path)
    summary = json.loads(summary_bytes)
    # NPZ access is lazy: do not materialize scores/classes at model-input time.
    with np.load(io.BytesIO(pixel_bytes), allow_pickle=False) as archive:
        masks = {name: archive[name] for name in ("scene_id", "quality_mask", "vegetation_mask", "classified_mask")}
    candidate = validate_eligibility(phase1, summary, masks)
    stac_path = tanager.raw_data_dir() / f"{SCENE_ID}.json"
    stac_bytes = read_required(stac_path)
    require(hashlib.sha256(stac_bytes).hexdigest() == phase1.summary["stac_snapshot_sha256"],
            "STAC changed while loading inputs")
    item = json.loads(stac_bytes)
    wavelengths, selected, metadata = tanager.select_bands(item["assets"][phase1.summary["surface_reflectance_asset"]])
    require(selected == phase1.summary["selected_bands"], "Selected-band metadata mismatch")
    require(item["properties"]["datetime"] == phase1.summary["acquisition_date"]
            and item["bbox"] == phase1.summary["bbox"], "STAC scene metadata mismatch")
    provenance = {
        "stage1_summary": {"path": str(tanager.OUTPUT_DIR / "scene_summary.json"), "sha256": phase1.summary_sha256},
        "source_hdf5": {"path": str(phase1.source_path), "sha256": phase1.summary["source_download"]["sha256"]},
        "stage2_summary": {"path": str(summary_path), "sha256": hashlib.sha256(summary_bytes).hexdigest()},
        "stage2_pixels": {"path": str(pixel_path), "sha256": hashlib.sha256(pixel_bytes).hexdigest()},
        "stac_snapshot": {"path": str(stac_path), "sha256": hashlib.sha256(stac_bytes).hexdigest()},
    }
    return MLInputs(phase1, summary, candidate, wavelengths, metadata, provenance)


def audit_band(values: np.ndarray, wavelength: float, nodata=None) -> tuple[np.ndarray, dict]:
    valid = np.isfinite(values) & (values >= 0)
    if isinstance(nodata, (int, float)):
        valid &= values != nodata
    reasons = []
    if ATMOSPHERIC_EXCLUSION_NM[0] <= wavelength <= ATMOSPHERIC_EXCLUSION_NM[1]:
        reasons.append("atmospheric_caution_1350_1450_nm")
    if not valid.any():
        reasons.append("no_valid_candidate_reflectance")
    elif np.ptp(values[valid]) == 0:
        reasons.append("constant_candidate_reflectance")
    return valid, {"wavelength_nm": float(wavelength), "valid_candidate_count": int(valid.sum()),
                   "invalid_candidate_count": int((~valid).sum()),
                   "above_one_candidate_count": int((valid & (values > 1)).sum()),
                   "exclusion_reasons": reasons, "retained": not reasons}


def collect_spectra(inputs: MLInputs) -> Spectra:
    wavelengths = inputs.wavelengths_nm
    require(wavelengths.ndim == 1 and np.isfinite(wavelengths).all()
            and (np.diff(wavelengths) > 0).all(), "Invalid spectral wavelength vector")
    indices = np.flatnonzero((wavelengths >= WINDOW_NM[0]) & (wavelengths <= WINDOW_NM[1]))
    require(indices.size > 0, "No bands inside compatibility window")
    flat = np.flatnonzero(inputs.candidate_mask)
    complete = np.ones(flat.size, dtype=bool)
    audit, kept = [], []
    with h5py.File(inputs.phase1.source_path, "r") as source:
        cube = source[f"{tanager.HDF_ROOT}/surface_reflectance"]
        require(cube.shape == (wavelengths.size, *inputs.candidate_mask.shape), "Source cube/grid mismatch")
        # Preserve source dtype; read only small band blocks, not the full cube.
        matrix = np.empty((flat.size, indices.size), dtype=cube.dtype)
        for offset in range(0, indices.size, READ_BANDS):
            group = indices[offset:offset + READ_BANDS]
            block = cube[int(group[0]):int(group[-1]) + 1]
            for index, plane in zip(group, block):
                values = plane.ravel()[flat]
                valid, row = audit_band(values, wavelengths[index], inputs.band_metadata[index].get("nodata"))
                row["source_band_index_zero_based"] = int(index)
                audit.append(row)
                if row["retained"]:
                    matrix[:, len(kept)] = values
                    kept.append(int(index))
                    complete &= valid
            print(f"Audited {min(offset + READ_BANDS, indices.size)}/{indices.size} bands", flush=True)
    require(len(kept) >= 2, "Fewer than two usable spectral bands")
    require(complete.sum() >= 3, "Fewer than three complete vegetation spectra; no imputation is allowed")
    values = np.ascontiguousarray(matrix[complete, :len(kept)])
    eligible = np.zeros(inputs.candidate_mask.shape, dtype=bool)
    eligible.ravel()[flat[complete]] = True
    return Spectra(values, flat[complete], eligible, np.array(kept), audit, flat.size)


def fit_anomaly(values: np.ndarray) -> ModelResult:
    """Fit and score spectra alone. No labels, risk arrays, weights or tuning input."""
    require(values.ndim == 2 and values.shape[0] >= 3 and values.shape[1] >= 2
            and np.isfinite(values).all() and (values >= 0).all(), "Model requires finite nonnegative spectra")
    count = min(FIT_SAMPLE_CAP, len(values))
    rng = np.random.Generator(np.random.PCG64(SEED))
    rows = np.sort(rng.choice(len(values), size=count, replace=False)) if count < len(values) else np.arange(count)
    # A fixed single BLAS/OpenMP thread reduces platform/thread-order variability.
    with threadpool_limits(limits=1):
        training = values[rows].astype(np.float64)
        scaler = StandardScaler(copy=True, with_mean=True, with_std=True)
        scaled = scaler.fit_transform(training)
        require((scaler.var_ > 0).all(), "A fitting-sample band has zero variance; stop without silent feature changes")
        pca = PCA(n_components=PCA_VARIANCE, svd_solver="full", whiten=False, copy=True, random_state=SEED)
        pca.fit(scaled)
        embedded = pca.transform(scaled)
        require(np.isfinite(embedded).all() and np.isfinite(pca.explained_variance_ratio_).all(), "Nonfinite PCA output")
        forest = IsolationForest(**FOREST_CONFIG)
        forest.fit(embedded)
        scores = np.empty(len(values), dtype=np.float64)
        for start in range(0, len(values), SCORE_BATCH_SIZE):
            batch = values[start:start + SCORE_BATCH_SIZE].astype(np.float64)
            projected = pca.transform(scaler.transform(batch))
            require(np.isfinite(projected).all(), "Nonfinite PCA projection")
            scores[start:start + len(batch)] = -forest.score_samples(projected)
    require(np.isfinite(scores).all(), "Nonfinite anomaly scores")
    return ModelResult(scores, rows, scaler, pca, forest)


def compare_stage2(inputs: MLInputs, spectra: Spectra, result: ModelResult) -> tuple[dict, np.ndarray]:
    """Post-fit descriptive context only; risk cannot reach fit_anomaly."""
    record = inputs.provenance["stage2_pixels"]
    data = read_required(Path(record["path"]))
    require(hashlib.sha256(data).hexdigest() == record["sha256"], "Stage 2 evidence changed after eligibility loading")
    with np.load(io.BytesIO(data), allow_pickle=False) as archive:
        risk, classes = archive["risk_score"], archive["risk_class"]
    require(risk.shape == classes.shape == inputs.candidate_mask.shape, "Stage 2 comparison grid mismatch")
    require(np.isfinite(risk[inputs.candidate_mask]).all()
            and ((risk[inputs.candidate_mask] >= 0) & (risk[inputs.candidate_mask] <= 100)).all(),
            "Invalid Stage 2 comparison scores")
    require(np.array_equal(classes, stress.classify_scores(risk)), "Stage 2 comparison classes disagree with scores")
    x, y = result.scores, risk.ravel()[spectra.flat_indices]
    rho = None
    if np.ptp(x) > 0 and np.ptp(y) > 0:
        rho = float(np.corrcoef(rankdata(x, method="average"), rankdata(y, method="average"))[0, 1])
    groups = {}
    for code, name in enumerate(stress.CLASS_NAMES, 1):
        values = x[classes.ravel()[spectra.flat_indices] == code]
        groups[name] = {"count": len(values), "anomaly_statistics": stress.robust_statistics(values) if len(values) else None}
    return {"population_count": len(x), "spearman_rank_correlation": rho,
            "method": "Pearson correlation of average-tie ranks on the same ML-eligible pixels; no p-value or inferential claim. Null if either score is constant.",
            "anomaly_by_stage2_relative_risk_class": groups,
            "used_for_training_feature_selection_or_tuning": False,
            "interpretation": LIMITATIONS[4]}, risk


def make_summary(inputs: MLInputs, spectra: Spectra, model: ModelResult, comparison: dict) -> dict:
    ratios = model.pca.explained_variance_ratio_
    cumulative = np.cumsum(ratios)
    return {
        "schema_version": 1, "stage": "4.6", "stage_name": "Experimental Unsupervised Spectral Anomaly ML",
        "scene_id": SCENE_ID, "acquisition_date": inputs.phase1.summary["acquisition_date"],
        "wavelength_window_nm": list(WINDOW_NM), "satellite_813_response_simulated": False,
        "image_shape_rows_columns": list(spectra.eligible_mask.shape),
        "quality_valid_pixel_count": int(inputs.phase1.quality_mask.sum()),
        "stage2_candidate_vegetation_pixel_count": spectra.candidate_count,
        "eligible_vegetation_pixel_count": len(spectra.values),
        "candidate_pixels_excluded_for_incomplete_spectra": spectra.candidate_count - len(spectra.values),
        "vegetation_threshold": inputs.stage2_summary["vegetation_threshold"],
        "eligibility_rule": "Verified Stage 2 quality-valid NDVI-screened vegetation with finite NDVI/NDRE/NDMI, then require finite, nonnegative, non-STAC-nodata reflectance in EVERY retained band. Excluded-band invalids do not exclude pixels.",
        "eligible_membership_sha256": membership_hash(spectra.flat_indices),
        "in_window_band_count": len(spectra.audit), "usable_band_count": len(spectra.band_indices),
        "excluded_band_count": len(spectra.audit) - len(spectra.band_indices),
        "usable_source_band_indices_zero_based": spectra.band_indices.tolist(),
        "usable_wavelengths_nm": inputs.wavelengths_nm[spectra.band_indices].tolist(),
        "band_exclusion_rule": "Exclude all centers in 1350-1450 nm inclusive, bands with no usable candidate values, and constant candidate bands. Audit all in-window bands directly; no Stage 4.5 risk-group statistics drive selection.",
        "band_audit": spectra.audit,
        "fitting_sample_size": len(model.fit_rows), "fitting_sample_cap": FIT_SAMPLE_CAP,
        "sampling_method": "Uniform without replacement from eligible pixels only; numpy Generator(PCG64(seed)); sorted selected rows. Use all if population <= cap. No risk stratification or sample weights.",
        "fitting_membership_sha256": membership_hash(spectra.flat_indices[model.fit_rows]),
        "membership_hash_encoding": "sorted zero-based row-major flat pixel indices as little-endian int64",
        "deterministic_seed": SEED,
        "scaling_method": "StandardScaler: per-band fitting-sample mean and population standard deviation (ddof=0); with_mean=True, with_std=True, copy=True; float64 fitting/transforms",
        "pca": {"rule": "Smallest component count with cumulative standardized fitting-sample variance strictly greater than 0.99 (sklearn full SVD rule). No risk-dependent selection.",
                "n_components_parameter": PCA_VARIANCE, "svd_solver": "full", "whiten": False, "copy": True,
                "random_state": SEED, "retained_component_count": int(model.pca.n_components_),
                "explained_variance_ratio": ratios.tolist(), "cumulative_explained_variance_ratio": cumulative.tolist(),
                "cumulative_explained_variance": float(cumulative[-1]),
                "interpretation": "Variance of standardized sample spectra, not physical drought indicators or accuracy."},
        "isolation_forest": {**FOREST_CONFIG, "effective_max_samples": int(model.forest.max_samples_),
                             "auto_offset_used_for_scoring": False,
                             "contamination_note": "auto supplies a library offset only; raw score_samples ignores it. No predict, decision_function, anomaly labels or anomaly-prevalence estimate."},
        "anomaly_score_definition": SCORE_DEFINITION, "score_is_probability": False,
        "calibrated_agronomic_classifier": False, "anomaly_statistics": stress.robust_statistics(model.scores),
        "descriptive_stage2_comparison": comparison,
        "input_provenance": inputs.provenance,
        "software_versions": {"python": platform.python_version(), **{name: version(name) for name in
                              ("numpy", "h5py", "scipy", "scikit-learn", "threadpoolctl", "joblib", "matplotlib")}},
        "reproducibility": {"network_required": False, "blas_openmp_threads": 1, "score_batch_size": SCORE_BATCH_SIZE,
                            "read_band_block_size": READ_BANDS,
                            "note": "Exact reruns checked in the pinned environment; numerical/PNG byte identity across library versions, hardware or fonts is not guaranteed. Runtime is printed, not embedded as nondeterministic metadata."},
        "memory": {"eligible_spectra_bytes": spectra.values.nbytes,
                   "fit_float64_matrix_bytes": len(model.fit_rows) * len(spectra.band_indices) * 8,
                   "note": "Band-block reads, candidate matrix in source dtype, 20000-row fit cap, batched full-population scoring; these are array sizes, not peak process memory."},
        "pixel_evidence": {"file": "anomaly_pixel_evidence.npz", "layout": "Original row/column grid; image coordinates, no field boundaries or georeferenced export",
                           "layers": "scene_id scalar, eligible_mask bool, anomaly_score float64 (NaN outside eligibility), fitting_flat_indices int64, usable_source_band_indices int64; allow_pickle=False"},
        "scientific_limitations": LIMITATIONS,
        "future_supervised_learning": "Requires independent ground-truth labels from farmer observations, agronomist verification and calibrated IoT. Future EO spectral, temporal, weather and field features may support locally calibrated Random Forest or XGBoost; neither is implemented here.",
        "data_attribution": "Planet Labs PBC; CC-BY-4.0. Reference notebooks: Dr. Vincent Markiet / Space42.",
        "method_references": {
            "isolation_forest": "https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html",
            "pca": "https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html",
            "scaler": "https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html"},
    }


def score_grid(spectra: Spectra, model: ModelResult) -> np.ndarray:
    grid = np.full(spectra.eligible_mask.shape, np.nan, dtype=np.float64)
    grid.ravel()[spectra.flat_indices] = model.scores
    return grid


def save_figures(inputs: MLInputs, spectra: Spectra, model: ModelResult, risk: np.ndarray,
                 summary: dict, output: Path) -> None:
    os.environ["MPLCONFIGDIR"] = str(output / ".matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    anomaly = score_grid(spectra, model)
    low, high = float(model.scores.min()), float(model.scores.max())
    footer = ("Exploratory, scene-relative and unsupervised · not a probability or diagnosis\n"
              "Gray: unassessed pixels · image coordinates, no field boundaries · Planet Labs PBC / CC-BY-4.0")

    def panel(fig, ax, values, title, palette, vmin, vmax, label):
        cmap = plt.get_cmap(palette).with_extremes(bad="#dce1e4")
        im = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
        ax.set(title=title, xlabel="Image column", ylabel="Image row")
        fig.colorbar(im, ax=ax, shrink=0.8, pad=0.03, label=label)

    def save(fig, name):
        temporary = output / (name + ".tmp")
        fig.savefig(temporary, format="png", dpi=160, facecolor=fig.get_facecolor())
        plt.close(fig)
        temporary.replace(output / name)

    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12,
                         "figure.facecolor": "#f7faf9", "axes.facecolor": "#f7faf9"}):
        fig, ax = plt.subplots(figsize=(11, 10))
        fig.subplots_adjust(left=0.08, right=0.96, bottom=0.13, top=0.86)
        fig.suptitle("Relative spectral anomaly in vegetation", fontsize=20, y=0.97)
        fig.text(0.5, 0.925, f"Stage 4.6 · {SCENE_ID} · {len(model.scores):,} eligible pixels", ha="center")
        panel(fig, ax, anomaly, "Continuous within-scene score", "viridis", low, high,
              "Anomaly score · higher = more unusual")
        fig.text(0.08, 0.035, footer, fontsize=10, linespacing=1.6)
        save(fig, "anomaly_score.png")

        fig, axes = plt.subplots(1, 3, figsize=(18, 8))
        fig.subplots_adjust(left=0.045, right=0.97, bottom=0.20, top=0.80, wspace=0.35)
        fig.suptitle("Scene context · descriptive comparison only", fontsize=21, y=0.97)
        rho = summary["descriptive_stage2_comparison"]["spearman_rank_correlation"]
        rho_text = f"{rho:+.3f}" if rho is not None else "undefined (constant scores)"
        fig.text(0.5, 0.905, f"Same ML-eligible vegetation in all panels · Spearman rank correlation with Stage 2: {rho_text}\n"
                 "Shared scene evidence is not independent validation; agreement does not establish moisture stress.",
                 ha="center", va="top", linespacing=1.7)
        panel(fig, axes[0], np.where(spectra.eligible_mask, inputs.phase1.indices["NDVI"], np.nan),
              "NDVI · vegetation context", "YlGn", 0, 1, "NDVI")
        panel(fig, axes[1], np.where(spectra.eligible_mask, risk, np.nan),
              "Stage 2 · relative moisture-risk proxy", "magma", 0, 100, "Relative risk score")
        panel(fig, axes[2], anomaly, "Stage 4.6 · spectral anomaly", "viridis", low, high, "Higher = more unusual")
        fig.text(0.045, 0.05, footer + "\nStage 2 scores/classes were accessed only after fitting; no model tuning uses this comparison.",
                 fontsize=10, linespacing=1.6)
        save(fig, "anomaly_context.png")

        ratios = model.pca.explained_variance_ratio_
        cumulative = np.cumsum(ratios)
        x = np.arange(1, len(ratios) + 1)
        fig, axes = plt.subplots(1, 2, figsize=(13, 7))
        fig.subplots_adjust(left=0.08, right=0.96, bottom=0.25, top=0.78, wspace=0.26)
        fig.suptitle("PCA · a compact representation of vegetation spectra", fontsize=19, y=0.97)
        fig.text(0.5, 0.88, f"{len(spectra.band_indices)} usable bands → {len(ratios)} retained components · "
                 f"{cumulative[-1] * 100:.4f}% cumulative sample variance\n"
                 f"StandardScaler + full SVD · fixed uniform fitting sample: {len(model.fit_rows):,} pixels · seed {SEED}",
                 ha="center", va="top", linespacing=1.6)
        axes[0].bar(x, ratios * 100, color="#247d78")
        axes[0].set(ylabel="Explained variance (%)", title="Individual retained components")
        axes[1].plot(x, cumulative * 100, "o-", color="#247d78")
        axes[1].axhline(99, ls="--", color="#af6629", label="Fixed 99% target")
        axes[1].set(ylabel="Cumulative variance (%)", ylim=(0, 101), title="Smallest count exceeding 99%")
        axes[1].legend(loc="lower right", frameon=False)
        for ax in axes:
            ax.set(xlabel="Principal component", xticks=x)
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
        fig.text(0.08, 0.06, "Variance refers to standardized fitting-sample spectra; this is not model accuracy.\n"
                 "Principal components are not physical drought indicators. Low-variance anomalies may be discarded.\n"
                 "Atmospheric caution bands and missing bands stay excluded; no imputation or smoothing.", linespacing=1.7)
        save(fig, "pca_summary.png")


def validate_output(output: Path) -> Path:
    output = output.resolve()
    for directory in ("outputs/tanager", "outputs/stress", "outputs/sentinel", "outputs/fusion",
                      "outputs/spectral", "dashboard", "src", "tests", "references", ".git", ".agents", ".codex"):
        protected = (tanager.REPO_ROOT / directory).resolve()
        require(output != protected and protected not in output.parents and output not in protected.parents,
                "Output must not overlap an existing stage or protected project directory")
    raw = tanager.raw_data_dir().resolve()
    require(output != raw and raw not in output.parents and output not in raw.parents, "Output must not overlap raw data")
    return output


def run_pipeline(*, output: Path = OUTPUT_DIR) -> dict:
    output = validate_output(output)
    started = time.perf_counter()
    inputs = load_inputs()
    spectra = collect_spectra(inputs)
    print(f"Fitting on up to {FIT_SAMPLE_CAP:,} of {len(spectra.values):,} eligible spectra", flush=True)
    model = fit_anomaly(spectra.values)
    comparison, risk = compare_stage2(inputs, spectra, model)
    summary = make_summary(inputs, spectra, model, comparison)
    output.mkdir(parents=True, exist_ok=True)
    save_figures(inputs, spectra, model, risk, summary, output)
    path = output / "anomaly_pixel_evidence.npz"
    with path.with_suffix(".npz.tmp").open("wb") as stream:
        np.savez_compressed(stream, scene_id=np.array(SCENE_ID), eligible_mask=spectra.eligible_mask,
                            anomaly_score=score_grid(spectra, model),
                            fitting_flat_indices=spectra.flat_indices[model.fit_rows].astype("<i8"),
                            usable_source_band_indices=spectra.band_indices.astype("<i8"))
    path.with_suffix(".npz.tmp").replace(path)
    tanager.write_json(output / "ml_summary.json", summary)
    print(f"Eligible: {len(model.scores):,}; usable bands: {len(spectra.band_indices)}; "
          f"PCA: {model.pca.n_components_} components, {sum(model.pca.explained_variance_ratio_):.8%} variance")
    print(f"SUCCESS: Stage 4.6 saved under {output}; elapsed {time.perf_counter() - started:.2f} seconds")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        run_pipeline()
    except (tanager.PipelineError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Stage 4.6 stopped: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0

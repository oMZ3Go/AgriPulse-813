"""Small presentation/validation helpers for the offline submission notebook.

Scientific calculations stay in the unchanged agripulse modules. This module
does not select a product decision or invoke any full-scene pipeline.
"""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(path):
    raw = path.read_bytes()
    if path.suffix == ".json":
        raw = json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    elif path.suffix == ".csv":
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def install_offline_guard():
    """Deny external Python socket access; local Jupyter kernel IPC is allowed."""
    def audit(event, args):
        if event in ("socket.connect", "socket.getaddrinfo"):
            address = args[1] if event == "socket.connect" else args[0]
            host = address[0] if isinstance(address, tuple) else address
            if host not in ("localhost", "127.0.0.1", "::1"):
                raise RuntimeError("Offline submission: external network access is disabled")
        if event == "open" and isinstance(args[0], (str, bytes)):
            name = str(args[0]).replace("\\", "/").lower()
            if name.endswith((".h5", ".hdf5", ".hdf", ".tif", ".tiff")) or "/data/raw/" in name:
                raise RuntimeError("Offline submission: raw satellite input is not permitted")
    sys.addaudithook(audit)


def load_sample(root):
    directory = root / "data/sample_input"
    provenance = read_json(directory / "provenance.json")
    for name, record in provenance["artifacts"].items():
        raw = (directory / name).read_bytes()
        if name.endswith(".csv"):
            raw = raw.replace(b"\r\n", b"\n")
        require(hashlib.sha256(raw).hexdigest() == record["sha256"], f"Sample checksum mismatch: {name}")
    with np.load(directory / "tanager_sample.npz", allow_pickle=False) as archive:
        sample = {name: archive[name] for name in archive.files}
    require(sample["scene_id"].item() == provenance["scene_id"], "Sample scene mismatch")
    require(sample["spectra"].shape == (provenance["sample_size"], provenance["spectral_band_count"]),
            "Sample shape mismatch")
    return sample, provenance


def temporal_rows(root, cutoff):
    cutoff = datetime.fromisoformat(cutoff)
    with (root / "data/sample_input/sentinel_timeseries_sample.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        eligible = all(datetime.fromisoformat(t) <= cutoff for t in row["acquisition_datetimes"].split(";"))
        require(row["eligible_at_decision_cutoff"] == str(eligible).lower()
                and row["after_decision_cutoff"] == str(not eligible).lower(), "Temporal cutoff flags are inconsistent")
        row["eligible"] = eligible
        for key in row:
            if key.startswith(("ndvi_", "ndre_", "ndmi_")) or key == "valid_footprint_percentage":
                row[key] = float(row[key])
    return rows


def validated_result(root):
    contract = read_json(root / "examples/product_contract_konya.json")
    fusion = read_json(root / "dashboard/public/data/konya/fusion.json")
    require(contract == read_json(root / "dashboard/public/data/konya/contract.json"), "Contract snapshots disagree")
    require(contract["decision_state"] == fusion["decision"] == "GROUND_VERIFICATION_REQUIRED", "Unexpected decision")
    require(contract["automation_allowed"] is fusion["automation_allowed"] is False, "Automation must be disabled")
    require(contract["analysis_level"] == "EO_ENHANCED", "Unexpected analysis level")
    require(fusion["spectral_evidence"]["state"] == "RELATIVE_HOTSPOTS_PRESENT", "Unexpected spectral state")
    require(fusion["temporal_evidence"]["state"] == "NEUTRAL_OR_MIXED", "Unexpected temporal state")
    require(fusion["ground_evidence"]["state"] == contract["data_availability"]["ground"] == "UNAVAILABLE", "Unexpected ground state")
    ml_evidence = next(e for e in contract["evidence"] if e["source"] == "ml")
    require(contract["data_availability"]["ml"] == "AVAILABLE" and ml_evidence["used_for_decision"] is False
            and ml_evidence["score_is_probability"] is False, "Unexpected ML decision role")
    return contract, fusion


def make_figure(indices, screening, model, rows, contract, provenance):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 2, figsize=(14, 11), facecolor="#f7faf8")
    fig.subplots_adjust(left=.08, right=.96, top=.85, bottom=.23, hspace=.52, wspace=.26)
    fig.text(.08, .962, "AgriPulse-813", fontsize=26, weight="bold", color="#163d32")
    fig.text(.08, .925, "Beyond The Limit · Syria  |  From spectral signals to grounded decisions.", fontsize=11)
    fig.text(.08, .895, "REAL KONYA DATA · 08 JUN 2025  |  Panels A, B, D: compact reproducibility sample", fontsize=10, color="#52665f")
    ax = axes[0, 0]
    ndvi = indices["NDVI"].ravel()
    veg = screening.vegetation_mask.ravel()
    bins = np.linspace(-1, 1, 35)
    ax.hist([ndvi[~veg & np.isfinite(ndvi)], ndvi[veg]], bins=bins, stacked=True,
            color=["#b5beb7", "#267d65"], label=["Below screen / background", "NDVI-screened vegetation"])
    ax.axvline(.3, color="#926622", linestyle="--", linewidth=1.4, label="NDVI = 0.30")
    ax.set(title=f"A  |  NDVI evidence · {len(ndvi):,} sampled pixels", xlabel="NDVI (unitless)", ylabel="Sampled pixel count")
    ax.legend(fontsize=8, frameon=False)

    ax = axes[0, 1]
    usable = screening.classified_mask
    dots = ax.scatter(indices["NDMI"][usable], screening.risk_score[usable], c=indices["NDRE"][usable],
                      cmap="viridis", s=12, alpha=.65, rasterized=True)
    ax.set(title="B  |  Relative spectral screening", xlabel="NDMI · main driver (unitless)",
           ylabel="Sample-relative score (0–100)", ylim=(-2, 102))
    fig.colorbar(dots, ax=ax, pad=.02, fraction=.04, label="NDRE · supporting modifier")
    ax.text(.02, .04, "Within-sample ranks; not a probability", transform=ax.transAxes, fontsize=8)

    ax = axes[1, 0]
    cutoff = datetime.fromisoformat(contract["decision_as_of"])
    for eligible, color, label, marker in [(True, "#267d65", "Decision-time eligible (19)", "o"),
                                            (False, "#9b6c99", "Later / retrospective (25)", "s")]:
        group = [r for r in rows if r["eligible"] == eligible]
        dates = [datetime.fromisoformat(r["date"]) for r in group]
        ax.plot(dates, [r["ndmi_median"] for r in group], color=color, marker=marker,
                markersize=3, linewidth=1.3, label=label)
        ax.fill_between(dates, [r["ndmi_p25"] for r in group], [r["ndmi_p75"] for r in group], color=color, alpha=.13)
    ax.axvline(cutoff, color="#775e2b", linestyle="--", linewidth=1.2, label="June 9 acquisition cutoff")
    ax.axvspan(cutoff, datetime.fromisoformat(rows[-1]["date"]), color="#9b6c99", alpha=.035)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set(title="C  |  Sentinel-2 temporal context · 44 real dates", ylabel="Vegetation NDMI (unitless)",
           xlabel="Shading: spatial P25–P75, not confidence intervals")
    ax.legend(fontsize=8, frameon=False, loc="lower left")

    ax = axes[1, 1]
    ax.hist(model.scores, bins=25, color="#516d93", edgecolor="white", linewidth=.5)
    ax.set(title=f"D  |  Experimental spectral anomaly · {len(model.scores)} spectra",
           xlabel="−IsolationForest.score_samples (not probability)", ylabel="Sampled vegetation count")
    ax.text(.98, .94, "StandardScaler → PCA → IsolationForest\nSeed 813 · no training labels\nHigher = more unusual within this sample",
            transform=ax.transAxes, ha="right", va="top", fontsize=8, linespacing=1.6)
    for ax in axes.flat:
        ax.set_facecolor("white")
        ax.grid(axis="y", alpha=.12)
        ax.set_axisbelow(True)
    fig.text(.08, .158, "VALIDATED FULL-SCENE PRODUCT DECISION · loaded from the existing contract", fontsize=10, weight="bold", color="#52665f")
    fig.text(.08, .119, contract["decision_state"], fontsize=21, weight="bold", color="#805b22")
    fig.text(.08, .087, "EO_ENHANCED  |  Relative hotspots  |  Neutral / mixed temporal evidence  |  Ground evidence unavailable", fontsize=10)
    fig.text(.08, .057, "AUTOMATIC INTERVENTION: NOT ALLOWED", fontsize=12, weight="bold", color="#8a3535")
    fig.text(.08, .026, "Sample ranks and ML differ from full-scene results. No spatial map is implied. Decision support requires ground verification.", fontsize=9)
    return fig


def make_summary(root, provenance, screening, model, rows, trends, contract, fusion):
    return {
        "project": "AgriPulse-813", "team": "Beyond The Limit", "country": "Syria",
        "theme": "Precision Agriculture & Crop Intelligence", "tagline": "From spectral signals to grounded decisions.",
        "source_scene_id": provenance["scene_id"], "source_date": provenance["source_date"],
        "source_location": provenance["location"], "sample_provenance": provenance,
        "compact_sample_calculations": {
            "scope": "Reproduction of the workflow on a subset; sample quantiles are not full-scene quantiles.",
            "sample_size": provenance["sample_size"], "classified_vegetation_pixels": int(screening.classified_mask.sum()),
            "stage2_methodology": screening.summary["methodology"], "stage2_statistics": screening.statistics,
            "ml": {"family": "StandardScaler -> PCA -> IsolationForest", "random_state": 813,
                   "spectra_count": len(model.scores), "bands": provenance["spectral_band_count"],
                   "pca_components": int(model.pca.n_components_),
                   "pca_explained_variance_ratio": model.pca.explained_variance_ratio_.tolist(),
                   "score_min": float(model.scores.min()), "score_median": float(np.median(model.scores)),
                   "score_max": float(model.scores.max()), "used_for_decision": False,
                   "score_is_probability": False, "supervised_training": False,
                   "interpretation": "Spectrally unusual vegetation relative to the current sample; no drought, disease or crop-failure diagnosis."}},
        "sentinel_temporal_context": {
            "observations": len(rows), "eligible_at_cutoff": sum(r["eligible"] for r in rows),
            "later_retrospective_observations": sum(not r["eligible"] for r in rows),
            "decision_as_of": contract["decision_as_of"], "later_observations_used_for_decision": False,
            "operational_availability": "not established; acquisition-time-gated retrospective reconstruction",
            "decision_time_trends_reproduced_from_csv": trends,
            "validated_near_tanager_baseline": fusion["temporal_evidence"]["baseline"]},
        "validated_full_scene_result": {
            "scope": "Loaded from the committed full-scene contract/evidence; not inferred from this sample.",
            "analysis_level": contract["analysis_level"], "spectral_state": fusion["spectral_evidence"]["state"],
            "temporal_state": fusion["temporal_evidence"]["state"], "ground_state": fusion["ground_evidence"]["state"],
            "final_decision": contract["decision_state"], "automation_allowed": contract["automation_allowed"],
            "decision_as_of": contract["decision_as_of"], "ml_available": contract["data_availability"]["ml"],
            "ml_used_for_decision": False, "recommended_next_action": contract["recommended_next_action"],
            "sources": {path: {"canonical_json_sha256": canonical_hash(root / path)} for path in
                        ("examples/product_contract_konya.json", "dashboard/public/data/konya/fusion.json")}},
        "scientific_cautions": ["Decision support, not ground truth.", "No drought probability, disease diagnosis, crop-failure prediction or calibrated confidence.",
                                "Ground evidence is required before intervention; automation is disabled.",
                                "NDMI drives relative screening; NDVI/NDRE are correlated supporting modifiers.",
                                "Experimental unsupervised ML does not change Stage 4's decision."],
        "limitations": [provenance["scope"], provenance["spatial_interpretation"], provenance["availability_caution"],
                        "Quality-valid sampling excludes masked pixels; sample vegetation coverage is not full-scene coverage.",
                        "ML is fitted and scored within the same sample; it is exploratory, not an out-of-sample evaluation.",
                        "Exact floating-point results can vary across library versions, BLAS implementations or hardware.",
                        *contract["limitations"]],
        "execution_requirements": {"network": False, "gpu": False, "raw_satellite_files": False,
                                   "credentials": False, "dashboard_or_node": False},
    }

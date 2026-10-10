"""Deterministic Stage 5B presentation export. No processing, downloads or inference.

Only explicitly selected JSON fields and existing PNGs enter the public package.
Run from any directory. --check detects stale/missing exports without writing.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agripulse import product_contract as pc

SCENE = "20250608_091605_90_4001"
DESTINATION = ROOT / "dashboard/public/data/konya"
FIGURES = {
    "spatial": [("stress/moisture_stress_risk.png", "Scene-relative moisture-risk score", "Relative vegetation ranks; gray pixels are unassessed. Image-pixel axes, not field boundaries or a geographic overlay."),
                ("stress/moisture_stress_classes.png", "Relative risk classes", "Class extent is not drought prevalence or calibrated severity."),
                ("stress/expert_evidence.png", "NDVI, NDRE, NDMI and risk", "Shared spectral proxies on the same classified vegetation population; not independent validation.")],
    "temporal": [("sentinel/temporal_evidence.png", "Full-season temporal context", "April–July 2025 retrospective context: 44 observations. Dates after the decision cutoff do not select the Stage 4 decision. Shading shows spatial P25–P75, not confidence intervals.")],
    "fusion": [("fusion/evidence_fusion.png", "Stage 4 evidence fusion", "Saved acquisition-time-gated reconstruction; not proof of a live operational decision in June 2025.")],
    "spectral": [("spectral/hyperspectral_value.png", "Hyperspectral information context", "More spectral detail does not establish improved prediction accuracy."),
                 ("spectral/group_spectral_signatures.png", "Group spectral signatures", "Groups were selected using Stage 2 risk. Their separation is not independent confirmation of moisture stress.")],
    "ml": [("ml/anomaly_score.png", "Experimental spectral anomaly score", "Continuous scene-relative score; not a probability or a diagnostic threshold."),
           ("ml/anomaly_context.png", "Anomaly and Stage 2 context", "The layers answer different questions. Their relationship is descriptive, not independent validation."),
           ("ml/pca_summary.png", "PCA summary", "Retained sample variance is not accuracy or physical importance.")],
}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def select(data, *keys):
    return {key: data[key] for key in keys}


def build_package(root=ROOT):
    sources = {}

    def read(relative):
        data = (root / relative).read_bytes()
        sources[relative] = {"path": relative, "sha256": digest(data), "bytes": len(data)}
        return json.loads(data)

    contract = read("examples/product_contract_konya.json")
    require(contract == pc.konya_example().to_dict(), "Stage 4.7 snapshot differs from the validated contract")
    scene = read("outputs/tanager/scene_summary.json")
    stress = read("outputs/stress/stress_summary.json")
    stats = read("outputs/stress/stress_statistics.json")
    temporal = read("outputs/sentinel/temporal_summary.json")
    decision = read("outputs/fusion/decision.json")
    fusion = read("outputs/fusion/fusion_summary.json")
    spectral = read("outputs/spectral/spectral_summary.json")
    ml = read("outputs/ml/ml_summary.json")
    for value in [scene["scene_id"], stress["source_scene_id"], temporal["source_scene_id"], decision["source_scene_id"], spectral["source_scene"], ml["scene_id"]]:
        require(value == SCENE, "Mixed or unsupported scenes; no export written")
    require(decision["decision"] == fusion["decision"] == contract["decision_state"], "Decision mismatch")
    require(decision["automation_allowed"] is False and fusion["automation_allowed"] is False, "Automation must remain blocked")
    require(decision["matched_rule_id"] == fusion["matched_rule_id"] == "D06", "Unexpected rule")
    require(datetime.fromisoformat(decision["decision_as_of"]) == datetime.fromisoformat(contract["decision_as_of"]), "Cutoff mismatch")
    require(decision["recommended_next_step"] == contract["recommended_next_action"], "Next action mismatch")
    geometry = contract["aoi"]["geometry"]
    bbox = [geometry[k] for k in ("west", "south", "east", "north")]
    require(all(item["bbox"] == bbox for item in (scene, stress, temporal, decision)), "AOI mismatch")
    require(decision["spectral_evidence"]["state"] == "RELATIVE_HOTSPOTS_PRESENT", "Unexpected spectral state")
    require(decision["temporal_evidence"]["state"] == "NEUTRAL_OR_MIXED", "Unexpected temporal state")
    require(decision["ground_evidence"]["state"] == contract["data_availability"]["ground"] == "UNAVAILABLE" and not decision["ground_evidence"]["observations"], "Unexpected ground evidence")
    require(ml["score_is_probability"] is False and ml["calibrated_agronomic_classifier"] is False, "ML semantics mismatch")
    # Recheck saved, local lineage; never reopen raw HDF5 or Sentinel cache.
    for record in fusion["input_provenance"].values():
        path = root / record["path"]
        require(path.resolve().is_relative_to((root / "outputs").resolve()), "Invalid lineage path")
        require(digest(path.read_bytes()) == record["sha256"], f"Stale fusion lineage: {record['path']}")
    require(digest((root / "outputs/tanager/scene_summary.json").read_bytes()) == stress["phase1_summary_sha256"], "Stale Stage 1 lineage")
    for upstream in (spectral, ml):
        for key, relative in {"stage1_summary": "outputs/tanager/scene_summary.json", "stage2_summary": "outputs/stress/stress_summary.json", "pixels": "outputs/stress/pixel_evidence.npz", "stage2_pixels": "outputs/stress/pixel_evidence.npz"}.items():
            if key in upstream["input_provenance"]:
                require(digest((root / relative).read_bytes()) == upstream["input_provenance"][key]["sha256"], "Stale spectral/ML lineage")

    documents = {
        "contract": contract,
        "simple": {"projection": pc.konya_example(pc.PresentationMode.SIMPLE).presentation_content(),
                   "assessment": "Ground verification required",
                   "satellite": "Relative areas of concern are present",
                   "temporal": "No strong broad moisture decline confirmation",
                   "ml": "Unusual spectral patterns are present in some vegetation, but this does not identify their cause.",
                   "next_action": "Inspect highlighted areas and collect site-specific ground evidence before intervention."},
        "spatial": {"summary": select(stress, "classified_vegetation_pixels", "vegetation_threshold", "risk_class_percentages", "risk_class_percentage_denominator", "methodology", "limitations"), "statistics": stats},
        "temporal": {"decision_time": decision["temporal_evidence"], "season": select(temporal, "requested_date_range", "usable_temporal_observations", "interpretation", "limitations", "cloud_masking_methodology", "trend_methodology"), "retrospective": fusion["retrospective_context_not_used_for_decision"]},
        "fusion": decision,
        "spectral": select(spectral, "number_of_bands_in_range", "bands_with_statistics_in_both_groups", "group_definitions", "information_comparison", "methodology", "limitations"),
        "ml": select(ml, "stage_name", "eligible_vegetation_pixel_count", "usable_band_count", "excluded_band_count", "fitting_sample_size", "pca", "isolation_forest", "anomaly_score_definition", "anomaly_statistics", "descriptive_stage2_comparison", "scientific_limitations", "score_is_probability", "calibrated_agronomic_classifier"),
    }
    output = {}
    figures = {}
    for section, entries in FIGURES.items():
        figures[section] = []
        for relative, title, caption in entries:
            original = "outputs/" + relative
            data = (root / original).read_bytes()
            require(data.startswith(b"\x89PNG\r\n\x1a\n"), f"Invalid PNG: {relative}")
            width, height = struct.unpack(">II", data[16:24])
            name = "figures/" + Path(relative).name
            output[name] = data
            figures[section].append({"src": "/data/konya/" + name, "title": title, "caption": caption, "width": width, "height": height, "source": original, "sha256": digest(data)})
    documents["provenance"] = {"scene": select(scene, "scene_id", "acquisition_date", "bbox", "ground_sample_distance_m", "spatial_resolution_m", "projection", "exact_selected_wavelengths", "valid_pixel_definition", "license", "data_attribution"), "sources": list(sources.values()), "lineage": fusion["upstream_lineage"], "attribution": "Planet Labs PBC, CC-BY-4.0. Sentinel-2: Copernicus / ESA via Microsoft Planetary Computer. Reference notebooks: Dr. Vincent Markiet / Space42."}
    for name, document in documents.items():
        output[name + ".json"] = encode(document)
    output["manifest.json"] = encode({"schema_version": "5B.1", "scene_id": SCENE, "files": {name: {"path": name + ".json", "sha256": digest(output[name + ".json"])} for name in documents}, "figures": figures})
    return output


def export(destination=DESTINATION, *, check=False):
    package = build_package()
    if check:
        for name, data in package.items():
            require((destination / name).is_file() and (destination / name).read_bytes() == data, f"Stale or missing export: {name}")
        require({str(p.relative_to(destination)).replace('\\', '/') for p in destination.rglob('*') if p.is_file()} == set(package), "Unexpected public package files")
    else:
        for name, data in package.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return len(package), sum(map(len, package.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    count, size = export(check=args.check)
    print(f"{'Verified' if args.check else 'Exported'} {count} files, {size:,} bytes; scientific artifacts unchanged.")

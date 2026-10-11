"""Submission checks use real bundled measurements; no synthetic production data."""
import csv
from datetime import datetime
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import nbformat
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import export_submission_sample as exporter
import execute_submission_notebook as runner
import export_dashboard
import submission_workflow as workflow
from agripulse import ml, stress, tanager


class SubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample, cls.provenance = workflow.load_sample(ROOT)

    def test_real_sample_schema_provenance_and_size(self):
        p, s = self.provenance, self.sample
        self.assertEqual(p["scene_id"], "20250608_091605_90_4001")
        self.assertEqual(s["spectra"].shape, (2048, 240))
        self.assertEqual(p["random_seed"], 813)
        self.assertEqual(p["sources"]["source_hdf5"]["sha256"], "f3115eb5eb3fe5355326e81a4041e08f060887f1d4264ed810df19f4de08e53a")
        for record in p["sources"].values():
            self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$")
            self.assertFalse(Path(record["file"]).is_absolute())
        self.assertIn("CC-BY-4.0", p["attribution"])
        self.assertTrue(np.all(np.diff(s["source_flat_indices"]) > 0))
        self.assertLess((ROOT / "data/sample_input/tanager_sample.npz").stat().st_size, 2_500_000)

    def test_archive_byte_determinism(self):
        first = exporter.deterministic_npz(self.sample)
        self.assertEqual(first, exporter.deterministic_npz(dict(reversed(list(self.sample.items())))))
        self.assertEqual(first, (ROOT / "data/sample_input/tanager_sample.npz").read_bytes())

    def test_deterministic_real_sampling_membership(self):
        evidence = ROOT / "outputs/stress/pixel_evidence.npz"
        if not evidence.exists():
            self.skipTest("Maintainer-only source-mask check; bundled notebook does not require local outputs")
        with np.load(evidence, allow_pickle=False) as archive:
            expected = exporter.select_pixels(archive["quality_mask"])
            np.testing.assert_array_equal(expected, self.sample["source_flat_indices"])
            np.testing.assert_array_equal(expected, exporter.select_pixels(archive["quality_mask"]))

    def test_exporter_has_no_missing_source_fallback(self):
        with patch.object(ml, "load_inputs", side_effect=FileNotFoundError("Real inputs missing")):
            with self.assertRaisesRegex(FileNotFoundError, "Real inputs missing"):
                exporter.build_package()

    def test_sample_indices_match_saved_real_stage2_values(self):
        s = self.sample
        indices = tanager.compute_indices({name: s[name].reshape(-1, 1) for name in tanager.TARGETS_NM}, s["valid_mask"].reshape(-1, 1))
        result = stress.assess_stress(indices, s["valid_mask"].reshape(-1, 1))
        np.testing.assert_array_equal(result.vegetation_mask.ravel(), s["vegetation_mask"])
        self.assertTrue(np.isnan(result.risk_score[~result.classified_mask]).all())
        evidence = ROOT / "outputs/stress/pixel_evidence.npz"
        if evidence.exists():
            with np.load(evidence, allow_pickle=False) as archive:
                for name in stress.INDEX_NAMES:
                    original = archive[name.lower()].ravel()[s["source_flat_indices"]]
                    mask = result.classified_mask.ravel()
                    np.testing.assert_array_equal(indices[name].ravel()[mask], original[mask])

    def test_ml_is_deterministic_unsupervised_and_excludes_atmosphere(self):
        s = self.sample
        wave = s["wavelength_nm"]
        self.assertFalse(np.any((wave >= 1350) & (wave <= 1450)))
        values = s["spectra"][s["ml_eligible_mask"]]
        a, b = ml.fit_anomaly(values), ml.fit_anomaly(values.copy())
        np.testing.assert_array_equal(a.scores, b.scores)
        self.assertEqual(a.forest.random_state, 813)
        self.assertTrue(np.isfinite(a.scores).all())
        self.assertTrue(np.all(s["ml_eligible_mask"] <= s["vegetation_mask"]))

    def test_temporal_cutoff_and_real_observations(self):
        rows = workflow.temporal_rows(ROOT, self.provenance["decision_as_of"])
        self.assertEqual(len(rows), 44)
        self.assertEqual(sum(r["eligible"] for r in rows), 19)
        self.assertTrue(all(not r["eligible"] for r in rows if r["date"] >= "2025-07-01"))
        source = ROOT / "outputs/sentinel/sentinel_timeseries.csv"
        if source.exists():
            saved = list(csv.DictReader(io.StringIO(source.read_text(encoding="utf-8"))))
            compact = list(csv.DictReader(io.StringIO((ROOT / "data/sample_input/sentinel_timeseries_sample.csv").read_text(encoding="utf-8"))))
            self.assertEqual(saved, [{k: r[k] for k in saved[0]} for r in compact])

    def test_straddling_mosaic_uses_all_acquisitions(self):
        # A real existing multi-acquisition row; cutoff between its actual sources.
        with (ROOT / "data/sample_input/sentinel_timeseries_sample.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        row = next(r for r in rows if len(r["acquisition_datetimes"].split(";")) > 1)
        times = sorted(datetime.fromisoformat(t) for t in row["acquisition_datetimes"].split(";"))
        cutoff = (times[0] + (times[-1] - times[0]) / 2).isoformat()
        row = dict(row, eligible_at_decision_cutoff="false", after_decision_cutoff="true")
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "data/sample_input"
            directory.mkdir(parents=True)
            (directory / "sentinel_timeseries_sample.csv").write_text(stream.getvalue(), encoding="utf-8")
            self.assertFalse(workflow.temporal_rows(Path(tmp), cutoff)[0]["eligible"])

    def test_line_endings_do_not_change_semantic_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "data/sample_input", root / "data/sample_input")
            path = root / "data/sample_input/sentinel_timeseries_sample.csv"
            before = workflow.canonical_hash(path)
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            self.assertEqual(before, workflow.canonical_hash(path))
            workflow.load_sample(root)
            path = root / "contract.json"
            document = workflow.read_json(ROOT / "examples/product_contract_konya.json")
            path.write_text(json.dumps(document), encoding="utf-8")
            before = workflow.canonical_hash(path)
            path.write_bytes(json.dumps(document, indent=4).replace("\n", "\r\n").encode())
            self.assertEqual(before, workflow.canonical_hash(path))

    def test_notebook_portability_visible_output_and_pins(self):
        path = ROOT / "notebooks/AgriPulse_813_PoC.ipynb"
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        # Scan decoded text, not JSON escape sequences after ordinary colons.
        parts = [c.source for c in notebook.cells]
        for cell in notebook.cells:
            for output in cell.get("outputs", []):
                parts.append(output.get("text", ""))
                parts.extend(value for mime, value in output.get("data", {}).items() if mime.startswith("text/"))
        text = "\n".join(parts)
        self.assertNotRegex(text, r"[A-Za-z]:[\\/]")
        self.assertNotIn("AGRIPULSE_DATA_DIR", text)
        self.assertNotIn("OneDrive", text)
        code = [c for c in notebook.cells if c.cell_type == "code"]
        self.assertGreaterEqual(len(code), 10)
        self.assertTrue(all(c.execution_count is not None for c in code))
        self.assertTrue(any("image/png" in o.get("data", {}) for c in code for o in c.outputs))
        for line in (ROOT / "requirements.txt").read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                self.assertRegex(line, r"^[A-Za-z0-9_-]+==[0-9]+\.[0-9]+\.[0-9]+$")

    def test_validated_truth_and_outputs(self):
        contract, fusion = workflow.validated_result(ROOT)
        summary = workflow.read_json(ROOT / "results/example_summary.json")
        result = summary["validated_full_scene_result"]
        self.assertEqual(result["final_decision"], contract["decision_state"])
        self.assertFalse(result["automation_allowed"])
        self.assertFalse(result["ml_used_for_decision"])
        self.assertEqual(result["temporal_state"], "NEUTRAL_OR_MIXED")
        self.assertEqual(result["spectral_state"], "RELATIVE_HOTSPOTS_PRESENT")
        self.assertFalse(summary["compact_sample_calculations"]["ml"]["supervised_training"])
        self.assertTrue((ROOT / "results/example_output.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_existing_package_semantics_survive_checkout_line_endings(self):
        if not (ROOT / "outputs/fusion/decision.json").exists():
            self.skipTest("Maintainer-only full package provenance check")
        package = export_dashboard.build_package()
        for name, expected in package.items():
            actual = (ROOT / "dashboard/public/data/konya" / name).read_bytes()
            if name.endswith(".json"):
                self.assertEqual(json.loads(actual), json.loads(expected), name)
            else:
                self.assertEqual(actual, expected, name)

    def test_fresh_clone_clean_kernels_offline_and_deterministic(self):
        # Copy only repository inputs: no outputs/, raw sources, caches or existing results.
        with tempfile.TemporaryDirectory(prefix="agripulse-clone-") as tmp:
            root = Path(tmp)
            for relative in ("data/sample_input", "src/agripulse"):
                shutil.copytree(ROOT / relative, root / relative, ignore=shutil.ignore_patterns("__pycache__"))
            for relative in ("notebooks/AgriPulse_813_PoC.ipynb", "scripts/submission_workflow.py",
                             "examples/product_contract_konya.json", "dashboard/public/data/konya/contract.json",
                             "dashboard/public/data/konya/fusion.json", "dashboard/public/data/konya/temporal.json"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            nbpath = root / "notebooks/AgriPulse_813_PoC.ipynb"
            notebook = nbformat.read(nbpath, as_version=4)
            # Exercise the offline/raw-data guards after the setup cell. No external call succeeds.
            position = next(i for i, c in enumerate(notebook.cells) if c.cell_type == "code") + 1
            notebook.cells.insert(position, nbformat.v4.new_code_cell('''
import socket
for action in (lambda: socket.getaddrinfo("example.invalid", 443),
               lambda: open("forbidden_source.h5", "rb")):
    try:
        action()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Offline/raw-source guard did not reject access")
assert not (root / "outputs").exists()
'''))
            nbformat.write(notebook, nbpath)
            with patch.dict("os.environ", {"AGRIPULSE_DATA_DIR": str(root / "absent-raw-input")}):
                first = runner.execute(root)
                summary = (root / "results/example_summary.json").read_bytes()
                second = runner.execute(root, working_directory=root / "notebooks")
                self.assertEqual(summary, (root / "results/example_summary.json").read_bytes())
            self.assertEqual(json.loads(summary), workflow.read_json(ROOT / "results/example_summary.json"))
            self.assertFalse((root / "outputs").exists())
            print("Fresh-copy clean-kernel runtimes:", first["notebook_runtime_seconds"], second["notebook_runtime_seconds"])


if __name__ == "__main__":
    unittest.main()

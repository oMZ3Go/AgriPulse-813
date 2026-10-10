"""Stage 5B export fidelity tests use only the existing real scientific artifacts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("export_dashboard", ROOT / "scripts/export_dashboard.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class DashboardExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = exporter.build_package()

    def document(self, name):
        return json.loads(self.package[name + ".json"])

    def test_export_matches_current_artifacts_and_is_deterministic(self):
        self.assertEqual(self.package, exporter.build_package())
        exporter.export(check=True)

    def test_contract_and_decision_are_unchanged(self):
        self.assertEqual(self.document("contract"), json.loads((ROOT / "examples/product_contract_konya.json").read_text()))
        self.assertEqual(self.document("fusion"), json.loads((ROOT / "outputs/fusion/decision.json").read_text()))
        self.assertEqual(self.document("contract")["decision_state"], "GROUND_VERIFICATION_REQUIRED")
        self.assertIs(self.document("contract")["automation_allowed"], False)
        self.assertEqual(self.document("simple")["projection"], exporter.pc.konya_example(exporter.pc.PresentationMode.SIMPLE).presentation_content())

    def test_real_metrics_and_temporal_cutoff_are_preserved(self):
        real_ml = json.loads((ROOT / "outputs/ml/ml_summary.json").read_text())
        for key, value in self.document("ml").items():
            self.assertEqual(value, real_ml[key])
        self.assertAlmostEqual(real_ml["descriptive_stage2_comparison"]["spearman_rank_correlation"], .003357, places=6)
        self.assertEqual(self.document("temporal")["decision_time"]["historical_observations_used"], 19)
        self.assertEqual(self.document("temporal")["season"]["usable_temporal_observations"], 44)
        self.assertFalse(self.document("temporal")["retrospective"]["used_in_decision"])
        self.assertEqual(self.document("spatial")["statistics"], json.loads((ROOT / "outputs/stress/stress_statistics.json").read_text()))

    def test_figures_are_byte_identical_and_payloads_match_manifest_hashes(self):
        manifest = self.document("manifest")
        for entry in manifest["files"].values():
            self.assertEqual(hashlib.sha256(self.package[entry["path"]]).hexdigest(), entry["sha256"])
        for figures in manifest["figures"].values():
            for figure in figures:
                data = self.package[figure["src"].removeprefix("/data/konya/")]
                self.assertEqual(data, (ROOT / figure["source"]).read_bytes())
                self.assertEqual(hashlib.sha256(data).hexdigest(), figure["sha256"])

    def test_only_allowlisted_small_artifacts_are_exported(self):
        self.assertEqual(len(self.package), 19)
        self.assertLess(sum(map(len, self.package.values())), 5_000_000)
        self.assertTrue(all(Path(name).suffix in (".json", ".png") for name in self.package))
        for name, data in self.package.items():
            if name.endswith(".json"):
                self.assertNotIn(b"C:\\\\", data)
                self.assertNotIn(b"access_token", data)

    def test_export_is_offline_and_does_not_write_scientific_inputs(self):
        paths = [*ROOT.glob("outputs/**/*"), *ROOT.glob("src/agripulse/*.py"), ROOT / "examples/product_contract_konya.json"]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
        with tempfile.TemporaryDirectory() as temporary, patch("socket.socket.connect", side_effect=AssertionError("Offline export")):
            exporter.export(Path(temporary))
            exporter.export(Path(temporary), check=True)
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})

    def test_mismatched_scene_or_science_stops_export_before_writing(self):
        original = Path.read_bytes
        cases = [
            ("outputs/ml/ml_summary.json", "scene_id", "other-scene"),
            ("outputs/ml/ml_summary.json", "score_is_probability", True),
            ("outputs/fusion/decision.json", "automation_allowed", True),
            ("outputs/fusion/decision.json", "decision", "MONITOR"),
            ("outputs/stress/stress_summary.json", "classified_vegetation_pixels", 1),
        ]
        for filename, key, value in cases:
            with self.subTest(filename=filename, key=key):
                target = ROOT / filename
                def changed(path):
                    raw = original(path)
                    if path == target:
                        data = json.loads(raw)
                        data[key] = value
                        return exporter.encode(data)
                    return raw
                with tempfile.TemporaryDirectory() as temporary, patch.object(Path, "read_bytes", changed):
                    with self.assertRaises(ValueError):
                        exporter.export(Path(temporary))
                    self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_check_detects_missing_stale_and_unexpected_exports(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            exporter.export(destination)
            (destination / "simple.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "Stale"):
                exporter.export(destination, check=True)
            exporter.export(destination)
            (destination / "unexpected.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                exporter.export(destination, check=True)


if __name__ == "__main__":
    unittest.main()

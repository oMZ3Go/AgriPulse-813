"""Stage 4.5 tests: actual local Tanager data, offline reproduction and guards.

Small explicit vectors test boundary/statistics rules only; they never become
production imagery. Existing Stage 1/2 artifacts are required, not synthesized.
"""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agripulse import spectral, tanager


def upstream_hashes():
    return {str(path): tanager.sha256(path) for name in ("tanager", "stress", "sentinel", "fusion")
            for path in (tanager.REPO_ROOT / "outputs" / name).iterdir() if path.is_file()}


def offline():
    return patch("requests.sessions.Session.request", side_effect=AssertionError("Stage 4.5 must be offline"))


class SpectralRuleTests(unittest.TestCase):
    def test_window_boundaries_and_order(self):
        wavelengths = np.array([399.99, 400, 665, 1700, 1700.01])
        np.testing.assert_array_equal(spectral.window_band_indices(wavelengths), [1, 2, 3])
        for bad in ([500, 400], [400, 400], [400, np.nan], [400, np.inf], [], [1701, 1800]):
            with self.subTest(bad=bad), self.assertRaises(tanager.PipelineError):
                spectral.window_band_indices(np.array(bad))

    def test_percentiles_exclude_invalid_values_without_clipping(self):
        # Only the four finite, nonnegative, non-nodata observations enter percentiles.
        data = np.array([np.nan, np.inf, -np.inf, -0.1, 999.0, 0.0, 0.2, 0.4, 1.2])
        original = np.percentile
        with patch.object(spectral.np, "percentile", wraps=original) as percentile:
            stats = spectral.band_statistics(data, nodata=999.0)
            np.testing.assert_array_equal(percentile.call_args.args[0], [0, 0.2, 0.4, 1.2])
        self.assertEqual(stats["valid_pixel_count"], 4)
        self.assertEqual(stats["excluded_pixel_count"], 5)
        self.assertEqual(stats["above_one_pixel_count"], 1)
        self.assertAlmostEqual(stats["p25"], 0.15)
        self.assertAlmostEqual(stats["median"], 0.3)
        self.assertAlmostEqual(stats["p75"], 0.6)
        empty = spectral.band_statistics(np.array([np.nan, -1, np.inf]))
        self.assertEqual(empty["valid_pixel_count"], 0)
        self.assertTrue(all(empty[key] is None for key in ("p25", "median", "p75")))
        json.dumps(empty, allow_nan=False)

    def test_ties_are_retained_and_empty_classes_fail_without_retuning(self):
        pixels = {key: np.ones((2, 4), dtype=bool) for key in ("quality_mask", "vegetation_mask", "classified_mask")}
        pixels["risk_score"] = np.array([[5, 5, 5, 50], [50, 95, 95, 95]], dtype=float)
        groups, _ = spectral.select_groups(pixels)
        self.assertEqual(int(groups["lower"].sum()), 3)
        self.assertEqual(int(groups["higher"].sum()), 3)
        self.assertFalse((groups["lower"] & groups["higher"]).any())
        pixels["risk_score"][:] = 50
        with self.assertRaisesRegex(tanager.PipelineError, "empty"):
            spectral.select_groups(pixels)

    def test_protected_output_directories_are_rejected_before_reading(self):
        for name in ("tanager", "stress", "sentinel", "fusion"):
            with self.subTest(name=name), patch.object(spectral, "load_inputs") as loader:
                with self.assertRaisesRegex(tanager.PipelineError, "existing stage"):
                    spectral.run_pipeline(output=tanager.REPO_ROOT / "outputs" / name / "nested")
                loader.assert_not_called()


class RealSceneSpectralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = upstream_hashes()
        with offline(), redirect_stdout(io.StringIO()):
            cls.inputs = spectral.load_inputs()
            cls.summary = spectral.analyze(cls.inputs)
        cls.groups, cls.definitions = spectral.select_groups(cls.inputs.pixels)

    @classmethod
    def tearDownClass(cls):
        if cls.before != upstream_hashes():
            raise AssertionError("Existing Stage 1-4 outputs changed during Stage 4.5 tests")

    def test_quality_vegetation_and_risk_classes_are_preserved(self):
        pixels = self.inputs.pixels
        for key, mask in self.groups.items():
            with self.subTest(group=key):
                self.assertTrue(pixels["quality_mask"][mask].all())
                self.assertTrue(pixels["vegetation_mask"][mask].all())
                self.assertTrue(pixels["classified_mask"][mask].all())
                self.assertTrue(np.isfinite(pixels["risk_score"][mask]).all())
                self.assertTrue((pixels["risk_class"][mask] == (1 if key == "lower" else 4)).all())
                self.assertTrue((pixels["ndvi"][mask] >= self.inputs.stage2_summary["vegetation_threshold"]).all())
        self.assertFalse((self.groups["lower"] & self.groups["higher"]).any())

    def test_sampling_is_deterministic_and_uses_entire_quantile_class_intersections(self):
        again, definitions = spectral.select_groups(self.inputs.pixels)
        self.assertEqual(definitions, self.definitions)
        scores = self.inputs.pixels["risk_score"]
        classified = self.inputs.pixels["classified_mask"]
        q25, q75 = np.percentile(scores[classified], [25, 75])
        np.testing.assert_array_equal(again["lower"], classified & (scores <= q25) & (scores < 25))
        np.testing.assert_array_equal(again["higher"], classified & (scores >= q75) & (scores >= 75))
        for key in again:
            np.testing.assert_array_equal(self.groups[key], again[key])
        self.assertEqual(int(again["lower"].sum()), 24373)
        self.assertEqual(int(again["higher"].sum()), 21203)

    def test_invalid_pixels_cannot_be_sampled(self):
        pixels = dict(self.inputs.pixels)
        locations = np.argwhere(self.groups["lower"])[:4]
        for key, location in zip(("quality_mask", "vegetation_mask", "classified_mask", "risk_score"), locations):
            pixels[key] = pixels[key].copy()
            pixels[key][tuple(location)] = np.nan if key == "risk_score" else False
        groups, _ = spectral.select_groups(pixels)
        for location in locations:
            self.assertFalse(any(mask[tuple(location)] for mask in groups.values()))

    def test_metadata_window_order_and_no_silent_band_omission(self):
        summary = self.summary
        actual = np.array(summary["wavelengths_nm"])
        expected_indices = np.flatnonzero((self.inputs.wavelengths_nm >= 400) & (self.inputs.wavelengths_nm <= 1700))
        np.testing.assert_array_equal(actual, self.inputs.wavelengths_nm[expected_indices])
        self.assertTrue((np.diff(actual) > 0).all())
        self.assertEqual(summary["number_of_bands_in_range"], 260)
        self.assertEqual(summary["bands_with_statistics_in_both_groups"], 250)
        self.assertEqual(len(summary["bands_without_comparable_statistics_nm"]), 10)
        self.assertFalse(summary["information_comparison"]["satellite_813_response_simulated"])

    def test_all_statistics_finite_or_explicitly_missing_and_percentiles_ordered(self):
        json.dumps(self.summary, allow_nan=False)
        for group in self.summary["groups"].values():
            for row in group["band_statistics"]:
                self.assertEqual(row["valid_pixel_count"] + row["excluded_pixel_count"], group["selected_pixel_count"])
                if row["valid_pixel_count"]:
                    self.assertTrue(np.isfinite([row[k] for k in ("p25", "median", "p75")]).all())
                    self.assertLessEqual(row["p25"], row["median"])
                    self.assertLessEqual(row["median"], row["p75"])
                else:
                    self.assertTrue(all(row[k] is None for k in ("p25", "median", "p75")))

    def test_statistics_match_independent_reads_of_real_cube_including_gaps(self):
        wavelengths = np.array(self.summary["wavelengths_nm"])
        with h5py.File(self.inputs.phase1.source_path, "r") as source:
            cube = source[f"{tanager.HDF_ROOT}/surface_reflectance"]
            # Across the window, with blue-band exclusions and an empty water-vapor band.
            for target in (401, 665, 775, 1225, 1380, 1540, 1698):
                position = int(np.argmin(np.abs(wavelengths - target)))
                band_index = self.summary["source_band_indices_zero_based"][position]
                plane = cube[band_index]
                nodata = self.inputs.band_metadata[band_index].get("nodata")
                for key, mask in self.groups.items():
                    values = plane[mask].astype(float)
                    valid = np.isfinite(values) & (values >= 0)
                    if isinstance(nodata, (float, int)):
                        valid &= values != nodata
                    row = self.summary["groups"][key]["band_statistics"][position]
                    self.assertEqual(row["valid_pixel_count"], int(valid.sum()))
                    if valid.any():
                        np.testing.assert_array_equal([row[k] for k in ("p25", "median", "p75")],
                                                      np.percentile(values[valid], [25, 50, 75]))
        for low, high, delta in zip(self.summary["groups"]["lower"]["band_statistics"],
                                    self.summary["groups"]["higher"]["band_statistics"],
                                    self.summary["median_difference_higher_minus_lower"]):
            if low["median"] is None or high["median"] is None:
                self.assertIsNone(delta)
            else:
                self.assertEqual(delta, high["median"] - low["median"])

    def test_contrast_ranking_uses_fixed_windows_and_excludes_baseline_and_caution(self):
        report = self.summary["exploratory_contrast_regions"]
        w = np.array(self.summary["wavelengths_nm"])
        difference = np.array(self.summary["median_difference_higher_minus_lower"], dtype=float)
        baseline = [meta["wavelength_nm"] for meta in self.summary["existing_index_bands"].values()]
        all_windows = report["all_eligible_windows_ranked"]
        self.assertEqual(all_windows, sorted(all_windows, key=lambda row: (-row["mean_absolute_median_difference"], row["window_nm"][0])))
        self.assertEqual(report["regions"][0], all_windows[0])
        for row in all_windows:
            start, end = row["window_nm"]
            self.assertEqual(end - start, 25)
            mask = (w >= start) & (w < end)
            self.assertTrue(np.isfinite(difference[mask]).all())
            self.assertTrue((np.abs(w[mask, None] - np.array(baseline)) > 15).all())
            self.assertFalse(((w[mask] >= 1350) & (w[mask] <= 1450)).any())
            self.assertAlmostEqual(row["mean_absolute_median_difference"], float(np.mean(np.abs(difference[mask]))), places=14)
        selected = report["regions"]
        self.assertLessEqual(len(selected), 3)
        for i, row in enumerate(selected):
            for other in selected[i + 1:]:
                self.assertGreaterEqual(abs(row["window_nm"][0] - other["window_nm"][0]), 100)

    def test_mismatched_lineage_masks_scores_and_scene_are_rejected(self):
        for change in ("lineage", "mask", "score", "scene"):
            summary = deepcopy(self.inputs.stage2_summary)
            pixels = dict(self.inputs.pixels)
            location = tuple(np.argwhere(self.groups["lower"])[0])
            if change == "lineage":
                summary["source_hdf5_sha256"] = "wrong"
            elif change == "scene":
                pixels["scene_id"] = np.array("wrong")
            else:
                key = "quality_mask" if change == "mask" else "risk_score"
                pixels[key] = pixels[key].copy()
                pixels[key][location] = False if change == "mask" else 99.9
            with self.subTest(change=change), self.assertRaises(tanager.PipelineError):
                spectral.validate_stage2(self.inputs.phase1, summary, pixels)

    def test_real_outputs_reproduce_offline_and_upstream_files_remain_unchanged(self):
        files = {"spectral_summary.json", "group_spectral_signatures.png", "spectral_difference.png", "hyperspectral_value.png"}
        before = upstream_hashes()
        with tempfile.TemporaryDirectory(dir=tanager.REPO_ROOT / "outputs") as directory:
            output = Path(directory)
            with offline(), patch("socket.create_connection", side_effect=AssertionError("No network")), redirect_stdout(io.StringIO()):
                actual = spectral.run_pipeline(output=output)
                first = {p.name: tanager.sha256(p) for p in output.iterdir() if p.is_file()}
                repeated = spectral.run_pipeline(output=output)
                second = {p.name: tanager.sha256(p) for p in output.iterdir() if p.is_file()}
            self.assertEqual(actual, self.summary)
            self.assertEqual(actual, repeated)
            self.assertEqual(set(first), files)
            self.assertEqual(first, second)
            self.assertEqual(json.loads((output / "spectral_summary.json").read_text()), self.summary)
            for filename in files - {"spectral_summary.json"}:
                self.assertEqual((output / filename).read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            # Compare against the actual requested deliverables as well as two fresh runs.
            self.assertEqual(first, {name: tanager.sha256(spectral.OUTPUT_DIR / name) for name in files})
        self.assertEqual(before, upstream_hashes())


if __name__ == "__main__":
    unittest.main()

"""Stage 3 tests: real cached COG windows plus small deterministic trend inputs.

Run the real pipeline first. Missing data is an error, never a dummy-data fallback.
No network or new satellite acquisition is permitted during these tests.
"""

import csv
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agripulse import sentinel


class TrendTests(unittest.TestCase):
    # These are explicitly deterministic unit-test vectors, not satellite data.
    def test_elapsed_days_and_directions(self):
        dates = ["2025-04-01", "2025-04-03", "2025-04-11", "2025-04-21"]
        increasing = sentinel.robust_trend(dates, [0.1, 0.12, 0.2, 0.3])
        decreasing = sentinel.robust_trend(dates, [0.7, 0.68, 0.6, 0.5])
        self.assertAlmostEqual(increasing["slope_per_day"], 0.01)
        self.assertEqual(increasing["direction"], "increasing")
        self.assertAlmostEqual(decreasing["slope_per_day"], -0.01)
        self.assertEqual(decreasing["direction"], "decreasing")
        stable = sentinel.robust_trend(dates, [0.4, 0.4, 0.4, 0.4])
        self.assertEqual(stable["direction"], "broadly stable")
        self.assertEqual(stable["slope_per_day"], 0)

    def test_outlier_and_missing_dates_do_not_imply_daily_spacing(self):
        dates = [f"2025-04-{day:02}" for day in (1, 2, 4, 7, 11, 16, 22)]
        values = [0.1, 0.11, 0.13, 0.99, 0.2, 0.25, 0.31]
        result = sentinel.robust_trend(dates, values)
        self.assertAlmostEqual(result["slope_per_day"], 0.01)
        self.assertEqual(result["direction"], "increasing")

    def test_bad_and_insufficient_trend_inputs(self):
        for dates, values in [(["2025-04-02", "2025-04-01"], [0.1, 0.2]),
                              (["2025-04-01", "2025-04-01"], [0.1, 0.2]),
                              (["2025-04-01"], [np.nan])]:
            with self.assertRaises(sentinel.PipelineError):
                sentinel.robust_trend(dates, values)
        self.assertIsNone(sentinel.robust_trend(["2025-04-01"], [0.1])["slope_per_day"])


class RealSentinelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = json.loads((sentinel.OUTPUT_DIR / "temporal_summary.json").read_text())
        cls.observations = json.loads((sentinel.OUTPUT_DIR / "sentinel_timeseries.json").read_text())["observations"]
        catalog = json.loads(Path(cls.summary["catalog_snapshot"]["path"]).read_text())
        cls.items = catalog["items"]
        cls.grouped, cls.dropped = sentinel.group_daily(cls.items)
        cls.grid, cls.footprint = sentinel.make_grid(cls.summary["bbox"], cls.summary["footprint_geometry"], cls.summary["grid"]["crs"])
        cls.directory = Path(cls.summary["raw_window_directory"])
        cls.threshold = cls.summary["vegetation_threshold"]
        first = cls.grouped[next(iter(cls.grouped))][0]
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Tests must be offline")):
            cls.arrays, cls.receipt = sentinel.load_scene(first, cls.grid, cls.directory, offline=True)

    def test_all_real_indices_finite_bounded_and_cloud_pixels_excluded(self):
        vegetation_count = 0
        excluded_count = 0
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Tests must be offline")):
            for items in self.grouped.values():
                for item in items:
                    with self.subTest(scene=item["id"]):
                        arrays, receipt = sentinel.load_scene(item, self.grid, self.directory, offline=True)
                        indices, valid = sentinel.scene_indices(arrays, receipt["calibration"], self.footprint)
                        vegetation, stats = sentinel.vegetation_statistics(indices, valid, self.threshold)
                        excluded = ~self.footprint | ~np.isin(arrays["SCL"], sentinel.ACCEPTED_SCL)
                        self.assertFalse(valid[excluded].any())
                        self.assertFalse(vegetation[excluded].any())
                        self.assertFalse(vegetation[indices["NDVI"] < self.threshold].any())
                        for name in sentinel.INDICES:
                            values = indices[name]
                            self.assertTrue(np.isfinite(values[valid]).all())
                            self.assertTrue((np.abs(values[valid]) <= 1 + 1e-12).all())
                            self.assertTrue(np.isnan(values[~valid]).all())
                            if vegetation.any():
                                self.assertAlmostEqual(stats[name]["median"], float(np.median(values[vegetation])), places=13)
                        vegetation_count += int(vegetation.sum())
                        excluded_count += int(excluded.sum())
        self.assertGreater(vegetation_count, 0)
        self.assertGreater(excluded_count, 0)

    def test_real_xml_calibration_not_uncorrected_dn_ratios(self):
        receipt = self.receipt
        xml = Path(receipt["product_metadata_xml"])
        self.assertEqual(sentinel.sha256(xml), receipt["product_metadata_sha256"])
        self.assertEqual(sentinel.parse_calibration(xml.read_bytes()), receipt["calibration"])
        indices, valid = sentinel.scene_indices(self.arrays, receipt["calibration"], self.footprint)
        y, x = np.argwhere(valid)[0]
        nir_dn, red_dn = float(self.arrays["B8A"][y, x]), float(self.arrays["B04"][y, x])
        nir_meta, red_meta = receipt["calibration"]["B8A"], receipt["calibration"]["B04"]
        nir = (nir_dn + nir_meta["add_offset_dn"]) / nir_meta["quantification_value"]
        red = (red_dn + red_meta["add_offset_dn"]) / red_meta["quantification_value"]
        self.assertAlmostEqual(indices["NDVI"][y, x], (nir - red) / (nir + red), places=13)

    def test_invalid_reflectance_and_missing_index_excluded(self):
        indices, valid = sentinel.scene_indices(self.arrays, self.receipt["calibration"], self.footprint)
        vegetation, _ = sentinel.vegetation_statistics(indices, valid, self.threshold)
        pixels = [tuple(p) for p in np.argwhere(vegetation)[:4]]
        arrays = {key: values.copy() for key, values in self.arrays.items()}
        arrays["B04"][pixels[0]] = 0  # Mark actual observations nodata/invalid.
        arrays["B11"][pixels[1]] = np.nan
        arrays["B8A"][pixels[2]] = 1  # Below the real product's additive offset.
        masked_indices, masked_valid = sentinel.scene_indices(arrays, self.receipt["calibration"], self.footprint)
        for pixel in pixels[:3]:
            self.assertFalse(masked_valid[pixel])
            self.assertTrue(all(np.isnan(values[pixel]) for values in masked_indices.values()))
        indices["NDMI"][pixels[3]] = np.nan
        screened, _ = sentinel.vegetation_statistics(indices, valid, self.threshold)
        self.assertFalse(screened[pixels[3]])

    def test_same_day_overlap_not_counted_twice_and_exact_duplicates_removed(self):
        day = next(day for day, items in self.grouped.items() if len(items) > 1)
        items = self.grouped[day]
        obs, mosaic, _ = sentinel.process_day(day, items, self.grid, self.footprint,
                                              self.directory, self.threshold, offline=True)
        union = np.zeros(self.footprint.shape, dtype=bool)
        for item in items:
            arrays, receipt = sentinel.load_scene(item, self.grid, self.directory, offline=True)
            _, valid = sentinel.scene_indices(arrays, receipt["calibration"], self.footprint)
            union |= valid
        self.assertEqual(obs["valid_pixel_count"], int(union.sum()))
        self.assertEqual(sum(s["contributing_pixels"] for s in obs["sources"]), int(union.sum()))
        self.assertLessEqual(int(union.sum()), sum(s["valid_pixels_in_footprint"] for s in obs["sources"]))
        first_arrays, first_receipt = sentinel.load_scene(items[0], self.grid, self.directory, offline=True)
        first_indices, first_valid = sentinel.scene_indices(first_arrays, first_receipt["calibration"], self.footprint)
        for name in sentinel.INDICES:
            np.testing.assert_array_equal(mosaic[name][first_valid], first_indices[name][first_valid])
        repeated, dropped = sentinel.group_daily([items[0], items[0]])
        self.assertEqual(sum(map(len, repeated.values())), 1)
        self.assertEqual(dropped, [items[0]["id"]])

    def test_saved_observations_reconstruct_from_real_windows(self):
        for saved in self.observations:
            with self.subTest(date=saved["date"]):
                computed, _, _ = sentinel.process_day(saved["date"], self.grouped[saved["date"]], self.grid,
                                                      self.footprint, self.directory, self.threshold, offline=True)
                self.assertEqual(computed, saved)

    def test_chronology_summary_fields_and_csv_json_agree(self):
        dates = [o["date"] for o in self.observations]
        self.assertEqual(dates, sorted(set(dates)))
        required = {"bbox", "requested_date_range", "stac_scenes_found", "usable_temporal_observations",
                    "dates_used", "cloud_masking_methodology", "vegetation_threshold", "sentinel_bands",
                    "temporal_statistics", "tanager_acquisition_date", "closest_sentinel_observation", "limitations"}
        self.assertTrue(required <= self.summary.keys())
        self.assertEqual(self.summary["dates_used"], dates)
        self.assertEqual(self.summary["stac_scenes_found"], len(self.items))
        self.assertEqual(self.summary["usable_temporal_observations"], len(dates))
        self.assertEqual(len(dates) + len(self.summary["excluded_dates"]), len(self.grouped))
        self.assertEqual(self.summary["grid"], self.grid)
        self.assertEqual(self.summary["bbox"], sentinel.source_area()[0]["bbox"])
        for meta in self.summary["sentinel_bands"].values():
            self.assertTrue(400 <= meta["center_wavelength_nm"] <= 1700)
        with (sentinel.OUTPUT_DIR / "sentinel_timeseries.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), len(dates))
        for row, observation in zip(rows, self.observations):
            self.assertEqual(row["date"], observation["date"])
            self.assertEqual(row["acquisition_datetimes"].split(";"),
                             [s["acquisition_datetime"] for s in observation["sources"]])
            self.assertEqual(row["scene_ids"].split(";"), [s["scene_id"] for s in observation["sources"]])
            for name in sentinel.INDICES:
                for stat in ("median", "p25", "p75"):
                    actual = float(row[f"{name.lower()}_{stat}"])
                    self.assertTrue(np.isfinite(actual))
                    self.assertEqual(actual, observation["statistics"][name][stat])

    def test_baseline_excludes_target_and_handles_zero_mad_explicitly(self):
        closest = self.summary["closest_sentinel_observation"]
        baseline = sentinel.baseline_comparison(self.observations, self.summary["tanager_acquisition_date"], closest)
        self.assertEqual(baseline, self.summary["baseline_comparison"])
        self.assertNotIn(closest["date"], baseline["dates"])
        if not baseline["available"]:
            self.assertIn("reason", baseline)
            return
        if baseline["available"]:
            for result in baseline["indices"].values():
                self.assertTrue(0 <= result["target_empirical_percentile"] <= 100)
                self.assertTrue(np.isfinite(result["baseline_median"]))
                self.assertTrue(np.isfinite(result["baseline_mad"]))
        # A single real prior observation exercises the zero-MAD branch with
        # minimum_dates=1 for this unit test only; no satellite data is invented.
        earlier = next(o for o in self.observations if o["date"] in baseline["dates"])
        constant = sentinel.baseline_comparison([earlier], self.summary["tanager_acquisition_date"], closest, minimum_dates=1)
        for result in constant["indices"].values():
            self.assertEqual(result["baseline_mad"], 0)
            self.assertIsNone(result["target_distance_in_unscaled_mad"])


if __name__ == "__main__":
    unittest.main()

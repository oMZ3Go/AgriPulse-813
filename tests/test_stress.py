"""Regression/integration tests using the actual completed local Tanager scene.

Run Phase 1 and Phase 2 before these tests. Missing real inputs are errors, not
replaced by dummy scenes. Invalid-input checks mark real observations unusable.
"""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agripulse import stress, tanager


class RealSceneStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Phase 2 must never fetch another scene or redownload the source.
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Phase 2 must be offline")):
            cls.inputs = stress.load_phase1_inputs()
        cls.result = stress.assess_stress(cls.inputs.indices, cls.inputs.quality_mask)

    def test_phase1_refactor_preserves_original_statistics(self):
        saved = json.loads((tanager.OUTPUT_DIR / "index_statistics.json").read_text())
        for name, values in self.inputs.indices.items():
            recomputed = tanager.summarize(values)
            for key, expected in saved[name].items():
                self.assertAlmostEqual(recomputed[key], expected, places=12)

    def test_risk_scores_are_bounded(self):
        scores = self.result.risk_score[self.result.classified_mask]
        self.assertGreater(scores.size, 0)
        self.assertTrue(np.isfinite(scores).all())
        self.assertTrue(((scores >= 0) & (scores <= 100)).all())
        # Supporting evidence cannot create risk independently of the NDMI term.
        np.testing.assert_array_less(scores - 1e-10, self.result.moisture_deficit[self.result.classified_mask])
        factor = self.result.support_factor[self.result.classified_mask]
        self.assertTrue(((factor >= 0.8) & (factor <= 1.0)).all())

    def test_nonvegetation_is_excluded(self):
        excluded = self.inputs.quality_mask & (self.inputs.indices["NDVI"] < stress.DEFAULT_NDVI_THRESHOLD)
        self.assertGreater(int(excluded.sum()), 0)
        self.assertTrue(np.isnan(self.result.risk_score[excluded]).all())
        self.assertTrue((self.result.risk_class[excluded] == 0).all())

    def test_original_invalid_pixels_are_excluded(self):
        invalid = ~self.inputs.quality_mask
        self.assertGreater(int(invalid.sum()), 0)
        self.assertTrue(np.isnan(self.result.risk_score[invalid]).all())
        self.assertTrue((self.result.risk_class[invalid] == 0).all())
        for percentiles in self.result.percentiles.values():
            self.assertTrue(np.isnan(percentiles[invalid]).all())

    def test_missing_or_nonfinite_evidence_cannot_receive_risk(self):
        indices = {name: array.copy() for name, array in self.inputs.indices.items()}
        quality = self.inputs.quality_mask.copy()
        pixels = [tuple(pixel) for pixel in np.argwhere(self.result.classified_mask)[:5]]
        indices["NDMI"][pixels[0]] = np.nan
        indices["NDRE"][pixels[1]] = np.nan
        indices["NDVI"][pixels[2]] = np.nan
        indices["NDMI"][pixels[3]] = np.inf
        quality[pixels[4]] = False
        result = stress.assess_stress(indices, quality)
        for pixel in pixels:
            self.assertTrue(np.isnan(result.risk_score[pixel]))
            self.assertEqual(result.risk_class[pixel], 0)
        self.assertEqual(result.summary["vegetation_pixels_missing_index_evidence"], 3)

    def test_all_output_statistics_are_finite(self):
        def check(value):
            if isinstance(value, dict):
                for entry in value.values():
                    check(entry)
            elif isinstance(value, (int, float)):
                self.assertTrue(np.isfinite(value))
        check(self.result.statistics)
        check(json.loads((stress.OUTPUT_DIR / "stress_statistics.json").read_text()))

    def test_class_percentages_sum_to_one_hundred(self):
        percentages = self.result.statistics["risk_class_percentages"]
        self.assertAlmostEqual(sum(percentages.values()), 100.0, places=10)
        counts = self.result.statistics["risk_class_counts"]
        self.assertEqual(sum(counts.values()), int(self.result.classified_mask.sum()))
        for name in stress.CLASS_NAMES:
            self.assertAlmostEqual(percentages[name], counts[name] / self.result.classified_mask.sum() * 100)

    def test_class_boundaries(self):
        # Scalar score-boundary unit test; these are not satellite data or labels.
        scores = np.array([0, 24.999, 25, 49.999, 50, 74.999, 75, 100, np.nan])
        np.testing.assert_array_equal(stress.classify_scores(scores), [1, 1, 2, 2, 3, 3, 4, 4, 0])

    def test_ranks_are_monotone_and_ties_are_equal(self):
        values = self.inputs.indices["NDMI"][self.result.classified_mask]
        ranks = self.result.percentiles["NDMI"][self.result.classified_mask]
        order = np.argsort(values)
        self.assertTrue((np.diff(ranks[order]) >= 0).all())
        ties = np.diff(values[order]) == 0
        self.assertTrue((np.diff(ranks[order])[ties] == 0).all())
        self.assertAlmostEqual(float(ranks.mean()), 50.0, places=10)
        # Independently check midranks for observed low, middle and high values.
        for value in (values.min(), np.median(values), values.max()):
            selected = np.flatnonzero(values == value)
            if selected.size:
                expected = 100 * ((values < value).sum() + 0.5 * (values == value).sum()) / values.size
                self.assertAlmostEqual(ranks[selected[0]], expected, places=12)

    def test_threshold_is_configurable_and_empty_screen_is_rejected(self):
        stricter = stress.assess_stress(self.inputs.indices, self.inputs.quality_mask, ndvi_threshold=0.4)
        self.assertLess(int(stricter.vegetation_mask.sum()), int(self.result.vegetation_mask.sum()))
        self.assertFalse((stricter.classified_mask & (self.inputs.indices["NDVI"] < 0.4)).any())
        with self.assertRaises(tanager.PipelineError):
            stress.assess_stress(self.inputs.indices, self.inputs.quality_mask, ndvi_threshold=0.99)
        for threshold in (np.nan, np.inf, -0.1, 0, 1):
            with self.subTest(threshold=threshold), self.assertRaises(tanager.PipelineError):
                stress.assess_stress(self.inputs.indices, self.inputs.quality_mask, threshold)

    def test_no_ndmi_contrast_does_not_invent_a_ranking(self):
        # Select two genuinely repeated NDMI observations from this real ortho scene.
        values = self.inputs.indices["NDMI"][self.result.classified_mask]
        unique, counts = np.unique(values, return_counts=True)
        repeated = unique[counts >= 2]
        self.assertGreater(repeated.size, 0)
        subset = self.result.classified_mask & (self.inputs.indices["NDMI"] == repeated[0])
        with self.assertRaises(tanager.PipelineError):
            stress.assess_stress(self.inputs.indices, subset)

    def test_saved_pixel_evidence_reconstructs_scores_and_statistics(self):
        summary = json.loads((stress.OUTPUT_DIR / "stress_summary.json").read_text())
        stats = json.loads((stress.OUTPUT_DIR / "stress_statistics.json").read_text())
        with np.load(stress.OUTPUT_DIR / "pixel_evidence.npz", allow_pickle=False) as evidence:
            classified = evidence["classified_mask"]
            self.assertEqual(str(evidence["scene_id"]), self.inputs.summary["scene_id"])
            self.assertEqual(classified.shape, self.inputs.quality_mask.shape)
            expected = ((100 - evidence["ndmi_percentile"]) *
                        (0.8 + 0.1 * (1 - evidence["ndvi_percentile"] / 100)
                         + 0.1 * (1 - evidence["ndre_percentile"] / 100)))
            np.testing.assert_allclose(evidence["risk_score"], expected, rtol=0, atol=1e-12, equal_nan=True)
            self.assertTrue(np.isnan(evidence["risk_score"][~classified]).all())
            np.testing.assert_array_equal(evidence["risk_class"], stress.classify_scores(expected))
            self.assertEqual(int(classified.sum()), summary["classified_vegetation_pixels"])
            self.assertAlmostEqual(sum(summary["risk_class_percentages"].values()), 100.0, places=10)
            for name in stress.INDEX_NAMES:
                values = evidence[name.lower()][classified]
                np.testing.assert_array_equal(values, self.inputs.indices[name][classified])
                self.assertAlmostEqual(float(np.median(values)), stats["vegetation_indices"][name]["median"], places=12)
            for name in ("ndvi", "ndre"):
                conditions = evidence[f"{name}_condition"]
                self.assertTrue((conditions[~classified] == 0).all())
                np.testing.assert_array_equal(conditions[classified],
                    np.searchsorted([25, 75], evidence[f"{name}_percentile"][classified], side="right") + 1)


if __name__ == "__main__":
    unittest.main()

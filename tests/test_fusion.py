"""Stage 4 regression tests on saved real evidence, with unit-only scenarios.

Synthetic alterations stay in memory inside tests; production inputs are never
modified. Stage 4 tests block network calls and raw satellite access explicitly.
"""

from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import io
from itertools import product
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agripulse import fusion, sentinel, tanager


@contextmanager
def saved_evidence_only():
    with ExitStack() as stack:
        for target in ("requests.sessions.Session.request", "urllib.request.urlopen", "socket.socket.connect",
                       "rasterio.open", "h5py.File", "agripulse.sentinel.load_scene",
                       "agripulse.stress.load_phase1_inputs"):
            stack.enter_context(patch(target, side_effect=AssertionError(f"Stage 4 must not call {target}")))
        yield


def copy_metadata(inputs):
    """Isolate unit scenarios without copying or mutating the real pixel arrays."""
    return replace(inputs, stress_summary=deepcopy(inputs.stress_summary),
                   stress_statistics=deepcopy(inputs.stress_statistics),
                   temporal_summary=deepcopy(inputs.temporal_summary),
                   observations=deepcopy(inputs.observations))


def refresh_test_temporal_summary(inputs):
    """Make an in-memory test scenario internally consistent, never write it."""
    summary, observations = inputs.temporal_summary, inputs.observations
    dates = [o["date"] for o in observations]
    summary["dates_used"] = dates
    summary["usable_temporal_observations"] = len(dates)
    summary["candidate_dates"] = len(dates) + len(summary["excluded_dates"])
    summary["stac_scenes_found"] = (sum(len(o["sources"]) for o in observations + summary["excluded_dates"])
                                     + len(summary["reprocessing_duplicates_dropped"]))
    for name in sentinel.INDICES:
        medians = [o["statistics"][name]["median"] for o in observations]
        summary["temporal_statistics"][name] = {
            "daily_medians": medians, "median_of_daily_medians": float(np.median(medians)),
            "min_daily_median": min(medians), "max_daily_median": max(medians),
            "trend": sentinel.robust_trend(dates, medians),
        }
    closest = sentinel.closest_observation(observations, summary["tanager_acquisition_date"])
    summary["closest_sentinel_observation"] = closest
    summary["baseline_comparison"] = sentinel.baseline_comparison(observations, summary["tanager_acquisition_date"], closest)


class RuleMatrixTests(unittest.TestCase):
    def test_temporal_percentile_boundaries_and_agreement(self):
        scenarios = [
            (0, "decreasing", "DECLINE_SUPPORT", "RELATIVELY_LOW"),
            (24.999, "decreasing", "DECLINE_SUPPORT", "RELATIVELY_LOW"),
            (25, "decreasing", "NEUTRAL_OR_MIXED", "BROAD_HISTORICAL_RANGE"),
            (50, "increasing", "NEUTRAL_OR_MIXED", "BROAD_HISTORICAL_RANGE"),
            (75, "increasing", "NEUTRAL_OR_MIXED", "BROAD_HISTORICAL_RANGE"),
            (75.001, "increasing", "RECOVERY_OR_WETTER", "RELATIVELY_HIGH"),
            (100, "increasing", "RECOVERY_OR_WETTER", "RELATIVELY_HIGH"),
        ]
        for percentile, direction, state, position in scenarios:
            with self.subTest(percentile=percentile, direction=direction):
                actual = fusion.temporal_category(percentile, direction, baseline_available=True)
                self.assertEqual(actual[:2], (state, position))

    def test_conflicting_or_stable_temporal_evidence_is_not_forced(self):
        for percentile, direction in ((10, "increasing"), (90, "decreasing"),
                                      (10, "broadly stable"), (90, "broadly stable"), (50, "decreasing")):
            with self.subTest(percentile=percentile, direction=direction):
                state, _, _ = fusion.temporal_category(percentile, direction, baseline_available=True)
                self.assertEqual(state, "NEUTRAL_OR_MIXED")
                result = fusion.select_rule("RELATIVE_HOTSPOTS_PRESENT", state, "UNAVAILABLE")
                self.assertEqual(result["decision"], "GROUND_VERIFICATION_REQUIRED")

    def test_missing_temporal_components_are_insufficient(self):
        for percentile, direction, available in ((None, "increasing", False), (10, "insufficient observations", True)):
            self.assertEqual(fusion.temporal_category(percentile, direction, baseline_available=available)[0], "INSUFFICIENT")
        for percentile in (-0.1, 100.1, np.nan):
            with self.assertRaises(tanager.PipelineError):
                fusion.temporal_category(percentile, "decreasing", baseline_available=True)

    def test_all_48_state_combinations_block_automation(self):
        fired = set()
        for spectral, temporal, ground in product(fusion.SPECTRAL_STATES, fusion.TEMPORAL_STATES, fusion.GROUND_STATES):
            with self.subTest(spectral=spectral, temporal=temporal, ground=ground):
                result = fusion.select_rule(spectral, temporal, ground)
                self.assertIs(result["automation_allowed"], False)
                self.assertTrue(result["recommended_next_step"])
                fired.add(result["rule_id"])
                if "INSUFFICIENT" in (spectral, temporal):
                    self.assertEqual(result["decision"], "INSUFFICIENT_EVIDENCE")
                if ground == "UNAVAILABLE":
                    self.assertNotIn(result["decision"], ("ELEVATED_CONCERN", "ACTION_REVIEW_REQUIRED"))
        self.assertEqual(fired, {rule["id"] for rule in fusion.RULES})

    def test_future_rule_examples_are_explicit_human_review_scenarios(self):
        examples = [
            ("RELATIVE_HOTSPOTS_PRESENT", "DECLINE_SUPPORT", "VERIFIED_LOW", "D02", "ACTION_REVIEW_REQUIRED"),
            ("RELATIVE_HOTSPOTS_PRESENT", "NEUTRAL_OR_MIXED", "UNAVAILABLE", "D06", "GROUND_VERIFICATION_REQUIRED"),
            ("RELATIVE_HOTSPOTS_PRESENT", "NEUTRAL_OR_MIXED", "VERIFIED_NORMAL", "D05", "MONITOR"),
            ("RELATIVE_HOTSPOTS_PRESENT", "DECLINE_SUPPORT", "VERIFIED_NORMAL", "D04", "GROUND_VERIFICATION_REQUIRED"),
            ("INSUFFICIENT", "DECLINE_SUPPORT", "VERIFIED_LOW", "D01", "INSUFFICIENT_EVIDENCE"),
        ]
        for spectral, temporal, ground, rule_id, decision in examples:
            result = fusion.select_rule(spectral, temporal, ground)
            self.assertEqual((result["rule_id"], result["decision"]), (rule_id, decision))
            self.assertIs(result["automation_allowed"], False)

    def test_unknown_states_fail_instead_of_falling_through(self):
        with self.assertRaises(tanager.PipelineError):
            fusion.select_rule("RELATIVE_HOTSPOTS_PRESENT", "NEUTRAL_OR_MIXED", "UNVERIFIED_LOW")

    def test_ground_schema_has_no_fabricated_reading_or_universal_threshold(self):
        matrix = fusion.decision_matrix()
        ground = matrix["future_ground_contract"]
        self.assertIs(ground["implemented_in_stage4"], False)
        self.assertEqual(ground["current_production_state"], "UNAVAILABLE")
        required = {"sensor_id", "sensor_timestamp", "soil_moisture_value", "soil_moisture_unit",
                    "location", "quality_valid", "calibration_reference", "interpretation", "interpretation_authority"}
        self.assertTrue(required <= set(ground["observation_schema"]["required"]))
        self.assertEqual(ground["observation_schema"]["properties"]["soil_moisture_value"], {"type": "number"})
        self.assertNotIn("observations", ground)
        self.assertTrue(all(rule["automation_allowed"] is False for rule in matrix["rules"]))


class RealFusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with saved_evidence_only():
            cls.inputs = fusion.load_inputs()
            cls.decision, cls.summary = fusion.fuse(cls.inputs)

    def test_actual_evidence_states_and_decision(self):
        decision = self.decision
        self.assertEqual(decision["decision_as_of"], "2025-06-09T08:35:59.024Z")
        self.assertEqual(decision["spectral_evidence"]["state"], "RELATIVE_HOTSPOTS_PRESENT")
        self.assertEqual(decision["spectral_evidence"]["classified_vegetation_pixels"], 97490)
        self.assertEqual(decision["temporal_evidence"]["state"], "NEUTRAL_OR_MIXED")
        self.assertEqual(decision["ground_evidence"]["state"], "UNAVAILABLE")
        self.assertEqual(decision["ground_evidence"]["observations"], [])
        self.assertEqual(decision["decision"], "GROUND_VERIFICATION_REQUIRED")
        self.assertEqual(decision["matched_rule_id"], "D06")
        self.assertIs(decision["automation_allowed"], False)
        self.assertIs(decision["spectral_evidence"]["score_is_probability"], False)

    def test_decision_time_counts_slope_and_baseline(self):
        temporal = self.decision["temporal_evidence"]
        self.assertEqual(temporal["historical_observations_used"], 19)
        self.assertEqual(temporal["observations_strictly_before_cutoff"], 18)
        self.assertEqual(self.summary["temporal_selection_audit"]["excluded_count"], 25)
        self.assertEqual(temporal["dates_used"][-1], "2025-06-09")
        self.assertAlmostEqual(temporal["decision_time_trends"]["NDMI"]["slope_per_day"], 0.0025893425197895145, places=14)
        self.assertEqual(temporal["baseline"]["observation_count"], 17)
        self.assertAlmostEqual(temporal["ndmi_baseline_percentile"], 52.94117647058823)
        self.assertEqual(temporal["ndmi_baseline_position"], "BROAD_HISTORICAL_RANGE")
        self.assertNotIn("2025-06-09", temporal["baseline"]["dates"])
        self.assertIs(self.summary["retrospective_context_not_used_for_decision"]["used_in_decision"], False)

    def test_future_observations_changed_or_removed_cannot_change_june_decision(self):
        cutoff = sentinel.utc(fusion.DEFAULT_DECISION_AS_OF)
        altered = copy_metadata(self.inputs)
        # Deliberately extreme synthetic future values, used ONLY in this test.
        for observation in altered.observations:
            if max(map(sentinel.utc, observation["acquisition_datetimes"])) > cutoff:
                for name, center, width in (("NDVI", 0.32, 0.01), ("NDRE", -0.4, 0.02), ("NDMI", -0.8, 0.02)):
                    observation["statistics"][name] = dict(zip(("min", "p25", "median", "p75", "max"),
                                                             (center - width, center - width / 2, center, center + width / 2, center + width)))
        refresh_test_temporal_summary(altered)
        with saved_evidence_only():
            changed_decision, changed_summary = fusion.fuse(altered)
        self.assertEqual(changed_decision, self.decision)  # Includes the complete reasoning trace.
        self.assertEqual(changed_summary["retrospective_context_not_used_for_decision"]["full_season_trends"]["NDMI"]["direction"], "decreasing")
        removed = copy_metadata(self.inputs)
        removed.observations = [o for o in removed.observations if max(map(sentinel.utc, o["acquisition_datetimes"])) <= cutoff]
        refresh_test_temporal_summary(removed)
        with saved_evidence_only():
            without_future, summary = fusion.fuse(removed)
        self.assertEqual(without_future, self.decision)
        self.assertEqual(summary["temporal_selection_audit"]["excluded_count"], 0)

    def test_cutoff_includes_exact_timestamp_but_not_one_microsecond_later(self):
        cutoff = sentinel.utc(fusion.DEFAULT_DECISION_AS_OF) - timedelta(microseconds=1)
        result, _ = fusion.temporal_evidence(self.inputs.observations, self.inputs.stress_summary["acquisition_date"],
                                            fusion.FusionConfig(decision_as_of=cutoff.isoformat()))
        self.assertEqual(result["historical_observations_used"], 18)
        self.assertNotIn("2025-06-09", result["dates_used"])
        self.assertLessEqual(sentinel.utc(result["closest_observation"]["acquisition_datetime"]), cutoff)

    def test_real_daily_mosaic_straddling_cutoff_is_fully_excluded(self):
        first = self.inputs.observations[0]
        self.assertGreater(len(first["acquisition_datetimes"]), 1)
        cutoff = first["acquisition_datetimes"][0]
        evidence, audit = fusion.temporal_evidence(self.inputs.observations, self.inputs.stress_summary["acquisition_date"],
                                                 fusion.FusionConfig(decision_as_of=cutoff))
        self.assertEqual(evidence["historical_observations_used"], 0)
        self.assertEqual(evidence["state"], "INSUFFICIENT")
        self.assertEqual(audit["excluded_observations"][0]["date"], first["date"])

    def test_supporting_greenness_cannot_select_moisture_state(self):
        observations = deepcopy(self.inputs.observations)
        for observation in observations:
            observation["statistics"]["NDVI"]["median"] = 0.31
            observation["statistics"]["NDRE"]["median"] = -0.5
        result, _ = fusion.temporal_evidence(observations, self.inputs.stress_summary["acquisition_date"], fusion.FusionConfig())
        original = self.decision["temporal_evidence"]
        self.assertEqual(result["state"], original["state"])
        self.assertEqual(result["decision_time_trends"]["NDMI"], original["decision_time_trends"]["NDMI"])
        self.assertEqual(result["baseline"]["indices"]["NDMI"], original["baseline"]["indices"]["NDMI"])

    def test_future_tanager_is_insufficient_and_has_explainable_trace(self):
        with saved_evidence_only():
            decision, _ = fusion.fuse(self.inputs, fusion.FusionConfig(decision_as_of="2025-06-07T00:00:00Z"))
        self.assertEqual(decision["spectral_evidence"]["state"], "INSUFFICIENT")
        self.assertNotIn("relative_score_maximum", decision["spectral_evidence"])
        self.assertEqual(decision["decision"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(decision["reasoning_trace"][0]["rule_id"], "SPECTRAL_INSUFFICIENT")
        self.assertEqual(decision["reasoning_trace"][-2]["rule_id"], "D01")

    def test_incompatible_scene_datetime_bbox_and_catalog_fail(self):
        changes = (
            ("bbox", lambda x: x.temporal_summary["bbox"].__setitem__(0, 31.0)),
            ("scene", lambda x: x.temporal_summary.__setitem__("source_scene_id", "WRONG_SCENE")),
            ("datetime", lambda x: x.temporal_summary.__setitem__("tanager_acquisition_date", "2025-06-09T09:16:05Z")),
            ("catalog", lambda x: x.temporal_summary["catalog_snapshot"]["query"].__setitem__("collection", "unrelated-collection")),
            ("footprint", lambda x: x.temporal_summary["grid"].__setitem__("width", 999)),
        )
        for label, change in changes:
            with self.subTest(change=label):
                inputs = copy_metadata(self.inputs)
                change(inputs)
                with self.assertRaises(tanager.PipelineError):
                    fusion.fuse(inputs)

    def test_inconsistent_summaries_counts_and_product_timestamps_fail(self):
        changes = (
            lambda x: x.stress_statistics["risk_score"].__setitem__("median", 90.0),
            lambda x: x.temporal_summary.__setitem__("usable_temporal_observations", 45),
            lambda x: x.observations[0]["sources"][0].__setitem__("contributing_pixels", 1),
            lambda x: x.observations[0]["sources"][0].__setitem__("scene_id", x.observations[0]["sources"][0]["scene_id"].replace("20250407T", "20250707T")),
        )
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                inputs = copy_metadata(self.inputs)
                change(inputs)
                with self.assertRaises(tanager.PipelineError):
                    fusion.fuse(inputs)

    def test_mismatched_pixel_scene_or_changed_scores_fail(self):
        for change in ("scene_id", "risk_score"):
            inputs = copy_metadata(self.inputs)
            inputs.pixels = dict(inputs.pixels)
            if change == "scene_id":
                inputs.pixels[change] = np.array("WRONG_SCENE")
            else:
                inputs.pixels[change] = inputs.pixels[change].copy()
                pixel = tuple(np.argwhere(inputs.pixels["classified_mask"])[0])
                inputs.pixels[change][pixel] = 101
            with self.subTest(change=change), self.assertRaises(tanager.PipelineError):
                fusion.fuse(inputs)

    def test_missing_input_fails_loudly_and_never_downloads(self):
        with tempfile.TemporaryDirectory(dir=tanager.REPO_ROOT / "outputs") as directory, saved_evidence_only():
            with self.assertRaisesRegex(tanager.PipelineError, "Required input is missing"):
                fusion.load_inputs(Path(directory))

    def test_input_hashes_identify_exact_saved_evidence(self):
        self.assertEqual(set(self.summary["input_provenance"]), set(fusion.INPUT_FILES))
        for name, relative in fusion.INPUT_FILES.items():
            content = (tanager.REPO_ROOT / relative).read_bytes()
            record = self.summary["input_provenance"][name]
            self.assertEqual(record["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(record["size_bytes"], len(content))

    def test_reasoning_trace_matches_actual_rule_path(self):
        trace = self.decision["reasoning_trace"]
        self.assertEqual([step["rule_id"] for step in trace], [
            "SPECTRAL_RELATIVE_HOTSPOTS_PRESENT", "TEMPORAL_BASELINE_BROAD_HISTORICAL_RANGE",
            "TEMPORAL_TREND", "TEMPORAL_NEUTRAL_OR_MIXED", "GROUND_UNAVAILABLE", "D06", "AUTOMATION_DISABLED"])
        self.assertIn("52.94", trace[1]["explanation"])
        self.assertIn("19 eligible", trace[2]["explanation"])
        self.assertIn(self.decision["decision"], trace[-2]["explanation"])
        self.assertTrue(all(step["explanation"] for step in trace))

    def test_required_decision_schema_is_finite_and_contains_no_retrospective_fields(self):
        required = {"decision", "decision_as_of", "automation_allowed", "recommended_next_step",
                    "spectral_evidence", "temporal_evidence", "ground_evidence", "reasoning_trace", "limitations"}
        self.assertTrue(required <= self.decision.keys())
        self.assertNotIn("retrospective_context_not_used_for_decision", self.decision)
        self.assertNotIn("input_provenance", self.decision)  # Later-file hashes cannot alter this historical decision.
        self.assertNotIn("observations", self.decision["spectral_evidence"])
        json.dumps(self.decision, allow_nan=False)
        json.dumps(self.summary, allow_nan=False)

    def test_real_pipeline_outputs_reproduce_offline_without_raw_assets(self):
        expected_files = {"decision.json", "fusion_summary.json", "decision_matrix.json", "decision_report.md", "evidence_fusion.png"}
        before = {key: tanager.sha256(tanager.REPO_ROOT / relative) for key, relative in fusion.INPUT_FILES.items()}
        with tempfile.TemporaryDirectory(dir=tanager.REPO_ROOT / "outputs") as directory:
            output = Path(directory)
            with saved_evidence_only(), redirect_stdout(io.StringIO()):
                actual = fusion.run_pipeline(output=output)
                first = {p.name: tanager.sha256(p) for p in output.iterdir() if p.is_file()}
                repeated = fusion.run_pipeline(output=output)
                second = {p.name: tanager.sha256(p) for p in output.iterdir() if p.is_file()}
            self.assertEqual(set(first), expected_files)
            self.assertEqual(first, second)
            self.assertEqual(actual, self.decision)
            self.assertEqual(actual, repeated)
            self.assertEqual(json.loads((output / "decision.json").read_text()), actual)
            self.assertEqual((output / "evidence_fusion.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        after = {key: tanager.sha256(tanager.REPO_ROOT / relative) for key, relative in fusion.INPUT_FILES.items()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

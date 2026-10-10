"""Stage 4.6 real-scene regression tests and small exclusion-rule fixtures.

No fabricated satellite evidence is written into production output directories.
The real existing local scene and previous outputs are required, never downloaded.
"""

from contextlib import contextmanager, ExitStack, redirect_stdout
from copy import deepcopy
from dataclasses import replace
import inspect
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agripulse import ml, stress, tanager


@contextmanager
def offline():
    with ExitStack() as stack:
        for target in ("requests.sessions.Session.request", "socket.create_connection", "socket.socket.connect",
                       "agripulse.tanager.download_source", "agripulse.tanager.download_range"):
            stack.enter_context(patch(target, side_effect=AssertionError("Stage 4.6 must be offline")))
        yield


def protected_hashes():
    paths = []
    for name in ("tanager", "stress", "sentinel", "fusion", "spectral"):
        paths.extend(p for p in (tanager.REPO_ROOT / "outputs" / name).rglob("*") if p.is_file())
        paths.append(tanager.REPO_ROOT / "src/agripulse" / f"{name}.py")
    # Include all tracked frontend sources without traversing node_modules/.next.
    import subprocess
    tracked = subprocess.check_output(["git", "ls-files", "dashboard"], cwd=tanager.REPO_ROOT, text=True)
    paths.extend(tanager.REPO_ROOT / name for name in tracked.splitlines())
    return {str(p): tanager.sha256(p) for p in paths}


class MLRuleTests(unittest.TestCase):
    def test_invalid_reflectance_and_nodata_are_excluded_without_clipping(self):
        values = np.array([np.nan, np.inf, -np.inf, -0.1, 999, 0, 0.3, 1.2])
        valid, audit = ml.audit_band(values, 500, nodata=999)
        np.testing.assert_array_equal(valid, [False] * 5 + [True] * 3)
        self.assertEqual(audit["above_one_candidate_count"], 1)
        self.assertEqual(audit["invalid_candidate_count"], 5)
        self.assertTrue(audit["retained"])
        self.assertEqual(values[-1], 1.2)

    def test_atmospheric_boundaries_empty_and_constant_bands_are_explicit(self):
        values = np.array([0.1, 0.3, 0.6])
        for wavelength in (1350, 1400, 1450):
            self.assertFalse(ml.audit_band(values, wavelength)[1]["retained"])
        for wavelength in (1349.99, 1450.01):
            self.assertTrue(ml.audit_band(values, wavelength)[1]["retained"])
        self.assertIn("no_valid_candidate_reflectance", ml.audit_band(np.array([np.nan, -1]), 500)[1]["exclusion_reasons"])
        self.assertIn("constant_candidate_reflectance", ml.audit_band(np.array([0.3, 0.3]), 500)[1]["exclusion_reasons"])

    def test_missing_retained_values_drop_pixels_but_excluded_bands_never_return(self):
        # Rule fixture only; combines valid zeros, nodata, gaps and window edges.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rule_fixture.h5"
            wavelengths = np.array([399, 400, 500, 600, 700, 1365, 1450, 1700, 1701])
            base = (np.arange(12) / 10).reshape(3, 4)
            cube = np.stack([base + i / 100 for i in range(9)])
            cube[2].flat[:4] = [np.nan, -np.inf, -0.1, 999]
            cube[3] = 0.2
            cube[4:6] = np.nan
            with h5py.File(path, "w") as source:
                source.create_dataset(f"{tanager.HDF_ROOT}/surface_reflectance", data=cube)
            mask = np.ones((3, 4), bool)
            mask.flat[10:] = False
            inputs = SimpleNamespace(wavelengths_nm=wavelengths, candidate_mask=mask,
                                     phase1=SimpleNamespace(source_path=path), band_metadata=[{"nodata": 999}] * 9)
            with redirect_stdout(io.StringIO()):
                spectra = ml.collect_spectra(inputs)
            np.testing.assert_array_equal(spectra.band_indices, [1, 2, 7])
            np.testing.assert_array_equal(spectra.flat_indices, np.arange(4, 10))
            self.assertTrue(np.isfinite(spectra.values).all())
            np.testing.assert_array_equal(spectra.values, cube[[1, 2, 7]].reshape(3, -1)[:, 4:10].T)
            self.assertEqual(len(spectra.audit), 7)
            self.assertEqual(sum(not row["retained"] for row in spectra.audit), 4)

    def test_model_rejects_invalid_empty_and_constant_spectra(self):
        for data in (np.empty((0, 3)), np.ones((4, 1)), np.ones((4, 3)),
                     np.array([[1, 2], [np.nan, 3], [2, 4]]), np.array([[1, 2], [-1, 3], [2, 4]])):
            with self.subTest(shape=data.shape), self.assertRaises(tanager.PipelineError):
                ml.fit_anomaly(data)

    def test_protected_output_paths_fail_before_loading_or_writing(self):
        for name in ("outputs/tanager", "outputs/stress/nested", "outputs/sentinel", "outputs/fusion",
                     "outputs/spectral", "outputs", "dashboard", "dashboard/new", "src", ".git"):
            with self.subTest(name=name), patch.object(ml, "load_inputs") as loader:
                with self.assertRaisesRegex(tanager.PipelineError, "overlap"):
                    ml.run_pipeline(output=tanager.REPO_ROOT / name)
                loader.assert_not_called()
        with self.assertRaisesRegex(tanager.PipelineError, "raw data"):
            ml.validate_output(tanager.raw_data_dir() / "new")

    def test_cli_missing_input_reports_failure_without_network(self):
        with offline(), patch.object(ml, "load_inputs", side_effect=tanager.PipelineError("Missing required local input")):
            with redirect_stdout(io.StringIO()), patch("sys.stderr", new_callable=io.StringIO) as stderr:
                self.assertEqual(ml.main([]), 1)
            self.assertIn("Missing required local input", stderr.getvalue())


class RealSceneMLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = protected_hashes()
        with offline(), redirect_stdout(io.StringIO()):
            cls.inputs = ml.load_inputs()
            cls.spectra = ml.collect_spectra(cls.inputs)
            cls.model = ml.fit_anomaly(cls.spectra.values)
            cls.comparison, cls.risk = ml.compare_stage2(cls.inputs, cls.spectra, cls.model)
        cls.summary = ml.make_summary(cls.inputs, cls.spectra, cls.model, cls.comparison)
        with np.load(stress.OUTPUT_DIR / "pixel_evidence.npz", allow_pickle=False) as archive:
            cls.pixels = {name: archive[name] for name in archive.files}

    @classmethod
    def tearDownClass(cls):
        if cls.before != protected_hashes():
            raise AssertionError("Stages 1-4.5 or Stage 5A changed during ML tests")

    def test_only_quality_valid_vegetation_receives_finite_scores(self):
        mask = self.spectra.eligible_mask
        self.assertTrue(self.inputs.phase1.quality_mask[mask].all())
        self.assertTrue(self.pixels["vegetation_mask"][mask].all())
        self.assertTrue(self.pixels["classified_mask"][mask].all())
        grid = ml.score_grid(self.spectra, self.model)
        self.assertTrue(np.isfinite(grid[mask]).all())
        self.assertTrue(np.isnan(grid[~mask]).all())
        self.assertFalse(np.isfinite(grid[~self.inputs.phase1.quality_mask]).any())
        self.assertFalse(np.isfinite(grid[~self.pixels["vegetation_mask"]]).any())

    def test_band_audit_matches_real_missing_bands_and_full_caution_exclusion(self):
        audit = self.spectra.audit
        self.assertEqual(len(audit), 260)
        self.assertEqual(len(self.spectra.band_indices), 240)
        empty = [row for row in audit if row["valid_candidate_count"] == 0]
        self.assertEqual(len(empty), 10)
        self.assertAlmostEqual(empty[0]["wavelength_nm"], 1362.44)
        self.assertAlmostEqual(empty[-1]["wavelength_nm"], 1407.51)
        kept = set(self.spectra.band_indices)
        for row in audit:
            self.assertEqual(row["valid_candidate_count"] + row["invalid_candidate_count"], self.spectra.candidate_count)
            self.assertEqual(row["source_band_index_zero_based"] in kept, row["retained"])
            if 1350 <= row["wavelength_nm"] <= 1450:
                self.assertFalse(row["retained"])
        wavelengths = self.inputs.wavelengths_nm[self.spectra.band_indices]
        self.assertTrue(((wavelengths >= 400) & (wavelengths <= 1700)).all())
        self.assertTrue((np.diff(wavelengths) > 0).all())

    def test_spectra_equal_raw_reflectance_without_imputation(self):
        with h5py.File(self.inputs.phase1.source_path, "r") as source:
            cube = source[f"{tanager.HDF_ROOT}/surface_reflectance"]
            for position in (0, 53, 88, 150, 239):
                index = self.spectra.band_indices[position]
                expected = cube[index].ravel()[self.spectra.flat_indices]
                np.testing.assert_array_equal(self.spectra.values[:, position], expected)
        self.assertTrue(np.isfinite(self.spectra.values).all())
        self.assertTrue((self.spectra.values >= 0).all())

    def test_scaler_uses_only_fixed_uniform_sample(self):
        rows = self.model.fit_rows
        expected = np.sort(np.random.Generator(np.random.PCG64(813)).choice(len(self.spectra.values), 20000, replace=False))
        np.testing.assert_array_equal(rows, expected)
        self.assertEqual(len(np.unique(rows)), 20000)
        sample = self.spectra.values[rows].astype(np.float64)
        np.testing.assert_allclose(self.model.scaler.mean_, sample.mean(axis=0), rtol=1e-13)
        np.testing.assert_allclose(self.model.scaler.var_, sample.var(axis=0), rtol=1e-13)
        self.assertTrue(self.spectra.eligible_mask.ravel()[self.spectra.flat_indices[rows]].all())

    def test_pca_finite_minimal_99_percent_variance_and_ordered(self):
        pca = self.model.pca
        ratio = pca.explained_variance_ratio_
        cumulative = np.cumsum(ratio)
        self.assertTrue(np.isfinite(ratio).all())
        self.assertTrue((ratio >= 0).all())
        self.assertTrue((np.diff(ratio) <= 0).all())
        self.assertTrue((np.diff(cumulative) >= 0).all())
        self.assertGreater(cumulative[-1], 0.99)
        self.assertLessEqual(cumulative[-1], 1 + 1e-12)
        if len(cumulative) > 1:
            self.assertLessEqual(cumulative[-2], 0.99)
        with ml.threadpool_limits(limits=1):
            z = pca.transform(self.model.scaler.transform(self.spectra.values[:8192].astype(np.float64)))
        self.assertTrue(np.isfinite(z).all())
        self.assertEqual(z.shape[1], pca.n_components_)

    def test_score_orientation_exactly_negates_library_normality_score(self):
        with ml.threadpool_limits(limits=1):
            z = self.model.pca.transform(self.model.scaler.transform(self.spectra.values[:8192].astype(np.float64)))
            normality = self.model.forest.score_samples(z)
        np.testing.assert_array_equal(self.model.scores[:8192], -normality)
        self.assertEqual(np.argmax(self.model.scores[:8192]), np.argmin(normality))
        self.assertIn("higher means more spectrally unusual", self.summary["anomaly_score_definition"])

    def test_fixed_seed_forest_configuration_and_no_label_fitting_interface(self):
        self.assertEqual(list(inspect.signature(ml.fit_anomaly).parameters), ["values"])
        self.assertEqual(self.model.forest.get_params(), ml.FOREST_CONFIG)
        self.assertEqual(self.model.pca.random_state, 813)
        self.assertEqual(self.summary["deterministic_seed"], 813)
        self.assertEqual(self.model.forest.contamination, "auto")
        self.assertFalse(self.summary["isolation_forest"]["auto_offset_used_for_scoring"])

    def test_scene_lineage_masks_counts_and_metadata_mismatches_fail_loudly(self):
        for case in ("scene", "lineage", "bbox", "wavelength", "mask", "count", "pixel_scene"):
            summary, pixels = deepcopy(self.inputs.stage2_summary), dict(self.pixels)
            if case == "scene":
                summary["source_scene_id"] = "wrong"
            elif case == "lineage":
                summary["source_hdf5_sha256"] = "wrong"
            elif case == "bbox":
                summary["bbox"][0] += 1
            elif case == "wavelength":
                summary["analysis_wavelength_range_nm"] = [400, 2500]
            elif case == "count":
                summary["vegetation_pixels"] += 1
            elif case == "pixel_scene":
                pixels["scene_id"] = np.array("wrong")
            else:
                pixels["vegetation_mask"] = pixels["vegetation_mask"].copy()
                pixels["vegetation_mask"].flat[0] ^= True
            with self.subTest(case=case), self.assertRaises(tanager.PipelineError):
                ml.validate_eligibility(self.inputs.phase1, summary, pixels)

    def test_missing_required_local_inputs_fail_without_downloading(self):
        with tempfile.TemporaryDirectory() as directory, offline():
            empty = Path(directory)
            with patch.object(tanager, "OUTPUT_DIR", empty):
                with self.assertRaisesRegex(tanager.PipelineError, "missing"):
                    ml.load_inputs()
            with patch.object(stress, "load_phase1_inputs", return_value=self.inputs.phase1):
                with patch.object(stress, "OUTPUT_DIR", empty):
                    with self.assertRaisesRegex(tanager.PipelineError, "Missing required local input"):
                        ml.load_inputs()
                (empty / "stress_summary.json").write_bytes((stress.OUTPUT_DIR / "stress_summary.json").read_bytes())
                with patch.object(stress, "OUTPUT_DIR", empty):
                    with self.assertRaisesRegex(tanager.PipelineError, "pixel_evidence"):
                        ml.load_inputs()
            with patch.object(tanager, "raw_data_dir", return_value=empty):
                with self.assertRaises(FileNotFoundError):
                    ml.load_inputs()

    def test_source_checksum_and_stac_mismatch_fail_loudly(self):
        actual = tanager.sha256
        for target in (self.inputs.phase1.source_path.name, f"{ml.SCENE_ID}.json"):
            def changed(path):
                return "0" * 64 if Path(path).name == target else actual(path)
            with offline(), patch.object(tanager, "sha256", side_effect=changed), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(tanager.PipelineError, "checksum|STAC"):
                    ml.load_inputs()

    def test_risk_mutation_cannot_change_eligibility_spectra_fit_or_scores(self):
        # Strong regression: rewrite ALL risk scores/classes in a temporary copy,
        # then run real loading, raw-spectrum collection and fitting again.
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            pixels = dict(self.pixels)
            pixels["risk_score"] = np.where(self.inputs.candidate_mask, 50.0, np.nan)
            pixels["risk_class"] = stress.classify_scores(pixels["risk_score"])
            np.savez_compressed(folder / "pixel_evidence.npz", **pixels)
            summary = deepcopy(self.inputs.stage2_summary)
            summary["risk_class_percentages"] = {"Low": 0, "Moderate": 0, "High": 100, "Very High": 0}
            (folder / "stress_summary.json").write_text(json.dumps(summary), encoding="utf-8")
            with offline(), patch.object(stress, "OUTPUT_DIR", folder), redirect_stdout(io.StringIO()):
                # A risk-formula call would break this test, even for validation.
                with patch.object(stress, "assess_stress", side_effect=AssertionError("Risk must not enter ML")):
                    inputs = ml.load_inputs()
                    spectra = ml.collect_spectra(inputs)
                    model = ml.fit_anomaly(spectra.values)
                    comparison, _ = ml.compare_stage2(inputs, spectra, model)
            np.testing.assert_array_equal(inputs.candidate_mask, self.inputs.candidate_mask)
            np.testing.assert_array_equal(spectra.values, self.spectra.values)
            np.testing.assert_array_equal(model.fit_rows, self.model.fit_rows)
            np.testing.assert_array_equal(model.scaler.mean_, self.model.scaler.mean_)
            np.testing.assert_array_equal(model.pca.components_, self.model.pca.components_)
            np.testing.assert_array_equal(model.scores, self.model.scores)
            self.assertIsNone(comparison["spearman_rank_correlation"])
            self.assertNotEqual(comparison, self.comparison)

    def test_risk_fields_are_not_required_for_loading_or_fitting(self):
        masks = {key: self.pixels[key] for key in ("scene_id", "quality_mask", "vegetation_mask", "classified_mask")}
        summary = deepcopy(self.inputs.stage2_summary)
        summary.pop("risk_class_percentages")
        summary.pop("methodology")
        with patch.object(stress, "assess_stress", side_effect=AssertionError("No risk fitting")):
            mask = ml.validate_eligibility(self.inputs.phase1, summary, masks)
        np.testing.assert_array_equal(mask, self.inputs.candidate_mask)

    def test_postfit_comparison_is_descriptive_and_uses_same_population(self):
        from scipy.stats import spearmanr
        expected = spearmanr(self.model.scores, self.risk[self.spectra.eligible_mask]).statistic
        self.assertAlmostEqual(self.comparison["spearman_rank_correlation"], expected, places=14)
        self.assertEqual(self.comparison["population_count"], len(self.model.scores))
        groups = self.comparison["anomaly_by_stage2_relative_risk_class"]
        self.assertEqual(sum(group["count"] for group in groups.values()), len(self.model.scores))
        self.assertFalse(self.comparison["used_for_training_feature_selection_or_tuning"])
        self.assertIn("not independent validation", self.comparison["interpretation"])

    def test_changed_comparison_input_is_rejected(self):
        changed = deepcopy(self.inputs.provenance)
        changed["stage2_pixels"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(tanager.PipelineError, "changed after"):
            ml.compare_stage2(replace(self.inputs, provenance=changed), self.spectra, self.model)

    def test_summary_is_finite_and_records_parameters_exclusions_and_limitations(self):
        json.dumps(self.summary, allow_nan=False)
        self.assertFalse(self.summary["score_is_probability"])
        self.assertFalse(self.summary["calibrated_agronomic_classifier"])
        self.assertFalse(self.summary["satellite_813_response_simulated"])
        self.assertFalse(self.summary["reproducibility"]["network_required"])
        self.assertEqual(self.summary["eligible_vegetation_pixel_count"], len(self.model.scores))
        self.assertEqual(self.summary["eligible_membership_sha256"], ml.membership_hash(self.spectra.flat_indices))
        self.assertEqual(self.summary["usable_band_count"] + self.summary["excluded_band_count"], 260)

    def test_full_pipeline_reproduces_all_artifacts_byte_for_byte_offline(self):
        names = {"anomaly_score.png", "anomaly_context.png", "pca_summary.png", "ml_summary.json", "anomaly_pixel_evidence.npz"}
        before = protected_hashes()
        with tempfile.TemporaryDirectory(dir=tanager.REPO_ROOT / "outputs") as directory:
            output = Path(directory)
            with offline(), redirect_stdout(io.StringIO()):
                first = ml.run_pipeline(output=output)
                hashes = {name: tanager.sha256(output / name) for name in names}
                second = ml.run_pipeline(output=output)
            self.assertEqual(first, second)
            self.assertEqual(first, self.summary)
            self.assertEqual(hashes, {name: tanager.sha256(output / name) for name in names})
            self.assertEqual(hashes, {name: tanager.sha256(ml.OUTPUT_DIR / name) for name in names})
            for name in names:
                if name.endswith(".png"):
                    self.assertEqual((output / name).read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            with np.load(output / "anomaly_pixel_evidence.npz", allow_pickle=False) as archive:
                self.assertEqual(archive["scene_id"].item(), ml.SCENE_ID)
                np.testing.assert_array_equal(archive["eligible_mask"], self.spectra.eligible_mask)
                np.testing.assert_array_equal(archive["anomaly_score"], ml.score_grid(self.spectra, self.model))
                np.testing.assert_array_equal(archive["fitting_flat_indices"], self.spectra.flat_indices[self.model.fit_rows])
                np.testing.assert_array_equal(archive["usable_source_band_indices"], self.spectra.band_indices)
        self.assertEqual(before, protected_hashes())


if __name__ == "__main__":
    unittest.main()

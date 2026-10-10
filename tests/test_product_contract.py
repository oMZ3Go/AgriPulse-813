"""Stage 4.7 contract tests; hypothetical records stay in memory only.

The Konya regression reads the existing real saved artifacts without downloads,
scientific processing, or writes to production evidence/frontend files.
"""

from dataclasses import FrozenInstanceError, fields, replace
import hashlib
from itertools import product
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agripulse import product_contract as pc

A = pc.AvailabilityState
L = pc.AnalysisLevel
D = pc.DecisionState
AS_OF = "2025-06-09T08:35:59.024Z"


def aoi():
    return pc.AreaOfInterest("unit-field", pc.BoundingBox(32.4, 37.5, 32.8, 37.8),
                            pc.TimeRange("2025-06-01T00:00:00Z", "2025-06-10T00:00:00Z"))


def ground(**changes):
    values = dict(observation_id="unit-human", location=pc.Point(32.5, 37.6),
                  timestamp="2025-06-09T08:00:00Z", crop_type="wheat",
                  observer_type=pc.ObserverType.FARMER, plant_condition=pc.PlantCondition.UNKNOWN,
                  soil_condition=pc.SoilCondition.UNKNOWN, recent_irrigation=pc.RecentIrrigation.UNKNOWN)
    return pc.GroundObservation(**(values | changes))


def calibration(**changes):
    values = dict(state=pc.CalibrationState.CALIBRATED, reference="unit-calibration-record",
                  site_reference="unit-site-soil-depth-context", calibrated_at="2025-05-01T00:00:00Z",
                  valid_until="2025-07-01T00:00:00Z")
    return pc.Calibration(**(values | changes))


def sensor(**changes):
    values = dict(sensor_id="unit-sensor", location=pc.Point(32.5, 37.6), timestamp="2025-06-09T08:00:00Z",
                  soil_moisture=0.25, air_temperature=25.0, relative_humidity=40.0,
                  state=pc.IoTState.CALIBRATED, calibration=calibration(), quality_valid=True)
    return pc.IoTEvidence(**(values | changes))


def evidence(availability):
    return tuple(pc.MLEvidence("unit-scene", ("unit-provenance",)) if source == pc.EvidenceSource.ML
                 else pc.EvidenceItem(source, "Unit-test evidence summary", ("unit-provenance",))
                 for source in pc.EvidenceSource if getattr(availability, source.value) == A.AVAILABLE)


def result(availability=None, **changes):
    availability = availability or pc.DataAvailability(sentinel=A.AVAILABLE)
    values = dict(use_case=pc.UseCase.EXPLORE_EARTH, presentation_mode=pc.PresentationMode.SIMPLE,
                  aoi=aoi(), decision_as_of=AS_OF, decision_state=D.MONITOR,
                  decision_reference="unit-reviewed-assessment", data_availability=availability,
                  evidence=evidence(availability), limitations=("Unit scenario, not production observations.",),
                  recommended_next_action="Review available evidence.")
    return pc.ProductResult(**(values | changes))


class VocabularyTests(unittest.TestCase):
    def test_exactly_three_independent_use_cases(self):
        self.assertEqual({v.value for v in pc.UseCase}, {"EXPLORE_EARTH", "VERIFY_MY_FIELD", "SMART_FARM"})
        self.assertEqual(len({pc.use_case_purpose(v) for v in pc.UseCase}), 3)

    def test_both_modes_work_with_every_use_case_without_inventing_capabilities(self):
        self.assertEqual({m.value for m in pc.PresentationMode}, {"SIMPLE", "EXPERT"})
        for use_case, mode in product(pc.UseCase, pc.PresentationMode):
            with self.subTest(use_case=use_case, mode=mode):
                assessment = result(use_case=use_case, presentation_mode=mode)
                self.assertEqual(assessment.analysis_level, L.PRELIMINARY_EO)
                self.assertEqual(assessment.data_availability.iot, A.NOT_CHECKED)
                self.assertFalse(assessment.automation_allowed)

    def test_unknown_enum_values_and_foreign_enums_fail(self):
        enums = (pc.UseCase, pc.PresentationMode, L, A, pc.EvidenceSource, pc.ObserverType,
                 pc.PlantCondition, pc.SoilCondition, pc.RecentIrrigation, pc.VerificationState,
                 pc.IoTState, pc.CalibrationState, pc.MLKind, D, pc.ContentCategory)
        for enum in enums:
            with self.subTest(enum=enum), self.assertRaises(ValueError):
                enum("invented")
        for source in pc.EvidenceSource:
            with self.subTest(source=source), self.assertRaises(ValueError):
                pc.DataAvailability(**{source.value: "invented"})
        for changes in ({"use_case": "invented"}, {"presentation_mode": "invented"},
                        {"decision_state": "DROUGHT_DETECTED"}, {"decision_state": "DISEASE_DETECTED"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                result(**changes)
        with self.assertRaises(ValueError):
            pc.DataAvailability(sentinel=True)
        with self.assertRaises(ValueError):
            ground(verification_state=pc.IoTState.CALIBRATED)

    def test_exact_enum_strings_normalize_and_objects_are_immutable(self):
        assessment = result(use_case="SMART_FARM", presentation_mode="EXPERT", decision_state="MONITOR")
        self.assertIs(assessment.use_case, pc.UseCase.SMART_FARM)
        with self.assertRaises(FrozenInstanceError):
            assessment.automation_allowed = True


class GeometryTests(unittest.TestCase):
    def test_all_three_geometries_and_global_coordinates(self):
        polygon = pc.Polygon((pc.Point(-10, -20), pc.Point(-9, -20), pc.Point(-9, -19), pc.Point(-10, -20)))
        for geometry in (pc.Point(179, -89), pc.BoundingBox(-180, -90, 180, 90), polygon):
            area = replace(aoi(), geometry=geometry, place_name=None, country=None)
            self.assertEqual(area.crs, "EPSG:4326")
            self.assertIn(area.to_dict()["geometry"]["type"], ("Point", "BoundingBox", "Polygon"))

    def test_required_fields_and_empty_identifiers_fail(self):
        for changes in ({"aoi_id": " "}, {"geometry": None}, {"requested_time_range": None},
                        {"place_name": ""}, {"country": 17}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(aoi(), **changes)
        with self.assertRaises(TypeError):
            pc.AreaOfInterest("missing-geometry-and-time")

    def test_invalid_coordinates_and_types_fail(self):
        for longitude, latitude in ((181, 0), (-181, 0), (0, 91), (0, -91), (float("nan"), 0),
                                    (0, float("inf")), ("32", 37), (True, 37)):
            with self.subTest(longitude=longitude, latitude=latitude), self.assertRaises(ValueError):
                pc.Point(longitude, latitude)
        for bounds in ((10, 0, 9, 1), (0, 1, 1, 0), (0, 0, 0, 1), (170, 0, -170, 1)):
            with self.assertRaises(ValueError):
                pc.BoundingBox(*bounds)

    def test_polygon_closure_degeneracy_crossings_and_dateline_fail(self):
        for coordinates in ([], [(0, 0), (1, 0), (1, 1)], [(0, 0), (1, 0), (2, 0), (0, 0)],
                            [(0, 0), (2, 2), (0, 2), (3, 0), (0, 0)],
                            [(179, 0), (-179, 0), (-179, 1), (179, 0)]):
            with self.subTest(coordinates=coordinates), self.assertRaises(ValueError):
                pc.Polygon(tuple(pc.Point(*p) for p in coordinates))

    def test_spatial_relevance_including_polygon_boundaries(self):
        vertices = tuple(pc.Point(*p) for p in ((0, 0), (2, 0), (2, 2), (0, 2), (0, 0)))
        area = replace(aoi(), geometry=pc.Polygon(vertices))
        for point in (pc.Point(1, 1), pc.Point(0, 0), pc.Point(2, 1)):
            self.assertTrue(area.contains(point))
        self.assertFalse(area.contains(pc.Point(3, 1)))
        self.assertTrue(aoi().contains(pc.Point(32.5, 37.6)))
        self.assertFalse(aoi().contains(pc.Point(0, 0)))
        point_area = replace(aoi(), geometry=pc.Point(32.5, 37.6))
        self.assertTrue(point_area.contains(pc.Point(32.5, 37.6)))
        self.assertFalse(point_area.contains(pc.Point(32.51, 37.6)))

    def test_time_ranges_validate_and_normalize_to_utc(self):
        period = pc.TimeRange("2025-06-09T11:00:00+03:00", "2025-06-09T09:00:00Z")
        self.assertEqual(period.start, "2025-06-09T08:00:00Z")
        for start, end in (("2025-06-09", AS_OF), ("2025-06-09T08:00:00", AS_OF),
                           ("bad", AS_OF), ("2025-06-10T00:00:00Z", AS_OF)):
            with self.assertRaises(ValueError):
                pc.TimeRange(start, end)


class GroundAndSensorTests(unittest.TestCase):
    def test_farmer_is_ground_evidence_not_automatically_verified_truth(self):
        observation = ground()
        self.assertEqual(observation.source, "HUMAN_OBSERVATION")
        self.assertEqual(observation.verification_state, pc.VerificationState.SELF_REPORTED)
        self.assertIs(observation.to_dict()["is_independent_ground_truth"], False)
        with self.assertRaises(TypeError):
            ground(is_independent_ground_truth=True)

    def test_reviewed_and_sensor_supported_observations_still_require_independent_validation(self):
        for observer, verification in product(pc.ObserverType, pc.VerificationState):
            record = ground(observer_type=observer, verification_state=verification,
                            verification_reference="unit-review-record")
            self.assertFalse(record.is_independent_ground_truth)
        for verification in (pc.VerificationState.EXPERT_VERIFIED, pc.VerificationState.SENSOR_SUPPORTED):
            with self.assertRaises(ValueError):
                ground(verification_state=verification)

    def test_ground_schema_accepts_categories_and_optional_fields(self):
        for plant, soil, irrigation in product(pc.PlantCondition, pc.SoilCondition, pc.RecentIrrigation):
            record = ground(plant_condition=plant, soil_condition=soil, recent_irrigation=irrigation,
                            symptoms="Unit symptom", notes="Unit note", photo_reference="unit-photo")
            self.assertEqual(record.plant_condition, plant)

    def test_irrigation_timing_and_invalid_ground_fields_fail(self):
        valid = ground(recent_irrigation="YES", recent_irrigation_timestamp="2025-06-09T07:00:00Z")
        self.assertIsNotNone(valid.recent_irrigation_timestamp)
        for changes in ({"observation_id": ""}, {"crop_type": ""}, {"location": (32, 37)},
                        {"timestamp": "2025-06-09"}, {"plant_condition": "HEALTHY_CONFIRMED"},
                        {"soil_condition": "invented"}, {"observer_type": "invented"},
                        {"recent_irrigation_timestamp": "2025-06-09T07:00:00Z"},
                        {"recent_irrigation": "YES", "recent_irrigation_timestamp": "2025-06-10T07:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ground(**changes)

    def test_sensor_units_and_optional_measurements_are_explicit(self):
        record = sensor(soil_temperature=20, ec=1.2, ph=7, leaf_wetness=12)
        serialized = record.to_dict()
        self.assertEqual(serialized["soil_moisture_unit"], "m3/m3")
        self.assertEqual(serialized["temperature_unit"], "degC")
        self.assertEqual(serialized["ec_unit"], "dS/m")
        self.assertTrue(record.usable_at(AS_OF, 3600))
        self.assertFalse(record.usable_at(AS_OF, 60))

    def test_only_calibrated_quality_valid_current_iot_is_usable(self):
        for state in pc.IoTState:
            cal = pc.Calibration() if state == pc.IoTState.UNCALIBRATED else calibration()
            record = sensor(state=state, calibration=cal)
            self.assertEqual(record.usable_at(AS_OF, 86400), state == pc.IoTState.CALIBRATED)
        self.assertFalse(sensor(quality_valid=False).usable_at(AS_OF, 86400))

    def test_expired_future_or_not_yet_calibrated_readings_are_unusable(self):
        records = (sensor(timestamp="2025-06-08T08:00:00Z"), sensor(timestamp="2025-06-10T08:00:00Z"),
                   sensor(calibration=calibration(valid_until="2025-06-09T08:10:00Z")),
                   sensor(calibration=calibration(calibrated_at="2025-06-09T08:10:00Z")))
        for record in records:
            self.assertFalse(record.usable_at(AS_OF, 86400))
        current = sensor(timestamp=AS_OF)
        self.assertTrue(current.usable_at(AS_OF, 0))

    def test_missing_and_inconsistent_calibration_metadata_fail(self):
        with self.assertRaises(ValueError):
            pc.Calibration(state="CALIBRATED")
        for changes in ({"reference": ""}, {"site_reference": None}, {"valid_until": None},
                        {"valid_until": "2025-04-01T00:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                calibration(**changes)
        with self.assertRaises(ValueError):
            sensor(calibration=pc.Calibration())
        with self.assertRaises(ValueError):
            sensor(state="UNCALIBRATED")

    def test_invalid_sensor_values_and_states_fail_loudly(self):
        for changes in ({"sensor_id": ""}, {"state": "invented"}, {"quality_valid": "true"},
                        {"soil_moisture": 25}, {"air_temperature": -274}, {"relative_humidity": 101},
                        {"soil_temperature": float("nan")}, {"ec": -1}, {"ph": 15}, {"leaf_wetness": -1},
                        {"air_temperature": float("inf")}, {"soil_moisture": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                sensor(**changes)
        for invalid in (-1, float("nan"), True):
            with self.assertRaises(ValueError):
                sensor().usable_at(AS_OF, invalid)


class ResolutionTests(unittest.TestCase):
    def test_sentinel_only_is_preliminary(self):
        self.assertEqual(pc.resolve_analysis_level(pc.DataAvailability(sentinel=A.AVAILABLE)), L.PRELIMINARY_EO)

    def test_each_richer_eo_source_enhances_without_claiming_accuracy(self):
        for source in ("temporal", "hyperspectral", "weather", "ml"):
            availability = pc.DataAvailability(sentinel=A.AVAILABLE, **{source: A.AVAILABLE})
            self.assertEqual(pc.resolve_analysis_level(availability), L.EO_ENHANCED)
            self.assertEqual(result(availability).decision_state, D.MONITOR)

    def test_human_ground_observation_produces_ground_informed(self):
        availability = pc.DataAvailability(sentinel=A.AVAILABLE, ground=A.AVAILABLE)
        assessment = result(availability, ground_observations=(ground(),))
        self.assertEqual(assessment.analysis_level, L.GROUND_INFORMED)

    def test_usable_iot_produces_site_monitored_with_optional_ground(self):
        for with_ground in (False, True):
            availability = pc.DataAvailability(sentinel=A.AVAILABLE, hyperspectral=A.AVAILABLE, iot=A.AVAILABLE,
                                               ground=A.AVAILABLE if with_ground else A.UNAVAILABLE)
            assessment = result(availability, iot_evidence=(sensor(),),
                                ground_observations=(ground(),) if with_ground else ())
            self.assertEqual(assessment.analysis_level, L.SITE_MONITORED)
            self.assertEqual(len(assessment.ground_observations), int(with_ground))

    def test_unavailable_uncalibrated_and_low_quality_sources_never_promote(self):
        for source, state in product((s.value for s in pc.EvidenceSource if s != pc.EvidenceSource.SENTINEL), A):
            if state == A.AVAILABLE:
                continue
            availability = pc.DataAvailability(sentinel=A.AVAILABLE, **{source: state})
            self.assertEqual(pc.resolve_analysis_level(availability), L.PRELIMINARY_EO)

    def test_ground_and_iot_available_flags_cannot_stand_in_for_records(self):
        for source in ("ground", "iot"):
            availability = pc.DataAvailability(sentinel=A.AVAILABLE, **{source: A.AVAILABLE})
            with self.assertRaises(ValueError):
                pc.resolve_analysis_level(availability)
            with self.assertRaises(ValueError):
                result(availability)

    def test_uncalibrated_invalid_stale_or_connected_iot_cannot_claim_monitored(self):
        for state in (pc.IoTState.UNCALIBRATED, pc.IoTState.INVALID, pc.IoTState.STALE, pc.IoTState.CONNECTED):
            cal = pc.Calibration() if state == pc.IoTState.UNCALIBRATED else calibration()
            record = sensor(state=state, calibration=cal)
            with self.assertRaises(ValueError):
                result(pc.DataAvailability(sentinel=A.AVAILABLE, iot=A.AVAILABLE), iot_evidence=(record,))
            availability = pc.DataAvailability(sentinel=A.AVAILABLE, iot=A.AVAILABLE_BUT_UNCALIBRATED
                                               if state == pc.IoTState.UNCALIBRATED else A.INSUFFICIENT_QUALITY)
            assessment = result(availability, iot_evidence=(record,))
            self.assertEqual(assessment.analysis_level, L.PRELIMINARY_EO)

    def test_missing_satellite_foundation_cannot_produce_a_normal_assessment(self):
        for state in A:
            if state == A.AVAILABLE:
                continue
            availability = pc.DataAvailability(sentinel=state, hyperspectral=A.AVAILABLE, ground=A.AVAILABLE, iot=A.AVAILABLE)
            for decision in D:
                if decision == D.INSUFFICIENT_DATA:
                    assessment = result(availability, decision_state=decision,
                                        ground_observations=(ground(),), iot_evidence=(sensor(),))
                    self.assertIsNone(assessment.analysis_level)
                else:
                    with self.assertRaises(ValueError):
                        result(availability, decision_state=decision, ground_observations=(ground(),), iot_evidence=(sensor(),))

    def test_outside_aoi_outside_time_and_future_records_fail(self):
        for factory, source, records_key in ((ground, "ground", "ground_observations"), (sensor, "iot", "iot_evidence")):
            availability = pc.DataAvailability(sentinel=A.AVAILABLE, **{source: A.AVAILABLE})
            for changes in ({"location": pc.Point(0, 0)}, {"timestamp": "2025-05-01T00:00:00Z"},
                            {"timestamp": "2025-06-09T09:00:00Z"}):
                with self.subTest(source=source, changes=changes), self.assertRaises(ValueError):
                    result(availability, **{records_key: (factory(**changes),)})

    def test_available_sources_require_summaries_and_provenance(self):
        with self.assertRaises(ValueError):
            result(evidence=())
        with self.assertRaises(ValueError):
            pc.EvidenceItem("sentinel", "Unit summary", ())
        with self.assertRaises(ValueError):
            result(evidence=(pc.EvidenceItem("weather", "Unit summary", ("unit-weather",)),))
        with self.assertRaises(ValueError):
            result(ground_observations=(ground(),))
        with self.assertRaises(ValueError):
            result(iot_evidence=(sensor(),))


class ResultAndPolicyTests(unittest.TestCase):
    def test_all_capability_combinations_and_decisions_block_automation(self):
        # All 2^7 usable/unusable capability combinations, across every permitted
        # decision, use case and mode. Other availability states are nonusable and
        # separately checked for every source in ResolutionTests.
        source_names = [f.name for f in fields(pc.DataAvailability)]
        human, measurement = ground(), sensor()
        count = 0
        for mask in product((False, True), repeat=len(source_names)):
            availability = pc.DataAvailability(**dict(zip(source_names, (A.AVAILABLE if b else A.UNAVAILABLE for b in mask))))
            decisions = tuple(D) if mask[0] else (D.INSUFFICIENT_DATA,)
            expected_level = (None if not mask[0] else L.SITE_MONITORED if mask[5]
                              else L.GROUND_INFORMED if mask[4] else L.EO_ENHANCED if any(mask[1:4]) or mask[6]
                              else L.PRELIMINARY_EO)
            for decision, use_case, mode in product(decisions, pc.UseCase, pc.PresentationMode):
                assessment = result(availability, decision_state=decision, use_case=use_case, presentation_mode=mode,
                                    ground_observations=(human,) if mask[4] else (), iot_evidence=(measurement,) if mask[5] else ())
                self.assertIs(assessment.automation_allowed, False)
                self.assertEqual(assessment.analysis_level, expected_level)
                count += 1
        self.assertEqual(count, 2304)

    def test_callers_cannot_override_automation_analysis_level_or_schema(self):
        for changes in ({"automation_allowed": True}, {"automation_allowed": False}, {"analysis_level": L.SITE_MONITORED},
                        {"schema_version": "future"}):
            with self.assertRaises(TypeError):
                result(**changes)
        with self.assertRaises((TypeError, ValueError)):
            replace(result(), automation_allowed=True)

    def test_ml_semantics_cannot_be_relabelled_as_diagnosis_probability_or_truth(self):
        ml = pc.MLEvidence("unit-scene", ("unit-provenance",))
        self.assertEqual(ml.kind.value, "EXPERIMENTAL_UNSUPERVISED_SPECTRAL_ANOMALY")
        self.assertEqual(ml.meaning, "Spectrally unusual vegetation relative to the current scene.")
        for flag in ("diagnosis_allowed", "used_for_decision", "score_is_probability", "is_independent_ground_truth"):
            self.assertIs(ml.to_dict()[flag], False)
            with self.assertRaises(TypeError):
                pc.MLEvidence("unit-scene", ("unit-provenance",), **{flag: True})
        with self.assertRaises(TypeError):
            pc.MLEvidence("unit-scene", ("unit-provenance",), meaning="Drought detected")
        with self.assertRaises(ValueError):
            pc.EvidenceItem("ml", "Drought detected", ("unit-provenance",))

    def test_ml_availability_never_selects_or_changes_any_supplied_decision(self):
        for decision in D:
            plain = result(decision_state=decision)
            with_ml = replace(plain, data_availability=replace(plain.data_availability, ml=A.AVAILABLE),
                              evidence=plain.evidence + (pc.MLEvidence("unit-scene", ("unit-provenance",)),))
            self.assertEqual(plain.decision_state, with_ml.decision_state)
            self.assertEqual(plain.recommended_next_action, with_ml.recommended_next_action)
            self.assertFalse(with_ml.automation_allowed)
            self.assertIn(pc.ML_LIMITATION, with_ml.limitations)

    def test_decision_action_reference_and_limitations_are_required(self):
        for changes in ({"decision_reference": ""}, {"recommended_next_action": " "},
                        {"limitations": ()}, {"limitations": ("",)}, {"decision_as_of": "bad"}):
            with self.assertRaises(ValueError):
                result(**changes)

    def test_json_is_deterministic_finite_normalized_and_detached(self):
        assessment = result()
        self.assertEqual(assessment.to_json(), assessment.to_json())
        equivalent = replace(assessment, decision_as_of="2025-06-09T11:35:59.024+03:00")
        self.assertEqual(assessment.to_json(), equivalent.to_json())
        decoded = json.loads(assessment.to_json())
        self.assertIs(decoded["automation_allowed"], False)
        self.assertEqual(decoded["analysis_level"], "PRELIMINARY_EO")
        decoded["evidence"][0]["summary"] = "changed detached copy"
        self.assertNotEqual(decoded, assessment.to_dict())
        parsed = json.loads(assessment.to_json(), parse_constant=lambda value: self.fail(value))
        self.assertEqual(assessment.to_json(), json.dumps(parsed, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n")

    def test_input_lists_are_copied_to_immutable_tuples(self):
        items = list(result().evidence)
        assessment = result(evidence=items)
        items.clear()
        self.assertEqual(len(assessment.evidence), 1)

    def test_simple_projection_excludes_all_expert_categories_and_evidence_payloads(self):
        assessment = pc.konya_example(pc.PresentationMode.SIMPLE)
        projected = assessment.presentation_content()
        self.assertEqual(set(projected), {c.value for c in pc.permitted_content(pc.PresentationMode.SIMPLE)})
        self.assertTrue(projected["inspection_recommended"])
        self.assertEqual(projected["evidence_level"], "EO_ENHANCED")
        expert_only = pc.permitted_content(pc.PresentationMode.EXPERT) - pc.permitted_content(pc.PresentationMode.SIMPLE)
        for category in expert_only:
            self.assertNotIn(category.value, projected)
            with self.assertRaises(ValueError):
                pc.validate_content_categories(pc.PresentationMode.SIMPLE, (category,))
        for technical in ("NDVI", "NDRE", "NDMI", "PCA", "provenance", "quality_masks", "evidence"):
            self.assertNotIn(technical, projected)

    def test_expert_mode_permits_details_and_retains_evidence_and_limitations(self):
        pc.validate_content_categories(pc.PresentationMode.EXPERT, tuple(pc.ContentCategory))
        assessment = pc.konya_example(pc.PresentationMode.EXPERT)
        self.assertEqual(assessment.presentation_content(), assessment.to_dict())
        self.assertTrue(assessment.presentation_content()["evidence"][0]["provenance"])
        self.assertIn(pc.ML_LIMITATION, assessment.presentation_content()["limitations"])
        with self.assertRaises(ValueError):
            pc.permitted_content("invented")
        with self.assertRaises(ValueError):
            pc.validate_content_categories("EXPERT", ("drought_probability",))


class RealKonyaRegressionTests(unittest.TestCase):
    def test_konya_matches_saved_stage4_truth_and_stage46_availability(self):
        saved = json.loads((ROOT / "outputs/fusion/decision.json").read_text(encoding="utf-8"))
        ml = json.loads((ROOT / "outputs/ml/ml_summary.json").read_text(encoding="utf-8"))
        assessment = pc.konya_example()
        self.assertEqual(saved["source_scene_id"], "20250608_091605_90_4001")
        self.assertEqual(saved["source_scene_id"], ml["scene_id"])
        self.assertEqual(assessment.aoi.geometry, pc.BoundingBox(*saved["bbox"]))
        self.assertEqual(assessment.decision_state.value, saved["decision"])
        self.assertEqual(assessment.decision_state, D.GROUND_VERIFICATION_REQUIRED)
        self.assertEqual(pc._time(assessment.decision_as_of), pc._time(saved["decision_as_of"]))
        self.assertEqual(assessment.recommended_next_action, saved["recommended_next_step"])
        self.assertIn(saved["matched_rule_id"], assessment.decision_reference)
        self.assertEqual(saved["spectral_evidence"]["state"], "RELATIVE_HOTSPOTS_PRESENT")
        self.assertEqual(saved["temporal_evidence"]["state"], "NEUTRAL_OR_MIXED")
        summaries = {e.source: e.summary for e in assessment.evidence if isinstance(e, pc.EvidenceItem)}
        self.assertIn(saved["spectral_evidence"]["state"], summaries[pc.EvidenceSource.HYPERSPECTRAL])
        self.assertIn(saved["temporal_evidence"]["state"], summaries[pc.EvidenceSource.TEMPORAL])
        self.assertEqual(assessment.data_availability.ground.value, saved["ground_evidence"]["state"])
        self.assertEqual(assessment.to_dict()["ground_observations"], saved["ground_evidence"]["observations"])
        self.assertFalse(saved["automation_allowed"])
        self.assertFalse(assessment.automation_allowed)
        self.assertFalse(ml["score_is_probability"])
        self.assertFalse(ml["calibrated_agronomic_classifier"])
        self.assertEqual(assessment.data_availability.ml, A.AVAILABLE)
        self.assertEqual(assessment.analysis_level, L.EO_ENHANCED)

    def test_konya_decision_is_identical_with_or_without_ml(self):
        for mode in pc.PresentationMode:
            without, with_ml = pc.konya_example(mode, include_ml=False), pc.konya_example(mode)
            self.assertEqual(without.decision_state, with_ml.decision_state)
            self.assertEqual(without.decision_reference, with_ml.decision_reference)
            self.assertEqual(without.recommended_next_action, with_ml.recommended_next_action)
            self.assertEqual(without.analysis_level, with_ml.analysis_level)
            self.assertIs(with_ml.automation_allowed, False)

    def test_saved_example_is_exact_deterministic_serialization(self):
        example = ROOT / "examples/product_contract_konya.json"
        self.assertEqual(example.read_bytes(), pc.konya_example().to_json().encode("utf-8"))

    def test_contract_generation_is_offline_and_previous_outputs_and_frontend_are_unchanged(self):
        tracked = subprocess.check_output(["git", "ls-files", "-z", "src", "dashboard"], cwd=ROOT).decode().split("\0")
        paths = [ROOT / name for name in tracked if name]
        paths.extend(p for p in (ROOT / "outputs").rglob("*") if p.is_file())
        self.assertTrue(any(p.suffix == ".npz" for p in paths))
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        with patch("socket.socket.connect", side_effect=AssertionError("Must stay offline")), \
             patch.object(Path, "open", side_effect=AssertionError("Contract must perform no file I/O")):
            for use_case, mode in product(pc.UseCase, pc.PresentationMode):
                assessment = replace(pc.konya_example(mode), use_case=use_case)
                json.loads(assessment.to_json())
                assessment.presentation_content()
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


if __name__ == "__main__":
    unittest.main()

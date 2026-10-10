"""Stage 4.7: validated product vocabulary, without processing or intervention.

This module uses only the standard library and performs no I/O. Availability is
an assertion by an upstream validator, not a discovery service. Evidence levels
describe capability, never accuracy, probability, severity or independent truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
import math
from typing import Literal


class UseCase(StrEnum):
    EXPLORE_EARTH = "EXPLORE_EARTH"
    VERIFY_MY_FIELD = "VERIFY_MY_FIELD"
    SMART_FARM = "SMART_FARM"


def use_case_purpose(use_case: UseCase) -> str:
    return {
        UseCase.EXPLORE_EARTH: "Preliminary Earth-observation screening of a selected agricultural region using data available for that location.",
        UseCase.VERIFY_MY_FIELD: "Combine satellite screening with a human observation from someone who can physically access the field.",
        UseCase.SMART_FARM: "Combine EO evidence with site-specific IoT measurements and future continuous monitoring.",
    }[_enum(UseCase, use_case)]


class PresentationMode(StrEnum):
    SIMPLE = "SIMPLE"
    EXPERT = "EXPERT"


class AnalysisLevel(StrEnum):
    PRELIMINARY_EO = "PRELIMINARY_EO"
    EO_ENHANCED = "EO_ENHANCED"
    GROUND_INFORMED = "GROUND_INFORMED"
    SITE_MONITORED = "SITE_MONITORED"


class AvailabilityState(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CHECKED = "NOT_CHECKED"
    NOT_CONNECTED = "NOT_CONNECTED"
    AVAILABLE_BUT_UNCALIBRATED = "AVAILABLE_BUT_UNCALIBRATED"
    INSUFFICIENT_QUALITY = "INSUFFICIENT_QUALITY"


class EvidenceSource(StrEnum):
    SENTINEL = "sentinel"
    TEMPORAL = "temporal"
    HYPERSPECTRAL = "hyperspectral"
    WEATHER = "weather"
    GROUND = "ground"
    IOT = "iot"
    ML = "ml"


class ObserverType(StrEnum):
    FARMER = "FARMER"
    RESEARCHER = "RESEARCHER"
    AGRONOMIST = "AGRONOMIST"


class PlantCondition(StrEnum):
    NORMAL = "NORMAL"
    MILD_WILTING = "MILD_WILTING"
    SEVERE_WILTING = "SEVERE_WILTING"
    YELLOWING = "YELLOWING"
    VISIBLE_DAMAGE = "VISIBLE_DAMAGE"
    UNKNOWN = "UNKNOWN"
    OTHER = "OTHER"


class SoilCondition(StrEnum):
    WET = "WET"
    MOIST = "MOIST"
    DRY = "DRY"
    VERY_DRY = "VERY_DRY"
    UNKNOWN = "UNKNOWN"


class RecentIrrigation(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class VerificationState(StrEnum):
    SELF_REPORTED = "SELF_REPORTED"
    EXPERT_VERIFIED = "EXPERT_VERIFIED"
    SENSOR_SUPPORTED = "SENSOR_SUPPORTED"


class IoTState(StrEnum):
    CONNECTED = "CONNECTED"
    CALIBRATED = "CALIBRATED"
    UNCALIBRATED = "UNCALIBRATED"
    STALE = "STALE"
    INVALID = "INVALID"


class CalibrationState(StrEnum):
    CALIBRATED = "CALIBRATED"
    UNCALIBRATED = "UNCALIBRATED"


class MLKind(StrEnum):
    EXPERIMENTAL_UNSUPERVISED_SPECTRAL_ANOMALY = "EXPERIMENTAL_UNSUPERVISED_SPECTRAL_ANOMALY"


class DecisionState(StrEnum):
    NO_CLEAR_CONCERN = "NO_CLEAR_CONCERN"
    MONITOR = "MONITOR"
    REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
    GROUND_VERIFICATION_REQUIRED = "GROUND_VERIFICATION_REQUIRED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ContentCategory(StrEnum):
    STATUS = "status"
    EVIDENCE_LEVEL = "evidence_level"
    INSPECTION_RECOMMENDED = "inspection_recommended"
    NEXT_ACTION = "next_action"
    KEY_LIMITATIONS = "key_limitations"
    NDVI = "NDVI"
    NDRE = "NDRE"
    NDMI = "NDMI"
    SPECTRAL_EVIDENCE = "spectral_evidence"
    TEMPORAL_METRICS = "temporal_metrics"
    HYPERSPECTRAL_DETAILS = "hyperspectral_details"
    PCA = "PCA"
    ML_ANOMALY = "ml_anomaly"
    PROVENANCE = "provenance"
    QUALITY_MASKS = "quality_masks"
    EVIDENCE_FUSION = "evidence_fusion"
    REASONING_TRACE = "reasoning_trace"
    LIMITATIONS = "limitations"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _enum(kind: type[StrEnum], value):
    _require(type(value) in (str, kind), f"Expected {kind.__name__}, got {value!r}")
    return kind(value)


def _set_enum(instance, name: str, kind: type[StrEnum]) -> None:
    object.__setattr__(instance, name, _enum(kind, getattr(instance, name)))


def _text(value, name: str) -> None:
    _require(isinstance(value, str) and bool(value.strip()), f"{name} must be nonempty text")


def _optional_text(value, name: str) -> None:
    if value is not None:
        _text(value, name)


def _number(value, name: str, low: float, high: float) -> None:
    _require(type(value) in (int, float) and math.isfinite(value)
             and low <= value <= high, f"{name} must be finite in [{low}, {high}]")


def _time(value: str) -> datetime:
    _text(value, "timestamp")
    _require("T" in value, "Use an ISO 8601 timestamp including time and timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.utcoffset() is not None, "Timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _set_time(instance, name: str) -> None:
    object.__setattr__(instance, name, _time(getattr(instance, name)).isoformat().replace("+00:00", "Z"))


def _tuple(instance, name: str, kind: type | tuple[type, ...]) -> tuple:
    value = getattr(instance, name)
    _require(isinstance(value, (list, tuple)), f"{name} must be a sequence")
    result = tuple(value)
    _require(all(isinstance(v, kind) for v in result), f"Invalid {name} item")
    object.__setattr__(instance, name, result)
    return result


def _texts(instance, name: str, *, required: bool = False) -> tuple[str, ...]:
    values = _tuple(instance, name, str)
    _require(not required or bool(values), f"{name} must not be empty")
    for value in values:
        _text(value, name)
    return values


def _plain(value):
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    return value


class JsonContract:
    def to_dict(self) -> dict:
        return _plain(self)

    def to_json(self) -> str:
        """Stable keys, preserved evidence order, UTC timestamps and finite JSON."""
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


@dataclass(frozen=True)
class Point(JsonContract):
    """WGS84 decimal degrees; named longitude/latitude avoid axis ambiguity."""

    longitude: float
    latitude: float
    type: Literal["Point"] = field(default="Point", init=False)

    def __post_init__(self):
        _number(self.longitude, "longitude", -180, 180)
        _number(self.latitude, "latitude", -90, 90)


@dataclass(frozen=True)
class BoundingBox(JsonContract):
    west: float
    south: float
    east: float
    north: float
    type: Literal["BoundingBox"] = field(default="BoundingBox", init=False)

    def __post_init__(self):
        Point(self.west, self.south)
        Point(self.east, self.north)
        _require(self.west < self.east and self.south < self.north,
                 "Bounding box must have positive extent; split antimeridian-crossing AOIs")


def _cross(a: Point, b: Point, c: Point) -> float:
    return ((b.longitude - a.longitude) * (c.latitude - a.latitude)
            - (b.latitude - a.latitude) * (c.longitude - a.longitude))


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return (_cross(a, b, p) == 0 and min(a.longitude, b.longitude) <= p.longitude <= max(a.longitude, b.longitude)
            and min(a.latitude, b.latitude) <= p.latitude <= max(a.latitude, b.latitude))


def _intersects(a: Point, b: Point, c: Point, d: Point) -> bool:
    return ((_cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0)
            or _on_segment(a, b, c) or _on_segment(a, b, d)
            or _on_segment(c, d, a) or _on_segment(c, d, b))


@dataclass(frozen=True)
class Polygon(JsonContract):
    """One closed simple exterior ring; holes and dateline wrapping are deferred."""

    vertices: tuple[Point, ...]
    type: Literal["Polygon"] = field(default="Polygon", init=False)

    def __post_init__(self):
        ring = _tuple(self, "vertices", Point)
        _require(len(ring) >= 4 and ring[0] == ring[-1], "Polygon needs a closed ring with at least three vertices")
        _require(len(set(ring[:-1])) == len(ring) - 1, "Polygon vertices must be distinct except closure")
        _require(max(p.longitude for p in ring) - min(p.longitude for p in ring) < 180,
                 "Split polygons spanning 180 degrees or crossing the antimeridian")
        edges = tuple(zip(ring, ring[1:]))
        area = sum(a.longitude * b.latitude - b.longitude * a.latitude for a, b in edges)
        _require(area != 0, "Polygon must have nonzero area")
        for i, (a, b) in enumerate(edges):
            for j in range(i + 1, len(edges)):
                if j == i + 1 or (i == 0 and j == len(edges) - 1):
                    continue
                _require(not _intersects(a, b, *edges[j]), "Polygon must not self-intersect")


@dataclass(frozen=True)
class TimeRange(JsonContract):
    start: str
    end: str

    def __post_init__(self):
        _set_time(self, "start")
        _set_time(self, "end")
        _require(_time(self.start) <= _time(self.end), "Time range start must be at or before end")


@dataclass(frozen=True)
class AreaOfInterest(JsonContract):
    aoi_id: str
    geometry: Point | BoundingBox | Polygon
    requested_time_range: TimeRange
    place_name: str | None = None
    country: str | None = None
    crs: Literal["EPSG:4326"] = field(default="EPSG:4326", init=False)

    def __post_init__(self):
        _text(self.aoi_id, "aoi_id")
        _require(isinstance(self.geometry, (Point, BoundingBox, Polygon)), "AOI requires a supported geometry")
        _require(isinstance(self.requested_time_range, TimeRange), "AOI requires a requested time range")
        _optional_text(self.place_name, "place_name")
        _optional_text(self.country, "country")

    def contains(self, point: Point) -> bool:
        _require(isinstance(point, Point), "location must be a Point")
        geometry = self.geometry
        if isinstance(geometry, Point):
            return geometry == point  # No unstated buffer or field boundary.
        if isinstance(geometry, BoundingBox):
            return (geometry.west <= point.longitude <= geometry.east
                    and geometry.south <= point.latitude <= geometry.north)
        inside = False
        for a, b in zip(geometry.vertices, geometry.vertices[1:]):
            if _on_segment(a, b, point):
                return True
            if (a.latitude > point.latitude) != (b.latitude > point.latitude):
                crossing = a.longitude + (point.latitude - a.latitude) * (b.longitude - a.longitude) / (b.latitude - a.latitude)
                if point.longitude < crossing:
                    inside = not inside
        return inside


@dataclass(frozen=True)
class GroundObservation(JsonContract):
    observation_id: str
    location: Point
    timestamp: str
    crop_type: str
    observer_type: ObserverType
    plant_condition: PlantCondition
    soil_condition: SoilCondition
    recent_irrigation: RecentIrrigation
    verification_state: VerificationState = VerificationState.SELF_REPORTED
    recent_irrigation_timestamp: str | None = None
    symptoms: str | None = None
    notes: str | None = None
    photo_reference: str | None = None
    verification_reference: str | None = None
    source: Literal["HUMAN_OBSERVATION"] = field(default="HUMAN_OBSERVATION", init=False)
    is_independent_ground_truth: Literal[False] = field(default=False, init=False)

    def __post_init__(self):
        _text(self.observation_id, "observation_id")
        _text(self.crop_type, "crop_type")
        _require(isinstance(self.location, Point), "Observation location must be a Point")
        _set_time(self, "timestamp")
        for name, kind in (("observer_type", ObserverType), ("plant_condition", PlantCondition),
                           ("soil_condition", SoilCondition), ("recent_irrigation", RecentIrrigation),
                           ("verification_state", VerificationState)):
            _set_enum(self, name, kind)
        for name in ("symptoms", "notes", "photo_reference", "verification_reference"):
            _optional_text(getattr(self, name), name)
        if self.verification_state != VerificationState.SELF_REPORTED:
            _text(self.verification_reference, "verification_reference for reviewed evidence")
        if self.recent_irrigation_timestamp is not None:
            _set_time(self, "recent_irrigation_timestamp")
            _require(self.recent_irrigation == RecentIrrigation.YES,
                     "An irrigation timestamp requires recent_irrigation YES")
            _require(_time(self.recent_irrigation_timestamp) <= _time(self.timestamp),
                     "Irrigation cannot occur after its observation")


@dataclass(frozen=True)
class Calibration(JsonContract):
    state: CalibrationState = CalibrationState.UNCALIBRATED
    reference: str | None = None
    site_reference: str | None = None
    calibrated_at: str | None = None
    valid_until: str | None = None

    def __post_init__(self):
        _set_enum(self, "state", CalibrationState)
        _optional_text(self.reference, "calibration reference")
        _optional_text(self.site_reference, "site calibration reference")
        for name in ("calibrated_at", "valid_until"):
            if getattr(self, name) is not None:
                _set_time(self, name)
        if self.state == CalibrationState.CALIBRATED:
            _text(self.reference, "calibration reference")
            _text(self.site_reference, "site calibration reference")
            _require(self.calibrated_at is not None and self.valid_until is not None,
                     "Calibrated evidence requires an explicit validity interval")
        if self.calibrated_at is not None and self.valid_until is not None:
            _require(_time(self.calibrated_at) <= _time(self.valid_until), "Reversed calibration interval")


@dataclass(frozen=True)
class IoTEvidence(JsonContract):
    sensor_id: str
    location: Point
    timestamp: str
    soil_moisture: float
    air_temperature: float
    relative_humidity: float
    state: IoTState
    calibration: Calibration
    quality_valid: bool = False
    soil_temperature: float | None = None
    ec: float | None = None
    ph: float | None = None
    leaf_wetness: float | None = None
    soil_moisture_unit: Literal["m3/m3"] = field(default="m3/m3", init=False)
    temperature_unit: Literal["degC"] = field(default="degC", init=False)
    relative_humidity_unit: Literal["percent"] = field(default="percent", init=False)
    ec_unit: Literal["dS/m"] = field(default="dS/m", init=False)
    ph_unit: Literal["pH"] = field(default="pH", init=False)
    leaf_wetness_unit: Literal["percent"] = field(default="percent", init=False)

    def __post_init__(self):
        _text(self.sensor_id, "sensor_id")
        _require(isinstance(self.location, Point), "Sensor location must be a Point")
        _set_time(self, "timestamp")
        _set_enum(self, "state", IoTState)
        _require(isinstance(self.calibration, Calibration), "Calibration metadata is required")
        _require(type(self.quality_valid) is bool, "quality_valid must be boolean")
        _number(self.soil_moisture, "soil_moisture", 0, 1)
        _number(self.air_temperature, "air_temperature", -273.15, math.inf)
        _number(self.relative_humidity, "relative_humidity", 0, 100)
        for name, low, high in (("soil_temperature", -273.15, math.inf), ("ec", 0, math.inf),
                                ("ph", 0, 14), ("leaf_wetness", 0, 100)):
            if getattr(self, name) is not None:
                _number(getattr(self, name), name, low, high)
        if self.state == IoTState.CALIBRATED:
            _require(self.calibration.state == CalibrationState.CALIBRATED,
                     "CALIBRATED sensor state requires calibrated metadata")
        if self.state == IoTState.UNCALIBRATED:
            _require(self.calibration.state == CalibrationState.UNCALIBRATED,
                     "UNCALIBRATED sensor state conflicts with calibrated metadata")

    def usable_at(self, as_of: str, max_age_seconds: float) -> bool:
        """Freshness is explicit and reproducible; connection alone proves nothing."""
        _number(max_age_seconds, "iot_max_age_seconds", 0, math.inf)
        instant, measured = _time(as_of), _time(self.timestamp)
        if (self.state != IoTState.CALIBRATED or not self.quality_valid
                or self.calibration.state != CalibrationState.CALIBRATED):
            return False
        return (0 <= (instant - measured).total_seconds() <= max_age_seconds
                and _time(self.calibration.calibrated_at) <= measured
                and instant <= _time(self.calibration.valid_until))


@dataclass(frozen=True)
class DataAvailability(JsonContract):
    """AVAILABLE means usable for this AOI/time, not merely discoverable or connected."""

    sentinel: AvailabilityState = AvailabilityState.NOT_CHECKED
    temporal: AvailabilityState = AvailabilityState.NOT_CHECKED
    hyperspectral: AvailabilityState = AvailabilityState.NOT_CHECKED
    weather: AvailabilityState = AvailabilityState.NOT_CHECKED
    ground: AvailabilityState = AvailabilityState.NOT_CHECKED
    iot: AvailabilityState = AvailabilityState.NOT_CHECKED
    ml: AvailabilityState = AvailabilityState.NOT_CHECKED

    def __post_init__(self):
        for attribute in fields(self):
            _set_enum(self, attribute.name, AvailabilityState)


def _relevant(record, aoi: AreaOfInterest, as_of: str) -> None:
    _require(aoi.contains(record.location), "Ground/IoT location is outside the requested AOI")
    start, end = aoi.requested_time_range.start, aoi.requested_time_range.end
    _require(_time(start) <= _time(record.timestamp) <= min(_time(end), _time(as_of)),
             "Ground/IoT timestamp is outside the requested range or after the decision cutoff")


def resolve_analysis_level(
    availability: DataAvailability, *, aoi: AreaOfInterest | None = None,
    as_of: str | None = None, ground_observations: tuple[GroundObservation, ...] = (),
    iot_evidence: tuple[IoTEvidence, ...] = (), iot_max_age_seconds: float = 86400,
) -> AnalysisLevel | None:
    """Resolve richness only. None means no usable Sentinel foundation in v1.

    Temporal history, hyperspectral, weather or experimental ML can enrich EO.
    Ground and IoT AVAILABLE assertions must be backed by relevant typed records.
    Precedence is site monitoring, human observation, enhanced EO, preliminary EO;
    all evidence is retained and none of these choices computes a decision.
    """
    _require(isinstance(availability, DataAvailability), "Typed availability is required")
    _number(iot_max_age_seconds, "iot_max_age_seconds", 0, math.inf)
    if as_of is not None:
        _time(as_of)
    for records, kind in ((ground_observations, GroundObservation), (iot_evidence, IoTEvidence)):
        _require(isinstance(records, (tuple, list)) and all(isinstance(r, kind) for r in records),
                 f"Expected {kind.__name__} records")
    if ground_observations or iot_evidence or AvailabilityState.AVAILABLE in (availability.ground, availability.iot):
        _require(isinstance(aoi, AreaOfInterest) and as_of is not None,
                 "Ground/IoT evidence requires an AOI and explicit decision cutoff")
        for record in (*ground_observations, *iot_evidence):
            _relevant(record, aoi, as_of)
    if availability.ground == AvailabilityState.AVAILABLE:
        _require(bool(ground_observations), "AVAILABLE ground requires a human observation")
    if availability.iot == AvailabilityState.AVAILABLE:
        _require(any(r.usable_at(as_of, iot_max_age_seconds) for r in iot_evidence),
                 "AVAILABLE IoT requires calibrated, quality-valid, current site evidence")
    if availability.sentinel != AvailabilityState.AVAILABLE:
        return None
    if availability.iot == AvailabilityState.AVAILABLE:
        return AnalysisLevel.SITE_MONITORED
    if availability.ground == AvailabilityState.AVAILABLE:
        return AnalysisLevel.GROUND_INFORMED
    if AvailabilityState.AVAILABLE in (availability.temporal, availability.hyperspectral, availability.weather, availability.ml):
        return AnalysisLevel.EO_ENHANCED
    return AnalysisLevel.PRELIMINARY_EO


@dataclass(frozen=True)
class EvidenceItem(JsonContract):
    source: EvidenceSource
    summary: str
    provenance: tuple[str, ...]

    def __post_init__(self):
        _set_enum(self, "source", EvidenceSource)
        _require(self.source != EvidenceSource.ML, "ML must use the constrained MLEvidence schema")
        _text(self.summary, "evidence summary")
        _texts(self, "provenance", required=True)


ML_LIMITATION = "Experimental spectral anomaly evidence is complementary only; not drought or disease detection, probability, calibrated agronomic prediction or ground truth."


@dataclass(frozen=True)
class MLEvidence(JsonContract):
    scene_id: str
    provenance: tuple[str, ...]
    source: EvidenceSource = field(default=EvidenceSource.ML, init=False)
    kind: MLKind = field(default=MLKind.EXPERIMENTAL_UNSUPERVISED_SPECTRAL_ANOMALY, init=False)
    meaning: str = field(default="Spectrally unusual vegetation relative to the current scene.", init=False)
    limitation: str = field(default=ML_LIMITATION, init=False)
    diagnosis_allowed: Literal[False] = field(default=False, init=False)
    used_for_decision: Literal[False] = field(default=False, init=False)
    score_is_probability: Literal[False] = field(default=False, init=False)
    is_independent_ground_truth: Literal[False] = field(default=False, init=False)

    def __post_init__(self):
        _text(self.scene_id, "ML scene_id")
        _texts(self, "provenance", required=True)


def permitted_content(mode: PresentationMode) -> frozenset[ContentCategory]:
    mode = _enum(PresentationMode, mode)
    if mode == PresentationMode.EXPERT:
        return frozenset(ContentCategory)
    return frozenset((ContentCategory.STATUS, ContentCategory.EVIDENCE_LEVEL,
                      ContentCategory.INSPECTION_RECOMMENDED, ContentCategory.NEXT_ACTION,
                      ContentCategory.KEY_LIMITATIONS))


def validate_content_categories(mode: PresentationMode, categories) -> None:
    allowed = permitted_content(mode)
    for category in categories:
        category = _enum(ContentCategory, category)
        _require(category in allowed, f"{category.value} is not permitted in {mode}")


PRODUCT_LIMITATIONS = (
    "Evidence levels describe available capability, not accuracy, confidence, probability or guarantees; more sources do not automatically improve accuracy.",
    "Analyse agricultural areas using Earth-observation data available for that location; coverage and usable quality differ by place and time.",
    "Decision support only. No autonomous intervention is allowed in this PoC; no decision state establishes a diagnosis.",
)


@dataclass(frozen=True)
class ProductResult(JsonContract):
    use_case: UseCase
    presentation_mode: PresentationMode
    aoi: AreaOfInterest
    decision_as_of: str
    decision_state: DecisionState
    decision_reference: str
    data_availability: DataAvailability
    evidence: tuple[EvidenceItem | MLEvidence, ...]
    limitations: tuple[str, ...]
    recommended_next_action: str
    ground_observations: tuple[GroundObservation, ...] = ()
    iot_evidence: tuple[IoTEvidence, ...] = ()
    iot_max_age_seconds: float = 86400
    analysis_level: AnalysisLevel | None = field(init=False)
    automation_allowed: Literal[False] = field(default=False, init=False)
    schema_version: Literal["4.7.1"] = field(default="4.7.1", init=False)

    def __post_init__(self):
        _set_enum(self, "use_case", UseCase)
        _set_enum(self, "presentation_mode", PresentationMode)
        _set_enum(self, "decision_state", DecisionState)
        _require(isinstance(self.aoi, AreaOfInterest), "Result requires a typed AOI")
        _set_time(self, "decision_as_of")
        _text(self.decision_reference, "decision_reference")
        _text(self.recommended_next_action, "recommended_next_action")
        _tuple(self, "ground_observations", GroundObservation)
        _tuple(self, "iot_evidence", IoTEvidence)
        _tuple(self, "evidence", (EvidenceItem, MLEvidence))
        _texts(self, "limitations", required=True)
        level = resolve_analysis_level(
            self.data_availability, aoi=self.aoi, as_of=self.decision_as_of,
            ground_observations=self.ground_observations, iot_evidence=self.iot_evidence,
            iot_max_age_seconds=self.iot_max_age_seconds,
        )
        object.__setattr__(self, "analysis_level", level)
        _require(level is not None or self.decision_state == DecisionState.INSUFFICIENT_DATA,
                 "Without usable Sentinel evidence the decision must be INSUFFICIENT_DATA")
        for source in EvidenceSource:
            records = tuple(e for e in self.evidence if e.source == source)
            state = getattr(self.data_availability, source.value)
            if state == AvailabilityState.AVAILABLE:
                _require(bool(records), f"AVAILABLE {source.value} needs an evidence summary and provenance")
            if records:
                _require(state in (AvailabilityState.AVAILABLE, AvailabilityState.AVAILABLE_BUT_UNCALIBRATED,
                                   AvailabilityState.INSUFFICIENT_QUALITY),
                         f"Evidence conflicts with {source.value} availability")
        if self.ground_observations:
            _require(self.data_availability.ground in (AvailabilityState.AVAILABLE, AvailabilityState.INSUFFICIENT_QUALITY),
                     "Ground records conflict with availability")
        if self.iot_evidence:
            _require(self.data_availability.iot in (AvailabilityState.AVAILABLE, AvailabilityState.AVAILABLE_BUT_UNCALIBRATED,
                                                   AvailabilityState.INSUFFICIENT_QUALITY),
                     "IoT records conflict with availability")
        required = list(PRODUCT_LIMITATIONS)
        if self.ground_observations:
            required.append("Human observations are ground evidence, not automatically independent scientific ground truth, including reviewed observations.")
        if self.iot_evidence:
            required.append("Site-specific sensors are fallible; calibration, quality, freshness and spatial relevance do not guarantee correctness or representativeness.")
        if any(isinstance(e, MLEvidence) for e in self.evidence):
            required.append(ML_LIMITATION)
        object.__setattr__(self, "limitations", tuple(dict.fromkeys((*required, *self.limitations))))

    def presentation_content(self) -> dict:
        """Content projection only; no frontend, templates or scientific inference.

        Full serialization is the scientific transport. SIMPLE deliberately omits
        evidence payloads, provenance and raw technical metrics from its projection.
        """
        if self.presentation_mode == PresentationMode.EXPERT:
            return self.to_dict()
        limitations = ["Screening is not a diagnosis; evidence richness does not measure accuracy."]
        if self.analysis_level is None:
            limitations.append("Usable satellite screening is unavailable.")
        if self.data_availability.ground != AvailabilityState.AVAILABLE:
            limitations.append("Human field observations are unavailable or not usable.")
        if self.data_availability.iot != AvailabilityState.AVAILABLE:
            limitations.append("Usable calibrated site monitoring is unavailable.")
        if self.data_availability.ml == AvailabilityState.AVAILABLE:
            limitations.append("Experimental evidence cannot establish a cause or diagnosis.")
        return {
            "status": self.decision_state.value,
            "evidence_level": self.analysis_level.value if self.analysis_level else None,
            "inspection_recommended": self.decision_state in (DecisionState.REVIEW_RECOMMENDED, DecisionState.GROUND_VERIFICATION_REQUIRED),
            "next_action": self.recommended_next_action,
            "key_limitations": limitations,
        }


def konya_example(presentation_mode: PresentationMode = PresentationMode.EXPERT, *, include_ml: bool = True) -> ProductResult:
    """Fixed, tested snapshot of the existing demo; never loads or reruns pipelines.

    Omitting the complementary Stage 4.6 layer cannot change the Stage 4 decision.
    The bbox comes from scientific artifacts, not the frontend's regional locator.
    """
    _require(type(include_ml) is bool, "include_ml must be boolean")
    evidence = (
        EvidenceItem(EvidenceSource.SENTINEL, "Sentinel-2 screening available for the demo AOI.",
                     ("outputs/sentinel/temporal_summary.json",)),
        EvidenceItem(EvidenceSource.HYPERSPECTRAL, "RELATIVE_HOTSPOTS_PRESENT; scene-relative spectral priorities for field verification.",
                     ("outputs/fusion/decision.json#/spectral_evidence", "outputs/spectral/spectral_summary.json")),
        EvidenceItem(EvidenceSource.TEMPORAL, "NEUTRAL_OR_MIXED; neither confirms nor rules out local stress.",
                     ("outputs/fusion/decision.json#/temporal_evidence",)),
    )
    if include_ml:
        evidence += (MLEvidence("20250608_091605_90_4001", ("outputs/ml/ml_summary.json",)),)
    return ProductResult(
        use_case=UseCase.EXPLORE_EARTH, presentation_mode=presentation_mode,
        aoi=AreaOfInterest(
            "konya-20250608_091605_90_4001",
            BoundingBox(32.44227196464563, 37.51375341016496, 32.70580618046614, 37.69491765950834),
            TimeRange("2025-04-01T00:00:00Z", "2025-07-31T23:59:59.999999Z"), "Konya", "Turkey"),
        decision_as_of="2025-06-09T08:35:59.024Z",
        decision_state=DecisionState.GROUND_VERIFICATION_REQUIRED,
        decision_reference="outputs/fusion/decision.json#/matched_rule_id=D06",
        data_availability=DataAvailability(
            sentinel=AvailabilityState.AVAILABLE, temporal=AvailabilityState.AVAILABLE,
            hyperspectral=AvailabilityState.AVAILABLE, weather=AvailabilityState.NOT_CHECKED,
            ground=AvailabilityState.UNAVAILABLE, iot=AvailabilityState.NOT_CONNECTED,
            ml=AvailabilityState.AVAILABLE if include_ml else AvailabilityState.NOT_CHECKED),
        evidence=evidence,
        limitations=(
            "Ground observations are unavailable; no ground measurements have been simulated.",
            "Stage 4 uses only acquisitions at or before the decision cutoff; later observations in the requested season do not select this decision.",
            "This is an acquisition-time-gated retrospective reconstruction, not proof of operational availability in June 2025.",
            "Relative hotspots are not drought prevalence; regional temporal medians do not validate individual hotspots.",
            "Masks, phenology, crop/canopy and soil differences, mixed pixels and residual atmosphere can confound shared spectral proxies.",
            "The short seasonal baseline is not a climatology; neutral or mixed temporal evidence does not exclude local stress.",
            "The 400-1700 nm window does not simulate Satellite 813 response; correlated evidence is not independent ground truth.",
        ),
        recommended_next_action="Review the hotspot map against field boundaries; obtain quality-checked, site-calibrated soil-moisture observations in representative hotspot and comparison areas before considering an intervention.",
    )

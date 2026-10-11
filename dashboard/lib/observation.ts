import { containsPoint, validBBox, type BBox } from "./aoi";

export const observationOptions = {
  observer_type: ["FARMER", "RESEARCHER", "AGRONOMIST"],
  plant_condition: ["NORMAL", "MILD_WILTING", "SEVERE_WILTING", "YELLOWING", "VISIBLE_DAMAGE", "UNKNOWN", "OTHER"],
  soil_condition: ["WET", "MOIST", "DRY", "VERY_DRY", "UNKNOWN"],
  recent_irrigation: ["YES", "NO", "UNKNOWN"],
} as const;
export type ObservationInput = {
  crop_type: string; observer_type: string; plant_condition: string; soil_condition: string; recent_irrigation: string;
  timestamp: string; recent_irrigation_timestamp: string; longitude: string; latitude: string; symptoms: string; notes: string; photo_reference: string;
};
export const emptyObservation: ObservationInput = { crop_type: "", observer_type: "", plant_condition: "", soil_condition: "", recent_irrigation: "", timestamp: "", recent_irrigation_timestamp: "", longitude: "", latitude: "", symptoms: "", notes: "", photo_reference: "" };
export type ObservationErrors = Partial<Record<keyof ObservationInput, string>>;
// datetime-local is explicitly labeled UTC. Round-trip validation rejects calendar rollover.
export function utcTimestamp(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value)) return null;
  const normalized = value.length === 16 ? value + ":00" : value;
  const date = new Date(normalized + "Z");
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 19) === normalized ? date.toISOString() : null;
}
export function validateObservation(input: ObservationInput, box: BBox, now = Date.now()): ObservationErrors {
  const errors: ObservationErrors = {};
  if (!input.crop_type.trim()) errors.crop_type = "This field is required.";
  for (const key of Object.keys(observationOptions) as (keyof typeof observationOptions)[]) {
    if (!(observationOptions[key] as readonly string[]).includes(input[key])) errors[key] = "This field is required.";
  }
  const time = utcTimestamp(input.timestamp);
  if (!time || Date.parse(time) > now) errors.timestamp = "Enter a valid UTC date and time, no later than now.";
  if (input.recent_irrigation_timestamp) {
    const irrigation = utcTimestamp(input.recent_irrigation_timestamp);
    if (input.recent_irrigation !== "YES" || !irrigation || !time || Date.parse(irrigation) > Date.parse(time)) errors.recent_irrigation_timestamp = "Irrigation time requires Yes and cannot be after the observation.";
  }
  const decimal = /^-?\d+(\.\d+)?$/;
  if (!decimal.test(input.longitude.trim()) || !decimal.test(input.latitude.trim()) || !validBBox(box) || !containsPoint(box, Number(input.longitude), Number(input.latitude))) {
    errors.longitude = "Enter a valid point inside the selected area.";
    errors.latitude = errors.longitude;
  }
  return errors;
}
export function makeObservation(input: ObservationInput) {
  return {
    observation_id: crypto.randomUUID(), source: "HUMAN_OBSERVATION" as const,
    crop_type: input.crop_type.trim(), observer_type: input.observer_type, plant_condition: input.plant_condition,
    soil_condition: input.soil_condition, recent_irrigation: input.recent_irrigation,
    timestamp: utcTimestamp(input.timestamp)!, recent_irrigation_timestamp: input.recent_irrigation_timestamp ? utcTimestamp(input.recent_irrigation_timestamp) : null,
    location: { type: "Point" as const, longitude: Number(input.longitude), latitude: Number(input.latitude) },
    symptoms: input.symptoms.trim() || null, notes: input.notes.trim() || null, photo_reference: input.photo_reference.trim() || null,
    verification_state: "SELF_REPORTED" as const, verification_reference: null, is_independent_ground_truth: false as const,
  };
}
export type Observation = ReturnType<typeof makeObservation>;

import { countryById, type Country } from "./scenes";

export type BBox = { west: number; south: number; east: number; north: number; type: "BoundingBox" };
export type SelectedArea = { country: Country; geometry: BBox };
export const coordinateKeys = ["west", "south", "east", "north"] as const;
export const coordinateLabels = ["West longitude", "South latitude", "East longitude", "North latitude"];
export function validBBox(box: BBox): boolean {
  return coordinateKeys.every((key) => Number.isFinite(box[key])) && box.west >= -180 && box.east <= 180 && box.south >= -90 && box.north <= 90 && box.west < box.east && box.south < box.north;
}
export function parseBBox(value: string | null): BBox | null {
  const parts = value?.split(",");
  if (!parts || parts.length !== 4 || parts.some((value) => !/^-?\d+(\.\d+)?$/.test(value))) return null;
  const [west, south, east, north] = parts.map(Number);
  const box: BBox = { west, south, east, north, type: "BoundingBox" };
  return validBBox(box) ? box : null;
}
export function selectedArea(countryId: string | null, value: string | null): SelectedArea | null {
  const country = countryById(countryId), geometry = parseBBox(value);
  return country && geometry ? { country, geometry } : null;
}
export const bboxString = (box: BBox) => coordinateKeys.map((key) => box[key]).join(",");
export const areaCenter = (box: BBox) => ({ longitude: (box.west + box.east) / 2, latitude: (box.south + box.north) / 2 });
// Geographic display estimate on a sphere, not a scientific scene/field measurement.
export const areaKm2 = (box: BBox) => 6371.0088 ** 2 * (box.east - box.west) * Math.PI / 180 * Math.abs(Math.sin(box.north * Math.PI / 180) - Math.sin(box.south * Math.PI / 180));
export const containsPoint = (box: BBox, longitude: number, latitude: number) => Number.isFinite(longitude) && Number.isFinite(latitude) && longitude >= box.west && longitude <= box.east && latitude >= box.south && latitude <= box.north;

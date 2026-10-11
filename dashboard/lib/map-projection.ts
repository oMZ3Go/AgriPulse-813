// Geographic context only. Web Mercator aligns local outlines, OSM tiles and AOIs.
export type Position = [number, number];
export type MapFrame = { x: number; y: number; width: number; height: number };
export const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
export const MAX_MAP_LATITUDE = 85.0511287798066;
export function project(longitude: number, latitude: number): Position {
  const phi = clamp(latitude, -MAX_MAP_LATITUDE, MAX_MAP_LATITUDE) * Math.PI / 180;
  return [(longitude + 180) / 360, (1 - Math.asinh(Math.tan(phi)) / Math.PI) / 2];
}
export function unproject(x: number, y: number): Position {
  return [clamp(x * 360 - 180, -180, 180), Math.atan(Math.sinh(Math.PI * (1 - 2 * clamp(y, 0, 1)))) * 180 / Math.PI];
}
export function frameAt(x: number, y: number, width: number): MapFrame {
  const w = clamp(width, .000001, 1), h = w / 2;
  return { x: clamp(x - w / 2, 0, 1 - w), y: clamp(y - h / 2, 0, 1 - h), width: w, height: h };
}

import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { geoArea, geoCentroid, geoContains, geoEquirectangular, geoGraticule10, geoPath } from "d3-geo";
import { feature, mesh } from "topojson-client";

// Reproducible geographic context, never a satellite image or analysis layer.
// Natural Earth 1:110m geometry, distributed by world-atlas (public-domain data).
const require = createRequire(import.meta.url);
const topology = JSON.parse(await readFile(require.resolve("world-atlas/countries-110m.json"), "utf8"));
const land = feature(topology, topology.objects.land);
const borders = mesh(topology, topology.objects.countries, (a, b) => a !== b);
const projection = geoEquirectangular().scale(2048 / (2 * Math.PI)).translate([1024, 512]).precision(0.1);
const path = geoPath(projection).digits(2);
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="2048" height="1024" viewBox="0 0 2048 1024">
<title>Natural Earth geographic context. Not satellite imagery or scene coverage.</title>
<rect width="2048" height="1024" fill="#10211c"/>
<path d="${path(land)}" fill="#48604f" stroke="#728570" stroke-width="0.5"/>
<path d="${path(borders)}" fill="none" stroke="#899882" stroke-opacity="0.25" stroke-width="0.55"/>
<path d="${path(geoGraticule10())}" fill="none" stroke="#b1c2b2" stroke-opacity="0.1" stroke-width="0.6"/>
</svg>\n`;
const directory = new URL("../public/globe/", import.meta.url);
await mkdir(directory, { recursive: true });
await writeFile(new URL("earth.svg", directory), svg);
const countries = feature(topology, topology.objects.countries).features.map((country) => {
  const id = country.id ?? `NE-${country.properties.name.toLowerCase().replaceAll(/[^a-z]+/g, "-")}`;
  // Focus the largest land polygon, avoiding distant territories pulling the camera offshore.
  const parts = country.geometry.type === "MultiPolygon" ? country.geometry.coordinates : [country.geometry.coordinates];
  const largest = parts.map((coordinates) => ({ type: "Polygon", coordinates })).sort((a, b) => geoArea(b) - geoArea(a))[0];
  let [lng, lat] = geoCentroid(largest);
  if (!geoContains(largest, [lng, lat])) [lng, lat] = largest.coordinates[0][0];
  return { ...country, id: String(id), properties: { name: country.properties.name, lat: +lat.toFixed(4), lng: +lng.toFixed(4) } };
}).sort((a, b) => a.properties.name.localeCompare(b.properties.name, "en"));
await writeFile(new URL("countries.json", directory), JSON.stringify({ type: "FeatureCollection", features: countries }) + "\n");
await mkdir(new URL("../lib/", import.meta.url), { recursive: true });
await writeFile(new URL("../lib/countries.json", import.meta.url), JSON.stringify(countries.map(({ id, properties }) => ({ id, ...properties })), null, 2) + "\n");
console.log(`Generated public/globe/earth.svg (${Math.round(Buffer.byteLength(svg) / 1024)} KiB).`);

import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { geoEquirectangular, geoGraticule10, geoPath } from "d3-geo";
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
console.log(`Generated public/globe/earth.svg (${Math.round(Buffer.byteLength(svg) / 1024)} KiB).`);

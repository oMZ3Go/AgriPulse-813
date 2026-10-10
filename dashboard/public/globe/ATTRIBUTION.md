# Globe geography

`earth.svg` is a locally generated equirectangular texture using Natural Earth
1:110m land and country geometry, supplied by the pinned `world-atlas` package.
Natural Earth geographic data is public domain:
https://www.naturalearthdata.com/about/terms-of-use/

Source package: https://github.com/topojson/world-atlas
Generation: `npm run globe:assets` from `dashboard/`.

The styling is created for AgriPulse-813. This asset provides regional orientation
only. It is not satellite imagery, a political assertion, an analysis footprint,
a field boundary, or a risk layer. The Konya and Syria locator coordinates are
approximate locators, not field boundaries. The Konya locator now uses the center
of the Stage 4.7 bounding box (rounded for display); its marker does not depict
the actual footprint.

Stage 5B also generates `countries.json` (polygon geometry) and
`../../lib/countries.json` (search metadata) from the same pinned package.
The 177 mapped countries/areas have Natural Earth numeric identifiers where
provided, otherwise stable `NE-` name identifiers. Some small countries and
territories are absent at this scale. Search and polygon picking share these IDs.
Focus uses the spherical centroid of each country's largest polygon, falling
back to a polygon coordinate when the centroid is outside it. Coordinates are
rounded deterministically. All runtime assets are local.

# Stage 5C closeout report

Local delivery: **11 October 2026**, Asia/Damascus. Continued from the existing
uncommitted Stage 5C implementation; prior work was preserved. No commit, push,
deployment, submission packaging or Notebook work was performed.

## Final UI/UX correction pass

The latest pass continues the same uncommitted implementation. It adds:

- **Explicit landing entry:** country clicks/search browse and focus only. No AOI
  section is rendered or scrolled into on the landing page. The map-icon
  **Choose an area** CTA carries purpose, view and country into `/scene`.
  Purpose cards and view controls remain selectable; the duplicate Continue
  CTA is absent. Header Explore Earth navigation scrolls to the geographic
  browser without starting the workflow.
- **Navigable steps:** 01–05 are keyboard-operable buttons that focus/scroll to
  purpose, view, geography, AOI and confirmation. Missing prerequisites have
  visible explanations. Completed/current/pending states are distinct. One
  shared heading component aligns 01 and 03 and supplies restrained teal,
  cyan, blue, blue-teal and gold accents. Reduced motion uses instant scrolling.
- **Country interaction policy:** ISO numeric code `376` is excluded from the
  selectable registry used by search, keyboard, globe hover/click and custom
  AOI URL restoration. Its existing polygon remains untouched geometry.
- **Calm landing rotation:** OrbitControls rotates at speed 0.18 while idle.
  Interaction pauses rotation, with a six-second rest before resuming when no
  country is selected. Focused countries, reduced motion, hidden tabs and
  offscreen globes pause it. Rotation changes renderer transforms directly;
  it does not set React state every frame.
- **Closer zoom and composition:** minimum altitude is 0.95 globe radii above
  the surface; maximum remains 3. The camera fits the smaller viewport
  dimension and widens only at close zoom to preserve an 8% atmosphere margin.
  A separate stage leaves top space and a clear control strip. Country tooltips
  are bounded within the container; marker labels retain readable widths.
- **Complete Expert blue theme:** navy surfaces and blue controls, active
  language switch, sidebar, actions, links, metadata, cards, table headers,
  figure frames, section numbers, scrollbars and focus outlines. Simple retains
  green/teal. Gold still identifies saved-demo context and verification limits.
- **Live manual BBOX:** all four valid fields immediately drive the overlay,
  center and approximate area. Editing any coordinate updates them; an invalid
  edit removes the selection/metadata and displays validation. **Use this area**
  validates again and enters the selected-area workspace in one action.
  There is no Apply coordinates button.
- **Unified map toolbar:** Draw, Pan, Clear, Redraw, zoom, fit and reset occupy
  one desktop row. Compact mobile buttons may wrap. Icons, names/tooltips,
  selected-tool states and keyboard focus remain available. Toolbar direction
  is explicit in Arabic; the geographic image is never mirrored.
- **Header polish:** shared compact identity, subtle elevated surfaces, contextual
  text/breadcrumbs, bordered navigation and language controls, responsive spacing
  and mode-aware colors. Existing sticky workspace controls remain intact.

The originally failing Ground Observation isolation test read immediately after
asynchronous view/section navigation. It could capture Expert overview as its
ML baseline or compare against a still-rendered Simple panel. The fix waits for
selected mode and the exact ML heading before comparing the complete evidence
text. The full Take Action/evidence comparisons and no-write assertions remain.

The detailed-map failure was test geometry: after removing Apply coordinates,
the test's raw pointer drag could target the portion of the map outside the
viewport. It now scrolls the actual map into view before measuring coordinates
or awaiting tiles, since visible-only loading intentionally excludes an offscreen
map even when its toolbar is visible. The outage test confirms an AOI while
HTTP 503 remains active, then checks successful map recovery. Projection precision, drawing, pan/zoom, attribution, fallback and scientific
isolation assertions remain. Theme checks wait for CSS transitions to settle;
landing picking waits for the globe's actual country hover before clicking.

## Product flow and workspace

The final pathway is **01 Purpose → 02 Simple/Expert → 03 Earth / geographic
selection → 04 AOI → 05 Confirmation → Workspace**. Three use cases share the
same geographic selection: Explore Earth, Verify My Field and Smart Farm.
Presentation depth remains independent of use case. Selected country, custom
BBOX, mode, use case and Expert section remain in URL state.

- Distinct numbered badges connect the workflow; the Earth section explicitly
  carries **03**. The single useful “Next: define your area” CTA remains beneath
  “Choose your view”. The duplicate beneath the globe was removed.
- Use Case and Simple/Expert occupy a dedicated sticky control row below the
  sticky header. Scroll offsets account for both rows. EN/AR controls remain
  available; controls do not depend on scrolling to the page start.
- The desktop sidebar stays sticky. A bordered scene/site card is visually
  separate from the evidence-navigation label and links. It uses one vertical
  overflow region only when viewport height requires it. Mobile uses compact
  site context and a horizontal navigation rail in normal document flow; the
  top controls remain sticky without stacking another tall fixed panel.
- Shared charcoal/green branding remains. Gold signals saved-scene context and
  verification constraints, teal geographic actions, blue temporal/technical
  context, and muted violet experimental spectral evidence. Simple retains a
  warmer assessment treatment; Expert uses the coherent blue technical theme described above.
- Stronger headings, emphasized labels, tabular numerals and monospace technical
  metadata improve hierarchy. Scrollbars follow the current mode's green or blue palette.
- Purpose-card transitions take 400 ms, with individual icon cues lasting
  500–600 ms. Motion is moderate, finite and disabled for reduced motion.

## AOI map, realistic geography and failure behavior

`aoi-map.tsx` now uses a shared Web Mercator projection for country outlines,
tiles and BBOX overlays. Local Natural Earth geography provides the overview;
**OpenStreetMap standard raster tiles appear from tile zoom 8**, with source
zoom capped at 19. Roads, settlements and recognizable geography become visible
as the user zooms toward the selection. No new package dependency was needed.

Provider: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`. Visible attribution is
**© OpenStreetMap contributors**, linked to
[OSM copyright/licensing](https://www.openstreetmap.org/copyright), alongside a
map-issue link. The map explicitly says **“Geographic context only · not EO
evidence”**. This layer is not an observation, analysis result, acquisition-date
match or scientific field boundary. A satellite service was not added; OSM is
the supported keyless basemap alternative for this PoC.

The integration follows the [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/):
browser User-Agent/Referer, ordinary HTTP caching, HTTPS, visible attribution,
and requests limited to the visible map and visible tiles. There is no prefetch,
bulk download, offline tile export, proxy or frontend secret. Automated map
interaction tests intercept tile requests with explicit test-only fixtures.

Supported interactions:

- Pointer pan and BBOX drawing, including reverse-direction drawing.
- Button zoom, keyboard `+`/`−`, arrow-key pan, reset and fit-to-selected-area.
- Live manual WGS84 coordinates, validation, clear/redraw and visible overlay.
  Use this area validates and confirms directly into the workspace.
- The overlay uses contrasting inner/outer strokes so it remains visible over
  both the local dark overview and light street tiles.
- Tile errors display an explicit unavailable message. Local outlines,
  coordinate input, drawing and confirmation remain usable. Successful tile
  loads clear previous errors when the view is retried. Missing local geography
  also leaves coordinate selection usable rather than crashing.

A single-view live smoke check requested **nine Konya tiles: all returned HTTP
200 with `image/png` and a valid localhost Referer**. The rendered map, roads,
AOI overlay and attribution were visually inspected. A first check inside the
restricted network sandbox returned `ERR_NETWORK_ACCESS_DENIED`; its graceful
fallback was observed. The network-enabled check then succeeded. Automated
tests separately cover HTTP 503 fallback, confirmation during the outage and successful recovery.

## Validated Konya and non-Konya behavior

The validated shortcut uses scene **20250608_091605_90_4001** and its exact
saved footprint, `[west, south, east, north]`:

```text
32.44227196464563, 37.51375341016496, 32.70580618046614, 37.69491765950834
```

Only the explicit validated demo loads the scientific package. A manually
selected custom AOI, even in Turkey, does not silently become the Konya demo.
Malformed links fail explicitly without falling back to Konya results.

Syria and arbitrary custom areas correctly show **AOI selected**, **Live EO
analysis not executed in this PoC**, **No EO assessment available for this
area**, and **Validated Konya demo available**. Tests verify this for Syria in all three
use cases and through manual Spain selection, across mode switches and reloads, with zero Konya scientific-package
requests. This is intentional PoC behavior, not a processing failure. The demo
link is available in every use case. No results are invented for other areas.

## Globe markers, zoom and focus

The drift came from a global button `transform` transition interpolating the
same transform written each camera frame by Three.js CSS2DRenderer. Each marker
now has a dedicated, unanimated projection wrapper; the interactive button is
inside it. Explicit lat/lng accessors and fixed surface altitude preserve the
geographic anchor, and button active effects cannot move the marker dot.

Browser regression samples compare rendered dot centers against the renderer's
projected coordinates on moving frames for **both Konya and Syria**, with less
than one CSS pixel tolerance. Coverage includes idle rotation, drag, zoom in/out, reset, responsive resize and
country changes. Existing actual polygon-raycasting and locator-click tests
also pass. Far-side visibility remains managed by the globe library.

Button/wheel zoom stays bounded to **0.95–3 globe radii above the surface**;
camera focus and reset are retained. The hover/focus backlight is one restrained
CSS radial gradient with a 400 ms opacity transition, no continuous animation,
no extra WebGL work and no pointer interception. Reduced motion disables its
transition and the existing camera travel.

## Ground Observation and scientific isolation

Verify My Field captures crop, observer role, plant/soil condition, irrigation
context, actual observation coordinates, UTC observation time, optional
irrigation time, symptoms, notes and a photo filename/reference. It validates
required fields, real calendar dates, nonfuture observation time, irrigation
order, numeric coordinates and containment inside the selected AOI. No photo
upload, backend or account is introduced.

The coordinate group identifies **Observation point · WGS84**, shows allowed
longitude/latitude ranges and offers **Use AOI center as starting point**.
Coordinates start empty. The helper explicitly says it is a convenience, not a
GPS reading; values stay editable. Accepting the unchanged suggestion requires
the user to check that it is the actual observation point before capture.
Editing coordinates retains the existing inside-AOI validation.

Captured observations remain **SELF_REPORTED**, **local-only**, and **not
independently verified**. The record has `is_independent_ground_truth: false`.
The downloadable JSON draft envelope has `storage: LOCAL_EXPORT_ONLY` and
`included_in_saved_assessment: false`. It is not a complete AssessmentResult.
Drafts stay in page memory through presentation switches and disappear on
reload/navigation unless the user exports a copy.

There is no observation-to-ML training, anomaly recalculation, saved-decision
update or automatic evidence promotion. Tests compare the Take Action text and
ML evidence before/after capture, check unchanged availability and analysis
level, assert no non-GET/HEAD requests, and verify local JSON export. The saved
historical package continues to report Ground Observation UNAVAILABLE because
the current local draft is not integrated into that assessment.

Unchanged product/scientific truth:

```text
analysis_level = EO_ENHANCED
decision_state = GROUND_VERIFICATION_REQUIRED
matched_rule_id = D06
automation_allowed = false
```

Stage 4.6 remains experimental, unsupervised, exploratory, scene-relative,
not field-calibrated spectral anomaly evidence. It neither diagnoses drought
or disease nor changes Stage 4. Its displayed Spearman rho remains approximately
**+0.003357**. The 19 decision-time observations remain distinct from the 44-date
retrospective full-season series.

## Take Action, tables, figures and Arabic

Take Action has a clipboard/verification icon, a restrained gold **Verification
required before action** cue, a clear next-step heading, and a separate lock
notice. **Automatic intervention: not allowed** and diagnostic limits remain
explicit. No numeric risk, probability, severity or confidence was introduced.

Scientific tables use consistent column geometry, explicit row/column scopes,
aligned numeric headings/cells and tabular numerals. Long headings wrap at
small widths. Figures fit their cards, preserve aspect ratio and are bounded to
the smaller of **60 viewport-height units or 560 px**. Original full-size links,
local scientific PNGs, captions and source labels remain available.

The shared language provider and translation dictionary cover core product
flows, controls, forms, validation, map explanations and principal scientific
cautions. Language preference persists in optional localStorage. Document
`lang`/`dir` switch with EN/AR; logical spacing, directional controls and numeric
isolation preserve RTL layout. Maps and scientific imagery are not mirrored.
The new map explanatory text uses automatic text direction independently of its
geographic coordinate frame. Globe loading/fallback text is translated too.

## Final validation

| Check | Final result |
| --- | --- |
| `npm.cmd run typecheck` | Passed. |
| `npm.cmd run build` | Passed; production routes prerendered successfully. |
| `npm.cmd run test:e2e` | **51 passed**, installed Microsoft Edge/Chromium against the final production build. |
| `git diff --check` | Passed. |
| Accessibility | **Zero serious or critical axe violations** in the tested EN/AR routes, forms, scientific views and detailed map. |
| Responsive layout | No horizontal viewport overflow at **1440, 1280, 1024, 768, 390 px**, and **360 px**. Sticky toolbar, table geometry and figure bounds explicitly tested in EN/AR at all six requested widths. |
| Runtime behavior | No unexpected console/page errors in the passing suite. Deliberate missing-package 404 and basemap 503 failures are isolated test cases. |
| Globe | Both markers follow projected positions during automatic/manual rotation, selection, zoom, resize and reset. Idle pause/resume, reduced motion, closer bounded zoom and polygon picking pass. |
| AOI / map | Drawing, coordinate entry, clear/redraw, confirmation, pan/zoom, fit, attribution, tile failure and successful recovery pass. The earlier live nine-tile Konya check passed. An additional final smoke check confirmed manual BBOX continuation while HTTP 503 remained active, with zero Konya requests. |
| Observation isolation | SELF_REPORTED capture, local export, helper review, inside-AOI validation, unchanged action/ML text/analysis level and no remote writes pass. |
| Scientific baseline | **72 of 72 SHA-256 hashes match**, zero protected-file changes after the final browser run; all three geography hashes also match. |
| Additional exporter diagnosis | Strict Python `--check` flags existing CRLF transport; read-only comparison finds nine CRLF-only JSON differences, ten byte-identical PNGs and zero other differences. |

The 51-test suite comprises 20 existing experience tests, 16 Stage 5C core
tests and 15 final-polish tests. Existing assertions were preserved except
earlier intentional Stage 5C behavior updates. Screenshots of desktop/mobile
flows, Arabic observation forms and EN/AR scientific tables were inspected;
original figures remained readable at full size and fitted the cards.

After the final hash match, temporary scientific-baseline JSON,
screenshot/trace/test-result artifacts and incremental TypeScript cache were
removed. The task-owned Next server was stopped. Intentional source, tests,
assets and reports were retained; installed dependencies and the local production
build remain available for review. The incoming uncommitted `next-env.d.ts`
production type imports were preserved, rather than reverting them to HEAD's
dev paths.

## Known limits

- Konya is the only saved validated EO package. There is no live global EO
  analysis, weather integration, IoT backend, supervised ML or intervention
  automation. Smart Farm remains explicitly NOT CONNECTED.
- OSM requires network access and is a best-effort public tile service, not a
  guaranteed production service. Attribution and policy must remain in place.
  No satellite basemap or field-boundary precision is claimed.
- Natural Earth overview is coarse and omits some small territories. Web
  Mercator map display is limited to about ±85.0511° latitude; manual WGS84
  input retains its ±90° validation. Antimeridian-crossing AOIs must be split.
  AOIs are boxes; polygon drawing and visual observation-point picking remain
  future work.
- Advanced artifact prose, original figure labels and some country names
  remain in English. Browser verification uses installed Edge/Chromium; it is
  not a full cross-browser or assistive-technology certification.
- Existing Windows CRLF scientific JSON causes the strict byte-level Python
  exporter `--check` to reject the checkout. A read-only regenerated-package
  comparison confirms all nine JSON differences are CRLF only and all ten PNGs
  are byte-identical. The established frontend hash check accepts exact LF or
  its CRLF transport equivalent, and still rejects tampering. No protected file
  was rewritten to work around this issue.

## Exact Stage 5C file inventory

The following **34 files** are the intended Stage 5C source, tests and
reports for a future reviewed commit. They remain **uncommitted and unstaged**.

Modified existing files (22):

```text
README.md
dashboard/README.md
dashboard/app/globals.css
dashboard/app/layout.tsx
dashboard/components/analysis-activity.tsx
dashboard/components/country-selector.tsx
dashboard/components/dashboard-shell.tsx
dashboard/components/earth-globe.tsx
dashboard/components/evidence-availability.tsx
dashboard/components/expert-shell.tsx
dashboard/components/globe-canvas.tsx
dashboard/components/header.tsx
dashboard/components/mode-switch.tsx
dashboard/components/product-flow.tsx
dashboard/components/scene-experience.tsx
dashboard/components/scientific-figure.tsx
dashboard/components/simple-shell.tsx
dashboard/components/use-case-picker.tsx
dashboard/lib/konya.ts
dashboard/lib/product.ts
dashboard/lib/scenes.ts
dashboard/tests/experience.spec.ts
```

New intentional files (12):

```text
dashboard/STAGE_5C_REPORT.md
dashboard/components/aoi-map.tsx
dashboard/components/aoi-picker.tsx
dashboard/components/ground-observation.tsx
dashboard/components/language-provider.tsx
dashboard/components/workflow-step-heading.tsx
dashboard/lib/aoi.ts
dashboard/lib/map-projection.ts
dashboard/lib/observation.ts
dashboard/lib/translations.ts
dashboard/tests/stage5c-polish.spec.ts
dashboard/tests/stage5c.spec.ts
```

The additional modified `dashboard/next-env.d.ts` was already present on entry
and retains production `.next/types/` imports generated by Next.js. It is listed
in status below but excluded from the intentional Stage 5C source inventory.
No dependency manifest, lockfile, protected science source/output, contract
example or public Konya artifact was changed. README edits preserve submission
structure and describe only Stage 5C.

## Protected-file verification

All **72 of 72** scientific files match their pre-pass SHA-256 values:
8 scientific Python modules, 6 runner scripts, 37 saved output files,
1 contract example, 19 exported dashboard artifacts and 1 exporter script.

The sorted manifest consists of `path`, one ASCII space, SHA-256, and LF per
entry. Its SHA-256 is:

```text
7df913ca09a9e52957ec51335064ce2cd4cf6c97cf9dd71931adc4836c0828e5
```

All **3 of 3** additional geography files also match:

| File | SHA-256 |
| --- | --- |
| `dashboard/lib/countries.json` | `7f08fd364993a0da805fe46182988f9ae826d93b72c1c78d934aa5ab8f2d4ff2` |
| `dashboard/public/globe/countries.json` | `e3cc4a6edbfea5f911fbb55a8a58f2b5e0551a3e05279d9c6149deb1e28b054e` |
| `dashboard/public/globe/earth.svg` | `44fad55aa320657c8055c826547dd14c8034cbbb490d1c0b7ea983621a581a35` |

## Final git status

**23 modified tracked files, 12 untracked intentional files; nothing staged.**

```text
 M README.md
 M dashboard/README.md
 M dashboard/app/globals.css
 M dashboard/app/layout.tsx
 M dashboard/components/analysis-activity.tsx
 M dashboard/components/country-selector.tsx
 M dashboard/components/dashboard-shell.tsx
 M dashboard/components/earth-globe.tsx
 M dashboard/components/evidence-availability.tsx
 M dashboard/components/expert-shell.tsx
 M dashboard/components/globe-canvas.tsx
 M dashboard/components/header.tsx
 M dashboard/components/mode-switch.tsx
 M dashboard/components/product-flow.tsx
 M dashboard/components/scene-experience.tsx
 M dashboard/components/scientific-figure.tsx
 M dashboard/components/simple-shell.tsx
 M dashboard/components/use-case-picker.tsx
 M dashboard/lib/konya.ts
 M dashboard/lib/product.ts
 M dashboard/lib/scenes.ts
 M dashboard/next-env.d.ts
 M dashboard/tests/experience.spec.ts
?? dashboard/STAGE_5C_REPORT.md
?? dashboard/components/aoi-map.tsx
?? dashboard/components/aoi-picker.tsx
?? dashboard/components/ground-observation.tsx
?? dashboard/components/language-provider.tsx
?? dashboard/components/workflow-step-heading.tsx
?? dashboard/lib/aoi.ts
?? dashboard/lib/map-projection.ts
?? dashboard/lib/observation.ts
?? dashboard/lib/translations.ts
?? dashboard/tests/stage5c-polish.spec.ts
?? dashboard/tests/stage5c.spec.ts
```

## Local commands

From `dashboard/`:

```powershell
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e
```

For local review, run `npm.cmd start` after a successful build and open
**http://127.0.0.1:3000**. The final tests used an explicitly started production
server reused by Playwright; that task-owned server was stopped at closeout.
From the repository root, `git diff --check` checks tracked whitespace.

**Stage 5C stops here. No later-stage work is included.**

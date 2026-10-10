# AgriPulse-813 · Stage 5B

A local Earth-observation product by **Beyond The Limit**, evolving the Stage 5A
Next.js / React / TypeScript shell. The original dark palette, Geist fonts,
layout language and 3D globe remain. Dependencies are unchanged and pinned.

## Run locally

Requires Node.js 20.9 or newer. In PowerShell, from the repository root:

```powershell
Set-Location .\dashboard
npm.cmd ci
npm.cmd run dev
```

Open **http://127.0.0.1:3000**. The included data package and geography work
without external APIs. Dependency installation still requires the usual package
registry access. Use `npm` instead of `npm.cmd` on macOS/Linux.

For production preview, stop the development server first:

```powershell
npm.cmd run build
npm.cmd start
```

## Product flows and presentation

- **Explore Earth** (`EXPLORE_EARTH`): select a country, prepare an agricultural
  area of interest, or open the existing validated Konya scene.
- **Verify My Field** (`VERIFY_MY_FIELD`): the same real EO assessment, followed
  by an honest field-verification pathway. Future Ground Observation includes
  crop/soil condition, irrigation context, symptoms, notes, location, timestamp
  and an optional photo. No form, submission or persistence is implemented.
- **Smart Farm** (`SMART_FARM`): the same EO assessment with a future sensor
  connection pathway. **IoT not connected**; no invented readings. Soil moisture,
  air temperature, humidity, optional soil temperature and calibration metadata
  are described as future evidence.

**SIMPLE / EXPERT describe presentation depth, independently of use case.**
Simple presents concise guidance without raw metrics. Expert exposes Overview,
Spatial risk, Temporal evidence, Hyperspectral analysis, ML spectral anomaly,
Decision fusion, Data provenance and Methodology / limitations.

Use case, mode, country and Expert section are encoded in URL parameters.
Switching use case does not change evidence richness or the decision; switching
presentation preserves the use case. All three use cases can open either view.

## Routes and geographic selection

- `/`: preserved landing identity, short nonblocking intro, globe, country
  search, three product choices and a direct validated-demo route.
- `/scene`: product choice, presentation depth, geographic selection and AOI
  preparation.
- `/dashboard`: the validated Konya package in Simple or Expert presentation.

Country search uses the same local IDs as the globe polygons. Partial,
case-insensitive and accent-insensitive search includes a Türkiye alias for
Turkey. The combobox supports arrow keys, Enter, Escape, visible focus and an
accessible list; the globe is an optional input method.

Search and globe picks update the same URL state. The camera focuses in 350 ms
(or immediately with reduced motion); country fill/outline distinguish hover and
selection. No automatic globe rotation runs. Konya's locator remains gold; Syria
is teal and explicitly **target deployment, not validated**. Locator clicks do
not also pick the polygon beneath them.

The local Natural Earth 1:110m dataset contains 177 mapped countries/areas.
Small countries and territories may be omitted at this scale; geography is not
a political assertion. Focus is calculated deterministically on the largest
polygon. No runtime geography requests leave this application. Regenerate with:

```powershell
npm.cmd run globe:assets
```

**Global location selection does not imply validated analysis for every
location.** A selected country is geographic context, not an analysed AOI.
Point, bounding-box and polygon selection are described as upcoming options;
drawing and global EO processing are not connected. Other locations never show
fabricated availability, completed processing or results. Konya is the only local
validated scientific package.

## Real Konya data bridge

From the repository root (requires the existing local scientific artifacts):

```powershell
.\.venv\Scripts\python.exe scripts\export_dashboard.py
.\.venv\Scripts\python.exe scripts\export_dashboard.py --check
```

The exporter reads Stage 1–4.6 artifacts and
`examples/product_contract_konya.json`, checks the Stage 4.7 snapshot against the
unchanged contract module, verifies scene/AOI/cutoff/decision invariants and saved
local lineage, then writes `public/data/konya/`.

The package contains nine JSON files and ten original PNG figures, **4,598,820
bytes** total. Export is deterministic, with no timestamps from the wall clock.
Only allowlisted summaries and figures are included. No HDF5, Sentinel cache,
pixel arrays, credentials or absolute local paths are shipped. Scientific
artifacts are read, never modified; no processing or scientific inference runs.

The manifest contains hashes for the JSON payloads and original figures.
The client checks JSON SHA-256 values and essential schema/decision invariants
before exposing any assessment. A missing, stale or inconsistent package shows
an error with retry, without displaying a partial assessment. Hashes detect
inconsistency; they do not establish source authenticity. Browser types are
derived from the generated JSON through type-only imports. TypeScript does not
recompute decisions, risk, trends or ML.

Scientific figures use local Next Image components with intrinsic dimensions,
lazy loading and original pixels (`unoptimized`). Only opened Expert sections
request their figures. Each figure has context, source attribution and a
full-size link; a missing figure has an explicit error state.

## Scientific truth displayed

Scene **20250608_091605_90_4001**, Konya, Turkey:

- Stage 2: **RELATIVE_HOTSPOTS_PRESENT**; relative vegetation sampling priorities.
- Stage 3 / decision-time context: **NEUTRAL_OR_MIXED**; no strong broad moisture
  decline confirmation, without ruling out local concern.
- Stage 4: **GROUND_VERIFICATION_REQUIRED**, rule **D06**.
- Analysis level: **EO_ENHANCED**, describing evidence richness, never accuracy,
  probability, guarantee or calibrated confidence.
- **automation_allowed: false**. No intervention controls exist.
- Ground Observation **UNAVAILABLE**, IoT **NOT_CONNECTED**, weather
  **NOT_CHECKED / not integrated**.
- Sentinel-2, temporal history, hyperspectral and experimental ML are available.

Simple guidance: inspect highlighted areas and collect site-specific ground
evidence before intervention. Expert shows the exact saved next action,
reasoning trace, original spatial/temporal/spectral/ML figures, structured
summaries, provenance and limitations.

**Temporal separation matters:** Stage 4 uses 19 observations at or before
`2025-06-09T08:35:59.024Z`. The Stage 3 full-season plot contains 44 observations
from April–July; later observations are clearly labeled retrospective context,
not decision inputs. Spatial P25–P75 bands are not confidence intervals.

**Experimental Spectral Anomaly ML** is unsupervised, exploratory, scene-relative
and not field-calibrated. It identifies unusual vegetation spectra, not their
cause. Scores are not probabilities or drought/disease detection. It is not
independent validation of Stage 2. The near-zero descriptive relationship
(**Spearman rho ≈ +0.003357**) is visible in Expert View. The ML layer does not
modify the Stage 4 decision.

## Activity, availability and motion

Analysis activity records actual local operations: selected Konya area, manifest,
contract, spatial/temporal/hyperspectral/ML documents, saved decision/provenance,
and summary/visualization references. Completed/current/pending/failed states
follow real promises. There are no artificial loading timers or satellite
download claims. It completes immediately when the package is ready and remains
expandable; figures load on demand afterward.

Availability is rendered from the Stage 4.7 contract; future evidence never gets
an available check. Use-case changes do not promote the evidence level.

The navbar is tighter and the current route is underlined. Teal guides primary
actions and geographic selection; gold identifies the validated scene and the
assessment requiring review. The established charcoal/green surfaces remain.

The intro completes in under half a second without hiding or disabling controls.
Each product card has a single 300–350 ms interaction: geographic sweep, marker
lock or sensor signal. No continuous decorative motion, particles or pulsing
loops. Reduced motion disables these effects and camera travel.

## Verification

From `dashboard/`:

```powershell
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e
```

To test the production build instead of the development server:

```powershell
$env:PLAYWRIGHT_PRODUCTION = '1'
npm.cmd run test:e2e
Remove-Item Env:\PLAYWRIGHT_PRODUCTION
```

Playwright uses installed Microsoft Edge by default. Override
`PLAYWRIGHT_CHANNEL` if another supported browser is installed.
Stop a manually running server before production testing.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\export_dashboard.py --check
git diff --check
```

The browser suite checks product flows, all evidence sections and figure loading,
search/keyboard behavior, actual globe picking, synchronization, failure/retry,
tamper rejection, real pending activity, reduced motion, WebGL fallback, runtime
errors, external requests, responsive widths 1440/1280/1024/768/390/360 and axe
serious/critical accessibility violations. Screenshots are saved in ignored
`test-results/`. Python tests verify exact contract/decision preservation, real
metrics, byte-identical figures, deterministic export, offline operation and
rejection of incompatible or stale inputs.

## Scope boundary

Stage 5B adds no backend, database, user accounts, weather API, IoT ingestion,
Ground Observation persistence, supervised ML, automatic irrigation, cloud
deployment or global Sentinel pipeline. Full AOI drawing and later product
polishing remain future work. Stages 1–4.7 remain unchanged.

See [the Stage 5B delivery report](STAGE_5B_REPORT.md) for the change inventory,
verification results and review notes.

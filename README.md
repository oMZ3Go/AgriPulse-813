# AgriPulse-813

Proof of Concept for the Arab Youth Space Hackathon 2026, Challenge 813.

## Phase 1 – Tanager Hyperspectral Pipeline

Processes real Planet Tanager data following the official
[agriculture notebook](references/01_agriculture_crop_intelligence.ipynb) and
[EO quickstart](references/00_EO_data_quickstart_notebook.ipynb). References remain
unchanged; this phase contains satellite processing only.

From the repository root, create the local environment and install dependencies
(Python 3.12 or newer; tested with Python 3.14):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the complete pipeline with this one command:

```powershell
.\.venv\Scripts\python.exe run_tanager.py
```

On Windows, raw HDF5 files, partial downloads, checkpoints, and STAC snapshots
default to **`C:\AgriPulseData\tanager`**, outside the repository and OneDrive.
To choose the raw-data directory explicitly for this PowerShell session:

```powershell
$env:AGRIPULSE_DATA_DIR = 'C:\AgriPulseData\tanager'
.\.venv\Scripts\python.exe run_tanager.py
```

`AGRIPULSE_DATA_DIR` names the final directory (no extra `tanager` suffix is added).
Without this variable, non-Windows systems fall back to `data/raw/tanager/` in
the repository. Code, Git, the environment, and generated analysis outputs stay
in the existing workspace.

On Linux/macOS, use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.
The default is the notebook's first scene, `20250608_091605_90_4001` (Konya,
Turkey). Append `--help` to list the three allowed notebook scenes or select
another with `--scene-id 20250331_113403_16_4001`.

The pipeline prints scene metadata and exact band centers, checks remote
`Content-Length`, then downloads the official surface-reflectance HDF5 into
the configured raw-data directory. Allow **2 GB free space** for the default **861 MiB** file
and its assembly. Four connections fetch verified 16 MiB ranges when the server
supports ranges and ETags; otherwise downloading uses one streaming connection.
Only four spectral planes are loaded for analysis.

The raw directory retains the STAC snapshot and URL/size/ETag/SHA-256 receipt.
Reruns require network access. Completed ranges are reused and incomplete ranges
resume at the saved byte offset only when their URL, ETag, byte range, size, and
SHA-256 checkpoint match. Checkpoints are saved after each flushed MiB. Changed
or unverified ranges restart; servers without range support use a full download.
Failures exit with code 1 and report the exact blocker and last successful step,
retaining partial data outside OneDrive for the next run. No substitute data is generated.

Expected outputs under `outputs/tanager/`:

| File | Contents |
| --- | --- |
| `scene_summary.json` | Scene/date/bbox/cloud metadata, spatial resolution, exact wavelengths and band indices, spectral counts, mask coverage, source checksum and software versions |
| `ndvi.png` | `(NIR - Red) / (NIR + Red)` |
| `ndre.png` | `(NIR - RedEdge) / (NIR + RedEdge)` |
| `ndmi.png` | `(NIR - SWIR) / (NIR + SWIR)` |
| `index_statistics.json` | Valid-pixel minimum, maximum, mean, median, population standard deviation, and count for each index |

Outputs are replaced when another scene is processed. Downloads, generated
outputs, temporary files, and the local environment are excluded from Git.

Following the notebook, the pipeline prefers `ortho_sr_hdf5`, falls back to
`basic_sr_hdf5`, reads `HDFEOS/GRIDS/HYP/Data Fields`, and converts exact STAC
`bands` / `eo:center_wavelength` values from micrometers to nanometers. It selects
the nearest centers to Red 665, Red Edge 705, NIR 860, and SWIR 1650 nm, using
only bands within **400–1700 nm**. The complete source file is retained.

The official valid mask requires `nodata_pixels == 0`, `beta_cloud_mask == 0`,
and `beta_cirrus_mask == 0`. Indices also exclude nonfinite/negative reflectances
and zero denominators, so their usable counts may differ. Zero sums are masked
instead of adding the notebook's epsilon, preserving the exact formulas. PNGs
use a fixed -1 to +1 scale, gray for excluded pixels, and image-pixel axes.

Scientific interpretation:

- Reflectance estimates reflected sunlight after atmospheric correction; this
  asset stores physical floats directly, without scaling or offset.
- Red Edge responds to canopy chlorophyll; SWIR responds to vegetation water
  absorption. Indices are proxies, without crop diagnosis or irrigation calibration.
- The requested 813 wavelength window does not simulate its sensor response or
  resolution. The 260 in-range bands include water-vapor bands at 1350–1450 nm;
  none of the four selected bands uses that region.
- Beta masks can leave haze, shadow, and mixed pixels. Statistics cover all valid
  land covers, without field segmentation or ground-truth validation.
- Scene `gsd` and orthorectified pixel spacing are reported separately.
- The notebook's NDRE table has a typo; its executable NIR/Red Edge formula is followed.

Data attribution: © Planet Labs PBC, CC-BY-4.0, as recorded in the official
scene metadata. Reference notebooks by Dr. Vincent Markiet / Space42.

## Phase 2 – Spectral Moisture Stress Risk

Run after Phase 1, from the repository root:

```powershell
.\.venv\Scripts\python.exe run_stress.py
```

Phase 2 runs offline on the **existing real scene** identified by
`outputs/tanager/scene_summary.json`. It verifies the saved STAC snapshot and
HDF5 checksum, reads raw data from `AGRIPULSE_DATA_DIR` (Windows default:
`C:\AgriPulseData\tanager`), and reuses Phase 1's wavelength selection, masks,
reflectance reader, and index formulas. It does not modify Phase 1 outputs or
download another scene. No additional dependencies are required.

The initial vegetation screen is **quality-valid NDVI ≥ 0.30**. This is a
configurable PoC cutoff, not a validated crop/soil/water classifier. It reduces
low-greenness background contamination but can exclude sparse, senescent or
severely affected vegetation and can retain non-crop vegetation. NDVI's general
relationship to vegetation cover supports screening, but does not validate this
specific threshold for Tanager. See [NASA's NDVI guidance](https://science.nasa.gov/earth/earth-observatory/measuring-vegetation-ndvi-evi/).

To change the screen:

```powershell
.\.venv\Scripts\python.exe run_stress.py --ndvi-threshold 0.35
```

The threshold must be between 0 and 1, exclusively. Only screened vegetation
with finite NDVI, NDRE **and** NDMI is classified. Vegetation coverage is reported
as a percentage of all quality-valid pixels; class percentages use classified
vegetation as their denominator. Missing evidence and excluded pixels remain
unassessed, never assigned zero/Low risk.

For each index `X`, a tie-aware empirical percentile is calculated within the
same classified vegetation population:

```text
P_X = 100 × (count of values below X + 0.5 × count equal to X) / N
NDMI deficit = 100 − P_NDMI
support factor = 0.8 + 0.1 × (1 − P_NDVI/100) + 0.1 × (1 − P_NDRE/100)
risk score = NDMI deficit × support factor
```

The result lies between **0 and 100**. Low NDMI rank drives the score, while
NDVI/NDRE only adjust that base by a factor of **0.8–1.0**. They cannot create
risk independently of the NDMI term. These coefficients are explicit,
uncalibrated PoC choices, not fitted parameters. Tied values share a percentile;
the method does not force extrema to 0/100. No NDMI contrast, or fewer than two
usable vegetation pixels, produces an error rather than an invented ranking.

The requested risk boundaries are retained, expressed for continuous scores:

| Spectral moisture-stress risk | Score interval |
| --- | --- |
| Low | 0 ≤ score < 25 |
| Moderate | 25 ≤ score < 50 |
| High | 50 ≤ score < 75 |
| Very High | 75 ≤ score ≤ 100 |

Scores are not rounded before classification. NDVI and NDRE supporting
conditions mean **lower quarter**, **middle half**, or **upper quarter** of
their vegetation distributions, not “Healthy/Stress” training labels.

Outputs under `outputs/stress/` (replaced on rerun):

| File | Contents |
| --- | --- |
| `moisture_stress_risk.png` | Continuous 0–100 scene-relative score; excluded pixels gray |
| `moisture_stress_classes.png` | Four requested spectral risk classes; excluded pixels gray |
| `expert_evidence.png` | NDVI, NDRE, NDMI and risk on the same classified vegetation pixels |
| `stress_statistics.json` | Vegetation-only min/max/mean/median/std, percentiles, IQR, MAD and risk-class counts/percentages |
| `stress_summary.json` | Scene provenance, threshold, coverage, denominators, formula, class boundaries, evidence schema and limitations |
| `pixel_evidence.npz` | Lossless per-pixel evidence on the original row/column grid: indices, percentiles, NDVI/NDRE conditions, NDMI deficit, supporting factor, score, class and masks |

Load the evidence with `numpy.load(path, allow_pickle=False)`. Float layers are
NaN outside classified vegetation. Integer class/condition layers use `0` for
excluded pixels. The complete codebook is in `stress_summary.json`; no pickle or
object arrays are required. Pixel coordinates are not field boundaries or a
georeferenced raster export. All spectral inputs remain inside 400–1700 nm.

**Scientific limits:** this is a **spectral risk/proxy**, not
**ground-truth-confirmed drought or water stress**, a probability, or an irrigation
prescription. [USGS describes NDMI as a vegetation-water-content index](https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index);
NDMI alone cannot establish the cause of a low value. Relative ranks can assign
high classes even in a scene with no confirmed stress, or understate uniformly
affected vegetation. Class percentages therefore do not measure drought
prevalence and are not directly comparable across scenes or thresholds.

Crop type, phenology, canopy density, soil, mixed pixels, beta masks and remaining
atmospheric/shadow effects can confound interpretation. The indices share NIR and
are correlated, so their agreement is not independent confirmation. The
dependence of index–moisture relationships on land cover and soil is illustrated
by [Gu et al. (2008)](https://pubs.usgs.gov/publication/70032687).
**Stage 3 below adds temporal Sentinel-2 evidence to help assess this spectral
proxy; ground sensors remain future work.** Phase 2 itself uses no temporal
evidence or ground-truth labels and introduces no supervised model, dashboard,
API or IoT component.

Run the tests after generating the real Phase 1 and Phase 2 outputs:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use the actual local Tanager scene, check the Phase 1 refactor, score bounds,
exclusions, invalid evidence, finite statistics, class percentages, ties,
configurable screening and reconstruction of scores from saved pixel evidence.

## Stage 3 – Sentinel-2 Temporal Evidence

Install the updated dependencies and run from the repository root after Stage 1:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_sentinel.py
```

**Tanager provides hyperspectral detail at one observation. Sentinel-2 adds more
frequent temporal monitoring. Together they provide spectral + temporal evidence,
not ground-truth confirmation of drought.** Stage 3 adds context without changing
the Stage 2 risk scores or manufacturing labels. No ML, sensors, API, dashboard,
irrigation logic or disease detection is implemented.

The query follows the Planetary Computer/STAC approach in the official
`references/00_EO_data_quickstart_notebook.ipynb`: `sentinel-2-l2a`, the **exact bbox
from the completed Tanager summary**, **2025-04-01 through 2025-07-31 inclusive**,
and scene cloud cover **<30%**. The analysis clips pixel centers to the actual
Tanager STAC footprint polygon inside that bbox. The original Tanager snapshot
checksum is verified; neither reference notebook is modified.

Only native-resolution COG windows intersecting this small area are read. COG
access transfers intersecting compressed blocks, which can extend slightly beyond
the requested window; it does not download entire Sentinel tiles. See
[Rasterio windowed reading](https://rasterio.readthedocs.io/en/latest/topics/windowed-rw.html).
The Windows cache defaults to **`C:\AgriPulseData\sentinel`**, outside OneDrive.
Override this separately from `AGRIPULSE_DATA_DIR`:

```powershell
$env:AGRIPULSE_SENTINEL_DATA_DIR = "D:\AgriPulseData\sentinel"
.\.venv\Scripts\python.exe run_sentinel.py
```

On other operating systems the fallback is ignored `data/raw/sentinel/`. The cache
contains the unsigned STAC snapshot, official calibration XML, compressed raster
windows and receipts with checksums. Successful windows are reused after an
interrupted run. Reruns use the saved catalog for reproducibility; pass
`--refresh-catalog` to query again. The pipeline stops on external access errors;
it never silently drops a failed download or substitutes artificial imagery.

| Input | Role | STAC center wavelength | Native → analysis spacing |
| --- | --- | --- | --- |
| B04 | Red | 665 nm | 10 → 20 m, area average |
| B05 | Red Edge | 704 nm | 20 → 20 m |
| B8A | NIR | 865 nm | 20 → 20 m |
| B11 | SWIR | 1610 nm | 20 → 20 m |
| SCL | Quality classification | Not a spectral analysis band | 20 → 20 m, nearest |

All inputs share a fixed 20 m UTM grid. Spectral metadata is extracted from each
real STAC item and preserved per scene; center wavelengths must be within
400–1700 nm. This compatibility check does not simulate 813's filter responses or
truncate Sentinel's broad spectral response tails. B04 is read at native 10 m
before averaging, avoiding uncertain overview resampling. Other bands use nearest
resampling. Any nodata contribution invalidates the destination cell.

**Calibration matters:** the code reads `BOA_QUANTIFICATION_VALUE` and the
band-specific `BOA_ADD_OFFSET` from each product's official XML, then computes
`reflectance = (DN + offset) / quantification`. The inspected 2025 products use
offset **−1000** and quantification **10000**. Raw DN ratios would therefore be
incorrect. Nodata DN=0 is excluded before calibration; negative/nonfinite
reflectances and nonpositive index denominators are excluded, not clipped.
See the [Copernicus processing description](https://sentiwiki.copernicus.eu/web/s2-processing).

The conservative SCL screen accepts **4 (vegetation) and 5 (not vegetated)** only.
It excludes **0 nodata, 1 saturated/defective, 2 topographic cast shadow, 3 cloud
shadow, 6 water, 7 unclassified, 8 medium cloud, 9 high cloud, 10 cirrus and 11
snow/ice**, plus unknown codes. This is stricter than the required cloud screen;
SCL is not a validated crop map. See the [SCL class legend](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/scene-classification/).

For clear land, Stage 3 reuses the Stage 1 normalized-difference formulas:

```text
NDVI = (B8A − B04) / (B8A + B04)
NDRE = (B8A − B05) / (B8A + B05)
NDMI = (B8A − B11) / (B8A + B11)
```

The vegetation screen is **NDVI ≥ 0.30**, with all three indices finite. This is
the same **uncalibrated PoC threshold** as Stage 2, not a crop classifier.
Statistics are the median and spatial P25/P75 over that date's vegetation pixels.
The shaded P25–P75 interval in figures is spatial spread, **not a confidence
interval**. Valid counts, vegetation counts, acquisition timestamps and each
source's scene cloud metadata accompany every observation.

Reprocessed copies of the same platform/tile/acquisition/orbit use the latest
generation. Multiple tiles or overpasses on the same UTC date form **one daily
clear-pixel mosaic**: sources are ordered by scene cloud percentage then ID; the
first valid source supplies all indices together at each pixel. Overlaps count
once. Pixels are never selected for having the highest NDVI. All source times and
contribution counts are recorded; there is no composite across different dates.

A date needs at least **20% valid footprint coverage** and **100 vegetation
pixels**. These configurable PoC coverage safeguards are not stress thresholds;
excluded dates and reasons remain in `temporal_summary.json`. Coverage can still
vary considerably, so the combined evidence figure includes clear-land and
vegetation coverage. Example configuration:

```powershell
.\.venv\Scripts\python.exe run_sentinel.py --ndvi-threshold 0.35 --min-valid-fraction 0.50
```

Each index's trend is the **Theil–Sen median of all pairwise slopes** between
retained daily medians, using actual elapsed calendar days. At least three dates
are required. A fitted change over the observed span with magnitude ≤ **0.02 index
units** is called **broadly stable**; otherwise the slope sign gives **increasing**
or **decreasing**. `--stable-change-tolerance` changes this descriptive PoC
tolerance. These are not significance tests or water-stress thresholds. A falling
NDMI trend is described as **temporal moisture-related decline evidence**, with
its causes unconfirmed.

If at least five usable dates occur in the **60 days strictly before Tanager**,
and the nearest retained Sentinel acquisition is within **7 days**, a baseline
comparison is included. Each date receives equal weight. For each index it reports
the baseline median and unscaled MAD, the nearest date's median, their difference,
the difference in MAD units (undefined if MAD=0), and a tie-aware empirical
percentile `100 × (count below + 0.5 × count equal) / N`. The compared date is
excluded from the baseline. A percentile is a rank, **not a drought probability**.

Generated files under `outputs/sentinel/` (ignored by Git; replaced on rerun):

| File | Contents |
| --- | --- |
| `sentinel_timeseries.json` | Chronological daily statistics, source times/clouds, calibration and window provenance |
| `sentinel_timeseries.csv` | Same dates, counts, cloud metadata, medians and P25/P75 in tabular form |
| `ndvi_timeseries.png` | NDVI median and spatial IQR, with Tanager date marked |
| `ndre_timeseries.png` | NDRE median and spatial IQR, with Tanager date marked |
| `ndmi_timeseries.png` | NDMI median and spatial IQR, with Tanager date marked |
| `temporal_evidence.png` | All three indices plus changing observation coverage |
| `temporal_summary.json` | Footprint/grid, filters, retained/excluded dates, closest acquisition, trends, baseline and limitations |

Semicolon-separated source IDs, acquisition times and cloud percentages in the
CSV follow the same source order. JSON preserves a full provenance record per
source, including the number of pixels it actually contributed.

Run the automated tests after the real Stages 1–3 outputs exist:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Stage 3 tests run offline against real cached windows: finite bounded indices,
calibration, masks, overlap handling, chronological dates, required summary fields,
CSV/JSON agreement and reconstruction of every retained daily statistic. Small
deterministic vectors test slope logic only; they are never used as satellite data.

**Scientific limits:** varying clouds, footprint coverage and daily vegetation
screens change the sampled population; this is not a fixed cohort of crop fields.
Harvest, phenology, canopy density, soil background, crop mixtures, irrigation and
residual atmospheric effects can all change the indices. Masking is imperfect,
and screening can remove the very vegetation that is declining. The short recent
baseline is not a multi-year climatology. The April–July trend cannot by itself
describe conditions on June 8. Tanager and Sentinel have different resolutions,
bandpasses and timestamps, so their values and risk classes are not directly
interchangeable. Shared spectral proxies are correlated; another sensor adds
temporal evidence, not independent ground truth. Ground sensors and validated
field observations remain future work.

## Stage 4 – Evidence Fusion & Decision Engine

Run from the repository root after generating the real Stage 2 and Stage 3 outputs:

```powershell
.\.venv\Scripts\python.exe run_fusion.py
```

Stage 4 runs **entirely offline**, including its first run. It reads the saved
stress summary, statistics and pixel evidence, plus the Sentinel temporal summary
and daily time series. No new dependencies, satellite downloads or raw raster/HDF5
processing are needed. Existing Stage 1–3 outputs are not modified.

| Component | Role in the decision |
| --- | --- |
| Tanager | Spatial/spectral prioritization: relative hotspots indicate where to seek verification |
| Sentinel-2 | Temporal context from observations eligible at the decision cutoff |
| Ground sensor | Future local verification; current ground evidence is `UNAVAILABLE` |
| Decision engine | Transparent categorical rules with a human-readable reasoning trace |

**AgriPulse currently supports decisions but does not autonomously irrigate based
only on satellite evidence.** In Stage 4, `automation_allowed` is **false for every
rule**, including future scenarios with ground evidence. There is no pump control,
irrigation-volume prescription, ML confidence, probability gauge or fabricated
ground measurement.

The default **`decision_as_of` is `2025-06-09T08:35:59.024Z`**, the requested
Sentinel acquisition nearest the Tanager observation. A daily mosaic is eligible
only when **every listed source acquisition is at or before this cutoff**. If a
mosaic straddles the cutoff, it is excluded entirely: aggregate statistics cannot
safely remove its later pixels. The representative timestamp alone is insufficient.
The Tanager evidence is also excluded if its acquisition is later than the cutoff.

For the current real data, **19 daily observations** are eligible: **18 strictly
before** the cutoff and one at the cutoff. **25 later observations are excluded**.
The engine reuses Stage 3's Theil–Sen function on eligible medians only. Its NDMI
slope is **+0.002589343 index units/day**, increasing. The stability convention is
unchanged: absolute fitted change over the eligible span ≤0.02 index units is
broadly stable; at least three dates are needed. These are descriptive PoC choices,
not significance tests or drought thresholds.

The baseline is recomputed from eligible observations in the **60 days strictly
before Tanager**, excluding the compared date. At least five dates and a closest
observation within seven days of Tanager are required. This gives **17 baseline
dates**, NDMI baseline median **0.245259**, closest NDMI **0.252172**, and empirical
baseline percentile **52.94**. NDVI/NDRE are retained as supporting vegetation
context; they cannot independently select a moisture evidence state.

The temporal classification uses the following exact rules:

| NDMI baseline percentile | Decision-time NDMI trend | Temporal state |
| --- | --- | --- |
| <25 | Decreasing | `DECLINE_SUPPORT` |
| >75 | Increasing | `RECOVERY_OR_WETTER` |
| Any other sufficient combination, including 25–75 inclusive | Central, stable or conflicting evidence | `NEUTRAL_OR_MIXED` |
| Baseline or trend unavailable | Insufficient evidence | `INSUFFICIENT` |

These are uncalibrated spectral evidence categories. `RECOVERY_OR_WETTER` does not
establish measured recovery, and `DECLINE_SUPPORT` does not establish drought.
The current combination is **`NEUTRAL_OR_MIXED`** because NDMI lies within its broad
historical range even though the eligible-window slope is increasing.

Stage 2 contributes **`RELATIVE_HOTSPOTS_PRESENT`** from saved High/Very High ranks
(relative scores ≥50) among **97,490 classified vegetation pixels**. Its score
median is **45.0131** and maximum **99.6965**. These ranks prioritize verification;
their percentages are **not calibrated stress prevalence**, and hotspot extent
does not set decision severity. The categorical interface also represents no
high-ranked hotspots, no measurable NDMI contrast, and insufficient spectral
evidence; invalid or incompatible saved Stage 2 files fail validation.

The ordered decision matrix uses the first matching rule:

| Rule | Condition, after preceding rules | Decision |
| --- | --- | --- |
| D01 | Either required satellite component insufficient | `INSUFFICIENT_EVIDENCE` |
| D02 | Relative hotspots + temporal decline support + verified low ground moisture | `ACTION_REVIEW_REQUIRED` |
| D03 | Other cases with verified low ground moisture | `ELEVATED_CONCERN` |
| D04 | Verified normal ground moisture conflicts with temporal decline support | `GROUND_VERIFICATION_REQUIRED` |
| D05 | Other cases with verified normal ground moisture | `MONITOR` |
| D06 | Relative hotspots + ground unavailable | `GROUND_VERIFICATION_REQUIRED` |
| D07 | Other temporal decline support + ground unavailable | `GROUND_VERIFICATION_REQUIRED` |
| D08 | Remaining sufficient combinations | `MONITOR` |

All rules block automation. The real result is **D06:
`GROUND_VERIFICATION_REQUIRED`**. The recommended next step is to review the
hotspot map against field boundaries, then obtain quality-checked, site-calibrated
soil-moisture observations in representative hotspot and comparison areas before
considering an intervention.

The future ground-observation schema is included in `decision_matrix.json`. It
describes sensor ID, timestamp, moisture value and unit, location, quality flag,
calibration reference, interpretation authority and optional measurement depth.
A future validator must establish temporal/spatial relevance and site/crop/soil
calibration before supplying `VERIFIED_LOW` or `VERIFIED_NORMAL`. No universal
soil-moisture threshold is defined. **Stage 4 has no ground-ingestion option**;
its real output contains `state: UNAVAILABLE` and an empty observations list.

Before fusion, the engine verifies scene IDs, acquisition timestamps, bbox and
footprint/grid, expected source collection/bands/masks, compatible vegetation
screens, and consistency of saved statistics. It checks Stage 2's saved masks,
ranks, score formula and classes against the NPZ evidence, and Stage 3's daily
source contributions, counts and summary values. SHA-256 hashes identify the
exact five input files parsed. Incompatible or inconsistent evidence fails loudly.
Hashes provide change detection, not source authentication.

Full-season statistics are integrity-checked and preserved only under
`retrospective_context_not_used_for_decision` in the technical summary. They never
select the June decision. A corrupted input can stop validation; changing valid
future observations cannot change the decision-time evidence or reasoning trace.

Generated files under `outputs/fusion/` (ignored by Git; replaced on rerun):

| File | Contents |
| --- | --- |
| `decision.json` | Decision, cutoff, evidence states, recommended next step, rule trace and limitations |
| `fusion_summary.json` | Input hashes, detailed methodology, eligibility audit and separate retrospective context |
| `decision_matrix.json` | Ordered rules, state vocabulary and future ground-observation schema |
| `evidence_fusion.png` | Real Tanager → Sentinel → unavailable ground evidence → decision chain; automation blocked |
| `decision_report.md` | Reviewer-readable explanation, actual values, provenance and scientific limits |

Run all tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Fusion tests use the real saved evidence and in-memory unit scenarios only. They
check cutoff boundaries, straddling mosaics, future-data invariance, temporal
conflicts, provenance failures, reasoning/schema correctness and every combination
in the categorical rule matrix. Offline integration tests block network access and
raw satellite readers, reproduce all five artifacts byte-for-byte, and verify that
source files remain unchanged. Synthetic scenarios are never written as production
evidence.

**Scientific limits:** this is a retrospective reconstruction gated by acquisition
time, not proof that archived products were operationally available at that time.
Regional medians do not validate individual hotspots; masks, changing vegetation
coverage, phenology, harvest and soil/canopy differences can affect both sensors.
The short baseline is not a climatology, and an increasing overall slope can hide
recent declines. Neutral/mixed evidence neither confirms nor rules out local stress.
Ground observations and site-specific validation remain necessary.

## Stage 4.5 – Why Hyperspectral?

The current PoC uses simple indices as an explainable baseline. Stage 4.5 uses
the **existing real Tanager scene `20250608_091605_90_4001`** to visualize the
additional spectral information retained around and between those index
wavelengths. Run offline after Stages 1 and 2:

```powershell
.\.venv\Scripts\python.exe run_spectral.py
```

This reuses the verified local HDF5, exact STAC wavelengths, official quality
mask and saved Stage 2 vegetation/risk evidence. No new dependencies or downloads
are needed. Existing stage outputs remain unchanged. The **400–1700 nm
compatibility window does not simulate Satellite 813 spectral response functions**.
The four-point baseline also uses Tanager bands, without multispectral bandpass
convolution.

| Available information | Real-scene result |
| --- | --- |
| Compact baseline | Red **665.87**, Red Edge **705.92**, NIR **861.26**, SWIR **1647.66 nm**, yielding NDVI/NDRE/NDMI |
| Full in-window profile | **260** narrow-band centers, **401.29–1697.65 nm**; **250** have usable statistics in both groups |
| Lower relative-risk group | **24,373** pixels: score ≤ population P25 (**21.2423**) AND Stage 2 Low (score <25) |
| Higher relative-risk group | **21,203** pixels: score ≥ population P75 (**71.4741**) AND Stage 2 Very High (score ≥75) |

Both groups contain only quality-valid, Stage 2 classified vegetation from the
**97,490-pixel** reference population (existing NDVI ≥0.30 screen). All members
of these fixed quartile/class intersections are used, including boundary ties;
there is no random subsampling or manual choice of striking pixels. Scores are
used only for sampling. Counts differ because the original class labels are
preserved. Per-band median/P25/P75 use finite, nonnegative, non-nodata reflectance;
valid/excluded counts are saved for every band. **Ten bands at 1362.44–1407.51 nm
have no usable values**: they remain explicit JSON `null` values and plot gaps,
without imputation. Small exclusions elsewhere can change the per-band population.
P25–P75 describes spatial spread, not a confidence interval.

The descriptive difference is **higher minus lower group median reflectance**.
Exploratory narrow-band contrast regions are selected from fixed 25 nm windows
by mean absolute difference, excluding centers within ±15 nm of the four index
bands and the Stage 1 atmospheric caution interval **1350–1450 nm**. Windows need
at least three bands, all with statistics in both groups; up to three windows
are shown, with centers at least 100 nm apart. These rules are fixed, not tuned.
All eligible window scores are saved. The selected windows are **1450–1475**,
**1550–1575**, and **1675–1700 nm**, with mean absolute differences **0.1871**,
**0.1778**, and **0.1684** reflectance units. These are correlated display contrasts,
not biomarkers or drought bands; the first borders the atmospheric caution region.

Generated files in `outputs/spectral/` (ignored by Git; replaced on rerun):

| File | Contents |
| --- | --- |
| `group_spectral_signatures.png` | Both group medians with shaded P25–P75 |
| `spectral_difference.png` | Signed median difference and exploratory contrast windows |
| `hyperspectral_value.png` | Four-point baseline versus the full spectral profile, on the same scale |
| `spectral_summary.json` | Source hashes, masks/population, group definitions/counts/membership hashes, per-band statistics, ranking rules/results, limitations and attribution |

**Confounding:** Stage 2 risk uses the same NDVI/NDRE/NDMI bands, so group
differences near those wavelengths are partly expected by construction. Separation
elsewhere is also correlated spectral evidence and **does not independently
validate water stress**. Crop type, phenology, canopy/soil mixtures and residual
atmospheric effects remain plausible explanations. No crop matching or ground
truth establishes the cause; the 260 bands are not 260 independent measurements.

**This is an exploratory information-content demonstration, not proof that
hyperspectral data improves drought-detection accuracy.** Indices provide a compact
interpretable baseline. Hyperspectral data preserves fine spectral structure that
can support future calibrated crop-specific models when ground truth becomes
available. Data attribution: Planet Labs PBC, **CC-BY-4.0**; reference notebooks by
Dr. Vincent Markiet / Space42.

Run all stages' tests with `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.
Stage 4.5 tests check real masks, deterministic nonoverlapping groups, wavelength
ordering/range, invalid-value exclusions, percentile ordering, source consistency,
fixed contrast rules, byte-for-byte offline artifact reproduction and unchanged
upstream outputs. Stage 4.5 adds no ML, disease classification, Sentinel processing,
IoT, dashboard or Stage 5 implementation.

## Stage 4.6 – Experimental Unsupervised Spectral Anomaly ML

**The anomaly layer identifies vegetation spectra that are unusual relative to
the current scene. It is not a drought, disease, or crop-stress classifier.**
Independent field ground truth is currently insufficient for defensible supervised
learning. Stage 2 risk classes and index-derived labels are therefore never used
as training targets, validation labels, sampling strata or tuning criteria.

Install the added lightweight Python dependencies once, then run from the repository
root with the existing Stage 1 and Stage 2 artifacts and local Tanager data:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_ml.py
```

The pipeline itself runs **entirely offline**, reusing `AGRIPULSE_DATA_DIR`
(Windows default `C:\AgriPulseData\tanager`) and scene `20250608_091605_90_4001`.
Missing files, mismatched scenes/lineage, altered HDF5/STAC checksums or inconsistent
eligibility masks fail loudly. No data downloads or substitute scenes are attempted.
Previous scientific outputs and the frontend are not modified.

The fixed pipeline is **StandardScaler → PCA → Isolation Forest**:

1. Reconstruct and verify Stage 2's quality-valid NDVI ≥0.30 vegetation screen,
   including finite NDVI/NDRE/NDMI eligibility, without computing or reading risk
   scores/classes for fitting. This starts with **97,490** candidate pixels.
2. Audit all **260** bands inside **400–1700 nm**. Conservatively exclude the
   entire **1350–1450 nm** atmospheric caution interval already identified in
   Stages 1/4.5: **20 bands**, including the **ten wholly unusable bands at
   1362.44–1407.51 nm**. Any additional empty or constant bands would also be
   explicitly excluded. **240 bands** remain. This is a compatibility window,
   **not a Satellite 813 spectral response simulation**.
3. Require finite, nonnegative, non-nodata reflectance in every retained band.
   This excludes **136** incomplete spectra, leaving **97,354 eligible pixels**.
   No interpolation, gap filling, smoothing, invalid-value replacement or clipping
   occurs. Reflectances above one are retained and counted in the band audit.
4. Sample **20,000** eligible pixels uniformly without replacement using
   NumPy `Generator(PCG64(813))`; sort the selected pixel indices. Fit the scaler
   using per-band sample means and population standard deviations (`ddof=0`).
5. Fit PCA with `n_components=0.99`, `svd_solver="full"`, `whiten=False`,
   `copy=True`, `random_state=813`. The smallest component count exceeding 99%
   of standardized fitting-sample variance is **5**, retaining **99.260896%**.
6. Fit Isolation Forest on those five components with **200 trees**,
   `max_samples=256`, `max_features=1.0`, `contamination="auto"`,
   `bootstrap=False`, `random_state=813`, `n_jobs=1`, `warm_start=False`,
   `verbose=0`. Score **all eligible pixels** in batches of 8,192; fitting and
   transforms use one BLAS/OpenMP thread.

The continuous anomaly score is **`-IsolationForest.score_samples(...)`**:
higher means more spectrally unusual. The observed range is **0.372270–0.718427**.
The library's automatic decision offset is unused; no binary anomaly labels,
assumed anomaly fraction, display threshold or calibrated probability is produced.
See the official [Isolation Forest score definition](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html)
and [PCA variance rule](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html).

After fitting, a descriptive comparison on the same 97,354 pixels gives
**Spearman ρ = +0.003357** with the Stage 2 relative moisture-risk score. The JSON
also reports anomaly distributions by the existing Stage 2 risk classes. No
comparison metric chooses features, components, model settings or thresholds.
Agreement does not prove moisture stress; disagreement does not prove either
method wrong. Both originate from the same scene, so this is **not independent
validation**. Near-zero rank correlation also does not establish independence.

Generated files in `outputs/ml/` (ignored by Git; replaced on rerun):

| File | Contents |
| --- | --- |
| `anomaly_score.png` | Continuous relative spectral anomaly; unassessed pixels gray |
| `anomaly_context.png` | NDVI, Stage 2 proxy and anomaly on identical eligible pixels; descriptive only |
| `pca_summary.png` | Individual and cumulative retained variance, sample size and fixed selection rule |
| `ml_summary.json` | Input hashes, eligibility, every band's audit/exclusion reasons, model configuration, sample/membership hashes, variance, score statistics, comparison and limitations |
| `anomaly_pixel_evidence.npz` | Lossless float64 scores, eligibility mask, scene ID, fitting pixel indices and retained band indices; about 0.69 MiB |

Load the NPZ with `allow_pickle=False`; scores are NaN outside eligibility, on
the original image grid. This compact evidence is saved for future integration;
Stage 5B is not implemented. Measured pipeline runs took **7.34–8.12 seconds**
on the development machine (excluding Python imports); a separate offline run
peaked at **469.68 MiB process working set** on Windows. The retained float32
spectra occupy **89.13 MiB**; one float64 fitting matrix occupies **36.62 MiB**.
These are array sizes, not peak process memory. Band-block reads, sample fitting
and batched scoring avoid loading the full hyperspectral cube into memory.

Run `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.
Stage 4.6 tests check exclusions, finite PCA/scores, variance ordering, score
orientation, fixed seeds, missing inputs, lineage and source checksums. A real-data
regression replaces all Stage 2 risk scores/classes and obtains identical fitting
membership, PCA components and anomaly scores. Two fresh runs block network access,
reproduce all five artifacts byte-for-byte and verify unchanged upstream outputs
and frontend files. Exact numerical/PNG identity across different library versions,
hardware or fonts is not guaranteed; dependencies and versions are recorded.

**Scientific limits:** results are scene-relative, unsupervised, exploratory,
not field-calibrated, not a probability or diagnosis, and not proof of agronomic
damage. Crop type, canopy structure/density, phenology, soil/background, mixed
pixels and residual atmosphere can drive unusual spectra. Quality/vegetation
screens can omit sparse or affected vegetation. Uniform pixel sampling represents
area rather than balanced fields, and spatially adjacent pixels are not independent
replicates. Standardization can emphasize noise; PCA may discard unusual
low-variance directions. Components have no assigned physical drought meaning.
There is no classification accuracy, F1, precision, recall or ROC-AUC claim.

Future supervised learning requires **independent ground-truth labels** from farmer
observations, agronomist verification and calibrated IoT measurements. EO spectral
features, temporal features, weather, field observations and calibrated IoT may
then support locally calibrated Random Forest or XGBoost models. These inputs and
supervised models remain future work; none is implemented in Stage 4.6.

## Stage 4.7 – Scientific Product & Evidence Contract

[`product_contract.py`](src/agripulse/product_contract.py) defines the typed,
validated boundary for future product integration. It uses standard-library frozen
dataclasses and string enums, adds no dependencies, and performs no I/O or scientific
analysis. [`product_contract_konya.json`](examples/product_contract_konya.json) is a
deterministic example of the contract, not a newly generated scientific result.

Three independent use cases describe user intent, without promising equal data
availability or upgrading evidence merely because a mode was selected:

| Use case | Purpose |
| --- | --- |
| `EXPLORE_EARTH` | Preliminary EO screening of a selected agricultural region using the data available there |
| `VERIFY_MY_FIELD` | Combine satellite screening with a human observation from someone able to access the field |
| `SMART_FARM` | Combine EO with site-specific IoT measurements and future continuous monitoring |

Presentation is independent: every use case supports **`SIMPLE`** and **`EXPERT`**.
`permitted_content()` and `validate_content_categories()` define the category
allowlist. `presentation_content()` provides a SIMPLE projection containing status,
evidence level, inspection recommendation, next action and concise limitations.
It omits raw metrics and evidence payloads. EXPERT permits NDVI/NDRE/NDMI, spectral
and temporal evidence, hyperspectral detail, PCA/anomaly evidence, quality masks,
provenance, evidence fusion, reasoning trace and full limitations. No UI is added.
Full `to_dict()` / `to_json()` serialization is the scientific transport, including
evidence even when the requested presentation is SIMPLE; it is not a rendering
allowlist. Future presenters must use the content contract, not display the entire
transport by default. Producer-authored next actions must use concise plain language.

| Analysis level | Capability represented |
| --- | --- |
| `PRELIMINARY_EO` | Usable Sentinel-2 screening only |
| `EO_ENHANCED` | Screening plus usable temporal history, hyperspectral, weather or experimental ML evidence |
| `GROUND_INFORMED` | EO plus a relevant human field observation |
| `SITE_MONITORED` | EO plus usable site-specific IoT, optionally with human observations |

These are **evidence-richness labels, not accuracy ranks, confidence scores,
probabilities or guarantees**. More sources do not automatically improve scientific
accuracy. The deterministic resolver uses site monitoring, then human observation,
then enriched EO, then preliminary EO as capability precedence; all evidence remains
in the result. Version 1 conservatively requires usable Sentinel-2 as its satellite
foundation. Without it, `analysis_level` is JSON `null` and only `INSUFFICIENT_DATA`
is permitted, even when other sources exist. Supporting other satellite foundations
requires a later explicit contract revision.

Availability is explicit for `sentinel`, `temporal`, `hyperspectral`, `weather`,
`ground`, `iot` and `ml`: `AVAILABLE`, `UNAVAILABLE`, `NOT_CHECKED`, `NOT_CONNECTED`,
`AVAILABLE_BUT_UNCALIBRATED`, or `INSUFFICIENT_QUALITY`. `AVAILABLE` asserts usable
evidence for the AOI and time, not merely file existence. Available sources require
an evidence summary and provenance; ground/IoT additionally require typed records.
Other states never promote capability. Upstream validation must still establish EO
coverage/quality and provenance: this contract does not authenticate artifacts.

**Global input:** `AreaOfInterest` includes an identifier, WGS84 geometry, optional
place/country and required inclusive UTC time range. Point, bounding box and simple
closed polygon are supported with finite coordinate/range validation. Coordinates
use named longitude/latitude; this is a typed geometry schema, not a GeoJSON parser.
Polygons with holes, multipolygons and antimeridian wrapping are deferred; split
crossing areas before use. Point AOIs have no implicit buffer. This represents
“Analyse agricultural areas using Earth-observation data available for that location,”
without a global coverage promise or any downloading implementation.

**Human ground evidence:** observations include ID, point location, timezone-aware
timestamp, crop, observer role (farmer/researcher/agronomist), plant/soil condition,
recent irrigation and optional irrigation time, symptoms, notes and photo reference.
They are explicitly `HUMAN_OBSERVATION`, default to `SELF_REPORTED`, and may record
`EXPERT_VERIFIED` or `SENSOR_SUPPORTED` with a verification reference. All retain
`is_independent_ground_truth: false`. Review or farmer reporting alone does not
establish independent scientific ground truth. Records must lie in the AOI, within
the requested time range and at or before the decision cutoff.

**IoT evidence:** records include sensor ID/location/time, volumetric soil moisture
(`m3/m3`), air temperature (`degC`), relative humidity (`percent`), and optional soil
temperature, EC (`dS/m`), pH and leaf wetness (`percent`). Sensor states distinguish
`CONNECTED`, `CALIBRATED`, `UNCALIBRATED`, `STALE` and `INVALID`. Calibration metadata
includes state, calibration and site-context references, and a validity interval.
Only calibrated, quality-valid, relevant, current measurements can support
`SITE_MONITORED`; a connection or uncalibrated reading cannot. Freshness uses an
explicit decision cutoff and configurable `iot_max_age_seconds` (default 86,400),
never the wall clock. This is an illustrative contract policy, not a validated
sampling interval or agronomic moisture threshold. Structural validity/calibration
does not guarantee sensor correctness, coverage or field representativeness.

**ML and decisions:** Stage 4.6 is represented only as
`EXPERIMENTAL_UNSUPERVISED_SPECTRAL_ANOMALY`, meaning “Spectrally unusual vegetation
relative to the current scene.” Fixed flags reject diagnosis, probability, ground
truth and decision-use claims. It is not drought/disease detection or a calibrated
agronomic prediction. The contract validates a supplied decision and its provenance;
it does not introduce another scientific decision engine. The product vocabulary is
`NO_CLEAR_CONCERN`, `MONITOR`, `REVIEW_RECOMMENDED`, `GROUND_VERIFICATION_REQUIRED`,
and `INSUFFICIENT_DATA`; none is a diagnosis. Every result includes evidence,
limitations, a next action and immutable **`automation_allowed: false`**.

The Konya snapshot (`20250608_091605_90_4001`) remains **`EO_ENHANCED`** with relative
spectral hotspots, neutral/mixed temporal evidence, unavailable ground evidence,
unconnected IoT, unchecked weather and available experimental ML. Its Stage 4 D06
decision remains **`GROUND_VERIFICATION_REQUIRED`** at
`2025-06-09T08:35:59.024Z`, with automation disabled, whether ML is included or not.
The requested April–July season does not extend the decision's acquisition cutoff.
This retrospective demo is not evidence of an operational decision made in 2025.

Future supervised learning requires independently validated ground-truth labels
from verified field/agronomist observations and calibrated IoT, matched to EO,
temporal and weather features with a suitable validation protocol. Neither labels
nor supervised ML, ingestion, weather APIs, downloads, backend or Stage 5B are
implemented here. Stages 1–4.6 and Stage 5A remain unchanged.

Run contract tests alone, or the complete scientific regression suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_product_contract.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Contract tests exercise invalid inputs, calibration/freshness/spatial relevance,
all 128 usable/unusable source combinations across the permitted decisions and
all use cases/modes (2,304 result scenarios), ML decision invariance, deterministic
serialization, presentation rules, the real Konya artifacts and unchanged prior
outputs/frontend. Existing real local artifacts are required for integration tests;
missing data is never downloaded or replaced with synthetic production evidence.

## Stage 5A – Modern UI Shell

The independent Next.js frontend in [`dashboard/`](dashboard/README.md) introduces
the **AgriPulse-813** identity by **Beyond The Limit**, an interactive Earth globe,
Konya scene selection, and Farmer / Expert workspace shells. **All analysis areas
are clearly labeled placeholders**; no Stage 1–4.5 output is read by the UI.
Konya, Turkey is the current validated demo scene. Syria and the Arab region are
the target deployment context, with no validated regional analysis in this demo.

From the repository root (Node.js 20.9 or newer):

```powershell
Set-Location .\dashboard
npm.cmd ci
npm.cmd run dev
```

Open **http://127.0.0.1:3000**. On macOS/Linux, use `npm` instead of `npm.cmd`.
The frontend uses Next.js, TypeScript, Tailwind CSS, Framer Motion, and
react-globe.gl. Production run instructions are in the [frontend README](dashboard/README.md).
Real scientific-output integration and evidence visualizations are deferred to
Stage 5B. Stage 5A adds no API, authentication, database, IoT, ML, or irrigation controls.

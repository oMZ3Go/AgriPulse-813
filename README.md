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
**Ground sensors and temporal Sentinel-2 evidence will be used later to increase
confidence.** They are not implemented here; no ground-truth labels, supervised
model, time-series pipeline, dashboard, API or IoT component is introduced.

Run the tests after generating the real Phase 1 and Phase 2 outputs:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use the actual local Tanager scene, check the Phase 1 refactor, score bounds,
exclusions, invalid evidence, finite statistics, class percentages, ties,
configurable screening and reconstruction of scores from saved pixel evidence.

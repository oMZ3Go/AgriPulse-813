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

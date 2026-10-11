# Compact real submission inputs

These are real measurements from the validated **Konya / Çumra, Türkiye** workflow,
not synthetic data. They demonstrate reproducibility of the workflow on a subset.
**Compact sample calculations are distinct from the validated full-scene product
decision**, which the notebook loads from `examples/product_contract_konya.json`
and the committed Konya evidence package. Sample ranks, quantiles and ML scores
are not claimed to equal the full-scene results.

## Source and attribution

- Tanager scene: `20250608_091605_90_4001`.
- Acquisition: `2025-06-08T09:16:05.903891Z`.
- BBox: `[32.44227196464563, 37.51375341016496, 32.70580618046614, 37.69491765950834]`.
- Raw asset: `20250608_091605_90_4001_ortho_sr_hdf5.h5`.
- Raw SHA-256: `f3115eb5eb3fe5355326e81a4041e08f060887f1d4264ed810df19f4de08e53a`.
- Planet Labs PBC, **CC-BY-4.0**, as recorded in the verified project STAC/Stage 1
  metadata. The sample is a selected subset, not a complete scene.
- Sentinel-2: Copernicus / ESA, processed through Microsoft Planetary Computer
  by the existing Stage 3 workflow, using Level-2A reflectance (`sentinel-2-l2a`).
  The checksum-verified local catalog links the Sentinel Data Legal Notice;
  its exact terms and required attribution wording are not stored locally.
  The Tanager CC-BY-4.0 statement above does not establish a Sentinel licence.
- Reference notebooks: Dr. Vincent Markiet / Space42, as credited in both original
  notebooks. A separate licence for their code has not been verified locally.
  See the [public licence and attribution section](../../README.md#data-and-third-party-attribution)
  for the remaining source-permission details.

The complete raw Tanager asset is **902,991,290 bytes** (approximately 903 MB) and
is excluded to keep the repository compact. No raw Sentinel cache, restricted
imagery or credentials are included. The notebook never opens the raw source.

## `tanager_sample.npz`

**1,767,291 bytes**, containing **2,048 pixels × 240 bands**.
The exporter calls the original `ml.load_inputs` / `stress.load_phase1_inputs`
loaders to verify raw HDF5 size/checksum, STAC checksum, Stage 1/2 lineage and masks.
The saved `outputs/ml/ml_summary.json` and `anomaly_pixel_evidence.npz` supply
the validated retained bands and ML eligibility. Existing evidence arrays do not
contain individual reflectance spectra, so those values are read from the verified
HDF5 `HDFEOS/GRIDS/HYP/Data Fields/surface_reflectance` dataset.

Selection is uniform without replacement from the sorted **359,001 quality-valid
source pixel indices**, using NumPy `Generator(PCG64(813))`, sample size 2,048,
then sorting the chosen indices. There is no risk-class stratification. The original
mask requires nodata/cloud/cirrus flags to be zero. All 2,048 sampled pixels are
therefore quality-valid; this sample cannot reproduce full-image quality coverage.

The original NDVI ≥ 0.30 screen retains **584 sampled vegetation pixels** with
all three indices finite. All 584 also have complete eligible spectra for ML.
The 1,464 remaining pixels are background/below-screen, not assigned a risk score.

Load with `numpy.load(path, allow_pickle=False)`:

| Array | Meaning |
| --- | --- |
| `spectra` | `(2048, 240)` physical source float32 reflectances, unchanged; not an image grid |
| `wavelength_nm` | Exact STAC band centers, 401.29–1697.65 nm |
| `source_band_indices` | Original zero-based HDF5 band indices |
| `red`, `red_edge`, `nir`, `swir` | Four selected reflectance vectors promoted to float64; invalids masked following the original reader |
| `valid_mask` | Original official quality mask at sampled pixels |
| `vegetation_mask` | Quality-valid finite NDVI ≥ 0.30 |
| `ml_eligible_mask` | Finite-index vegetation with finite, nonnegative, non-nodata reflectances in every retained band |
| `source_flat_indices`, `source_shape` | Original pixel identity on the `(673, 776)` source grid; no field boundaries/georeferenced export |
| `scene_id` | Source scene identifier |

Exact index centers: red **665.87**, red edge **705.92**, NIR **861.26**, SWIR
**1647.66 nm**. All wavelengths are stored individually. The 240 retained Stage 4.6
bands exclude the **20 centers within 1350–1450 nm inclusive** from the 260-band
compatibility window. Original source invalids are preserved in `spectra` and are
excluded by ML eligibility, not imputed. No clipping, smoothing, synthetic values
or sensor-response simulation is performed.

The source pixels are **noncontiguous**. Plot distributions and scatter plots,
not a fake spatial map. The notebook's N × 1 shape adapter exists only to call the
unchanged Stage 2 API.

## `sentinel_timeseries_sample.csv`

**44 real daily observations; 18,204 bytes** (LF representation), copied from
`outputs/sentinel/sentinel_timeseries.csv`. Original fields/values are preserved
and checked against `outputs/sentinel/sentinel_timeseries.json`. No temporal
subsampling or random seed is needed. Missing/rejected dates are not manufactured.
Scene IDs, representative/all source timestamps, cloud metadata, valid/vegetation
counts, footprint coverage and NDVI/NDRE/NDMI median/P25/P75 fields are retained.

Added fields:

- `eligible_at_decision_cutoff`: every listed source acquisition is at or before
  **2025-06-09T08:35:59.024Z**. There are **19** eligible observations.
- `after_decision_cutoff`: at least one acquisition is later; the entire daily
  mosaic is excluded from decision-time evidence. There are **25** later observations.
- `operational_availability`: `not_established` for all rows. These flags establish
  acquisition-time eligibility, not historical publication/processing availability.

The original CSV aligns source timestamps with source IDs, whereas its companion
JSON sorts the aggregate timestamp list. The exporter checks the same timestamp
collection without changing CSV order. The full April–July season is retrospective.
Later June/July observations **do not justify the June decision**. Spatial P25/P75
is dispersion among that day's vegetation pixels, not a confidence interval.

## `provenance.json` and regeneration

The manifest records input artifact names and original SHA-256 hashes, selection,
sample populations, exclusions, wavelengths, license, cutoff semantics and sample
hashes. Original hashes identify the maintainer's source bytes; those large/local
files are not notebook dependencies. Exported text uses UTF-8/LF; verification
tolerates CRLF conversion of the CSV, and validated JSON comparisons are semantic.

Evaluators run `python scripts/execute_submission_notebook.py` from the repository
root after installing `requirements.txt`. They do **not** run the exporter.

Maintainers with the already validated local artifacts may regenerate/check with:

```text
python scripts/export_submission_sample.py
python scripts/export_submission_sample.py --check
```

The exporter uses existing raw-data configuration only for regeneration, stops
if real inputs are missing/mismatched, never downloads substitutes and writes only
the compact NPZ, CSV and provenance manifest. The notebook has no dependency on
raw-data environment configuration. ZIP members have fixed timestamps and ordering.

Sample SHA-256 values (CSV hash uses LF):

```text
tanager_sample.npz
c222b82b6f2a937b3368151853abf06e1e4754a8c992009a0fface1a07e30e50
sentinel_timeseries_sample.csv
42769ff42ad76f0469376cf44f54bab091e149bb8654b6a3306be457dac30e4a
```

## Interpretation

The complete original pipeline gives **EO_ENHANCED**, **RELATIVE_HOTSPOTS_PRESENT**,
**NEUTRAL_OR_MIXED** temporal evidence and **UNAVAILABLE** ground evidence, leading
to **GROUND_VERIFICATION_REQUIRED** with **automation_allowed: false**.
Experimental spectral anomaly ML is complementary and does not change that decision.
Neither subset calculations nor full-scene evidence establishes drought probability,
disease diagnosis, crop-failure prediction, calibrated confidence or ground truth.

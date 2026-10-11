# Submission Stage A — reproducible notebook and real compact sample

Verification date: **2026-10-11**. Project: **AgriPulse-813**. Team:
**Beyond The Limit**, Syria. Theme: Precision Agriculture & Crop Intelligence.
Tagline: *From spectral signals to grounded decisions.*

The submission notebook executes end-to-end using repository inputs only, with
visible outputs, no external network access and no raw satellite files. The final
fresh-kernel run took **4.207 seconds**, including kernel startup and shutdown,
on **CPython 3.14.0, Windows x86-64**. **GPU required: NO**.

**Scientific Stages 1–4.7, their existing outputs, the committed product contract,
references and Stage 5C frontend were not modified. No commit or push was made.**

## 1. Created and modified files

Created:

| File | Role |
| --- | --- |
| `notebooks/AgriPulse_813_PoC.ipynb` | Executed English notebook, 26 cells: 16 Markdown and 10 code |
| `data/sample_input/tanager_sample.npz` | Real selected Tanager reflectance spectra, band vectors, masks and pixel identity |
| `data/sample_input/sentinel_timeseries_sample.csv` | Real Stage 3 observations with acquisition-cutoff flags |
| `data/sample_input/provenance.json` | Source hashes, selection method, license, exclusions and sample checksums |
| `data/sample_input/README.md` | Sample schema, provenance, limitations and regeneration instructions |
| `results/example_output.png` | Four-panel scientific figure with separate validated decision footer |
| `results/example_summary.json` | Separate compact calculations and authoritative full-scene result |
| `scripts/export_submission_sample.py` | Deterministic maintainer-only export from verified local real artifacts |
| `scripts/submission_workflow.py` | Notebook validation, offline guard, visualization and summary helpers |
| `scripts/execute_submission_notebook.py` | Fresh-kernel nbclient execution, output verification and runtime measurement |
| `tests/test_submission.py` | 13 focused real-data, portability and reproducibility tests |
| `SUBMISSION_STAGE_A_REPORT.md` | This report |

Modified:

- `README.md`: evaluator entrypoint, execution commands, embedded figure,
  team identity, sample/full-scene distinction and scientific caution.
- `requirements.txt`: six pinned notebook dependencies; all original pins retained.
- `.gitignore`: one narrow exception for `data/sample_input/tanager_sample.npz`.
  General NPZ/raw imagery/cache/checkpoint exclusions remain active.
- `scripts/export_dashboard.py`: cross-platform JSON export checks tolerate only
  CRLF/LF transport differences; binary export checks remain byte-strict.
- `tests/test_dashboard_export.py`: four regression tests for LF/CRLF acceptance
  and rejection of JSON/PNG changes.

The cross-platform follow-up edits only the exporter, its tests and this report.
The required notebook re-execution also refreshes its stored execution output;
all notebook cell sources are unchanged. Both example result files regenerate
byte-identically to their pre-fix versions.

Local verification logs, HTML preview and runtime receipts are ignored under
`outputs/submission_verification/`; they are not submission inputs or Git additions.

## 2. Exact Tanager provenance

Scene **20250608_091605_90_4001**, acquired **2025-06-08T09:16:05.903891Z**,
**Konya / Çumra, Türkiye**. BBox:
`[32.44227196464563, 37.51375341016496, 32.70580618046614, 37.69491765950834]`.

Raw asset: `20250608_091605_90_4001_ortho_sr_hdf5.h5`, **902,991,290 bytes**.
SHA-256: `f3115eb5eb3fe5355326e81a4041e08f060887f1d4264ed810df19f4de08e53a`.
Reflectance dataset: `HDFEOS/GRIDS/HYP/Data Fields/surface_reflectance`.
The raw file remains outside the submission.

The exporter reuses `ml.load_inputs` and `stress.load_phase1_inputs`, which verify
the HDF5 size/hash, STAC checksum, selected bands, scene metadata, Stage 1/2 lineage
and masks. `outputs/ml/ml_summary.json` and
`outputs/ml/anomaly_pixel_evidence.npz` supply retained spectral bands and verified
eligible-pixel membership. The existing evidence NPZ files hold masks/indices/scores,
not individual spectra; selected reflectance values are therefore read directly
from the verified raw file. No full hyperspectral cube is loaded into memory.

Additional original artifacts are `outputs/tanager/scene_summary.json`,
`outputs/stress/stress_summary.json`, `outputs/stress/pixel_evidence.npz` and the
scene's saved STAC JSON. Exact hashes for all source artifacts are preserved in
`data/sample_input/provenance.json`. Original raw data is required only by the
maintainer exporter, never by notebook execution.

Attribution/license: **Planet Labs PBC, CC-BY-4.0**, recorded in the validated source
metadata. The distributed sample is a selected subset. Reference notebooks:
Dr. Vincent Markiet / Space42.

## 3. Exact Sentinel provenance

`sentinel_timeseries_sample.csv` preserves all original fields and values from
`outputs/sentinel/sentinel_timeseries.csv`, checked against
`outputs/sentinel/sentinel_timeseries.json` for dates, acquisition timestamps and
NDVI/NDRE/NDMI median/P25/P75 values.

Original CSV SHA-256:
`9b9ba896c8b54d90938dd95fb07d7fe5252adb55bea1a481a0501e344644656b`.
Original JSON SHA-256:
`a028e224a8b3e39b58c9490513a3c1c91ea413097f7f0932f5ada20b36206a7b`.

There are **44 real retained daily observations**, **2025-04-07 through 2025-07-31**.
The sample retains source scene IDs, all acquisition times, cloud metadata,
coverage/counts and index statistics. No missing observations are fabricated.
Copernicus / ESA Sentinel-2 data were processed by the existing Stage 3 workflow
through Microsoft Planetary Computer. No network query is performed here.

CSV acquisition lists retain source-ID order; JSON aggregate acquisition lists
are sorted. The exporter validates the same timestamp collection without changing
the original CSV order.

## 4. Sample sizes and selection

| Artifact | Bytes | Content |
| --- | ---: | --- |
| `tanager_sample.npz` | 1,767,291 | 2,048 real pixels × 240 retained bands |
| `sentinel_timeseries_sample.csv` | 18,204 | 44 data rows plus header, LF representation |
| `provenance.json` | 3,988 | Compact manifest and source hashes |
| `example_output.png` | 356,916 | 2,100 × 1,650 pixels |
| `example_summary.json` | 17,731 | Finite structured output; no confidence percentages |

The notebook is approximately **504 KB**, including its embedded figure.

Tanager selection: sorted quality-valid source flat indices, uniform choice
without replacement using **NumPy Generator(PCG64(813))**, count **2,048**, then
sort the selected indices. Source population: **359,001 quality-valid pixels**.
There is no Stage 2 risk-class stratification or balancing by crop/field.
All sampled pixels are quality-valid; **584** pass the NDVI vegetation screen,
have all three indices finite and have complete ML spectra. The other **1,464**
are background/below-screen. Sample quality coverage is not full-image coverage.

Spectra preserve source float32 values. Four selected bands are promoted to
float64 and masked using the original reader's invalid-value rules. Exact centers:
red **665.87**, red edge **705.92**, NIR **861.26**, SWIR **1647.66 nm**.
All 240 band centers are stored in the NPZ, spanning **401.29–1697.65 nm**.
The 20 bands in **1350–1450 nm inclusive** remain excluded. No smoothing,
interpolation, clipping, imputation or synthetic fallback is used.

The NPZ stores source flat indices and the original **673 × 776** image shape.
Samples are noncontiguous; no fake spatial map is produced.

## 5. Notebook structure and scientific reuse

The title/identity cell is followed by these 15 English sections:

1. Project purpose.
2. Scientific interpretation and caution.
3. Reproducibility setup.
4. Data provenance.
5. Load the compact real Tanager sample.
6. Calculate NDVI, NDRE and NDMI.
7. Reproduce representative relative spectral screening.
8. Load Sentinel-2 temporal context.
9. Separate decision-time and retrospective observations.
10. Compact Experimental Spectral Anomaly ML.
11. Load the validated full-scene product contract.
12. Generate the example scientific figure.
13. Generate the structured example summary.
14. Interpret the result.
15. Limitations.

The notebook calls the unchanged authoritative functions:
`tanager.compute_indices`, `stress.assess_stress`, `sentinel.robust_trend` and
`ml.fit_anomaly`. Submission helpers handle input verification and presentation;
they do not replace scientific formulas or select a new product decision.

## 6. Stage 2 representation

The original **NDVI ≥ 0.30** screen, finite-index eligibility, tie-aware empirical
ranks, class boundaries and NDMI-driven score are preserved. NDVI/NDRE remain
supporting modifiers. The N × 1 adapter satisfies the original 2-D API and is
explicitly not a map. Sample vegetation ranks/quantiles are not claimed to equal
full-scene ranks/quantiles. Class counts are sample descriptions, not drought
prevalence. Unassessed pixels do not receive a zero/Low score.

## 7. Stage 3 cutoff handling

Cutoff: **2025-06-09T08:35:59.024Z**. Every listed source acquisition of a daily
mosaic must be at or before that instant. Straddling mosaics are excluded in full.
There are **19 eligible** and **25 later retrospective** dates. The notebook
reproduces all three decision-time trends with the original Stage 3 function and
checks exact equality to the saved Konya temporal package.

The CSV adds `eligible_at_decision_cutoff`, `after_decision_cutoff` and
`operational_availability`. The last is `not_established`, explicitly distinguishing
acquisition-time eligibility from historical publication/processing availability.
Later June/July observations do not justify the June decision. Plot shading is
spatial P25/P75, not confidence intervals.

Validated temporal meaning remains **NEUTRAL_OR_MIXED**. Near-Tanager NDMI is
approximately **0.00691235 index units above** the saved short-baseline median;
it does not demonstrate a strong broad moisture decline or exclude local stress.

## 8. Stage 4.6 representation

The original **StandardScaler → PCA → IsolationForest** function receives only
the **584 × 240** eligible reflectance matrix, never Stage 2 risk labels.
`random_state=813`, full-SVD PCA retaining 99% of standardized fitting variance,
200 isolation trees, `max_samples=256`, and one computation thread are unchanged.
The 1350–1450 nm atmospheric-caution exclusion is preserved.

Scores mean spectrally unusual vegetation relative to this sample. They are
neither probabilities nor drought/disease/crop-failure diagnoses. Training and
scoring are within-sample, exploratory and unsupervised; no supervised model,
accuracy claim or predictive validation is introduced. ML does not affect Stage 4.

## 9. Compact calculations versus authoritative truth

The notebook, sample README, figure and structured output explicitly separate
subset calculations from the validated full-scene decision. The notebook loads
`examples/product_contract_konya.json`, checks the committed Konya contract copy,
and reads the existing fusion/temporal JSON package. It does not recompute the
decision from sampled spectra.

| Validated field | Unchanged value |
| --- | --- |
| Analysis level | `EO_ENHANCED` |
| Spectral evidence | `RELATIVE_HOTSPOTS_PRESENT` |
| Temporal evidence | `NEUTRAL_OR_MIXED` |
| Ground evidence | `UNAVAILABLE` |
| Decision | `GROUND_VERIFICATION_REQUIRED` |
| Automation allowed | `false` |
| Experimental ML | Available, complementary, not used to change the decision |

## 10. Example outputs

The PNG contains an NDVI histogram, NDMI-versus-relative-screening scatter plot,
Sentinel NDMI context separated at the cutoff, and an anomaly-score histogram.
Panels A/B/D are explicitly compact-sample calculations; the footer separately
labels the validated full-scene decision and disabled automatic intervention.
The generated figure was visually inspected; labels and footer are readable.

The JSON includes project/team/theme, scene/date/location, sample provenance and
counts, screening statistics, ML interpretation, temporal handling, cautions and
limitations. `compact_sample_calculations` and `validated_full_scene_result` are
separate objects. Contract hashes are canonical JSON hashes, avoiding checkout
newline dependence. Runtime is excluded from deterministic scientific output.

## 11. Dependencies and environment

All existing scientific pins remain unchanged. Added:

```text
nbformat==5.11.1
nbclient==0.11.0
nbconvert==7.17.1
ipykernel==7.4.0
ipython==9.17.1
jupyter-client==8.10.0
```

These support notebook validation, fresh-kernel execution, optional HTML rendering,
the kernel and visible displays. No pandas, GPU stack or umbrella Jupyter server
dependency was added. `pip check` passed. This is a direct dependency list, not a
blind `pip freeze`; transitive packages are not a complete platform lockfile.
Scientific compatibility risk is minimized by preserving the validated pins.

The notebook was executed on **Python 3.14.0**. Windows execution was tested;
Linux/macOS paths are supported by the implementation but were not executed on
those operating systems in this session.

## 12. Execution and test results

- Final repository notebook: **4.207 seconds**, 26 cells, all **10 code cells**
  executed in order, zero cell failures, embedded PNG visible, both result files generated.
- Original Stage A isolated-copy runs: **4.309 and 3.850 seconds**, from repository root
  and `notebooks/`, each using a fresh kernel and an absent raw-data path.
- Isolated copies contained only submission inputs and source files: no raw data,
  prior `outputs/`, preexisting result files, dashboard server or Node installation.
- Offline guards rejected an external DNS request and a raw-file open. Local
  Jupyter kernel IPC is allowed; it is not an external service dependency.
- `nbformat` validation passed and `nbconvert` HTML rendering succeeded.
- **13/13 submission tests passed**: real provenance and size, deterministic
  archive/membership, missing-source failure, source-index fidelity, unsupervised
  ML determinism, real temporal fidelity, straddling cutoff, line endings,
  portable executed notebook/pins, authoritative truth, package semantics and
  two clean offline kernel runs.
- **121/121 existing scientific tests passed**: Stage 2 (12), Stage 3 (10),
  Stage 4 fusion (22), Stage 4.5 spectral (13), Stage 4.6 ML (22), Stage 4.7 contract (42).
- Dashboard export tests: **12/12 passed**, including four new regressions.
- Final complete discovery with `.\.venv\Scripts\python.exe -m pytest`:
  **146 passed, zero failures/errors**, **79.02 seconds**. Two non-failing warnings
  concern a dependency's Pydantic deprecation and the existing pytest cache path.

The previous `Stale or missing export: contract.json` error came solely from
Windows newline transport with `core.autocrlf=true`: the unchanged working-tree
contract has **4,221 bytes, 91 CRLF sequences**, while generated LF JSON has
**4,130 bytes, 91 LF characters**. All nine JSON documents differ only by LF/CRLF.

The fix is confined to `export(..., check=True)`: for `.json` artifacts only,
compare `actual.replace(b"\r\n", b"\n")` with
`expected.replace(b"\r\n", b"\n")`. No JSON decoding, reformatting or
re-serialization is used for this check. Export generation and existing
missing/unexpected-file checks are unchanged. PNG and all other non-JSON bytes
remain strictly compared. The saved package is never rewritten by a check.

Four new tests explicitly accept LF JSON and equivalent CRLF JSON without writes,
reject changed decisions, extra spaces and bare carriage returns, and reject
both a changed PNG byte and newline normalization applied to binary PNG data.
Existing tamper detection remains intact. The real-package exporter `--check`
now passes for all **19 files**, including ten unchanged PNGs.
No protected file, `.gitattributes` or Git newline configuration was changed.

## 13. Determinism

The exporter was run successfully twice (write, then `--check`), regenerating NPZ,
CSV and manifest from the real source. All three hashes matched. ZIP member order,
timestamps, compression settings and numeric byte order are fixed.

| Artifact | SHA-256 |
| --- | --- |
| `tanager_sample.npz` | `c222b82b6f2a937b3368151853abf06e1e4754a8c992009a0fface1a07e30e50` |
| `sentinel_timeseries_sample.csv` (LF) | `42769ff42ad76f0469376cf44f54bab091e149bb8654b6a3306be457dac30e4a` |
| `provenance.json` (LF) | `adcffab85572370870723b8f93eeeb59e0c82706d546167584377ee99eeb195a` |

Independent clean-kernel runs produced byte-identical structured result JSON,
also semantically equal to the repository result. Repeated original ML calls
produced identical scores. Exact PNG bytes are not a cross-platform requirement;
fonts, numerical libraries and hardware may change rendering or floating-point
values. Notebook timing text intentionally varies between runs.

## 14. Repository size, credentials and protected-file audit

The 12 new submission files total approximately **2.74 MB**, including the executed
notebook, documentation and helpers. The largest is the **1.77 MB** NPZ.
No Git candidate file is 10 MB or larger. No raw HDF5/raster, Sentinel cache,
`.env`, credentials, API tokens, private keys, notebook checkpoints, `__pycache__`
or temporary verification file enters the proposed changes. Credential-pattern
checks of new/modified text found no credentials. NPZ members contain numeric,
boolean and scene-ID arrays only; loading requires no pickle.

An initial SHA-256 snapshot covered **124 protected files**, including scientific
modules, existing output artifacts, product contract, references and tracked
frontend files. Final comparison found **zero changes**. All Git changes remain
unstaged. `git diff --check` passes. No commit or push was made.
This same 124-file baseline was rechecked after the cross-platform fix and
notebook execution: **124/124 hashes match**. The validated decision remains
`GROUND_VERIFICATION_REQUIRED`, automation stays disabled, and ML remains
complementary only. The notebook's cell sources and the example PNG/JSON hashes
also match their pre-fix versions.

## 15. Limitations and reproducibility commands

This is reproducibility of a compact workflow, not exact reconstruction of every
full-scene statistic. Uniform pixel sampling is not field/crop balancing. Shared
indices, screening, changing Sentinel coverage and atmosphere/phenology/soil/canopy
effects limit interpretation. No ground truth, disease diagnosis, drought
probability, crop-failure prediction or calibrated confidence is supplied. The
short seasonal baseline is not a climatology. Historical operational availability
is unknown. Independent ground evidence is required before intervention.

Fresh clone, from the repository root:

```text
python -m venv .venv
```

Activate on PowerShell with `.\.venv\Scripts\Activate.ps1` or on Linux/macOS with
`source .venv/bin/activate`, then:

```text
python -m pip install -r requirements.txt
python scripts/execute_submission_notebook.py
python -m unittest discover -s tests -p test_submission.py -v
```

Dependency installation needs package access; the notebook itself runs offline.
Two maintainer-only submission checks skip if original local outputs are absent;
the notebook integration and bundled sample checks still run. The complete old
scientific integration suite requires the original local data, as before.

Maintainer export verification (original real source data required):

```text
python scripts/export_submission_sample.py --check
```

Final session commands also included:

```text
python -m unittest discover -s tests -v
python scripts/execute_submission_notebook.py --report outputs/submission_verification/execution_final.json
python -m pytest
python scripts/execute_submission_notebook.py
python scripts/export_dashboard.py --check
python -m pip check
git diff --check
git status --short --untracked-files=all
```

Final Git state: branch `main` tracks `origin/main`; **5 modified existing files**
and **12 untracked submission files**, exactly those listed above. No staged
changes, commit or push. Work stops at Submission Stage A.

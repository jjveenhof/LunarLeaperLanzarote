# GPR Session

BEFORE ANYTHING ELSE: read QandA.md in this directory.

This file is loaded by sessions opened in Code/GPR/. The root CLAUDE.md
(loaded automatically alongside this) covers the overall project structure,
CRS, environment, and working conventions. The project root "Thesis Lunar Leaper"
is two levels up; data and results paths below are relative to the project root.

At the start of each session, read QandA.md in this directory for pending questions or
tasks. Any session (supervisor, Grav, QGIS) can write here -- entries are tagged
`From: [session] -> GPR`. To ask another session something, write into their QandA.md.
Delete entries from your own QandA.md once resolved.

## Pipeline

Processing order inside `apply_processing` (gpr_processing.py):

1. **Normalisation** (tracewise-rms-window) -- equalises trace amplitudes using RMS
   computed within a user-defined time window (in ns), then scales the full trace.
   Controlled by `normalize`, `norm_start_ns`, `norm_end_ns`.
2. **Dewow** -- running-mean DC removal. `dewow_window` (samples).
3. **Time-zero shift + trim** -- shifts data along time axis, trims trailing zeros.
   `tzero_shift` (samples, can be fractional).
4. **Max-time crop** -- discards samples after `max_time_ns` (ns).
5. **Spectral whitening** -- smoothed: divides spectrum by uniform_filter1d(|spec|, size=N).
   `whiten_window` (bins); 0 = off. Window=1 = pure whitening (identity filter).
   Applied before bandpass so the bandpass sets the final frequency extent.
6. **Bandpass** -- 4th-order Butterworth. `bandpass_low` / `bandpass_high` (MHz).
7. **SVD removal** -- removes first N singular vectors (horizontal coherent noise).
   `n_svd` (int); 0 = off. Interacts with whitening -- use both with care.
8. **Gain** -- linear time-varying gain. `gain_exponent` (float); 0 = off.

Batch processing (all profiles with saved params):
    python run_pipeline.py
    python run_pipeline.py Line2_100MHz   # single profile

run_pipeline.py reads `_params.json` written by GPRProcessing.ipynb, applies
apply_processing, saves `_processed.npz`, then calls topo_correction.py.

## Key Files

| File | Purpose |
|---|---|
| `GPRProcessing.ipynb` | Interactive notebook: load, tune, inspect, save params |
| `gpr_processing.py` | Core `apply_processing` function -- shared by notebook + run_pipeline |
| `run_pipeline.py` | Batch re-process all profiles using saved `_params.json` |
| `topo_correction.py` | Static topo correction using GNSS; reads `_processed.npz` |
| `plot_dual_freq.py` | Side-by-side comparison of 50 MHz vs 100 MHz for the same line |
| `GPRFieldVisual.ipynb` | Field visualisation notebook (separate from processing) |
| `tests/test_normalisation.py` | Verifies tracewise-rms-window window behaviour with synthetic data |
| `tests/test_topo_correction.py` | Tests for topo_correction.py |

Data paths (relative to project root):
- Raw stitched input: `Data/GPR/Stitched/{stem}_raw.npz` + `_raw.json` sidecar
- Saved params: `Data/GPR/Processed/{stem}_params.json`
- Processed output: `Data/GPR/Processed/{stem}_processed.npz`
- Topo-corrected: `Data/GPR/Topo/{stem}_topo.npz` + `_topo.png`
- Results plots: `Results/GPR/Topo/`

External dependency: `georadar-data-processing` (gdp) library located at
`Other data and scripts/Tube X/GPR/scripts/georadar-data-processing/`.
Scripts add this to sys.path at runtime; do not move it.

## Conventions

(ASCII-only scripts and the conda Python path are in the root CLAUDE.md.)

- Processing params are stored as JSON (`_params.json`) alongside processed data.
  The notebook writes them; run_pipeline.py reads them. This is the canonical way
  to reproduce a result.
- Normalisation uses `tracewise-rms-window` (not `tracewise-rms`). The plain
  `tracewise-rms` type ignores the window parameter entirely -- confirmed by
  reading gdp source and a passing unit test.
- Whitening: only smoothed whitening (`whiten_window`) is exposed. Pure whitening
  was removed because `whiten_window=1` is equivalent and the separate bool caused
  silent conflicts.
- SVD and whitening can be used together but may interact in non-obvious ways;
  no hard block in code, just be mindful.
- Widget layout in GPRProcessing.ipynb: two-column HBox (pre-processing left,
  filter/gain right) to keep controls compact alongside plots.
- Colorbar in notebook radargram: `len=0.30, y=0.84` -- sized to row 1 only.

## Current Focus

Interactive processing notebook (GPRProcessing.ipynb) is the active work item.
Core processing pipeline is stable. Next steps:

- Tune processing parameters for each line, save `_params.json` per profile.
- Run `run_pipeline.py` once params are finalised to batch-produce processed + topo NPZs.
- Investigate absolute signal strength differences between lines/frequencies
  (normalised amplitude spectrum hides absolute levels -- compare raw RMS or
  unnormalised mean spectra to assess coupling quality per line).
- Line 2 100 MHz has spectral notches at ~75 and ~160 MHz (hardware artifact from
  pulsEKKO antenna housing geometry, not geology). No processing fix available --
  those frequency bins are dead. Note this in any results writeup.

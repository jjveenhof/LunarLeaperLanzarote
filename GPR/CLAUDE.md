# GPR Session

BEFORE ANYTHING ELSE: read QandA.md in this directory.

This file is loaded by sessions opened in Code/GPR/. The root CLAUDE.md
(loaded automatically alongside this) covers the overall project structure,
CRS, environment, and working conventions. The project root "Thesis Lunar Leaper"
is two levels up; data and results paths below are relative to the project root.

QandA.md entries directed here are tagged `From: [session] -> GPR`.

## Pipeline

Processing order inside `apply_processing` (gpr_processing.py):

0. **Polarity** -- global sign correcting the acquisition convention (the antenna
   Tx/Rx were sometimes swapped). `polarity` (+1/-1); baked into the saved NPZ.
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

**flip_x** -- applied after `apply_processing` in `run_pipeline.py` (and in the
notebook on preview); reverses the trace order so North is on the left. Stored in
`_params.json`; baked into `_processed.npz` and propagated automatically to topo
and migration outputs. Currently `true` for Line3_50/100MHz only (acquired S->N).

Gain is NOT a processing step -- it is display-only (`display_gain`), never baked
into saved NPZs. See Conventions.

Batch processing (all profiles with saved params):
    python run_pipeline.py                # all profiles + downstream plots
    python run_pipeline.py Line2_100MHz   # single profile + its downstream plots
    python run_pipeline.py --no-scans     # skip the slow velocity-scan HTMLs
    python run_pipeline.py --no-plots     # processing + topo only

run_pipeline.py reads `_params.json` written by GPRProcessing.ipynb, applies
apply_processing, saves `_processed.npz`, then calls topo_correction.py. After
processing it regenerates the deterministic downstream outputs (incl. HTML, so a
browser refresh shows current data):
- dual-freq topo PNGs (per line)
- for any profile with a stored `migration_velocity_mns` (+ `migration_gain`) in
  its params: the migrated NPZ/PNG and, when both freqs of a line carry a pick,
  the migrated dual-freq PNG
- the flowerpetal 3D HTML
- velocity-scan HTMLs (opt-out with `--no-scans` -- they are the interactive
  picking tool, slow to rebuild)

The interactive GPRProcessing.ipynb and the standalone multiples schematic
(plot_multiples_schematic.py, hardcoded geometry) are NOT part of the pipeline.

## Key Files

| File | Purpose |
|---|---|
| `GPRProcessing.ipynb` | Interactive notebook: load, tune, inspect, save params |
| `gpr_processing.py` | Core `apply_processing` function -- shared by notebook + run_pipeline |
| `run_pipeline.py` | Batch re-process all profiles using saved `_params.json` |
| `topo_correction.py` | Static topo correction using GNSS; reads `_processed.npz` |
| `plot_dual_freq.py` | Side-by-side comparison of 50 MHz vs 100 MHz for the same line; gain read from params JSON per panel |
| `migrate_velocity_scan.py` | Stolt migration velocity scan; outputs interactive HTML with N/S annotations |
| `plot_flowerpetal_3d.py` | 3D Plotly view of petals + Line 3 + LiDAR cave, draped on GNSS surface (reads `_processed.npz`, NOT topo) |
| `check_polarity.py` | Per-profile polarity convention check (mean-trace first break) |
| `compare_intersections.py` | Polarity cross-check at Line/petal crossings (trace overlay + xcorr) |
| `gpr_constants.py` | Shared constants (`V_DEFAULT` wave velocity) |
| `GPRFieldVisual.ipynb` | Field visualisation notebook (separate from processing) |
| `tests/test_normalisation.py` | Verifies tracewise-rms-window window behaviour with synthetic data |
| `tests/test_topo_correction.py` | Tests for topo_correction.py |

Data paths (relative to project root):
- Raw stitched input: `Data/GPR/Stitched/{stem}_raw.npz` + `_raw.json` sidecar
- Saved params: `Data/GPR/Processed/{stem}_params.json`
- Processed output: `Data/GPR/Processed/{stem}_processed.npz`
- Topo-corrected: `Data/GPR/Topo/{stem}_topo.npz` + `_topo.png`
- Results plots: `Results/GPR/Topo/`
- Dual-freq PNGs: `Results/GPR/DualFreq/`
- Migration HTMLs: `Results/GPR/Migration/`

External dependency: `georadar-data-processing` (gdp) library located at
`Other data and scripts/Tube X/GPR/scripts/georadar-data-processing/`.
Scripts add this to sys.path at runtime; do not move it.

## Conventions

(ASCII-only scripts and the conda Python path are in the root CLAUDE.md.)

- Processing params are stored as JSON (`_params.json`) alongside processed data.
  The notebook writes them; run_pipeline.py reads them. This is the canonical way
  to reproduce a result.
- The migration pick is stored in params (`migration_velocity_mns`, `migration_gain`)
  so run_pipeline.py can re-migrate reproducibly. The picking itself is manual (read
  the velocity-scan HTML); once settled, add these two fields to make it pipeline-driven.
  Currently set on Line3_50/100MHz (v=0.125, gain 2.5). Depth-below-surface picks are
  recorded in `Data/GPR/Migration/tube_picks.csv` (air-gap corrected for the floor).
- Gain is display-only: NPZs store raw, un-gained amplitudes; `gain_exponent` in
  params records the intended display gain. Applied at render via `display_gain()`:
  notebook view slider, topo PNG (auto from params), `plot_dual_freq.py` (auto from
  params per panel; `--gain` overrides both), and `plot_flowerpetal_3d.py` interactive
  gain slider (`--gain` sets the initial one).
- Polarity is harmonised to the FlowerPetals (an arbitrary reference -- Tx/Rx
  swaps flip the sign, so there is no physically-correct one). `polarity: -1` in
  params negates a profile and is BAKED into the NPZ (unlike gain). Currently -1 on
  Line2_50MHz, Line3_50/100MHz, Line5_50/100MHz; +1 on the petals + Line2_100MHz.
  check_polarity.py verifies; re-run it after any reprocessing.
- Orientation convention: North on the left in all output plots. Controlled by
  `flip_x` in params. N/S labels are added by the output scripts (topo PNGs,
  migration HTMLs, dual-freq PNGs) -- NOT in the notebook (notebook has no
  geographic context). Line 3 is the only profile that needs flipping.
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
- `plot_flowerpetal_3d.py` drapes each trace at its GNSS elevation (Z = elev - depth).
  This positioning IS the topo correction -- equivalent to topo_correction.py's static
  shift but it keeps real surface relief, so it uses `_processed.npz`, not topo data.

## Current Focus

Processing pipeline, topo correction, draped 3D viz, and Stolt migration velocity
scan are all stable. Polarity is harmonised; North-left orientation convention is
enforced via `flip_x`. Active work: determining GPR velocity from the data itself
(diffraction / migration velocity analysis), validated blind against the LiDAR --
avoid calibrating velocity on the LiDAR (inverse crime for the lunar-analog argument).

- Line 2 100 MHz has spectral notches at ~75 and ~160 MHz (hardware artifact from
  pulsEKKO antenna housing geometry, not geology). No processing fix available --
  those frequency bins are dead. Note this in any results writeup.

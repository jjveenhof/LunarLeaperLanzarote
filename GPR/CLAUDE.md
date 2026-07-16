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
- for any profile flagged `migrate: true` in its params: the migrated NPZ/PNG
  (migrated at its `velocity`, with `migration_gain`) and, when both freqs of a
  line are flagged, the migrated dual-freq PNG
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
| `plot_dual_freq.py` | Stacked 50/100 MHz figure per line; migrated stage emits plain + `_picks`-annotated versions (tube_picks.csv; layout via `PICK_PANEL_CFG`); gain/clip/depth from params JSON |
| `plot_picks.py` | Single-frequency migrated sections with pick annotations (imports helpers from plot_dual_freq) |
| `plot_processing_steps.py` | Stacked one-panel-per-step figure (apply_processing `capture=`); default Line3_50MHz |
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
- Velocity is a single field `velocity` (m/ns). It is THE overburden-rock velocity
  -- topo correction and migration both read it, so they cannot drift apart. All
  profiles are currently 0.125.
- The migration pick is flagged with `migrate: true` (+ `migration_gain`) in params,
  so run_pipeline.py re-migrates the flagged profiles reproducibly at their
  `velocity`. The picking itself is manual (read the velocity-scan HTML); once you
  settle a velocity, set `velocity` to it and add `migrate: true` + `migration_gain`.
  Currently flagged on Line3_50/100MHz and Line5_50/100MHz (gain 2.5). Depth-below-
  surface picks live in `Data/GPR/Migration/tube_picks.csv` -- PICK-ONLY columns
  (line, ceiling, x_ceiling, floor_app, x_floor, notes); derived floor_real/cave
  height are computed by `plot_dual_freq.cave_geometry()` (v_air 0.3) and printed,
  not stored. L5 is ceiling-only, no floor reflector. Line 2 is intentionally not
  flagged (see Current Focus). Flower-petal migration is planned on straight
  sub-segments only. The notebook merges on save, so these pipeline-managed keys
  survive a re-save of the params from GPRProcessing.ipynb.
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

## Plot tuning: generate once, then ask -- never self-iterate
Claude CANNOT reliably judge whether a figure looks nice, is aligned, well spaced,
or the right text size. So do NOT try, and do NOT loop on appearance.
When making or adjusting a thesis plot:
  1. Generate the plot ONCE.
  2. STOP. Do not regenerate to chase a better look, and do not spend effort
     guessing what "should" be tuned -- you are bad at judging that.
  3. ASK the user what they want to tune (clip, aspect, text size, colours,
     spacing, ...).
  4. Add knobs for EXACTLY what the user names (module constant or CLI flag, with
     an inline comment on effect direction), regenerate ONCE, hand back.
Do NOT pre-expose every possible parameter -- add a knob only when asked. Re-run a
plot on your own ONLY for correctness (crash, wrong data, a value the user changed),
never to evaluate appearance. Processing is fast; the cost to avoid is Claude
deciding what to tune and iterating on its own taste.

## Current Focus

Processing pipeline, topo correction, draped 3D viz, and Stolt migration are all
stable. Velocity determination is DONE and SETTLED at v = 0.125 m/ns for BOTH lines
(L5 remigrated from its earlier 0.11 on 2026-07-16; diffraction collapse admits
0.10-0.13, one value chosen). Final picks: L3 ceiling 3.8 / floor_app 8.3 (real
14.6), L5 ceiling 8.6, in `tube_picks.csv`. Handed to the gravity inversion
(LINE_PRESETS updated 2026-07-16; Grav instructed via QandA to re-run everything).
NB: LiDAR may NOT be used to justify the velocity pick (blind-pick constraint) --
diffraction collapse is the only admissible evidence.

Active work: migrate the flower petals. Plan -- take reasonably straight sub-segments
of each petal and run them through the existing Stolt code, then 3D-plot the migrated
segments alongside the unmigrated draped sections. Full 3D migration is OUT OF SCOPE
for this thesis.

- Line 2 is deliberately NOT migrated (mixed results: fewest stacks, slack-tape
  positioning, and the 100 MHz spectral notches below). It stays a processed/topo
  profile only; no migration pick.
- Line 2 100 MHz has spectral notches at ~75 and ~160 MHz (hardware artifact from
  pulsEKKO antenna housing geometry, not geology). No processing fix available --
  those frequency bins are dead. Note this in any results writeup.

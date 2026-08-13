# GPR processing -- La Corona lava tube

GNSS-referenced GPR processing, topo correction, Stolt migration, and the 3-D draped
viewer for the La Corona survey. `DECISIONS.md` holds the choices the code cannot explain
on its own; thesis figure/table -> producer mapping is in `Code/TRACEABILITY.md`.

## Environment

Conda env `lacorona-lunarleaper-thesis`, built from `Code/environment.yml` one level up.
No `sys.path` setup is needed.

The one external dependency is **`georadar-data-processing`** (imported as `gdp`), a
public ETH package (LGPL v3) from `https://gitlab.com/pygp/georadar-data-processing`,
pinned by commit (517f008, 2026-03-20) in `environment.yml`. It is a normal pip install
and is imported directly. **You do not need the copy under
`Other data and scripts/Tube X/...`** -- that copy is stale and is not what imports at
runtime; the env's install wins. Only five functions are used, all from
`gpr_processing.py`: `dewow` and `filter_data` (`gdp.preprocessing.filtering`),
`normalize_data` (`gdp.preprocessing.normalizing`), `apply_gain` (`gdp.preprocessing.gain`),
`remove_svd` (`gdp.preprocessing.image_processing`).

## One command to regenerate everything deterministic

```
python run_all.py                 # run_pipeline + every standalone deterministic figure/QC script
python run_all.py --no-scans      # skip the slow interactive velocity-scan HTMLs
```

`run_all.py` prints the steps it CANNOT do -- see "Manual artifacts" below.

**Prerequisite:** the raw NPZs and `_params.json` already exist. They come from the
notebooks; `run_all` does not stitch or tune params, take the browser snapshots, or make
the velocity pick.

The core batch step is `run_pipeline.py`:

```
python run_pipeline.py                # all profiles + downstream plots
python run_pipeline.py Line2_100MHz   # single profile + its downstream plots
python run_pipeline.py --no-scans     # skip the slow velocity-scan HTMLs
python run_pipeline.py --no-plots     # processing + topo only
```

It reads the `_params.json` written by `GPRProcessing.ipynb`, applies `apply_processing`,
saves `_processed.npz`, then calls `topo_correction.py`. Afterwards it regenerates the
deterministic downstream outputs (including the HTMLs, so a browser refresh shows current
data): dual-freq topo PNGs per line; for any profile flagged `migrate: true`, the migrated
NPZ/PNG at its `velocity` and, when both frequencies of a line are flagged, the migrated
dual-freq PNG; the flower-petal 3-D HTML; and the velocity-scan HTMLs.

`GPRProcessing.ipynb` and the standalone `plot_multiples_schematic.py` (hardcoded geometry)
are not part of the pipeline.

## The processing chain

Order inside `apply_processing` (`gpr_processing.py`):

| # | Step | Controlled by |
|---|---|---|
| 0 | **Polarity** -- global sign fixing the acquisition convention (Tx/Rx were sometimes swapped). Baked into the saved NPZ. | `polarity` (+1/-1) |
| 1 | **Normalisation** (`tracewise-rms-window`) -- equalises trace amplitudes using RMS within a time window, then scales the full trace. | `normalize`, `norm_start_ns`, `norm_end_ns` |
| 2 | **Dewow** -- running-mean DC removal. | `dewow_window` (samples) |
| 3 | **Time-zero shift + trim** -- shifts along the time axis, trims trailing zeros. | `tzero_shift` (samples, may be fractional) |
| 4 | **Max-time crop** | `max_time_ns` |
| 5 | **Spectral whitening** -- divides the spectrum by `uniform_filter1d(abs(spec), size=N)`. Applied before bandpass so the bandpass sets the final frequency extent. | `whiten_window` (bins; 0 = off) |
| 6 | **Bandpass** -- 4th-order Butterworth. | `bandpass_low` / `bandpass_high` (MHz) |
| 7 | **SVD removal** -- removes the first N singular vectors (horizontal coherent noise). Interacts with whitening; use both with care. | `n_svd` (0 = off) |

`flip_x` is applied *after* `apply_processing`, in `run_pipeline.py`: it reverses trace
order so North ends up on the left. Stored in `_params.json`, baked into `_processed.npz`,
and propagated automatically to topo and migration outputs. Currently true for
Line3_50/100MHz only, which were acquired S->N.

Gain is **not** a processing step -- it is display-only and never baked into a saved NPZ.

## Conventions

- **Params are the reproduction unit.** `_params.json` sits alongside the processed data;
  the notebook writes it, `run_pipeline.py` reads it. This is the canonical way to
  reproduce a result.
- **Velocity is one field**, `velocity` (m/ns) -- THE overburden-rock velocity. Topo
  correction and migration both read it, so they cannot drift apart. All profiles are
  0.125.
- **Gain is display-only.** NPZs store raw, un-gained amplitudes; `gain_exponent` records
  the intended display gain, applied at render by `display_gain()` -- the notebook slider,
  the topo PNG, `plot_dual_freq.py` (per panel, `--gain` overrides), and the
  `plot_flowerpetal_3d.py` slider.
- **Polarity is harmonised to the FlowerPetals**, an arbitrary reference -- Tx/Rx swaps
  flip the sign, so there is no physically correct one. `polarity: -1` negates a profile
  and IS baked into the NPZ (unlike gain). Currently -1 on Line2_50MHz, Line3_50/100MHz
  and Line5_50/100MHz; +1 on the petals and Line2_100MHz. `check_polarity.py` verifies --
  re-run it after any reprocessing.
- **North on the left** in all output plots, via `flip_x`. N/S labels are added by the
  output scripts, not the notebook, which has no geographic context. Line 3 is the only
  profile needing a flip.
- **Normalisation must be `tracewise-rms-window`**, not `tracewise-rms`. The plain type
  ignores the window parameter entirely -- confirmed by reading the `gdp` source, and
  locked by a unit test.
- **Only smoothed whitening is exposed.** Pure whitening was removed because
  `whiten_window=1` is equivalent and a separate boolean caused silent conflicts.
- `plot_flowerpetal_3d.py` drapes each trace at its GNSS elevation (Z = elevation -
  depth). **That positioning IS the topo correction** -- equivalent to
  `topo_correction.py`'s static shift, but it preserves real surface relief, which is why
  it reads `_processed.npz` and not the topo data.

### The migration pick

Flagged with `migrate: true` (plus `migration_gain`) in params, so `run_pipeline.py`
re-migrates flagged profiles reproducibly at their `velocity`. The picking itself is
manual: read the velocity-scan HTML, settle on a velocity, then set `velocity` and add the
two keys. Currently flagged on Line3_50/100MHz and Line5_50/100MHz at gain 2.5.

Depth-below-surface picks live in `Data/GPR/Migration/tube_picks.csv`, with **pick-only
columns** (`line`, `ceiling`, `x_ceiling`, `floor_app`, `x_floor`, `notes`). Derived
`floor_real` and cave height are computed by `plot_dual_freq.cave_geometry()` (v_air 0.3)
and printed, not stored -- recompute rather than trusting a written-down number if a pick
or v_air changes. L5 is ceiling-only; it has no floor reflector.

`GPRProcessing.ipynb` merges on save, so these pipeline-managed keys survive a re-save of
the params from the notebook.

## Files

| File | Purpose |
|---|---|
| `GPRProcessing.ipynb` | Interactive notebook: load, tune, inspect, save params |
| `gpr_processing.py` | Core `apply_processing` -- shared by notebook and `run_pipeline` |
| `run_all.py` | One command: `run_pipeline` + every standalone deterministic figure/QC script |
| `run_pipeline.py` | Batch re-process all profiles from saved `_params.json` |
| `topo_correction.py` | Static topo correction from GNSS; `_processed.npz` -> `_topo.npz` |
| `plot_topo_section.py` | Topo QC-PNG renderer (`save_topo_figure`, `CLIP_FALLBACK`) |
| `plot_dual_freq.py` | Stacked 50/100 MHz figure per line; the migrated stage emits plain and `_picks`-annotated versions |
| `plot_picks.py` | Single-frequency migrated sections with pick annotations. **Diagnostic -- no live thesis figure** (superseded by the dual-freq picks) |
| `plot_processing_steps.py` | Stacked one-panel-per-step figure via `apply_processing(capture=)` |
| `migrate_velocity_scan.py` | Stolt velocity-scan CLI + HTML/PNG plotting |
| `migrate_scan_io.py` | Migration compute core: `migrate_at_velocity`, `save_migrated_npz`, `live_sample_taper`, `tgain_weights`, `norm99`, Stolt pad/taper constants |
| `plot_flowerpetal_3d.py` | 3-D Plotly scene builders + CLI: petals, Line 3 and the LiDAR cave draped on the GNSS surface |
| `flowerpetal_io.py` | Data layer of the 3-D viewer: `PROFILES`, path constants, loaders, `build_track_interps`, `petal_track`, `drape_curtain`, `split_panels` |
| `plot_petal_migration_3d.py` | 3-D view of Stolt-migrated petal SEGMENTS + migrated L3, flat-datum, in the same scene; ranges in `SEGMENTS` |
| `plot_petal_map.py` | Plan-view picking aid for choosing straight sub-segments |
| `plot_petal_migration_map.py` | Thesis plan-view map; imports `SEGMENTS` so it cannot drift from the 3-D plot |
| `plot_l2_spectral_diagnostics.py` | L2 100 MHz notch diagnostics vs a normal line (L3) |
| `plot_l2_svd_whiten.py` | Trial: does SVD or whitening fix the L2 notches? (Conclusion: no) |
| `check_polarity.py` | Per-profile polarity check (mean-trace first break) |
| `compare_intersections.py` | Polarity cross-check at line/petal crossings |
| `gpr_constants.py` | Shared constants (`V_DEFAULT`) |
| `GPRFieldVisual.ipynb` | Field visualisation, separate from processing |

**Data paths** (relative to the project root): raw stitched input
`Data/GPR/Stitched/{stem}_raw.npz` + `_raw.json`; saved params
`Data/GPR/Processed/{stem}_params.json`; processed `{stem}_processed.npz`; topo-corrected
`Data/GPR/Topo/{stem}_topo.npz` + `_topo.png`. Plots go to `Results/GPR/{Topo,DualFreq,Migration}/`.

## Verification

```
python goldenmaster.py check          # every tracked NPZ still bit-identical
python goldenmaster.py snapshot       # (re-)take the baseline -- only before an intended change
python -m pytest tests/
```

The golden master is a thin shim over the shared `Code/goldenmaster.py`, covering the 22
numerical outputs (9 `_processed.npz`, 9 `_topo.npz`, 4 `_migrated.npz`).

Tests: `test_apply_processing.py` (golden regression on the pipeline core plus
capture-label, polarity and crop invariants), `test_topo_correction.py`,
`test_normalisation.py`, and `test_goldenmaster_coverage.py`, which fails if a script
writes an `.npz` outside the golden-master manifest or a source glob matches nothing.

Frozen code is guarded by the golden master, not by unit tests -- do not add unit tests to it.

## Manual artifacts -- not reproducible by any script

The 3-D thesis figures are **hand-made browser captures of interactive HTML**, not
`save_figure` outputs. Grepping for a producing script will find none; that is expected.
To remake one, open the HTML, match the camera and gain, and screenshot. Do not try to
script it.

The HTMLs themselves are fully reproducible: `flowerpetal_unmigrated_3d.html` from
`plot_flowerpetal_3d.py` and `flowerpetal_migrated_3d.html` from
`plot_petal_migration_3d.py`, both into `Results/GPR/FlowerPetals3D/`. Only the capture is
manual.

**Annotated stills** (screenshot plus hand-drawn annotation), in the thesis repo's `GPR/`:
`FP3D_mig_SE_annotated.pdf` (`fig:fp3d-mig-snapshots-a`, SE-facing) and
`FP3D_mig_NE_annotated.pdf` (`fig:fp3d-mig-snapshots-b`, NE-facing), both from
`flowerpetal_migrated_3d.html`.

**Plain stills**, in `Appendices/Flowerpetals/`: `FP3D_allLines.png`,
`FP3D_allLinesWithLidar.png`, `FP3D_L3WithLidar.png`, `FP3D_FP2BackWithLidar.png`
(`fig:fp3d-a..d`, from the unmigrated HTML) and `FP3D_mig_allLines.png`,
`FP3D_mig_allLinesWithLidar.png`, `FP3D_mig_L3WithLidar.png`,
`FP3D_mig_FP2BackWithLidar.png` (`fig:fp3d-mig-a..d`, from the migrated HTML).

**Other human-in-the-loop steps:** the migration velocity pick (read by eye off the
velocity-scan HTML, then written into params) and the processing params themselves (tuned
in `GPRProcessing.ipynb`, saved as JSON -- the saved JSONs are the source of truth, and
`run_pipeline.py` replays them without the notebook).

## Status and settled decisions

Processing, topo correction, draped 3-D visualisation and Stolt migration are all stable.

**Velocity is settled at v = 0.125 m/ns for both lines** (L5 was remigrated from an earlier
0.11 on 2026-07-16; diffraction collapse admits 0.10-0.13 and one value was chosen). Final
picks in `tube_picks.csv`: L3 ceiling 3.8, floor_app 8.3 (real 14.6, *derived* by
`cave_geometry()` -- recompute it rather than trusting that number if the pick or v_air
changes); L5 ceiling 8.6. Handed to the gravity inversion 2026-07-16.

> **The LiDAR may NOT be used to justify the velocity pick.** The pick is blind by
> construction -- diffraction collapse is the only admissible evidence. Using the LiDAR
> would make the later LiDAR-vs-GPR comparison circular.

**Flower-petal migration is done** (2026-07-29). Straight sub-segments of each petal
(`SEGMENTS` in `plot_petal_migration_3d.py`) run through the existing 2-D Stolt code
(static topo correction -> taper -> Stolt), draped flat-datum alongside migrated L3.
**Full 3-D migration is out of scope.**

**Line 2 is deliberately not migrated** -- fewest stacks, slack-tape positioning, and the
spectral notches below. It stays a processed/topo profile with no migration pick.

**Line 2 100 MHz has spectral notches at ~75 and ~160 MHz.** Confirmed a hardware artifact
of the pulsEKKO antenna housing geometry, not geology. SVD/eigenimage removal and spectral
whitening were both trialled (`plot_l2_svd_whiten.py`) and neither removes it -- those
frequency bins are dead and there is no processing fix.

## Orphan PDFs in the thesis repo's `GPR/` folder

Listed 2026-08-12 so they can be pruned if wanted. **Nothing was deleted** -- the thesis is
frozen. Method: `ls GPR/*.pdf` against every `\includegraphics{GPR/...}` in `main.tex`.

*Produced but unused* -- a script still makes them, the thesis just does not include them:
`Line{3,5}_{50,100}MHz_picks.pdf` (superseded by the combined `_dual_freq_migrated_picks`),
`Line{3,5}_dual_freq_migrated.pdf` (superseded by the `_picks` variant), and
`Line{3,5}_dual_freq_topo.pdf` (the thesis only includes Line 2's). These regenerate on
every pipeline run, so deleting them from Overleaf is cosmetic.

*Stale -- unproduced and unused*, safe to delete: `arrival_chart.pdf` (no producing script
anywhere; superseded by `gpr_arrivals_schematic.pdf`) and `multiples_schematic.pdf`
(`plot_multiples_schematic.py` outputs the `gpr_arrivals_schematic` name, not this one).

## Layout

`Legacy/` holds quarantined trial artifacts that are not in the reproduce chain -- see its
own README. Its bulky binaries are gitignored by an explicit rule in `Code/.gitignore`; if
you rename that folder, update the rule in the same commit.

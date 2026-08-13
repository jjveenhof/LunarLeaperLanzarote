# GPR processing -- La Corona lava tube

GNSS-referenced GPR processing, topo correction, Stolt migration, and the 3-D draped
viewer for the La Corona survey. This README is the entry point; it does not restate the
pipeline -- **`CLAUDE.md` is the detailed reference** (pipeline order, per-file purpose,
conventions, current state) and is kept current. Read this to get oriented and to run
things; read `CLAUDE.md` when you need the details; read `DECISIONS.md` for the choices
that the code cannot explain to you.

## Environment
Conda env `lacorona-lunarleaper-thesis`, built from `Code/environment.yml` (one level up).
It pins the one external dependency, `gdp` (`georadar-data-processing`, public GitLab, LGPL
v3), by commit. Nothing needs `sys.path` setup. See `CLAUDE.md` "External dependency" for
the exact five functions used.

## One command to regenerate everything deterministic
```
python run_all.py                 # run_pipeline + every standalone deterministic figure/QC script
python run_all.py --no-scans      # skip the slow interactive velocity-scan HTMLs
```
`run_all.py` prints the steps it CANNOT do (they need a human) -- see `MANUAL_ARTIFACTS.md`:
the notebook-authored `_params.json`, the velocity pick from the scan HTML, and the browser
snapshots of the 3-D HTML. The core batch step is `run_pipeline.py` (reads the saved
`_params.json`, applies processing, writes the NPZs, then the downstream figures).

Prerequisite: the raw NPZs + `_params.json` already exist (produced by `GPRProcessing.ipynb`;
`run_all` does not stitch or tune params).

## Verifying nothing has drifted (golden master)
```
python goldenmaster.py check          # every tracked NPZ still bit-identical to the snapshot
python goldenmaster.py snapshot        # (re-)take the baseline -- only before an intended change
```
Thin shim over the shared `Code/goldenmaster.py`. It covers the 22 numerical outputs
(9 `_processed.npz`, 9 `_topo.npz`, 4 `_migrated.npz`). `test_goldenmaster_coverage.py`
asserts that set is COMPLETE -- that the pipeline writes nothing outside it (see Tests).

## Tests
```
python -m pytest tests/
```
`test_apply_processing.py` (golden regression on the pipeline core), `test_topo_correction.py`,
`test_normalisation.py`, and `test_goldenmaster_coverage.py`. Frozen code is guarded by the
golden master, not by unit tests -- do not add unit tests to it.

## Thesis figure / table -> producing script
Full map with `main.tex` labels and line numbers is Appendix A of `REFACTOR_FINDINGS.md`.
Summary:

| thesis output | producer |
|---|---|
| GPR processing-steps figures (L3/L5, LF+HF) | `plot_processing_steps.py` |
| before/after migration figures (L3/L5, LF+HF) | `migrate_velocity_scan.py` (`--pick-velocity`) |
| migrated dual-freq sections with picks (L3, L5) | `plot_dual_freq.py --stage migrated` |
| L2 dual-freq topo | `plot_dual_freq.py --stage topo` |
| L2 spectral-notch diagnostics / SVD+whiten trial | `plot_l2_spectral_diagnostics.py` / `plot_l2_svd_whiten.py` |
| flower-petal migration plan-view map | `plot_petal_migration_map.py` |
| LiDAR-cave overlay on migrated sections | `plot_lidar_cave_overlay.py` |
| arrivals/multiples schematic | `plot_multiples_schematic.py` |
| 3-D petal scenes (unmigrated / migrated) | `plot_flowerpetal_3d.py` / `plot_petal_migration_3d.py` (HTML; thesis stills are hand-captured -- see `MANUAL_ARTIFACTS.md`) |

Two thesis TABLES are settings, not calculated outputs, so they have no generator but ARE
checkable: `tab:gpr-acquisition` against `Data/GPR/Stitched/{stem}_raw.json` and the field
notes; `tab:gpr-processing` against `Data/GPR/Processed/{stem}_params.json` (both verified
2026-08-12 -- see `REFACTOR_FINDINGS.md` Appendix A, Tables).

## Layout
- `Legacy/` -- quarantined trial artifacts, NOT in the reproduce chain (see its README).
- `MANUAL_ARTIFACTS.md` -- the steps `run_all.py` cannot do.
- `ORPHAN_PDFS.md` -- unused PDFs in the Overleaf `GPR/` folder, for the author to prune.
- `REFACTOR_FINDINGS.md` -- the phase-1 audit + full traceability appendix.

# Thesis traceability -- every figure and table, and what made it

One place to answer "where did this number/figure in the thesis come from?". Labels are
`\label{}`s in `main.tex`; the thesis LaTeX lives outside this tree (see `README.md`).

Figure PDFs are written by `plot_utils.save_figure(fig, name, folder)`, which puts them in
`<thesis repo>/<folder>/<name>.pdf` and a browse PNG in `Results/`. So a figure's PDF path
plus this table is enough to find the code that drew it.

For **how to run** any of these, see the session's own `README.md`. This file is the map,
not the instructions.

---

## Gravimetry

### Figures

| Thesis label | Producing script |
|---|---|
| `fig:decay-examples` | `Grav/decay_examples.py` |
| `fig:decay-l2` .. `fig:decay-l5` | `Grav/station_decay.py` (appendix grids) |
| `fig:grav-detrend`, `fig:grav-detrended-residuals` | `Grav/detrend_regional.py` |
| `fig:grav-result-l4` | `Grav/visualise_line4.py` |
| `fig:residuals-grav` | `Grav/Inspect/inspect_lsq_residuals.py` |
| `fig:inversion-fit` | `Grav/Inversion/plot_misfit_row.py` |
| `fig:inversion-terrain-l3-circle`, `-l3-ellipse`, `-l5` | `Grav/Inversion/plot_model_terrain.py` |
| `fig:sensitivity-picks`, `fig:sensitivity-velocity` | `Grav/Inversion/plot_sensitivity.py` |
| `fig:freedepth` | `Grav/Inversion/freedepth.py` |
| `fig:freedepth-terrain-l3`, `-l5` | `Grav/Inversion/plot_freedepth_terrain.py` |
| `fig:density-sweep` | `Grav/Inversion/sweep_density.py` |

`decay_examples.py` and `visualise_line4.py` sat in an `Adhoc/` folder until 2026-08-12.
They produce live thesis figures, so they were misfiled; `Adhoc/` no longer exists.

### Tables

Only `tab:decay-fits` is written into the thesis directly. The rest were typed into
`main.tex` by hand, so the entry below names what reproduces the numbers.

| Thesis label | Source |
|---|---|
| `tab:decay-fits` | **generated** by `Grav/make_decay_table.py` (`\input` in `main.tex`) |
| `tab:corr_budget`, `tab:tc_perline` | **checked** by `Grav/make_thesis_tables.py --check` |
| `tab:se-budget` | **checked** by `Grav/make_thesis_tables.py --check` (`se_budget()`). Channels come from `invert_tube.size_area_se`, stored in each artifact by `run_inversion.py`; the MC column is the SD of the artifact ensemble areas. All 18 cells reproduce exactly. |
| `tab:detrend` | numbers printed by `Grav/detrend_regional.py` |
| `tab:lsq_results` | numbers printed by `Grav/Inspect/inspect_lsq.py` |
| `tab:inversion-results` | numbers printed by `Grav/Inversion/run_inversion.py` |
| `tab:freedepth` | numbers printed by `Grav/Inversion/freedepth.py` |
| `tab:density-sweep` | numbers printed by `Grav/Inversion/sweep_density.py` |

**Two known cells in `tab:tc_perline`, both L4, both benign** -- `make_thesis_tables.py
--check` reports exactly these and nothing else:

| Cell | Thesis | Reproduces as | Why |
|---|---|---|---|
| L4 Station SE | 0.014 | 0.013 | The 2026-08-01 `TAU_MIN` fix moved the raw median 0.013541 -> 0.013447, crossing a 3-dp rounding boundary. Worth 0.0001 mGal. Confirmed by rebuilding the 2026-06-11 state. |
| L4 TC Std | 0.040 | 0.041 | Transcription slip; the raw value is 0.041143 and its input has not changed since 12 June, so it cannot be a pipeline-state effect. |

The "Station SE" column is the **median `SE_lsq` over NON-BASE stations**, rounded
half-up -- the base station's SE is exactly 0 by datum definition, so including it would
drag every line toward zero. Anyone re-deriving this column and getting lower numbers has
probably included the base.

---

## GPR

### Figures

| Thesis PDF | Label | Producer |
|---|---|---|
| `gpr_arrivals_schematic.pdf` | `fig:multiple-schematics` | `plot_multiples_schematic.py:279` |
| `Line3_50MHz_processing_steps.pdf` | `fig:gpr-processing-steps` | `plot_processing_steps.py:151` |
| `Line3_100MHz_processing_steps.pdf` | `fig:l3-hf-processing-steps` | `plot_processing_steps.py:151` |
| `Line5_50MHz_processing_steps.pdf` | `fig:l5-lf-processing-steps` | `plot_processing_steps.py:151` |
| `Line5_100MHz_processing_steps.pdf` | `fig:l5-hf-processing-steps` | `plot_processing_steps.py:151` |
| `Line3_50MHz_before_after.pdf` | `fig:l3-before-after` | `migrate_velocity_scan.py:298` |
| `Line3_100MHz_before_after.pdf` | `fig:l3-hf-before-after` | `migrate_velocity_scan.py:298` |
| `Line5_50MHz_before_after.pdf` | `fig:l5-lf-before-after` | `migrate_velocity_scan.py:298` |
| `Line5_100MHz_before_after.pdf` | `fig:l5-hf-before-after` | `migrate_velocity_scan.py:298` |
| `Line3_dual_freq_migrated_picks.pdf` | `fig:mig-l3` | `plot_dual_freq.py:577` |
| `Line5_dual_freq_migrated_picks.pdf` | `fig:mig-l5` | `plot_dual_freq.py:577` |
| `Line2_dual_freq_topo.pdf` | `fig:l2-dual-freq-topo` | `plot_dual_freq.py:577` |
| `Line2_spectral_diagnostics.pdf` | `fig:l2-spectral-diagnostics` | `plot_l2_spectral_diagnostics.py:154` |
| `Line2_svd_whiten_trial.pdf` | `fig:l2-svd-whiten` | `plot_l2_svd_whiten.py:170` |
| `petal_migration_map.pdf` | `fig:petal-migration-map` | `plot_petal_migration_map.py:175` |
| `lidar_cave_overlay.pdf` | `fig:lidar-gpr-overlay` | `plot_lidar_cave_overlay.py:212` |
| `FP3D_mig_SE_annotated.pdf`, `FP3D_mig_NE_annotated.pdf` | `fig:fp3d-mig-snapshots-a/-b` | hand-captured from the 3-D HTML, then annotated |
| `Appendices/Flowerpetals/FP3D*.png` (8) | `fig:fp3d-a..d`, `fig:fp3d-mig-a..d` | browser screenshots of the 3-D HTML |

The 3-D scenes themselves are produced by `plot_flowerpetal_3d.py` and
`plot_petal_migration_3d.py` as interactive HTML. The thesis stills are screenshots of
those -- an intentional manual step, not a missing script.

### Tables

Both are settings tables with no generator, but both are checkable against source data,
and both were verified 2026-08-12.

| Thesis label | Source of truth | Verification result |
|---|---|---|
| `tab:gpr-acquisition` (`main.tex:385`) | Field notes; time window, antenna separation and trace spacing also in `Data/GPR/Stitched/{stem}_raw.json` (`Total_time_window`, `Antenna_sep`, `Step_size`) | Window / antenna-sep / spacing match the raw sidecars for all 9 profiles. Stack counts (2048/512/4096/4096) exist only in the field notes -- they are in no data file. |
| `tab:gpr-processing` (`main.tex:523`) | `Data/GPR/Processed/{stem}_params.json` | All cells match. Reference time-zero (ns) = `tzero_shift` (samples) x dt (1.6 ns at 50 MHz, 0.8 ns at 100 MHz); max-time crop = `max_time_ns`; dewow 25 samples, bandpass 20-100 / 40-200 MHz, normalisation start 50 ns. |

---

## LiDAR

| Thesis artifact | Label | Producer |
|---|---|---|
| Puerta Falsa before/after registration | `fig:puertafalsa-check` (`main.tex:1129`) | `verify_alignment.py` (default mode) |
| La Gente before/after registration | `fig:lagente-check` (`main.tex:1480`) | `verify_alignment.py --gente` |
| Vertical-residual RSS table (0.24 / 0.21 m) | `tab:lidar-vertical-budget` (`main.tex:1137`) | `gt_metrics.py` |
| L3 / L5 cross-section areas (203 / 182 m^2) | inversion results tables (`main.tex:937-938,1044`) | `slice_tube.py` -> `Data/LiDAR/lidar_line{3,5}.csv` |
| Sauro comparison figure | `fig:sauro-check` (`main.tex:1475`) | External (Sauro et al. 2020 scan) -- not this project's code |
| Overburden / envelope map inputs | (QGIS figures) | `Reregistered clouds/Gente_envelope.shp`, `QGIS project/caveheight_clean_laGente.tif` -- produced here, handed to QGIS |

---

## QGIS

Four thesis figures, all exported from print layouts in
`QGIS project/FieldworkReporting.qgz` to `<thesis repo>/Maps/*.pdf`.

**Not** `Research module report.qgz` -- despite the name, that file is stale and broken.
See `QGIS/DECISIONS.md`.

| Thesis figure | Layout | Key source layers |
|---|---|---|
| `main.tex:167`, regional DEM overview | `OverviewRegion` | `MergedDTM color`/`shade`, `Lava tube envelope`, `Tube Envelope - Cleaned and surface removed`, `PuertaFalsaCleanEnvelope` |
| `main.tex:358`, `fig:overview-fieldwork` panel (a) | `OverviewFieldworkAreaNoLegend` | `GPR_Lines`, `Flowerpetals`, `cavetop_clean_masked`, `cavetop_clean_masked_PuertaFalsa`, `cavetop_clean_masked_LaGente`, `LaGenteCleanEnvelope` |
| `main.tex:359`, `fig:overview-fieldwork` panels (b)/(c) | `NWFieldworkArea` | `GravLocations`, `GPR_Lines`, `cavetop_clean_masked_PuertaFalsa`, `cavetop_clean_masked_LaGente`, `LaGenteCleanEnvelope` |
| `main.tex:1157`, La Gente alignment | `LaGenteAlignment` | `AfterAlignmentInterpretation`, `Tube Envelope - Cleaned and surface removed`, `PuertaFalsaCleanEnvelope`, `LaGenteCleanEnvelope` |

Layouts that exist in the project but produce **nothing** in the thesis -- do not mistake
these for publishing anything: `ResearchModule` (empty, 0 map items),
`OverviewFieldworkArea` (superseded by the `...NoLegend` variant), `FlowerPetalOutreach`
(outreach material).

Two figures that look like they belong to QGIS but do not: `main.tex:601`
(`GPR/petal_migration_map`) is the GPR session, and `main.tex:1479`
(`Appendices/.../gente_check.png`) is the LiDAR session.

---

## Not produced by any script

Consolidated so nobody hunts for code that was never written.

| Thesis output | What it is |
|---|---|
| `fig:grav-loops` (`GravimeterLoopsSchematic.pdf`) | Hand-drawn schematic of the loop design. Source in `Figure sources/`. |
| `fig:workflow-grav`, `fig:workflow-inversion` | Hand-written TikZ, living in the thesis repo's `figures/workflow_*.tex`. Edit the TikZ. |
| `fig:grav-synthetic`, `fig:camacho-regional-trend` | External figures from the literature. |
| `fig:sauro-check` | External (Sauro et al. 2020). |
| `tab:grav-acquisition`, `tab:lsq_symbols`, `tab:inv-config`, `tab:inv-grid`, `tab:unc-channels` | Descriptive tables -- symbols, configuration, channel definitions. They describe the method, they do not report computed results. Edit `main.tex`. |
| The QGIS overburden rasters (`cavetop_clean_masked*.tif`) | A GUI product. The recipe and all inputs are documented, but no script exists and one was deliberately not written. Budget 15-20 min of QGIS time per area. See `QGIS/DECISIONS.md`. |
| The LiDAR re-registration | CloudCompare, seeded by eye then ICP. The 4x4 matrices in `LiDAR/alignment_transforms.txt` let you verify it; it cannot be regenerated unattended. |
| GPR `*_params.json` and the migration velocity pick | Tuned in a notebook / picked off an interactive scan. `GPR/run_all.py` reads the saved choices and prints what it cannot do. |

# GPR refactor -- Phase 1 findings (audit only)

Session: GPR. Date: 2026-08-03. Method: 8 parallel `Explore` subagents, one per
checklist item (a-h), each returning file:line evidence. No code changed.

**Reproduction check (rule 3):** the audit is read-only, so nothing was re-run to
compare against the thesis. No *stored* value contradicts the thesis. The one number
that disagrees with the docs -- `velocity 0.11` in `Line5_100MHz_svd1_params.json` --
is a stale `make_variant` experiment output, NOT a live-pipeline or thesis number, so
it is not a STOP item. Actual re-run verification happens in phase 2 per rule 2.

## Supervisor hypotheses -- verdicts

1. **gdp is the #1 handover risk** -- CONFIRMED, and worse than stated: only
   `tests/test_normalisation.py` bootstraps the gdp path; every production consumer
   (incl. `gpr_processing.py` and both notebooks) assumes gdp is already importable,
   and CLAUDE.md's claim that "scripts add it at runtime" is wrong. See F1.
2. **Notebook load-bearing, not in pipeline** -- CONFIRMED. `GPRProcessing.ipynb`
   writes `_params.json`; `run_pipeline.py` exits if absent. But the params contract is
   plain scalar JSON with merge-on-save preserving pipeline keys -- a successor CAN
   author params without the widget; the real dependency is that the tuned JSONs are
   kept. See F3.
3. **Four scripts >430 lines** -- one clean seam (`migrate_velocity_scan.py`), one
   already-mostly-separated (`topo_correction.py`), one partial
   (`plot_flowerpetal_3d.py`), one with NO clean seam (`plot_dual_freq.py`). See F9-F11.
4. **Cross-plot imports = plot modules are libraries** -- CONFIRMED and largely
   deliberate/good, but undocumented as a public surface. See F8.
5. **`SEGMENTS` protected, others not** -- CONFIRMED. `SEGMENTS` is single-definition +
   imported and carries no numbers in docs (drift-proof). The unprotected ones are
   `OFFSET_*`, section-starts 60/30, `V_AIR`, notch freqs. See F5.
6. **Best-tested session** -- misleading. `test_topo_correction.py` is real (13
   always-run assertions), but `test_normalisation.py` asserts nothing and isn't
   collected, and `apply_processing` has zero coverage. See F4.

---

## Ranked findings

### 1. gdp external dependency is unbootstrapped and mis-documented
- **Where:** `gpr_processing.py:61,71,72,145` (lazy `from gdp...`), `tests/test_normalisation.py:23-25` (only sys.path bootstrap), `Code/GPR/CLAUDE.md:95-97` (wrong claim), root `CLAUDE.md:43-46`.
- **What:** Production scripts `import gdp` assuming it is already importable; only the test constructs the path `Other data and scripts/Tube X/GPR/scripts/georadar-data-processing/`. CLAUDE.md says "scripts add this to sys.path at runtime" -- they do not. The dep is unpinned and lives outside git.
- **Why it hurts handover:** A successor on a fresh machine cannot run the processing pipeline at all until gdp is importable, and the docs point them the wrong way. This blocks goals (1) and (2) entirely.
- **Proposed action:** (phase 2, docs) Correct the CLAUDE.md claim; document exactly how to make gdp importable (its path, that it must be pip-installed or on PYTHONPATH, and the exact functions used: dewow, filter_data, normalize_data, apply_gain, remove_svd). Consider a single shared bootstrap import so production doesn't rely on ambient state. Escalate the "pin/vendor gdp" decision to Supervisor (cross-cutting, env spec).
- **Touches numbers?:** NO.
- **Effort:** S (docs) / M (bootstrap).

### 2. Thesis traceability table does not exist (build it -- it IS the handover artifact)
- **Where:** all `save_figure(..., 'GPR', ...)` call sites; `thesis-overleaf/main.tex`; `thesis-overleaf/GPR/`. Full mapping compiled in the Appendix below.
- **What:** There was no script->figure->label map. It now exists (Appendix A). Every thesis GPR figure except two (F... below) has an identified producer.
- **Why it hurts handover:** Without it a successor cannot find which script regenerates a given thesis figure -- directly goal (2).
- **Proposed action:** (phase 2, zero-risk) Land Appendix A into a `Code/GPR/README.md` traceability table.
- **Touches numbers?:** NO.
- **Effort:** S (data already gathered).

### 3. Two in-thesis figures have NO producing script
- **Where:** `main.tex:610,615` -> `GPR/FP3D_mig_SE_annotated.pdf`, `GPR/FP3D_mig_NE_annotated.pdf` (labels `fig:fp3d-mig-snapshots-a/b`). No `save_figure`/`_annotated` producer anywhere in the repo.
- **What:** Hand-annotated exports of the migrated-3D browser view, used in the Discussion body, with no reproducible script.
- **Why it hurts handover:** A successor cannot regenerate or re-annotate these -- goal (2) fails for two live figures.
- **Proposed action:** (phase 2, docs) Document their provenance (which HTML view + how annotated) next to the 3D scripts. Full reproducibility isn't achievable without re-doing manual annotation; at minimum record the recipe. Flag to author (he may accept "manual figure").
- **Touches numbers?:** NO.
- **Effort:** S.

### 4. `test_normalisation.py` is not a test; `apply_processing` has zero coverage
- **Where:** `tests/test_normalisation.py:1-112` (no `def test_*`, no assert, `plt.show()` at :112, tests the *external* `normalize_data` not the repo), vs `gpr_processing.py:66` (`apply_processing`, untested).
- **What:** The file that looks like the pipeline's normalisation test asserts nothing, isn't collected by pytest, and exercises a vendored function -- not `apply_processing`, which every downstream product depends on and which has no test at all. `test_topo_correction.py` is genuinely good (13 always-run assertions) but many of its tests `skipif` on the private `Data/` tree.
- **Why it hurts handover:** False green. A successor extending the pipeline (goal 3) has no regression net on the core function and a misleading test that suggests one exists.
- **Proposed action:** (phase 1 note now; phase 2) Rename/relabel `test_normalisation.py` as a demo (or convert to a real assert-based test), and add ONE golden-master test for `apply_processing` (synthetic radargram + fixed params + stored reference via `capture=`), which needs no private data.
- **Touches numbers?:** NO (adds a test).
- **Effort:** S (relabel) / M (golden test).

### 5. No single reproduce command; the chain is a 3-stage manual sequence
- **Where:** `GPRFieldVisual.ipynb` (stitch -> `Stitched/*_raw.npz`) -> `GPRProcessing.ipynb` (tune -> `Processed/*_params.json`) -> `run_pipeline.py` (replay). `run_pipeline.py` only subprocesses `plot_dual_freq.py`, `migrate_velocity_scan.py`, `plot_flowerpetal_3d.py`; 12 other figure/QC scripts run by hand.
- **What:** The reproduce path spans two manual notebooks plus a batch driver, and most thesis figures come from scripts the driver never calls.
- **Why it hurts handover:** A successor doesn't know the order or which manual script makes which figure -- goals (1)+(2).
- **Proposed action:** (phase 2, docs) A runbook in `Code/GPR/README.md`: the 3-stage order, notebook responsibilities, and (via Appendix A) which manual script makes each figure.
- **Touches numbers?:** NO.
- **Effort:** M.

### 6. `OFFSET_50/100MHZ` and section-start metres are duplicated, handled inconsistently
- **Where:** source `topo_correction.py:46-47`; COPY `plot_flowerpetal_3d.py:60-61`; literals `tests/test_topo_correction.py:172,184`; correct import `plot_lidar_cave_overlay.py:41`. Section-starts 60/30: `topo_correction.py:166,175`, `plot_flowerpetal_3d.py:87`, `plot_dual_freq.py:55-59` (`X_OFFSET_100MHZ`).
- **What:** The antenna offsets exist in 3 places (one imports, one copies, tests hard-code) and the 100 MHz section-start metres in 3 files. All currently agree, linked only by convention.
- **Why it hurts handover:** Editing one and not the others silently mis-registers geometry -- a successor changing an offset (goal 3) would corrupt topo/migration without warning.
- **Proposed action:** (phase 2, low-risk) Single source in `gpr_constants.py`; import everywhere including the flowerpetal copy; update tests to import.
- **Touches numbers?:** YES -- verify `Topo/*_topo.npz` and `Migration/*_migrated.npz` with `np.allclose` before/after.
- **Effort:** S-M.

### 7. Duplicated helpers that should be shared (geometry + spectral + norm)
- **Where:** `load_gnss_fp` verbatim in `plot_flowerpetal_3d.py:93` + `topo_correction.py:114`; the composed petal-track builder copied 3x (`plot_petal_migration_3d.py:72`, `plot_petal_migration_map.py:56`, `plot_petal_map.py:42`); `mean_trace_spectrum` in `plot_l2_spectral_diagnostics.py:69` + `plot_l2_svd_whiten.py:59`; `norm` in `check_polarity.py:61` + `compare_intersections.py:120`.
- **What:** True copy-paste of loaders/wrappers whose primitives are already shared. Note `profile_geometry.py` is a THIRD canonical shared module (load_flip/reconcile_geometry, imported by 4 files) -- good, and the right home pattern.
- **Why it hurts handover:** Divergence risk and unclear ownership; a successor won't know which copy is canonical.
- **Proposed action:** (phase 2, low-risk) Move `load_gnss_fp`/`load_gnss_lines`/`build_track_interps` and the petal-track wrapper into one geometry module (extend `profile_geometry.py` or a new `gpr_geometry.py`); `mean_trace_spectrum` into a shared spectral helper; `norm` into `plot_utils`/`gpr_constants`. Extract, then verify.
- **Touches numbers?:** YES for the geometry ones -- verify topo + overlay outputs. NO for spectral/norm (figure-only).
- **Effort:** M.

### 8. Plot modules are undocumented libraries (cross-imports)
- **Where:** `plot_picks.py:37` imports from `plot_dual_freq.py`; `plot_petal_*`/`plot_lidar_cave_overlay.py`/`compare_intersections.py` import from `plot_flowerpetal_3d.py`; `plot_petal_migration_3d.py:37` imports from `migrate_velocity_scan.py`. Full surface in Appendix B.
- **What:** Three plot scripts are de-facto libraries (their loaders/`make_figure`/`write_html`/constants are imported across the session). Good reuse, but not documented as a public API, so it's unclear which parts are safe to change.
- **Why it hurts handover:** A successor editing `plot_dual_freq.make_figure` or `plot_flowerpetal_3d`'s loaders could break 3-5 other scripts unknowingly (goal 3).
- **Proposed action:** (phase 2, docs) Document the shared surface in CLAUDE.md; longer term, moving the shared primitives into named modules (F7) removes the plot-imports-plot coupling.
- **Touches numbers?:** NO (docs).
- **Effort:** S.

### 9. `make_variant.py` + `Line5_100MHz_svd1_*` artifacts -- quarantine
- **Where:** `make_variant.py` (whole; not imported, not in CLAUDE.md Key Files); outputs `Data/GPR/Processed/Line5_100MHz_svd1_{params.json,processed.npz}`, `Data/GPR/Topo/Line5_100MHz_svd1_topo.{json,npz}`, `Results/GPR/Topo/Line5_100MHz_svd1_topo.png`, `Results/GPR/Migration/Line5_100MHz_svd1_stolt_velocity_scan.html`.
- **What:** The ad-hoc tool that generated the L2/SVD-notch experiment; nothing reads the `svd1` stem. Its conclusion ("hardware notch, no fix") is preserved in CLAUDE.md and the two `plot_l2_*` figures.
- **Why it hurts handover:** An undocumented script + orphan outputs (incl. the stale `velocity 0.11`) read as live work and confuse the reproduce map.
- **Proposed action:** (phase 2, quarantine) Move `make_variant.py` to `Code/GPR/Adhoc/` with a one-line header; list the 6 `svd1` data artifacts for the author to delete/quarantine (his veto, rule 5).
- **Touches numbers?:** NO (not in the live pipeline or thesis).
- **Effort:** S.

### 10. Derived / doc-only constants that can go stale silently
- **Where:** "14.6 m" (real floor) only in `Code/GPR/CLAUDE.md:173`, recomputed everywhere else by `plot_dual_freq.cave_geometry()`; `V_AIR=0.3` restated in `plot_dual_freq.py:65`, `plot_multiples_schematic.py:52`, `tube_picks.csv` header, `CLAUDE.md:116`; notch `75/160` in two `plot_l2_*` scripts + docs.
- **What:** Values that are computed (or single-sourced) in code but re-typed as frozen numbers in prose/duplicated scripts.
- **Why it hurts handover:** If the pick 8.3 or `V_AIR` changes, the code recomputes but the CLAUDE.md "14.6" silently lies.
- **Proposed action:** (phase 2, zero-risk docs) Label the CLAUDE.md 14.6 as "(derived from floor_app 8.3, v_air 0.3)"; centralise `V_AIR` in `gpr_constants.py`.
- **Touches numbers?:** NO (docs) / the `V_AIR` centralise is YES -- verify cave_geometry output.
- **Effort:** S.

--- RECOMMENDED CUT LINE (above: worth doing; below: honestly optional) ---

### 11. `migrate_velocity_scan.py` compute/plot split
- **Where:** `migrate_velocity_scan.py:106-end` (~500-line `main`); compute + `np.savez` at :190-201.
- **What:** Migration compute (build_section + `stolt_migration_2d` + NPZ writer) is crammed with two PNG figures and the scan-HTML in one `main`. It already persists an NPZ artifact -- the Grav `inversion_io.py` seam exists but isn't factored out.
- **Why it hurts handover:** Large single-function file; the strongest split candidate. But the payoff is modest vs the risk (the migrated NPZ is a thesis input).
- **Proposed action:** (phase 2, structural, one at a time) Extract compute + NPZ writer into `migrate_scan_io.py`; leave plotting reading the NPZ. Verify `np.allclose` on every `*_migrated.npz`.
- **Touches numbers?:** YES -- `Migration/*_migrated.npz` (thesis input). Verify hard.
- **Effort:** L.

### 12. `topo_correction.py` / `plot_flowerpetal_3d.py` splits -- optional
- **Where:** `topo_correction.py` (434, seam already exists: `apply_topo_correction` + NPZ writer vs `save_figure`); `plot_flowerpetal_3d.py` (650, partial seam: `drape_curtain`/`split_panels` vs `make_figure`/`write_html`, but `make_figure` also holds equalisation math).
- **What:** Both have real seams but neither is under size pressure that hurts handover; `plot_flowerpetal_3d`'s loader layer is better addressed as the shared-geometry extraction in F7.
- **Why it hurts handover:** Marginal. Splitting risks the topo NPZ / 3D outputs for little handover gain.
- **Proposed action:** Defer. Do F7 (extract shared loaders) first; reassess. `plot_dual_freq.py` has NO clean seam -- do not split it for size.
- **Touches numbers?:** YES (topo NPZ) if attempted.
- **Effort:** M-L.

---

## Appendix A -- Thesis traceability (GPR)

| thesis PDF | main.tex label | producer script:line |
|---|---|---|
| gpr_arrivals_schematic.pdf | fig:multiple-schematics | plot_multiples_schematic.py:279 |
| Line3_50MHz_processing_steps.pdf | fig:gpr-processing-steps | plot_processing_steps.py:151 |
| Line3_100MHz_processing_steps.pdf | fig:l3-hf-processing-steps | plot_processing_steps.py:151 |
| Line5_50MHz_processing_steps.pdf | fig:l5-lf-processing-steps | plot_processing_steps.py:151 |
| Line5_100MHz_processing_steps.pdf | fig:l5-hf-processing-steps | plot_processing_steps.py:151 |
| Line3_50MHz_before_after.pdf | fig:l3-before-after | migrate_velocity_scan.py:298 |
| Line3_100MHz_before_after.pdf | fig:l3-hf-before-after | migrate_velocity_scan.py:298 |
| Line5_50MHz_before_after.pdf | fig:l5-lf-before-after | migrate_velocity_scan.py:298 |
| Line5_100MHz_before_after.pdf | fig:l5-hf-before-after | migrate_velocity_scan.py:298 |
| Line3_dual_freq_migrated_picks.pdf | fig:mig-l3 | plot_dual_freq.py:577 |
| Line5_dual_freq_migrated_picks.pdf | fig:mig-l5 | plot_dual_freq.py:577 |
| Line2_dual_freq_topo.pdf | fig:l2-dual-freq-topo | plot_dual_freq.py:577 |
| Line2_spectral_diagnostics.pdf | fig:l2-spectral-diagnostics | plot_l2_spectral_diagnostics.py:154 |
| Line2_svd_whiten_trial.pdf | fig:l2-svd-whiten | plot_l2_svd_whiten.py:170 |
| petal_migration_map.pdf | fig:petal-migration-map | plot_petal_migration_map.py:175 |
| lidar_cave_overlay.pdf | fig:lidar-gpr-overlay | plot_lidar_cave_overlay.py:212 |
| FP3D_mig_SE_annotated.pdf | fig:fp3d-mig-snapshots-a | **UNKNOWN (manual)** -- F3 |
| FP3D_mig_NE_annotated.pdf | fig:fp3d-mig-snapshots-b | **UNKNOWN (manual)** -- F3 |
| Appendices/Flowerpetals/FP3D*.png (8) | fig:fp3d-a..d, fig:fp3d-mig-a..d | manual browser screenshots of the 3D HTML (expected) |

### Tables (settings-only; no generator, but checkable against source)

| thesis table | main.tex label | source of truth | verified 2026-08-12 |
|---|---|---|---|
| GPR acquisition parameters | tab:gpr-acquisition (main.tex:385) | field notes; time-window, antenna sep and trace spacing also in `Data/GPR/Stitched/{stem}_raw.json` (`Total_time_window`, `Antenna_sep`, `Step_size`) | window/ant-sep/spacing match the raw sidecars for all 9 profiles; stacks (2048/512/4096/4096) are field-note-only, not in any data file |
| GPR processing parameters | tab:gpr-processing (main.tex:523) | `Data/GPR/Processed/{stem}_params.json` | ALL cells match. Ref time-zero (ns) = `tzero_shift` (samples) x dt (1.6 ns @50MHz, 0.8 ns @100MHz); max-time crop = `max_time_ns`; dewow 25 samp, bandpass 20-100 / 40-200 MHz, norm start 50 ns all match. No drift -> no rule-3 escalation |

Orphan/stale outputs in `thesis-overleaf/GPR/` (exist, not `\includegraphics`'d): `multiples_schematic.pdf` (also unproduced), `arrival_chart.pdf` (also unproduced), `Line{3,5}_dual_freq_migrated.pdf`, `Line{3,5}_dual_freq_topo.pdf`, `Line{3,5}_{50,100}MHz_picks.pdf` (produced-but-unused). Author should confirm these can be pruned.

## Appendix B -- Cross-import surface (the shared library API)

- `plot_flowerpetal_3d.py` exports (imported by plot_petal_migration_3d/map, plot_petal_map, plot_lidar_cave_overlay, compare_intersections): `build_track_interps`, `load_gnss_fp/lines`, `load_edge/plumb/lidar`, `load_velocity`, `reconcile_geometry` (re-export of profile_geometry), `make_figure`, `write_html`, `PROFILES`, `PROC_DIR`, `GNSS_FP/LINES`, `GAIN_PRESETS`, `LIDAR_XYZ`, `OUT_DIR`.
- `plot_dual_freq.py` exports (plot_picks, plot_lidar_cave_overlay): `load_npz`, `load_param`, `load_clip`, `CMAP`, `X_OFFSET_100MHZ`, `PICKS_CSV`, `PICK_PANEL_CFG`, `load_flip`, `read_picks`, `annotate_pick`, `pick_entries`.
- `migrate_velocity_scan.py` exports (plot_petal_migration_3d): `live_sample_taper`, `PAD_T_FACTOR`, `PAD_X_TRACES`, `TAPER_W`, `TAPER_T_FRAC`.
- `topo_correction.py` exports: `apply_topo_correction` (migrate_velocity_scan, plot_petal_migration_3d), `OFFSET_50MHZ` (plot_lidar_cave_overlay); imported wholesale by run_pipeline, make_variant, tests.
- `profile_geometry.py` (canonical): `load_flip`, `reconcile_geometry` -> topo_correction, plot_flowerpetal_3d, plot_dual_freq, compare_intersections.

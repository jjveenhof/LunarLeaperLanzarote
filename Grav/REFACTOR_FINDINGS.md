# Grav session -- phase 1 refactor findings

Audit only, per `Code/REFACTOR.md`. **No code was changed.** Survey done with six
parallel Explore subagents (one per checklist area); every claim below carries file:line
evidence, and the two consequential ones were re-verified by hand before being written
down (one of them turned out to be a false positive -- see the Not-Confirmed list).

Scope: `Code/Grav/` = 45 scripts, ~7.6k lines (top level 14/2844, `Inversion/` 17/2930,
`Inspect/` 9/1224, `Adhoc/` 4/568, `Tests/` 1/39).

Ranked by handover value / risk. **The recommended cut line is marked.**

---

## 0. ESCALATION -- rule 3, reported to Supervisor separately

### [E1] `plot_area_summary.py` reports smaller SEs than the thesis
- **Where:** `Inversion/plot_area_summary.py:25-33`
- **What:** `RESULTS` is a hand-transcribed table. It holds L3 circle 227 +/- **32**,
  L3 ellipse 193 +/- **23**, L5 circle 167 +/- **30**. The thesis (`tab:inversion-results`)
  reports **41 / 24 / 36**, and the artifacts give MC 41.2 / 24.5 / 35.6 (analytic
  37.0 / 24.8 / 34.3). The hardcoded numbers match neither -- they predate the
  2026-07-29 `velocity_sigma` 0.010 -> 0.015 change.
- **Why it hurts handover:** its output `area_summary.pdf` is **not** in `main.tex`, so
  the thesis is unaffected -- but it IS cited in
  `Progress - Notes and Presentations/2026.08.17 Defence/Defence presentation scaffold.md:141`.
  The defence deck would show error bars ~25% tighter than the thesis.
- **Proposed action:** author decides. Escalated to root `QandA.md`; not touched.
- **Touches numbers?:** YES -- `Results/Grav/Inversion/artifacts/*.npz` are the reference.
- **Effort:** S

---

## 1. Reproducibility and traceability (highest handover value)

### [1] `run_pipeline.py` is not the whole chain, and does not say so
- **Where:** `run_pipeline.py:35-39,71-98`; `CLAUDE.md:12-24`
- **What:** four steps run; four more are manual and undocumented as such.
  `combine_gravimetry.py` (produces the only raw input) is listed as step 1 of the
  "Main chain" but is never called. **`detrend_regional.py` is not in the pipeline at
  all**, yet it produces `..._detrended.csv`, which every script in `Inversion/`
  consumes (`Inversion/invert_tube.py:63`). Also manual: `make_decay_table.py`,
  `visualise_lsq.py`, `visualise_CBA.py`, and all figures
  (`station_decay.main(plot=False)` at `run_pipeline.py:77`).
- **Why it hurts handover:** a successor types `run_pipeline.py`, gets no figures and no
  detrended file, and cannot run the inversion at all -- with nothing telling them why.
- **Proposed action:** a `Code/Grav/README.md` (or CLAUDE.md section) giving the true
  ordered command list, marking each step auto/manual. Docs only. Optionally, phase 3:
  add the missing steps to `run_pipeline.py` behind flags.
- **Touches numbers?:** NO (docs). YES if the pipeline is extended -- diff all of `PROC_DIR`.
- **Effort:** S (docs) / M (orchestration)

### [2] Thesis traceability table does not exist
- **Where:** new file; sources `main.tex` + `Code/plot_utils.py:75,152`
- **What:** all 16 gravimetry/inversion thesis figures now have a confirmed producing
  script (mapped during this audit -- see appendix below). Gaps found:
  `fig:grav-loops` (`main.tex:456`) has **no producing script**; `tab:tc_perline`
  (`:756`) and `tab:corr_budget` (`:735`) have **no script that prints their numbers**.
  Every other table is hand-transcribed from a script's stdout.
- **Why it hurts handover:** this is the single artifact that lets a successor verify a
  number or regenerate a figure without asking the author -- the goal sentence, literally.
- **Proposed action:** commit the appendix table below as `Code/Grav/TRACEABILITY.md`.
  Chase the three gaps with the author.
- **Touches numbers?:** NO
- **Effort:** S (table drafted already)

### [3] `decay_fits_table.tex` was hand-edited despite its "do not edit" banner
- **Where:** `make_decay_table.py:61,65`; `thesis-overleaf/Appendices/decay_fits_table.tex:5`
- **What:** the committed `.tex` has short caption `[Per-station gravimeter decay-fit
  results]`; the generator emits `[Per-station decay-fit results]`. Re-running the script
  silently reverts the author's edit.
- **Why it hurts handover:** a successor regenerating the table loses a hand edit with no
  warning. Generated-file-edited-by-hand is a trap that only bites later.
- **Proposed action:** move the caption text into `make_decay_table.py` so the generator
  is the single source. Also note `tab:decay-fits` is **never `\ref`'d** in `main.tex`.
- **Touches numbers?:** NO
- **Effort:** S

### [4] `Inspect/inspect_decay_residuals.py` uses the pre-fix settled rule
- **Where:** `Inspect/inspect_decay_residuals.py:23,41` vs `station_decay.py:136,259-260`
- **What:** imports only `SIGNIFICANCE_THRESHOLD`, not `TAU_MIN`, so it computes
  `settled = (not converged) or (|A| < SIG*SE_A)` -- missing the `tau < TAU_MIN` term.
  This is the exact bug fixed in the pipeline on 2026-08-01 (`CLAUDE.md:66-72`); the
  diagnostic still carries it and now disagrees with the pipeline by 2 stations.
- **Why it hurts handover:** a successor running the diagnostic to check the fits gets a
  classification that contradicts the CSVs, and no note says which is right.
- **Proposed action:** import `TAU_MIN` too. Diagnostic-only; touches no pipeline output.
- **Touches numbers?:** NO (figure only, `Results/Grav/Decay fitting/decay_residuals_*.png`)
- **Effort:** S

### [5] The settled/decaying rule is written twice
- **Where:** `station_decay.py:136` (`plot_line`) and `:259-260` (`main`)
- **What:** two independent copies of the same predicate, no shared function. This
  duplication already produced one live bug (see [4] / `CLAUDE.md:66-72`), and [4] shows
  a third copy exists in `Inspect/`.
- **Why it hurts handover:** the classification decides which value every station reports;
  three copies means the next edit re-opens the same bug.
- **Proposed action:** extract `is_settled(A, se_A, tau, converged)` in `station_decay.py`
  and call it from all three sites.
- **Touches numbers?:** YES -- diff `decay_fits.csv` + `station_gravity_decay.csv` (must
  be bit-identical; the rule is unchanged, only deduplicated).
- **Effort:** S

---

## 2. Duplication (the shared modules exist and are bypassed)

### [6] `BASE`/`PROC_DIR`/`RESULTS_DIR` re-derived in ~20 files
- **Where:** `parents[2]` in 6 top-level scripts; `parents[3]` in 14 subfolder scripts
  (e.g. `Inspect/inspect_G.py:10`, `Inversion/invert_tube.py:55`,
  `Tests/test_drift_correction_lsq.py:8`). `PROC_DIR` re-typed 8x, `"Results/Grav"` ~14x.
- **What:** `grav_utils.py:14-16` defines all three, and `CLAUDE.md:30-31` says to use it.
  Only `Inspect/inspect_corrections_comparison.py:30` imports `RESULTS_DIR`.
- **Why it hurts handover:** the `parents[2]` vs `parents[3]` split is exactly the
  fragility the shared module removes -- move a script one folder and it breaks silently.
- **Proposed action:** phase-2 import sweep, one file at a time.
- **Touches numbers?:** NO (paths resolve to the same place -- verify by diffing outputs).
- **Effort:** M

### [7] `plot_model_terrain.py` is a library and a script in one file
- **Where:** `Inversion/plot_model_terrain.py:79-148` (library) vs `:151-403` (`main`)
- **What:** `gravity_profile`, `gpr_surface`, `posterior_envelope` and the style
  constants are imported by `plot_freedepth_terrain.py` (`:97,114,161,99-211`) and by
  `freedepth.py:132`, which needs a **lazy import inside a function** to get at them.
  Meanwhile ~130 of `plot_freedepth_terrain.py`'s 264 lines are copy-pasted from the
  same file (canvas geometry `:216-224` vs `:128-133`, top panel `:311-337` vs `:182-205`,
  `outline()` `:202-206` vs `:117-121`, and ten more blocks).
- **Why it hurts handover:** this is the one place where the proven compute/plot seam has
  a genuine sibling, and the duplication means a fix to one terrain figure silently skips
  the other.
- **Proposed action:** extract `terrain_common.py` (profile/envelope/style/canvas), leave
  the two `main()`s. This is the `inversion_io.py` pattern applied once more.
- **Touches numbers?:** NO for the helpers -- but figures change if anything slips.
  Verify by regenerating all five terrain figures and diffing the artifact-derived numbers.
- **Effort:** M

### [8] Per-line colour palette defined 7x; station markers 3x and inconsistent
- **Where:** palette at `detrend_regional.py:41`, `visualise_CBA.py:48`,
  `Inversion/invert_tube.py:97` (**never read**), `Inversion/plot_model_terrain.py:65`,
  plus 4 partial re-spellings. Markers at `Adhoc/visualise_lines.py:37-39` (tie = `^`)
  vs `Inversion/plot_model_terrain.py:66-67` (tie = `v`) vs `detrend_regional.py:131`.
- **What:** the tie-station marker genuinely differs between figures in the same thesis.
- **Why it hurts handover:** a successor cannot tell which style is canonical.
- **Proposed action:** one definition in `plot_utils.py`. **Cross-session** -- the
  Supervisor owns `plot_utils.py`; propose, do not do.
- **Touches numbers?:** NO -- but changing a marker IS a figure change (rule 6). Only
  unify where the current figures already agree; leave the `^`/`v` split to the author.
- **Effort:** S (propose) / M (execute)

### [9] `InvCfg` built from `LINE_PRESETS` in 5 places; `sigma_pick=1.25` in 6
- **Where:** `freedepth.py:63-66`, `plot_sensitivity.py:53-61`, `inspect_beta1.py:66-76`,
  `sweep_density.py:94-96,133-135`, `run_inversion.py:102-112`
- **What:** every one re-specifies `sigma_pick=1.25` even though `invert_tube.py:118`
  already defaults to it. The x0 grid `arange(xmin-20, xmin+20, 0.5)` appears **8x** and
  the `floor or 16.0` L5 fallback **6x**.
- **Why it hurts handover:** changing a pick sigma requires finding six literals.
- **Proposed action:** a `cfg_for(line, **overrides)` helper in `invert_tube.py`; import it.
- **Touches numbers?:** YES -- re-run `run_inversion.py` and diff all artifacts.
- **Effort:** M

---

## 3. Correctness smells (no thesis number affected, but worth knowing)

### [10] Two different gravitational constants
- **Where:** `grav_utils.py:39` `G_NEWTON = 6.674e-11` vs `Inversion/forward_polygon.py:18`,
  `forward_fem.py:26`, `inspect_2d_validity.py:26` all `G = 6.6743e-11`
- **What:** the reduction chain and the forward model use different G (4 vs 5 digits).
  Relative difference 4.5e-5 -- on a 200 m^2 area that is 0.009 m^2, far below the 24 m^2 SE.
- **Why it hurts handover:** numerically irrelevant, but a successor will spot it and
  wonder which is intended.
- **Proposed action:** single constant in `grav_utils.py`, imported by the forward models.
- **Touches numbers?:** YES in principle -- diff artifacts; expect changes ~1e-5 relative.
- **Effort:** S

### [11] rho = 1.875 restated 9x across two unit systems; one baked into a filename
- **Where:** `grav_utils.py:49` (canonical), `integrate_corrections.py:43` (`TC_RHO`, a
  second literal in a file that already imports `RHO_DEFAULT`), `forward_polygon.py:19`
  and `forward_fem.py:27` (`1875.0` kg/m3), `inspect_2d_validity.py:26` (`-1875.0`),
  `inspect_beta1.py:53,55`, `sweep_density.py:65`, and
  **`plot_model_terrain.py:58`** -- `..._rho1p875_with_TC.csv` hardcoded, bypassing
  `grav_utils.rho_str` and silently pinning that figure to one density.
- **Why it hurts handover:** the density sweep is a headline result; a successor
  repeating it will not find all nine sites.
- **Proposed action:** import `RHO_DEFAULT`; build the filename with `rho_str`.
- **Touches numbers?:** NO at the default rho (same value) -- verify by diffing the
  terrain figures' source numbers.
- **Effort:** S

### [12] `invert()` has no grid-edge guard, unlike `freedepth.analyse()`
- **Where:** `Inversion/invert_tube.py:199-202` vs `freedepth.py:117-120`
- **What:** `size_lo/size_hi` are taken from `sizes[mask].min()/.max()` with no check that
  the mask touches the grid boundary. `freedepth.analyse()` gained exactly that guard on
  2026-08-01 after a fake bound appeared. A railed fit in `invert()` would report a
  truncated SE with no warning.
- **Why it hurts handover:** the current fits are interior, so nothing is wrong today --
  but a successor changing a pick or a density could rail the grid and not be told.
- **Proposed action:** mirror the guard; warn rather than change any value.
- **Touches numbers?:** NO for current inputs (verify: artifacts bit-identical).
- **Effort:** S

### [13] Tests: 39 lines, **zero assertions**
- **Where:** `Tests/test_drift_correction_lsq.py` (repo-wide grep for `assert` in
  `Code/Grav/` returns nothing)
- **What:** a print-only script with a `test_` name; everything runs at import, so pytest
  "passes" iff nothing raises. It is bound to live data (`station_gravity_decay.csv`), so
  it changes meaning whenever the pipeline reruns, and it covers Line 2 only.
- **The one test a successor would most want:** a **closed-form round-trip on
  `drift_correction_lsq.solve_line`** -- build a noise-free two-loop synthetic network with
  injected anomalies, drift rate and offset; assert the solver recovers them to ~1e-10,
  that `Grav_lsq == 0` exactly at `loc_id == 0` (the datum every downstream number rests
  on), that loop drift/offset come back as injected, and that `chi2_red ~ 0`. A second
  fixture with a shared base between loops would pin the duplication branch at
  `drift_correction_lsq.py:82-92`. Known-answer, so it survives any legitimate rerun.
- **Why it hurts handover:** `drift_correction_lsq.py` is 381 lines, is the step every
  later number inherits, and has no executable check at all.
- **Proposed action:** propose only, per the brief. Do not write in phase 1.
- **Touches numbers?:** NO
- **Effort:** M

---

## ============ RECOMMENDED CUT LINE ============
Everything above is worth doing. Below is honestly optional.

---

### [14] `freedepth.py` bypasses `inversion_io` with a parallel artifact format
- **Where:** `freedepth.py:87` (`np.savez` by hand), read at `freedepth.py:102`,
  `plot_freedepth_terrain.py:74` **and** `:105` (the same 12 MB cube loaded twice per run)
- **What:** writes `freedepth_line{N}.npz` outside `artifacts/`, with no stored `cfg`.
- **Proposed action:** either fold into `inversion_io` or document why it is separate
  (the cube is a different shape from the per-case artifact -- that is a fair reason).
- **Touches numbers?:** NO. **Effort:** M

### [15] Dead code
- **Where:** `forward_polygon.py:66` `tube_gz` (zero callers; only referenced in a comment
  at `invert_tube.py:159`), `invert_tube.py:97` `LINE_COLORS` and `:98` `DENSITY` (never
  read), `plot_model_terrain.py:60` `HERE` (unused, and the only user of its `Path` import).
- **Proposed action:** KEEP `tube_gz` with a header note (it documents the exact forward
  the truncation factor approximates -- that is handover value); delete the three unused
  names. **Effort:** S

### [16] Four `Inversion/` diagnostics have no `__main__` guard and stale geometry
- **Where:** `inspect_2d_validity.py:31` (`A,B,CZ = 8.5,5.5,10.5`, a frozen old best fit),
  `visualise_domain.py:25` (`CEILING,HEIGHT = 5.0,11.0` -- current picks are 3.8/14.6),
  `inspect_forward_scaling.py:20-52`, all executing at module scope.
- **What:** importing any of them runs them. Both geometries predate the final picks.
- **Proposed action:** QUARANTINE (rule 5) with a header saying they document the
  abandoned pyGIMLi/2-D-validity branch. **Effort:** S

### [17] `Adhoc/` misfiles two thesis-figure producers
- **Where:** `Adhoc/decay_examples.py` -> `fig:decay-examples` (`main.tex:637`);
  `Adhoc/visualise_line4.py` -> `fig:grav-result-l4` (`main.tex:809`)
- **What:** `CLAUDE.md:45` calls `Adhoc/` "one-offs and legacy plots", but two of its four
  scripts produce live thesis figures. Conversely `Inspect/inspect_lsq_residuals.py`
  produces `fig:residuals-grav` and is load-bearing (`inspect_lsq.py` is imported by it).
- **Proposed action:** either promote the two producers or fix the CLAUDE.md sentence.
  Renaming files is a bigger change -- the doc fix is the cheap 90%.
- **Touches numbers?:** NO. **Effort:** S

### [18] Genuinely finished one-offs -- candidates for quarantine
- `Adhoc/export_stations.py` (the colleague handoff already happened; its output
  `stations_for_corrections.csv` is dated 2026-06-12 vs an input of 2026-08-01 and is read
  by nothing), `Adhoc/visualise_lines.py` (legacy simple-drift branch; `CLAUDE.md:45`
  already says so), `Inspect/inspect_durations.py` (print-only; its question is answered
  quantitatively by `inspect_acquisition_noise.py`).
- **Proposed action:** QUARANTINE with one-line headers, do not delete. **Effort:** S

### [19] Orphan PDFs in the thesis repo
- **Where:** `Grav/detrend_line{2,3,5}.pdf` (`detrend_regional.py:274`),
  `Inversion/invert_line3_{circle,ellipse}.pdf` + `invert_line5_circle.pdf`
  (`plot_misfit.py:54`, superseded by `misfit_row`), `Inversion/area_summary.pdf`,
  and `Grav/line4_combined.pdf` -- **stale**, no current script can reproduce that
  basename (`visualise_line4.py:60,68` now emits `line4_combined_{CBA,SBA}_rho...`).
- **Proposed action:** list for the author; deleting files in the thesis repo is his call.
- **Effort:** S

### [20] CLAUDE.md has become a research journal -- proposed split
- **Where:** `Code/Grav/CLAUDE.md`, ~270 lines
- **What:** the density-sweep / beta1 section (~60 lines) is an excellent decision record
  but a newcomer cannot separate settled fact from working note.
- **Proposed action (propose only, author decides):** keep `CLAUDE.md` as the stable
  reference -- pipeline order, conventions, file contracts, current numbers -- and move the
  narrative to `Code/Grav/DECISIONS.md`: the beta1 mechanism and its falsified hypotheses,
  the density-tolerance derivation history, the velocity-channel redesign, the settled-rule
  bug. Rule: if it answers "what is true now" it stays; if it answers "why we chose this
  and what we ruled out" it moves, with a one-line pointer left behind.
- **Effort:** M

---

## Not confirmed / false positives (recorded so they are not re-raised)

- **`Adhoc/visualise_line4.py --cba` does NOT crash.** An agent reported a `KeyError` on
  `SE_lsq` at `:175-177` in CBA mode. Checked: `bouguer_anomaly_decay_rho1p875_with_TC.csv`
  **and** the plain SBA file both carry an `SE_lsq` column. `fig:grav-result-l4` reproduces.
- **The legacy chain still runs.** `drift_correction.py` and `station_means.py` both read
  files that exist with every column they index present; an agent re-executed
  `station_means.weighted_mean` and `drift_correction.correct_line` against the on-disk
  data read-only -- 124/124 stations both times. Two caveats, neither breaking:
  `simple_drift_decay.csv` on disk is stale (2026-06-12 vs an input of 2026-08-01), and
  `drift_correction.py:160` timestamps with `Time_first` while
  `drift_correction_lsq.py:311` uses `Time_mid` -- so the "comparison" is not like-for-like.
- **`Inversion/` as reference architecture: CONFIRMED, with named exceptions.**
  `plot_misfit.py`, `plot_misfit_row.py`, `plot_model_terrain.py` read artifacts and never
  run the search. `sample_ensemble` is called from `run_inversion.py` only -- the MC seam is
  clean. The grid-search seam has four exceptions: `plot_sensitivity.py` (documented),
  `sweep_density.py` and `freedepth.py` (self-documented), `inspect_beta1.py` (not
  documented anywhere). `CLAUDE.md:115-117` names only the first.

---

## Appendix -- thesis traceability (draft of [2])

Figures, all CONFIRMED unless noted. `save_figure(fig, name, folder)` writes
`thesis-overleaf/<folder>/<name>.pdf` (`Code/plot_utils.py:75,152`).

| Thesis label | Figure file | Producing script |
|---|---|---|
| `fig:decay-examples` | `Grav/decay_examples` | `Adhoc/decay_examples.py:152` |
| `fig:decay-l2..l5` | `Appendices/Grav decay fits/decay_line{2..5}` | `station_decay.py:346` |
| `fig:grav-detrend` | `Grav/detrend_fits` | `detrend_regional.py:361` |
| `fig:grav-detrended-residuals` | `Grav/detrended_residuals` | `detrend_regional.py:321` |
| `fig:grav-result-l4` | `Grav/line4_combined_CBA_rho1p875_seSBA` | `Adhoc/visualise_line4.py:240` |
| `fig:residuals-grav` | `Grav/lsq_residuals_hybrid_decay` | `Inspect/inspect_lsq_residuals.py:189` |
| `fig:inversion-fit` | `Inversion/misfit_row` | `Inversion/plot_misfit_row.py:98` |
| `fig:inversion-terrain-l3-circle` | `Inversion/terrain_model_line3_circle` | `Inversion/plot_model_terrain.py:401` |
| `fig:inversion-terrain-l3-ellipse` | `Inversion/terrain_model_line3_ellipse` | same |
| `fig:inversion-terrain-l5` | `Inversion/terrain_model_line5_circle` | same |
| `fig:sensitivity-picks` | `Inversion/sensitivity_picks` | `Inversion/plot_sensitivity.py:184` |
| `fig:sensitivity-velocity` | `Inversion/sensitivity_velocity` | `Inversion/plot_sensitivity.py:211` |
| `fig:freedepth` | `Inversion/freedepth` | `Inversion/freedepth.py:190` |
| `fig:freedepth-terrain-l3/l5` | `Inversion/freedepth_terrain_line{3,5}` | `Inversion/plot_freedepth_terrain.py:258` |
| `fig:density-sweep` | `Inversion/density_sweep` | `Inversion/sweep_density.py:249` |
| `fig:grav-loops` | `Equipment and Data Acquisition/GravimeterLoopsSchematic.pdf` | **UNKNOWN -- no script** |
| `fig:workflow-grav`, `fig:workflow-inversion` | `figures/workflow_*.tex` | hand-written TikZ |
| `fig:grav-synthetic`, `fig:camacho-regional-trend` | external images | not ours |

Tables. Only one is generated; the rest are hand-transcribed from script stdout.

| Thesis label | Source |
|---|---|
| `tab:decay-fits` | **GENERATED** by `make_decay_table.py:30,73` (`\input` at `main.tex:1436`) |
| `tab:lsq_results` | hand-written; numbers from `Inspect/inspect_lsq.py` |
| `tab:detrend` | hand-written; numbers from `detrend_regional.py:159-199` |
| `tab:inversion-results` | hand-written; numbers from `run_inversion.py:59` |
| `tab:freedepth` | hand-written; numbers from `freedepth.py:213-232` |
| `tab:density-sweep` | hand-written; numbers from `sweep_density.py:288-300` |
| `tab:corr_budget`, `tab:tc_perline` | **UNKNOWN generator -- no script prints these** |
| `tab:grav-acquisition`, `tab:lsq_symbols`, `tab:inv-config`, `tab:inv-grid`, `tab:unc-channels`, `tab:se-budget` | hand-written |

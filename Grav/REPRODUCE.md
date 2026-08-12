# Reproducing the gravimetry results

Written for a successor who has never seen this project. It answers three questions:
what to run and in what order, which thesis figure/table each script produces, and what
**cannot** be regenerated because it was made by hand.

Environment: `lacorona-lunarleaper-thesis`, built with `conda env create -f
../environment.yml`. Run scripts from the folder they live in. Paths all come from
`grav_utils.py` -- nothing needs configuring.

---

## 1. The data chain -- one command

```
python run_pipeline.py
```

That regenerates every CSV the figures, tables and inversion are built from:

| Step | Script | Writes (in `Data/Gravimetry/Processed/`) |
|---|---|---|
| 0 | `filter_gravimetry.py` | `filtered_gravimetry_all.csv` |
| 1 | `station_decay.py` | `station_gravity_decay.csv`, `decay_fits.csv` |
| 2 | `drift_correction_lsq.py` | `lsq_drift_decay.csv`, `lsq_drift_loops_decay.csv` |
| 3 | `apply_corrections.py` | `bouguer_anomaly_decay_rho{X}.csv` (SBA) |
| 4 | `integrate_corrections.py` | `..._colleague.csv`, `..._rho{X}_with_TC.csv` (CBA) |
| 5 | `detrend_regional.py` | `..._rho{X}_detrended.csv`, `detrend_trend_params_rho{X}.csv` |

Exit code is 0 only if all steps succeeded.

**Not run by `run_pipeline.py`, on purpose:**

- `combine_gravimetry.py` builds `combined_gravimetry.csv` from the raw CG-5 dumps, the
  field notes and the GNSS export. It reads **raw acquisition data**, which is frozen, so
  it is a one-time step. Use `run_pipeline.py --combine` if you really need it.

## 2. The inversion

```
cd Inversion
python run_inversion.py                          # the 3 thesis cases (untruncated)
python run_inversion.py --line 3 --truncate 10 15 # the truncated comparison cases
```

`run_inversion.py` is the ONLY script that runs the inversion. It writes one `.npz`
artifact per case to `Results/Grav/Inversion/artifacts/`; every plot script reads those
artifacts and never re-runs the search. Untruncated cases take ~2 min each, truncated
ones ~25 min.

Exceptions that legitimately run the engine themselves (each says so in its docstring):
`plot_sensitivity.py`, `sweep_density.py`, `freedepth.py`, `inspect_beta1.py`.

`sweep_density.py` re-runs the whole chain at many densities; it calls
`detrend_regional.py --no-plots` so it cannot clobber the canonical rho = 1.875 figures.

## 3. Figures and tables

```
python visualise_lsq.py ; python visualise_CBA.py
python make_decay_table.py            # -> thesis-overleaf/Appendices/decay_fits_table.tex
python make_thesis_tables.py --check  # verifies tab:corr_budget + tab:tc_perline
cd Inversion && python plot_misfit_row.py ; python plot_model_terrain.py ...
```

Figures land in `Results/Grav/` as browse PNGs; `plot_utils.save_figure` writes the thesis
PDFs straight into the Overleaf clone (`THESIS_REPO`, default `C:\Users\jj_ve\thesis-overleaf`).

### Which script makes which thesis figure

| Thesis label | Producing script |
|---|---|
| `fig:decay-examples` | `decay_examples.py` |
| `fig:decay-l2..l5` | `station_decay.py` (appendix grids) |
| `fig:grav-detrend`, `fig:grav-detrended-residuals` | `detrend_regional.py` |
| `fig:grav-result-l4` | `visualise_line4.py` |
| `fig:residuals-grav` | `Inspect/inspect_lsq_residuals.py` |
| `fig:inversion-fit` | `Inversion/plot_misfit_row.py` |
| `fig:inversion-terrain-*` | `Inversion/plot_model_terrain.py` |
| `fig:sensitivity-picks`, `fig:sensitivity-velocity` | `Inversion/plot_sensitivity.py` |
| `fig:freedepth` | `Inversion/freedepth.py` |
| `fig:freedepth-terrain-l3/l5` | `Inversion/plot_freedepth_terrain.py` |
| `fig:density-sweep` | `Inversion/sweep_density.py` |

`decay_examples.py` and `visualise_line4.py` were moved OUT of `Adhoc/` on 2026-08-12
(they produce live thesis figures, so they were misfiled; `Adhoc/` is now gone).
`Inspect/` still holds one figure producer and one load-bearing helper:
`inspect_lsq_residuals.py` makes `fig:residuals-grav` and imports `inspect_lsq.py`.

### Which script backs which thesis table

| Thesis label | Source |
|---|---|
| `tab:decay-fits` | **generated** by `make_decay_table.py` (`\input` in main.tex) |
| `tab:corr_budget`, `tab:tc_perline` | **checked** by `make_thesis_tables.py --check` |
| `tab:se-budget` | **checked** by `make_thesis_tables.py --check` (`se_budget()`). Channels from `invert_tube.size_area_se` (`area_se_data/pick/vel/det/tot`), stored in each artifact by `run_inversion.py`; the MC column is the SD of the artifact ensemble areas. All 18 cells reproduce exactly. |
| `tab:detrend` | numbers printed by `detrend_regional.py` |
| `tab:lsq_results` | numbers printed by `Inspect/inspect_lsq.py` |
| `tab:inversion-results` | numbers printed by `run_inversion.py` |
| `tab:freedepth` | numbers printed by `freedepth.py` |
| `tab:density-sweep` | numbers printed by `sweep_density.py` |

Only `tab:decay-fits` is written directly into the thesis. The rest are typed into
`main.tex`; the scripts above print the same numbers so they can be checked.

---

## 4. MANUAL ARTIFACTS -- these cannot be regenerated

Do not waste time looking for a script. There isn't one.

| Artifact | What it is | If you need to change it |
|---|---|---|
| `fig:grav-loops` (`Equipment and Data Acquisition/GravimeterLoopsSchematic.pdf`) | Hand-drawn schematic of the survey loop design. | Edit the source in `Figure sources/`. |
| `fig:workflow-grav`, `fig:workflow-inversion` | Hand-written TikZ, live in `thesis-overleaf/figures/workflow_*.tex`. | Edit the TikZ directly. |
| `fig:grav-synthetic`, `fig:camacho-regional-trend` | External figures from the literature, not produced here. | Not ours -- re-cite. |
| `tab:grav-acquisition`, `tab:lsq_symbols`, `tab:inv-config`, `tab:inv-grid`, `tab:unc-channels` | Hand-written descriptive tables (symbols, configuration, channel definitions). They describe the method rather than reporting computed results. | Edit `main.tex`. |

`tab:se-budget` was listed here until 2026-08-12 and does NOT belong: every cell is a
calculated area-uncertainty contribution, and all 18 reproduce from the artifacts. It is
in the s3 table above. Do not confuse it with `tab:unc-channels`, which is the channel
*definitions* table and is genuinely descriptive.

### Two cells that need a footnote (both L4, both understood)

The `tab:tc_perline` **"Station SE" column is the MEDIAN `SE_lsq` over NON-BASE stations**,
rounded half-up. The base station's SE is exactly 0 by datum definition, so averaging it in
would be meaningless. Raw values: L2 0.013808, L3 0.020285, L4 0.013541, L5 0.028816 ->
0.014 / 0.020 / 0.014 / 0.029, i.e. **the thesis row is correct**. (An earlier version of
this file said the column could not be reproduced. That was wrong: the base station had
been left in, which pulled every line toward zero.)

Two L4 cells still differ from the thesis, and both are benign:

| cell | thesis | now | why |
|---|---|---|---|
| L4 Station SE | 0.014 | 0.013 | Genuine pipeline-state difference, worth 0.0001 mGal. The 2026-08-01 `TAU_MIN` fix moved the raw median 0.013541 -> 0.013447, which crosses the 3-dp rounding boundary. Confirmed by rebuilding the 2026-06-11 state (`ed6f723`). |
| L4 TC Std | 0.040 | 0.041 | Transcription slip. The raw value is 0.041143 and its input (`LL_gravity_corrections.csv`) has not changed since 12 June, so this one cannot be a pipeline-state effect. |

`make_thesis_tables.py --check` reports exactly these two and nothing else. Neither is
worth changing in a frozen thesis; do not "fix" either side.

### One stale sentence in the Discussion

`main.tex:1002` quotes the inversion SEs as 40 / 28 / 35 where the table, the Conclusion and
the defence deck all say 41 / 24 / 36. Those prose numbers come from a run made BEFORE the
2026-07-30 velocity-channel redesign: the ellipse value of 28 is unreachable with the
current engine (24-25 at any plausible velocity sigma) but the pre-2026-07-30 engine gives
27.1-27.2. See the root `QandA.md` (2026-08-12). Author's call; nothing changed.

---

## 5. Verifying you have not broken anything

`goldenmaster.py` freezes every numerical output so a refactor can be proved
non-regressing:

```
python goldenmaster.py snapshot   # once, BEFORE editing
python goldenmaster.py check      # after every change -- must PASS
```

It compares 74 processed CSVs and the inversion artifacts with an absolute tolerance of
1e-12, and exits non-zero on any deviation. Figures are deliberately not covered: PDF/PNG
bytes differ between runs even with identical data, so verify the numbers instead.

## 6. Legacy / comparison scripts (not in the main chain)

`Legacy/` holds finished one-offs, kept for their decision history rather than deleted:
`export_stations.py` (one-time QGIS export), `visualise_lines.py` (plots the superseded
simple-drift output), `inspect_durations.py` (one-time occupation-time check).
`tests/inspect_lsq_line2.py` is a print-only diagnostic -- it was named
`test_drift_correction_lsq.py`, which implied coverage it never had.

- `drift_correction.py` (simple linear drift) and `station_means.py` (station means) are
  the pre-LSQ / pre-decay methods, kept for comparison. Both still run against current
  inputs. Two caveats: the on-disk `simple_drift_decay.csv` is older than its input, and
  `drift_correction.py` timestamps with `Time_first` while the LSQ uses `Time_mid`, so the
  comparison is not exactly like-for-like.
- `run_pipeline.py --all` re-runs the legacy filtering configs. Note this also rewrites
  `filtered_gravimetry_all.csv`, which is the MAIN chain's input.

## 7. Orphan PDFs in the thesis repo (2026-08-12) -- LISTED, NOT DELETED

These gravity PDFs sit in `thesis-overleaf/` but no `\includegraphics` references them.
Nothing here has been removed: the Overleaf repo belongs to the author, and an
"unreferenced" figure may still be wanted for the defence.

| File | Status |
|---|---|
| `Inversion/area_summary.pdf` | INTENTIONAL. Not in main.tex, but cited by the defence deck. Keep. |
| `Grav/detrend_line{2,3,5}.pdf` | Superseded by the combined `detrend_fits.pdf`. Probably prunable. |
| `Grav/line4_combined.pdf` | Older name; the thesis uses `line4_combined_CBA_rho1p875_seSBA.pdf`. |
| `Inversion/invert_line3_circle.pdf`, `invert_line3_ellipse.pdf`, `invert_line5_circle.pdf` | Superseded by `misfit_row.pdf` + the terrain figures. |

Re-run the check with `Code/Grav/` tooling any time; it is a plain scan of every `.tex`
for `\includegraphics` targets.

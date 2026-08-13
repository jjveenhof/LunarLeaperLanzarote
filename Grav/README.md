# Gravimetry -- La Corona lava tube

CG-5 relative gravity survey processing and the GPR-constrained inversion of the tube
cross-section. Written for a successor who has never seen this project: what to run and in
what order, how the method works, and what cannot be regenerated because it was made by
hand.

`DECISIONS.md` holds the choices the code cannot explain on its own. Thesis figure/table
-> producer mapping is in `Code/TRACEABILITY.md`.

Environment: `lacorona-lunarleaper-thesis`, built with `conda env create -f
../environment.yml`. Run scripts from the folder they live in -- all paths come from
`grav_utils.py` and nothing needs configuring.

---

## 1. The data chain -- one command

```
python run_pipeline.py
```

Regenerates every CSV that the figures, tables and inversion are built from, into
`Data/Gravimetry/Processed/`:

| Step | Script | Writes |
|---|---|---|
| 0 | `filter_gravimetry.py` | `filtered_gravimetry_all.csv` (config "all": every QC-passed reading) |
| 1 | `station_decay.py` | `station_gravity_decay.csv` (g_inf per station), `decay_fits.csv` |
| 2 | `drift_correction_lsq.py` | `lsq_drift_decay.csv`, `lsq_drift_loops_decay.csv` (LSQ network adjustment, datum g_base = 0) |
| 3 | `apply_corrections.py` | `bouguer_anomaly_decay_rho{X}.csv` -- SBA (FAC + latitude + Bouguer slab) |
| 4 | `integrate_corrections.py` | `..._colleague.csv`, `..._rho{X}_with_TC.csv` -- CBA (adds the terrain correction) |
| 5 | `detrend_regional.py` | `..._rho{X}_detrended.csv`, `detrend_trend_params_rho{X}.csv` |

Exit code is 0 only if every step succeeded.

**Not run by `run_pipeline.py`, on purpose:** `combine_gravimetry.py` builds
`combined_gravimetry.csv` from the raw CG-5 dumps, the field notes and the GNSS export. It
reads **raw acquisition data**, which is frozen, so it is a one-time step. Use
`run_pipeline.py --combine` if you genuinely need it.

Other flags: `--with-simple-drift` (legacy linear drift, for comparison) and `--all` (also
re-runs the legacy drop5/keepLast station-mean configs). **`--all` also rewrites
`filtered_gravimetry_all.csv`, which is the main chain's input.**

### Shared code

`grav_utils.py` holds paths, rho filename formatting, normal gravity, the FAC and Bouguer
factors, and along-profile distance. Use it rather than redefining any of them.

### The regional de-trend

`detrend_regional.py` fits a robust, uncertainty-weighted per-line trend to the CBA (Huber
IRLS, weights 1/SE^2) and reports chi2_red per line. It uses **gravity only -- no GPR or
LiDAR -- to avoid an inverse crime.** It also projects the island-scale regional map
gradient (Camacho et al. 2001; `MAP_GRAD_MAG`/`AZ` in the script) onto each line as a check.

- Line 4 is skipped: bent geometry, not used for inversion.
- **Line 2's cave low is off-centre, so its self-fit is contaminated** -- adopt the map or
  Line-5 gradient there instead.
- **Lines on different bases are not on a common datum** (Lines 3 and 4 share one; Lines 2
  and 5 do not). Trends are therefore fit per line, never as one cross-line plane.

### Conventions

- All anomalies are relative to the base station (g_base = 0). Corrections are applied
  relative to the per-line per-day base mean, so RTK day-to-day bias cancels within a day.
- Default density rho = 1.875 g/cm3 (matching the colleague's corrections). Filenames
  encode it via `grav_utils.rho_str` (1.875 -> `rho1p875`); never round it.
- SE columns strictly match their value column (SBA <-> SE_SBA, CBA <-> SE_CBA). No silent
  substitution when an SE is unavailable.
- A station counts as **settled** if the fit did not converge, OR |A| < SE_A, OR tau <
  `TAU_MIN` (0.5 min -- a degenerate spike fit). Settled stations report the weighted mean;
  decaying ones the fitted g_inf. `main()` was missing the tau term until 2026-08-01, so
  `decay_fits.csv` said 10 settled while the figures labelled 12. Fixed; 12 now matches the
  thesis text (10 that had time + 2 judged settled). Propagation was contained to Line 4
  (1-2 uGal; LSQ max 2.5 uGal on L4, exactly 0 on Lines 2/3/5 despite L3 and L4 sharing a
  base) -- no inversion input moved, so no published number changed.
- **The colleague's corrections file** is `Data/Gravimetry/Processed/LL_gravity_corrections.csv`
  (`FA_correction`, `BA_correction`, `Terrain_correction`), all in mGal. The terrain
  correction is small: mean ~0.10 mGal, varying only ~0.05 mGal along Line 3 (std ~0.016,
  ~4% of the cave anomaly), most of which the detrend absorbs. *The superseded
  `LL_gravity_corrections_old.csv` has unphysical ~200 mGal TC values -- ignore it.*

### Appendix decay-fit figures

`station_decay.py` also writes the per-line appendix grids, and `make_decay_table.py` turns
`decay_fits.csv` into the companion LaTeX table (two 62-row blocks on one page). The panels
show **shape only** -- y is relative and the title carries just station and tau -- so the
absolute gravity lives in that table.

> **Figure-sizing gotcha.** Those grids used to be built 16.8 in wide and squeezed into
> `\textwidth` by LaTeX, so 7 pt text landed on the page at ~2.7 pt. Build appendix grids at
> their FINAL width (`FIG_W_IN`) and pt means pt. Same for legend and title reserves -- use
> absolute inches, not figure fractions, or the gap grows with the row count.

---

## 2. The inversion

```
cd Inversion
python run_inversion.py                           # the 3 thesis cases (untruncated)
python run_inversion.py --line 3 --truncate 10 15 # the truncated comparison cases
```

`run_inversion.py` is the **only** script that runs the inversion. It writes one `.npz`
artifact per case to `Results/Grav/Inversion/artifacts/`; every plot script reads those
artifacts and never re-runs the search.

Exceptions that legitimately run the engine themselves (each says so in its docstring):
`plot_sensitivity.py`, `sweep_density.py`, `freedepth.py`, `inspect_beta1.py`.
`sweep_density.py` re-runs the whole chain at many densities and calls `detrend_regional.py
--no-plots` so it cannot clobber the canonical rho = 1.875 figures.

### Architecture -- compute is detached from plotting

One driver runs the inversion and Monte Carlo once and persists artifacts; every plot reads
them. That seam is `inversion_io.py` (`save_artifact` / `load_artifact` / `cfg_of`).

- **`invert_tube.py`** -- the pure numerical engine. No CLI, no matplotlib, no globals,
  nothing runs on import. Dense grid search over (size, x0) with a DC baseline fitted
  analytically at every grid point (relative gravity means an arbitrary datum; dof = n-3).
  Forward model, the `size_area_se` budget and the `sample_ensemble` MC are all pure
  functions taking an explicit `InvCfg`. Two modes: **circle** (fix the GPR ceiling, fit R)
  and **ellipse** (fix ceiling and floor, fit half-width a).
- **`forward_polygon.py`** -- fast analytic 2-D Talwani polygon forward, pure numpy.
  `forward_fem.py` is the pyGIMLi equivalent, for validation only and needing an env that
  has `pygimli` (the project env deliberately does not).
- **Plot scripts read artifacts, never run the inversion:** `plot_misfit_row.py`,
  `plot_misfit.py`, `plot_model_terrain.py` (best-fit tube under the measured surface, true
  scale, auto-overlaying the LiDAR ground truth). `plot_sensitivity.py` is the exception --
  it runs the engine for a pick sweep no artifact covers.

**Uncertainty budget**, combined in quadrature: data (chi2-rescaled grid interval) + GPR
picks (analytic propagation) + velocity (systematic depth scaling) + detrend slope. The
truncation bracket is kept separate, as a systematic.

**GPR inputs are final** (2026-07-16, both lines migrated at v = 0.125): L3 ceiling 3.8 /
floor 14.6 m (air-gap corrected); L5 ceiling 8.6 m, no floor, so circle-only.

---

## 3. Results and settled questions

**LiDAR-validated.** L3 untruncated ellipse 193 +/- 24 vs LiDAR 203 m^2 (~5%); L5 circle
167 +/- 36 vs 182 (~8% low, chi2_red 1.9). Both inside 1 SE. The reported area SEs are the
**MC** values.

Two qualifications on that result:

- The L3 roof aligns with the LiDAR void top, but **the L5 8.6 m ceiling sits ~5.7 m above
  the LiDAR roof** (~14.3 m depth). The area validates; the L5 roof-alignment argument is
  weaker.
- **Ground truth favours the UNTRUNCATED 2-D model** -- the pit-truncation correction
  overshoots (truncated L3 gives 210-320). The choice between the two is *model
  selection*, not input tuning, so it stays free of inverse crime.

The velocity channel was fixed on 2026-07-30 to a common-mode **depth shift** by the
overburden (`ceiling*dv`), preserving cave height: the air-gap correction makes the void
height v_air-fixed, so only the ceiling scales with v_rock. This dropped the L3-ellipse
velocity channel from 13 to 7 m^2. `velocity_sigma` = 0.015 m/ns since 2026-07-29.

All profile plots read N (left) -> S (right), matching the GPR sections.

### Settled -- deliberately NOT swept, so they are not relitigated

- **Detrend model form:** assume linear. Short-profile linearisation; the regional field is
  linear over tens of metres. It is a justified assumption, not a fitted result.
- **Terrain correction:** treat as exact. The magnitude is tiny (~0.05 mGal variation on L3,
  ~4% of the cave anomaly, mostly absorbed by the baseline and detrend), so its uncertainty
  cannot move the area.
- **2-D vs 3-D / finite tube length:** already bracketed by the truncation runs -- truncating
  toward the pit *is* the finite-strike correction, the dominant 2-D departure. Full 3-D FEM
  is out of scope as second-order. The truncation bracket is therefore the
  2-D-limitation bound.

### Free-depth grid search (`freedepth.py`, done 2026-08-01)

Circle only; the ellipse variant was not run. Stacks the existing (size, x0) search over a
ceiling grid into a cube; dof = n-4.

L3: c = 2.5 m (1SE 1.75-3.25), A = 196 (172-222), chi2_nu 5.3 -- **tight, so L3 does
separate size from depth; L5 does not.** L5: c = 21.8 m (1SE 14.0 to unbounded), A =
437 (>= 249), chi2_nu 1.5.

Gravity alone puts the LiDAR ceiling at 0.9 sigma and the L5 GPR pick at 2.3 sigma, giving
independent support for the "wrong arrival" reading *without* using LiDAR as a constraint.
On L3 both references sit at ~1.5 sigma.

> `CEIL_GRID` runs to 40 m. Extending it did NOT close L5's valley, and past ~39 m the best
> radius hits the top of `RADIUS_GRID` (19.9 m); `analyse()` guards against reporting the
> fake upper bound this produces. **L5's spread is bounded by the search grid, not the
> data.**

`plot_freedepth_terrain.py` is the terrain twin, deliberately sharing
`plot_model_terrain.py`'s layout. **The one substantive difference:** its
ensemble is drawn from the chi2 cube (weight ~ `exp(-dchi2/2kappa^2)`), a data-only
posterior, not `sample_ensemble`'s input-perturbation posterior. The spreads are not
comparable. Detrend uncertainty is not in it -- deferred, not judged negligible.

### Density chain-sweep (`sweep_density.py`, done 2026-07-30)

The question was turned around: instead of assuming a rho range and reporting an area
bracket, sweep wide (1.4-2.8) and report the density **tolerance**.

The response is an offset hyperbola `A = a/rho + b` (R2 >= 0.997); equivalently `rho*A = a +
b*rho`, so `b` is the drift of the recovered mass deficit with rho. Fitted (beta0, beta1):
L3 circle 738/-161, L3 ellipse 506/-75, L5 circle 317/-1 -- **L5 is pure 1/rho, L3 is not.**

Tolerance (rho departure before the induced area change exceeds 1 SE): **L3 +/-0.156
(circle) / +/-0.147 (ellipse), L5 +/-0.323 g/cm3** -- 8.3 / 7.9 / 17.2% on the binding
(downward) side. The SE reference is the MC SE (41.2 / 24.5 / 35.6 m^2), switched
2026-08-01 from the analytic budget because the thesis reports the MC values; a
tolerance quoted against an SE that appears nowhere in the tables would be unusable.

The tolerance is the closed-form crossing of the fitted hyperbola with the A0 -/+ SE band,
`rho = beta0/(A0 -/+ SE - beta1)` -- not an interpolation of the swept points (which
inherited the size-grid area quantisation) and not the linear `SE*rho0/beta0` estimate.
Useful identity: `beta0 = rho0*(A0 - beta1)`, so relative tolerance ~ `(SE/A0)/(1 -
beta1/A0)`. All three have SE/A0 = 13-21%, and **it is beta1 that tightens L3, not a
better-constrained area** -- L3 circle has a *larger* SE than L5 (41 vs 36 m^2) yet half the
tolerance.

**Mechanism** (`inspect_beta1.py`, redone properly 2026-08-01 -- this supersedes an earlier
"unresolved / three falsified hypotheses" note, withdrawn because its
topographic-curvature estimate was under-specified).

rho enters in two places and both matter: the **chain** (Bouguer and TC scale with rho, so
the detrended CBA itself moves) and the **contrast**. Freezing the data at rho0 so only the
contrast varies, beta1 is already -94/-23/-53 with the chain off -- so much of beta1 is the
*inversion*, because the fitted shape is constrained (circle top pinned at the ceiling, only
R free) and the anomaly width therefore changes with R too. The shape-free mass-deficit
argument does not transfer exactly.

The chain contribution (full minus chain-off) is -67/-52/**+52**: comparable in magnitude,
**opposite in sign on L5**. The sign is explained by the data alone, with no inversion:
`d(CBA)/drho` at the cave minus the flanks is **+44.6 uGal per g/cm3 on L3** (the low gets
shallower with rho -> less area -> beta1 down) but **-35.2 on L5** (the low deepens -> beta1
up).

> **Therefore L5's near-pure hyperbola is a COINCIDENCE** -- a cancellation of two comparable
> terms, not evidence that L5 obeys theory or is immune to the feedback.

Ruled out as the between-line discriminator, both by controlled tests:

- **Depth.** Force both lines to the same ceiling (circle on both). At 3 m, L3 is -152 vs L5
  -13 -- 12x apart at identical geometry. Within L3, deeper makes it *worse* (-152 -> -293
  over ceiling 3 -> 13 m), the opposite of the "deeper feels topography less" story. L5 stays
  flat (-13 -> -4) at every depth.
- **Size.** Two independent controls, both negative. (i) Forcing the ceiling also moves the
  recovered area, giving matched-area pairs across lines: L3 at ceiling 3 m (A = 206) vs L5
  at ceiling 11 m (A = 201) gives beta1 -152 vs -5, 30x apart at matched size. (ii) A real
  size sweep -- an ellipse of imposed height on a fixed centroid (9.2 m), same geometry on
  both lines, so depth and size are matched row by row. Within L3, beta1 swings **+81 ->
  -98** while the area stays 153-202 m^2, and is **non-monotonic in height: beta1 is not a
  function of area.** (So the apparent `beta1/A ~ -0.7` in the ceiling sweep was depth doing
  the work, since size and depth move together there, so **that ratio is meaningless**.) L5
  stays flat (-19 to +19) throughout.

> Caveat: the first test holds the CEILING fixed (centroid moves), the
> second holds the CENTROID fixed (ceiling moves 7.2 -> 1.2 m). Neither alone is a perfect
> depth control; together they bracket it, and L5 is flat under both. The one within-L3 trend
> consistent across both is that a larger *vertical extent* drives beta1 more negative -- area
> does not.

Take-away: both the correction and the
inversion feedback affect beta0 and beta1; L5 being pure is a coincidence; the two questions
that matter for lunar application are depth and size, and neither is the cause; one-at-a-time
sensitivity machinery breaks down for a chain-coupled parameter like this. With only two
lines, line identity is confounded with everything else.

*Pipeline gaps closed to enable this:* TC is now rescaled by rho/1.875 in
`integrate_corrections.py` (TC is linear in rho, so no rerun by the colleague was needed);
`detrend_regional.py --no-plots` exists because its figure names do not encode rho and
sweeping would clobber the canonical figures; and `InvCfg.density` plus `it.det_file(rho)` /
`it.trend_file(rho)` make the inversion follow the swept rho.

### Still open

**LiDAR-pick robustness.** Re-invert L3/L5 with ceiling and floor read off
`Data/LiDAR/lidar_line{3,5}.csv` as the constraint, and compare the recovered area to the
GPR-pick area. Similar areas would mean the result is insensitive to ~1 m pick differences.

> This is **strictly a sensitivity-to-constraint test, not a second validation** --
> feeding in LiDAR geometry and then comparing to the LiDAR area double-uses the ground truth
> and is an inverse crime.

The free-depth and robustness results look contradictory and are not: the depth prior is **necessary**, but its **precision is
forgiving**. A pick error of plausible size does not change the result, so residual bias in the picks
is immaterial.

---

## 4. Verifying you have not broken anything

```
python goldenmaster.py snapshot   # once, BEFORE editing
python goldenmaster.py check      # after every change -- must PASS
python -m pytest tests/
```

`goldenmaster.py` compares 74 processed CSVs and the inversion artifacts at an absolute
tolerance of 1e-12 and exits non-zero on any deviation. Figures are deliberately not
covered: PDF and PNG bytes differ between runs even with identical data, so verify the
numbers instead.

`tests/test_goldenmaster_coverage.py` asserts the manifest is complete, so a newly added
output cannot go silently unprotected.

---

## 5. What cannot be regenerated

Do not waste time looking for a script -- there isn't one. See `Code/TRACEABILITY.md` for the
full list, including the hand-drawn loop schematic, the TikZ workflow figures, and the
descriptive tables. `Code/TRACEABILITY.md` also records the two known L4 cells in
`tab:tc_perline` and the definition of its Station SE column.

One known internal discrepancy, recorded so it is not mistaken for a pipeline error:
**`main.tex:1002` quotes the inversion SEs as 40 / 28 / 35**, where `tab:inversion-results`,
`tab:se-budget` and the Conclusion all say 41 / 24 / 36. Those prose numbers come from a run
made before the 2026-07-30 velocity-channel redesign -- the ellipse value of 28 is
unreachable with the current engine (24-25 at any plausible velocity sigma), but the
pre-2026-07-30 engine gives 27.1-27.2. The thesis is frozen; nothing was changed.

---

## 6. Legacy and comparison scripts

`Legacy/` holds finished one-offs, kept for their decision history rather than deleted:
`export_stations.py` (a one-time QGIS export), `visualise_lines.py` (plots the superseded
simple-drift output), and `inspect_durations.py` (a one-time occupation-time check).
`tests/inspect_lsq_line2.py` is a print-only diagnostic despite living under `tests/`.

`drift_correction.py` (simple linear drift) and `station_means.py` (station means) are the
pre-LSQ and pre-decay methods, kept for comparison. Both still run against current inputs.
Two caveats: the on-disk `simple_drift_decay.csv` is older than its input, and
`drift_correction.py` timestamps with `Time_first` while the LSQ uses `Time_mid`, so the
comparison is not exactly like-for-like.

`Inspect/` holds diagnostics (LSQ stats, base stations, decay residuals, corrections
comparison). It is not purely diagnostic: `inspect_lsq_residuals.py` produces a thesis
figure and imports `inspect_lsq.py`.

---

## 7. Orphan PDFs in the thesis repo (listed 2026-08-12, NOT deleted)

These gravity PDFs sit in the thesis repo but no `\includegraphics` references them. Nothing
was removed.

| File | Status |
|---|---|
| `Inversion/area_summary.pdf` | **Intentional.** Not referenced by `main.tex`; kept deliberately. |
| `Grav/detrend_line{2,3,5}.pdf` | Superseded by the combined `detrend_fits.pdf`. Probably prunable. |
| `Grav/line4_combined.pdf` | Older name; the thesis uses `line4_combined_CBA_rho1p875_seSBA.pdf`. |
| `Inversion/invert_line3_circle.pdf`, `invert_line3_ellipse.pdf`, `invert_line5_circle.pdf` | Superseded by `misfit_row.pdf` plus the terrain figures. |

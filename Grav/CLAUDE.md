# Gravimetry Session

BEFORE ANYTHING ELSE: read QandA.md in this directory.

This file is loaded by sessions opened in Code/Grav/. The root CLAUDE.md
(loaded automatically alongside this) covers the overall project structure,
CRS, environment, and working conventions. The project root "Thesis Lunar Leaper"
is two levels up; data and results paths below are relative to the project root.

QandA.md entries directed here are tagged `From: [session] -> Grav`.

## Gravimetry Pipeline (Code/Grav/)
Run with `python run_pipeline.py`. Flags: `--with-simple-drift` (legacy linear drift
for comparison), `--all` (also reruns the legacy drop5/keepLast station-mean configs).

Main chain (the "decay" config):
1. `combine_gravimetry.py`     -> combined_gravimetry.csv  (CG-5 + GNSS + field notes; run manually)
2. `filter_gravimetry.py`      -> filtered_gravimetry_all.csv  (config "all": every QC-passed reading)
3. `station_decay.py`          -> station_gravity_decay.csv (g_inf per station) + decay_fits.csv (fit params)
4. `drift_correction_lsq.py`   -> lsq_drift_decay.csv + lsq_drift_loops_decay.csv
                                  (LSQ network adjustment, datum g_base = 0)
5. `apply_corrections.py`      -> bouguer_anomaly_decay_rho{X}.csv  (FAC + latitude + Bouguer slab = SBA)
6. `integrate_corrections.py`  -> bouguer_anomaly_decay_colleague.csv and ..._rho{X}_with_TC.csv
                                  (adds colleague's terrain correction -> CBA; skipped if his file is absent)

Parallel/legacy (NOT in the main chain): `drift_correction.py` (simple linear drift
-> simple_drift_{config}.csv) is an alternative to the LSQ step, kept for comparison only.
`station_means.py` (-> station_gravity_{config}.csv) is the legacy alternative to the decay fit.

Shared constants/helpers (paths, rho filename formatting, normal gravity, FAC/Bouguer
factors, along-profile distance) live in `grav_utils.py` -- use it instead of redefining them.

Visualisation: `visualise_lsq.py` (LSQ profiles), `visualise_CBA.py` (auto-detects CBA/SBA).
Diagnostics in `Inspect/` (LSQ stats, base stations, decay residuals, corrections comparison).
One-offs and legacy plots in `Adhoc/` (incl. `visualise_lines.py` for the simple-drift output).
Plots are saved under `Results/Grav/`.

Regional de-trend: `detrend_regional.py` fits a robust, uncertainty-weighted per-line trend
to the CBA (Huber IRLS, weights 1/SE^2; gravity only -- no GPR/LiDAR, to avoid an inverse
crime), reports chi2_red per line, writes residuals to
`bouguer_anomaly_decay_rho{X}_detrended.csv`, and projects the island-scale regional map
gradient (Camacho et al. 2001; set MAP_GRAD_MAG/AZ in the script) onto each line to check
the fit. Plots in `Results/Grav/Detrend/`. Line 4 skipped (bent geometry, not for inversion).
Note: Line 2's cave low is off-centre, so its self-fit is contaminated -- adopt the
map/Line-5 gradient there. Lines on different bases are NOT on a common datum (Lines 3&4
share one; Lines 2 and 5 do not), so trends are fit per line, never as one cross-line plane.

### Conventions
- All anomalies are relative to the base station (g_base = 0). Corrections (FAC, LAT, BC, TC)
  are applied relative to the per-line per-day base mean: RTK day-to-day bias cancels within a day.
- Default density rho = 1.875 g/cm3 (matches colleague). Filenames encode rho via
  `grav_utils.rho_str` (1.875 -> `rho1p875`); never round it.
- SE columns strictly match their value column (SBA <-> SE_SBA, CBA <-> SE_CBA);
  no silent substitution when an SE is unavailable.
- Colleague's corrections file: `Data/Gravimetry/Processed/LL_gravity_corrections.csv`
  (FA_correction, BA_correction, Terrain_correction). All values are in mGal by
  convention. The terrain correction is small: mean ~0.10 mGal, and on Line 3 it
  varies only ~0.05 mGal across the profile (std ~0.016, ~4% of the cave anomaly),
  most of which the detrend/baseline absorbs -- so it is a minor systematic for the
  inversion. (The superseded `LL_gravity_corrections_old.csv` has unphysical
  ~200 mGal TC values; ignore it.)

## GPR-constrained tube inversion (`Inversion/`)
Gravity-for-volume inversion of the La Corona tube on the detrended CBA residual.
Architecture: COMPUTE is detached from PLOTTING (refactor 2026-07-29). One driver
runs the inversion + Monte Carlo once and persists artifacts; every plot reads them.
- `forward_polygon.py` -- fast analytic 2-D Talwani polygon forward (pure numpy).
  `forward_fem.py` is the pyGIMLi FEM equivalent (validation/3-D only; needs the
  `pygimli` env). `inspect_*` scripts are validation diagnostics -- incl.
  `inspect_beta1.py`, the switch tests behind the density-offset mechanism (see below;
  reuses the per-rho chain CSVs already on disk, so it needs no pipeline rerun).
- `invert_tube.py` -- the pure NUMERICAL ENGINE (no CLI, no matplotlib, no globals,
  nothing runs on import). Dense grid search over (size, x0) with a DC baseline
  fitted analytically at every grid point (relative gravity -> arbitrary datum;
  dof = n-3); forward, `size_area_se` budget, `sample_ensemble` MC -- all pure
  functions taking an explicit `InvCfg` (velocity, velocity_sigma, sigma_pick,
  slope_se, truncate). Modes: circle (fix GPR ceiling, fit R) and ellipse (fix
  ceiling+floor, fit half-width a). Uncertainty budget combined in quadrature: data
  (chi2-rescaled grid interval) + GPR picks (analytic propagation) + velocity
  (systematic depth scaling) + detrend slope (from `detrend_trend_params_*.csv`);
  truncation kept separate as a systematic bracket.
- `run_inversion.py` -- THE driver, the ONLY script that runs the inversion. Builds
  an `InvCfg` per (line, mode, truncation) from `LINE_PRESETS` + CLI, computes best
  fit + chi2 surface + budget + 300-sample ensemble, writes one artifact each.
  CLI: `--line {3,5} --truncate inf 10 15 --ceiling --floor --modes --sigma-pick
  --velocity --velocity-sigma --seed --ensemble`. Run it after any input change.
- `inversion_io.py` -- artifact persistence (`save_artifact`/`load_artifact`/
  `cfg_of`); one `.npz` per case at `Results/Grav/Inversion/artifacts/` (gitignored,
  regenerable). This is the seam decoupling compute from plotting.
- GPR inputs FINAL (2026-07-16, BOTH lines migrated at v 0.125): L3 ceiling 3.8/floor
  14.6 m (air-gap corrected); L5 ceiling 8.6 m (no floor -> circle-only). No
  placeholders left.
- Plot scripts (READ artifacts, never run the inversion): `plot_misfit_row.py`
  (3-panel misfit surfaces, 1SE/2SE contours), `plot_misfit.py` (standalone per-mode
  surface, 1SE/2SE contours -- aligned with the row), `plot_model_terrain.py` (best-fit tube under the
  measured surface, true scale, auto-overlays the `Data/LiDAR/lidar_line{N}.csv` ground truth,
  ensemble drawn from the artifact). `plot_sensitivity.py` is the exception -- it
  RUNS the engine (pick sweep, no artifact covers it) with its own `InvCfg`; kept
  flexible for the planned sensitivity analyses.

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
- Inversion built + uncertainty budget complete; **LiDAR-validated** (FINAL GPR geom
  2026-07-16): L3 untruncated ellipse 193+/-24 vs LiDAR 203 m^2 (~5%); L5 circle
  167+/-36 vs 182 (~8% low, chi2_red 1.9). Both inside 1 SE. (Area SEs are the
  reported MC values; velocity_sigma = 0.015 m/ns since 2026-07-29 -- see
  [[update-gpr-velocity-picks]]. Velocity channel FIXED 2026-07-30 to a common-mode
  DEPTH SHIFT by the overburden (ceiling*dv), cave height preserved -- the air-gap
  correction makes the void height v_air-fixed, so only the ceiling scales with
  v_rock. This dropped the L3-ellipse velocity channel 13->7 m^2 (co-leading only on
  L5 now; circles unchanged). Applies to both size_area_se and sample_ensemble; the
  terrain-plot GPR-pick band uses ceiling*dv for both picks too.) L3 roof aligns with the
  LiDAR void top; NB the L5 8.6 m ceiling sits ~5.7 m above the LiDAR roof (~14.3 m
  depth) -- area validates but the L5 roof-alignment argument is weaker (flagged to GPR).
  Ground truth favors the UNTRUNCATED 2-D model -- the pit-truncation correction
  overshoots (truncated L3: 210-320). Frame as model selection, not input tuning
  (no inverse crime).
- All profile plots read N (left) -> S (right) to match the GPR sections.

### Remaining uncertainty / sensitivity work (planned 2026-07-07)
Settled -- NO sweep, reasons recorded so we don't relitigate:
- Detrend model form: assume LINEAR (short-profile linearisation; regional field is
  linear over tens of m). State as justified assumption only.
- Terrain correction: treat as EXACT. Magnitude tiny (~0.05 mGal var on L3, ~4% of the
  cave anomaly, mostly absorbed by baseline/detrend) -> its uncertainty can't move area.
- 2-D vs 3-D / finite tube length: ALREADY bracketed by the truncation runs (truncating
  toward the pit IS the finite-strike correction = dominant 2-D departure). Full 3-D FEM
  out of scope (2nd-order). Frame the truncation bracket as the 2-D-limitation bound.

Still to do (order was B -> A -> density; DENSITY IS DONE, B and A remain):
1. **Plan B -- LiDAR-pick robustness.** Re-invert L3/L5 with ceiling/floor read off
   `Data/LiDAR/lidar_line{3,5}.csv` as the constraint; compare recovered AREA to the GPR-pick area.
   Similar -> result insensitive to ~1 m pick differences. Frame STRICTLY as
   sensitivity-to-constraint, NOT a 2nd validation (feeding LiDAR geom + comparing to
   LiDAR area double-uses ground truth = inverse crime). Empirically bounds the total
   depth-constraint sensitivity, subsuming the rough guessed velocity/pick sigma.
2. **Plan A -- free-depth grid search (non-uniqueness).** Add depth as a search axis
   (circle: ceiling,R,x0; ellipse: ceiling,floor,a,x0), float DC, slice chi2 in the
   (depth, area) plane. Expect a BROAD soft depth-size valley (gravity has weak, not
   zero, depth resolution via anomaly width). Frame as quantifying the tightening:
   "gravity alone constrains ceiling to +/-X m; GPR pick reduces it to +/-Y m." Do NOT
   oversell as "unconstrained" -- a tight valley would backfire.
3. ~~**Density chain-sweep**~~ -- **DONE 2026-07-30** (`sweep_density.py`). Question was
   turned around: instead of assuming a rho range and reporting an area bracket, sweep
   WIDE (1.4-2.8) and report the density TOLERANCE. Results: response is an offset
   hyperbola `A = a/rho + b` (R2 >= 0.997); equivalently `rho*A = a + b*rho`, so b is
   the drift of the recovered MASS DEFICIT with rho. Fitted (beta0, beta1): L3 circle
   738/-161, L3 ellipse 506/-75, L5 circle 317/-1 -> L5 is pure 1/rho, L3 is not.
   Tolerance (rho departure before the induced area change exceeds 1 SE): **L3 +/-0.156
   (circle) / +/-0.147 (ellipse), L5 +/-0.323 g/cm3**, i.e. 8.3 / 7.9 / 17.2% on the
   binding (downward) side. The SE reference is the **MC** SE (SD of the artifact
   ensemble: 41.2/24.5/35.6 m^2) -- switched 2026-08-01 from the analytic `area_se_tot`
   budget (37.0/24.8/34.3) because the thesis reports the MC values in
   tab:inversion-results, and a tolerance quoted against an SE the reader cannot find
   there is a trap. `sweep_density.nominal_se()` now reads the artifact.
   NB the tolerance is the closed-form crossing of the FITTED HYPERBOLA with the
   A0 -/+ SE band, `rho = beta0/(A0 -/+ SE - beta1)` (switched 2026-08-01 from
   interpolating the swept points, which inherited the size-grid area quantisation --
   ~2-5 m^2, the same order as the fit residual -- and depended on the rho step; it
   moved the L3 ellipse 7.2 -> 7.9%). Not the linear `SE*rho0/beta0` estimate either. Useful identity: `beta0 = rho0*(A0 - beta1)`, so relative
   tolerance ~ `(SE/A0)/(1 - beta1/A0)` -- all three have SE/A0 = 13-21%, and it is
   beta1 that tightens L3, NOT a better-constrained area (L3 circle has a LARGER SE than
   L5, 41 vs 36 m^2, yet half the tolerance).
   Fig `density_sweep`, Table `tab:density-sweep`.
   MECHANISM (redone properly 2026-08-01, `inspect_beta1.py` -- supersedes the earlier
   "unresolved / three falsified hypotheses" note; the old topographic-curvature estimate
   was under-specified, do NOT resurrect it). rho enters in TWO places and both matter:
   (1) the CHAIN (Bouguer + TC scale with rho -> the detrended CBA itself moves) and
   (2) the CONTRAST. Switch test, freezing the data at rho0 so only the contrast varies:
   beta1 is ALREADY -94/-23/-53 with the chain off -- i.e. much of beta1 is the INVERSION,
   because the fitted shape is constrained (circle top pinned at the ceiling, only R free)
   so the anomaly WIDTH changes with R too, and the shape-free mass-deficit argument does
   not transfer exactly. Chain contribution (full minus chain-off) = -67/-52/**+52**:
   comparable magnitude, OPPOSITE SIGN on L5. Sign explained by the data alone (no
   inversion): d(CBA)/drho at the cave minus the flanks is **+44.6 uGal per g/cm3 on L3**
   (low gets shallower with rho -> less area -> beta1 down) but **-35.2 on L5** (low
   deepens -> beta1 up). => **L5's near-pure hyperbola is a COINCIDENCE, a cancellation of
   two comparable terms -- NOT evidence that L5 obeys theory or is immune to the
   feedback.** Do not claim otherwise in the thesis.
   RULED OUT as the between-line discriminator, both by controlled tests:
   - DEPTH: force both lines to the same ceiling (circle on both). At 3 m, L3 -152 vs
     L5 -13 (12x apart at identical geometry); and within L3 deeper makes it WORSE
     (-152 -> -293 over ceiling 3->13 m), the opposite of the "deeper feels topography
     less" story. L5 stays flat (-13 -> -4) at every depth.
   - SIZE: two independent controls, both negative. (i) Forcing the ceiling also moves
     the recovered area, giving matched-area pairs ACROSS lines: L3 @ ceiling 3 m
     (A=206) vs L5 @ ceiling 11 m (A=201) -> beta1 -152 vs -5, 30x apart at matched
     size. (ii) TEST D, the real size sweep -- an ellipse of imposed height on a FIXED
     centroid (9.2 m), same geometry on both lines, so depth AND size are matched
     row-by-row. Within L3 beta1 swings **+81 -> -98** while the area stays 153-202 m^2
     and is NON-MONOTONIC in height: beta1 is NOT a function of area. (So the apparent
     `beta1/A ~ -0.7` in the ceiling sweep was DEPTH doing the work, since size and
     depth move together there -- do not quote that ratio.) L5 stays flat (-19..+19)
     throughout, and at the matched row h=4 (L3 A=153 beta1=+81 vs L5 A=158 beta1=+6)
     the lines still differ ~13x.
     Caveat when writing this up: TEST B holds the CEILING fixed (centroid moves),
     TEST D holds the CENTROID fixed (ceiling moves 7.2 -> 1.2 m), so neither alone is
     a perfect depth control -- together they bracket it, and L5 is flat under both.
     The one within-L3 trend consistent across B and D is that a larger VERTICAL EXTENT
     (deeper tube bottom) drives beta1 more negative; area does not.
   Take-away for the thesis (keep SHORT, it bloats the discussion): both the correction
   and the inversion feedback affect beta0 AND beta1; L5 being pure is a coincidence; the
   two questions that matter for the Moon are depth and size, and neither is the cause;
   OAT machinery breaks down for a chain-coupled parameter like this -> further research
   needed. With only 2 lines, line identity is confounded with everything else.
   Pipeline gaps closed to enable this: TC now rescaled by rho/1.875 in
   `integrate_corrections.py` (TC is linear in rho -- no rerun by the colleague needed);
   `detrend_regional.py --no-plots` (its figure names do NOT encode rho, so sweeping
   would clobber the canonical rho=1.875 figures + thesis PDFs); `InvCfg.density` +
   `it.det_file(rho)`/`it.trend_file(rho)` so the inversion follows the swept rho.

Reconciliation to state explicitly (A and B look contradictory but aren't): the depth
prior is NECESSARY (A) but its PRECISION is forgiving (B). Turns the "subjective picks"
weakness into a strength and neutralises the ground-truth-bias worry -- a pick error of
plausible size doesn't change the result, so residual bias is immaterial. Picks are the
acknowledged weakest link; these two experiments (supervisor-suggested) justify them.

- Earlier: pipeline refactor (2026-06-12, grav_utils.py shared constants, intuitive
  file names, simple drift behind --with-simple-drift). CBA profiles via
  `visualise_CBA.py`; diagnostics in `Inspect/`.

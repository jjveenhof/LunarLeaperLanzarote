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
- `forward_polygon.py` -- fast analytic 2-D Talwani polygon forward (pure numpy).
  `forward_fem.py` is the pyGIMLi FEM equivalent (validation/3-D only; needs the
  `pygimli` env). `inspect_*` scripts are validation diagnostics.
- `invert_tube.py` -- THE inversion. Dense grid search over (size, x0) with a DC
  baseline fitted analytically at every grid point (relative gravity -> arbitrary
  datum; dof = n-3). CLI: `--line {3,5} --truncate inf 10 15 --ceiling --floor`.
  Modes: circle (fix GPR ceiling, fit R) and ellipse (fix ceiling+floor, fit
  half-width a). Uncertainty budget combined in quadrature: data (chi2-rescaled
  grid interval) + GPR picks (analytic propagation) + velocity (systematic depth
  scaling) + detrend slope (from `detrend_trend_params_*.csv`); truncation kept
  separate as a systematic bracket. GPR inputs FINAL (2026-07-01, per-line velocity):
  L3 v 0.125, ceiling 3.5/floor 14.3 m (air-gap corrected); L5 v 0.11, ceiling 10.5 m
  (no floor -> circle-only). No placeholders left.
- `plot_model_terrain.py` -- best-fit tube under the measured surface (GPR-line
  GNSS projected onto the same straight profile axis), true scale, auto-overlays
  `lidar_line{N}.csv` ground truth. Station styling matches the other grav plots.

## Current Focus
- Inversion built + uncertainty budget complete; **LiDAR-validated** (FINAL GPR geom):
  L3 untruncated ellipse 188+/-23 vs LiDAR 203 m^2 (~7%); L5 circle 196+/-36 vs 182 (~8%).
  Both inside 1 SE; model roofs align with the LiDAR void tops. Ground truth favors the
  UNTRUNCATED 2-D model -- the pit-truncation correction overshoots. Frame as model
  selection, not input tuning (no inverse crime).
- All profile plots read N (left) -> S (right) to match the GPR sections.
- Next: density chain-sweep (re-run pipeline per rho -> re-detrend -> re-invert) --
  the last quantifiable systematic. (All GPR picks/velocities now final.)
- Earlier: pipeline refactor (2026-06-12, grav_utils.py shared constants, intuitive
  file names, simple drift behind --with-simple-drift). CBA profiles via
  `visualise_CBA.py`; diagnostics in `Inspect/`.

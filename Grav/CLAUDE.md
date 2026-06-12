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

### Conventions
- All anomalies are relative to the base station (g_base = 0). Corrections (FAC, LAT, BC, TC)
  are applied relative to the per-line per-day base mean: RTK day-to-day bias cancels within a day.
- Default density rho = 1.875 g/cm3 (matches colleague). Filenames encode rho via
  `grav_utils.rho_str` (1.875 -> `rho1p875`); never round it.
- SE columns strictly match their value column (SBA <-> SE_SBA, CBA <-> SE_CBA);
  no silent substitution when an SE is unavailable.
- Colleague's corrections file: `Data/Gravimetry/Processed/LL_gravity_corrections.csv`
  (FA_correction, BA_correction, Terrain_correction). All values are in mGal by
  convention. The terrain correction is genuinely large at this site.

## Current Focus
- Pipeline refactor completed (2026-06-12): all scripts use grav_utils.py for shared
  constants, file names are now intuitive (lsq_drift_decay, station_gravity_decay, etc.),
  simple drift is behind --with-simple-drift flag, visualise_lines.py moved to Adhoc/.
- All 12 scripts smoke-tested; zero stale filename references.
- Next: scientific interpretation -- the CBA profiles are the primary deliverable.
  `visualise_CBA.py` and the Inspect/ scripts are the tools for that.

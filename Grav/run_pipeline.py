"""
Run the gravimetry processing pipeline (decay branch, the preferred configuration).

THIS SCRIPT IS THE WHOLE DATA CHAIN. Running it regenerates every CSV that the
inversion, the figures and the thesis tables are built from:

  Step 0: filter_gravimetry ("all") -> filtered_gravimetry_all.csv
  Step 1: station_decay             -> station_gravity_decay.csv, decay_fits.csv
  Step 2: drift_correction_lsq      -> lsq_drift_decay.csv, lsq_drift_loops_decay.csv
  Step 3: apply_corrections         -> bouguer_anomaly_decay_rho{X}.csv  (FAC + LAT + BC = SBA)
  Step 4: integrate_corrections     -> ..._colleague.csv, ..._rho{X}_with_TC.csv
                                       (skipped if the colleague's corrections file is absent)
  Step 5: detrend_regional          -> ..._rho{X}_detrended.csv, detrend_trend_params_rho{X}.csv

Step 5 was added 2026-08-11. It had never been in the pipeline even though EVERY script
in Inversion/ consumes its output, so a successor who ran run_pipeline.py and then the
inversion was silently inverting a stale residual.

What this script does NOT do (run these yourself, in this order, after it):

  combine_gravimetry.py   BEFORE everything -- builds Data/Gravimetry/combined_gravimetry.csv
                          from the raw CG-5 dumps, the field notes and the GNSS export. It is
                          deliberately NOT called here: it reads RAW ACQUISITION DATA and its
                          inputs never change, so it is a one-time step, not a pipeline stage.
                          Pass --combine to include it (see below).
  Inversion/run_inversion.py    the inversion + Monte Carlo -> artifacts
  the figure scripts            visualise_lsq / visualise_CBA / Inversion/plot_*
  make_decay_table.py           the appendix decay-fit LaTeX table
  make_thesis_tables.py         the correction-budget + per-line TC thesis tables

See REPRODUCE.md in this folder for the full run order, including the figures.

Flags
-----
  --combine             Also run combine_gravimetry.py FIRST (raw CG-5 + notes + GNSS ->
                        combined_gravimetry.csv). Only needed if the raw data or the field
                        notes changed; the raw data is frozen, so normally you do not.

  --with-simple-drift   Also run the legacy simple linear drift correction
                        (drift_correction.py -> simple_drift_decay.csv).
                        This is a comparison method, parallel to the LSQ step,
                        not part of the main chain.

  --all                 First rerun every legacy filtering config (CONFIGS in
                        filter_gravimetry.py) through the station-mean branch:
                          filter_gravimetry  -> filtered_gravimetry_{name}.csv
                          station_means      -> station_gravity_{name}.csv
                          drift_correction   -> simple_drift_{name}.csv
                          drift_correction_lsq -> lsq_drift_{name}.csv
                        NOTE: CONFIGS includes "all", so this also rewrites
                        filtered_gravimetry_all.csv -- the MAIN chain's input.

Exit code is 0 only if every step succeeded; a failure anywhere is fatal and reported.

Usage
-----
    python run_pipeline.py
    python run_pipeline.py --with-simple-drift
    python run_pipeline.py --all
"""

import subprocess
import sys
import traceback
from pathlib import Path

from filter_gravimetry    import main as run_filter, CONFIGS
from station_means        import main as run_means
from drift_correction     import main as run_drift
from drift_correction_lsq import main as run_lsq
from grav_utils           import PROC_DIR

HERE = Path(__file__).resolve().parent


def run(config_name):
    filt  = PROC_DIR / f"filtered_gravimetry_{config_name}.csv"
    means = PROC_DIR / f"station_gravity_{config_name}.csv"
    corr  = PROC_DIR / f"simple_drift_{config_name}.csv"

    sep = "-" * 60
    print(f"\n{sep}\n  CONFIG: {config_name}\n{sep}")

    print("\n-- Step 1: filter --")
    run_filter(config_name, out_file=filt)

    print("\n-- Step 2: station means --")
    run_means(in_file=filt, out_file=means)

    print("\n-- Step 3: simple drift correction --")
    run_drift(in_file=means, out_file=corr)

    print("\n-- Step 4: LSQ drift correction --")
    run_lsq(config_name)


def run_script(name, *args):
    """Run a sibling script in its own process, and RAISE if it fails.

    Used for the steps that do their work at module level (they parse sys.argv on
    import), so they cannot simply be imported and called."""
    cmd = [sys.executable, str(HERE / name), *args]
    print(f"    $ {name} {' '.join(args)}")
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {r.returncode}")


def run_decay(with_simple_drift=False):
    """Decay branch: decay fit -> LSQ drift -> corrections -> terrain -> detrend."""
    from station_decay import main as run_station_decay

    sep = "-" * 60
    print(f"\n{sep}\n  CONFIG: decay\n{sep}")

    # The decay fit needs every reading: the "all" filtered file.
    # ALWAYS re-filter. This used to be skipped when the file already existed, which
    # meant an edit to exclusions.csv silently did not propagate -- you would rerun the
    # pipeline, see it succeed, and get the old exclusions. Filtering is cheap; the
    # stale-input trap is not.
    print("\n-- Step 0: filter (all readings, input to decay fit) --")
    run_filter("all", out_file=PROC_DIR / "filtered_gravimetry_all.csv")

    print("\n-- Step 1: exponential decay fit --")
    run_station_decay(plot=False)   # saves station_gravity_decay.csv, skips plots

    print("\n-- Step 2: LSQ drift correction --")
    run_lsq("decay")

    print("\n-- Step 3: gravity corrections (free-air, latitude, Bouguer) --")
    from apply_corrections import main as run_corrections
    run_corrections()

    print("\n-- Step 4: integrate colleague corrections (terrain) --")
    if (PROC_DIR / "LL_gravity_corrections.csv").exists():
        from integrate_corrections import main as run_integrate
        run_integrate()
    else:
        print("LL_gravity_corrections.csv not found -- skipping")

    # Step 5 closes the gap between "the pipeline finished" and "the inversion input is
    # current". Everything in Inversion/ reads the detrended residual + trend params.
    # This also refreshes the Detrend figures (and their PDFs in the Overleaf clone),
    # because they are this step's product.
    print("\n-- Step 5: regional de-trend (inversion input) --")
    run_script("detrend_regional.py")

    if with_simple_drift:
        print("\n-- Optional: simple drift correction (comparison only) --")
        run_drift(
            in_file  = PROC_DIR / "station_gravity_decay.csv",
            out_file = PROC_DIR / "simple_drift_decay.csv",
        )


if __name__ == "__main__":
    run_all           = "--all" in sys.argv
    with_simple_drift = "--with-simple-drift" in sys.argv
    do_combine        = "--combine" in sys.argv

    if do_combine:
        print("\n-- Pre-step: combine raw CG-5 + notes + GNSS --")
        run_script("combine_gravimetry.py")

    if run_all:
        for name in CONFIGS:
            run(name)

    run_decay_success = True
    try:
        run_decay(with_simple_drift=with_simple_drift)
    except Exception:
        run_decay_success = False
        traceback.print_exc()

    print(f"\n{'-'*60}")
    if run_all:
        print(f"  All {len(CONFIGS)} legacy configs complete.")
    if run_decay_success:
        print(f"  Decay config complete.")
    else:
        print(f"  Decay config FAILED -- see traceback above.")
    print(f"{'-'*60}")

    # Exit NON-ZERO on failure. This used to always exit 0, so a broken pipeline looked
    # identical to a good one to any caller (a shell &&-chain, CI, or a successor running
    # it unattended). The traceback above was the only signal.
    sys.exit(0 if run_decay_success else 1)

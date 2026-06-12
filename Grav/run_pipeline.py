"""
Run the gravimetry processing pipeline (decay branch, the preferred configuration):

  Step 0: filter_gravimetry ("all") -> filtered_gravimetry_all.csv   (if missing)
  Step 1: station_decay             -> station_gravity_decay.csv, decay_fits.csv
  Step 2: drift_correction_lsq      -> lsq_drift_decay.csv, lsq_drift_loops_decay.csv
  Step 3: apply_corrections         -> bouguer_anomaly_decay_rho{X}.csv  (FAC + LAT + BC = SBA)
  Step 4: integrate_corrections     -> ..._colleague.csv, ..._rho{X}_with_TC.csv
                                       (skipped if the colleague's corrections file is absent)

Flags
-----
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

Usage
-----
    python run_pipeline.py
    python run_pipeline.py --with-simple-drift
    python run_pipeline.py --all
"""

import sys
import traceback

from filter_gravimetry    import main as run_filter, CONFIGS
from station_means        import main as run_means
from drift_correction     import main as run_drift
from drift_correction_lsq import main as run_lsq
from grav_utils           import PROC_DIR


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


def run_decay(with_simple_drift=False):
    """Decay branch: decay fit -> LSQ drift -> corrections -> terrain."""
    from station_decay import main as run_station_decay

    sep = "-" * 60
    print(f"\n{sep}\n  CONFIG: decay\n{sep}")

    # The decay fit needs every reading: the "all" filtered file
    filt_all = PROC_DIR / "filtered_gravimetry_all.csv"
    if not filt_all.exists():
        print("\n-- Step 0: filter (all readings, input to decay fit) --")
        run_filter("all", out_file=filt_all)

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

    if with_simple_drift:
        print("\n-- Optional: simple drift correction (comparison only) --")
        run_drift(
            in_file  = PROC_DIR / "station_gravity_decay.csv",
            out_file = PROC_DIR / "simple_drift_decay.csv",
        )


if __name__ == "__main__":
    run_all           = "--all" in sys.argv
    with_simple_drift = "--with-simple-drift" in sys.argv

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

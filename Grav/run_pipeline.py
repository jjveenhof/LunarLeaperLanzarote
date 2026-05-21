"""
Run the full gravimetry processing pipeline for every filtering configuration,
and optionally the exponential-decay station means.

Standard pipeline (per CONFIGS entry in filter_gravimetry.py):
  filter_gravimetry  -> filtered_gravimetry_{name}.csv
  station_means      -> station_means_{name}.csv
  drift_correction   -> drift_corrected_{name}.csv

Decay pipeline (run_decay()):
  station_decay      -> station_means_decay.csv   (g_inf as gravity estimate)
  drift_correction   -> drift_corrected_decay.csv
"""

from pathlib import Path
from filter_gravimetry    import main as run_filter, CONFIGS
from station_means        import main as run_means
from drift_correction     import main as run_drift
from drift_correction_lsq import main as run_lsq

PROC_DIR = Path(__file__).resolve().parents[2] / "Data/Gravimetry/Processed"


def run(config_name):
    filt  = PROC_DIR / f"filtered_gravimetry_{config_name}.csv"
    means = PROC_DIR / f"station_means_{config_name}.csv"
    corr  = PROC_DIR / f"drift_corrected_{config_name}.csv"

    sep = "-" * 60
    print(f"\n{sep}\n  CONFIG: {config_name}\n{sep}")

    print("\n-- Step 1: filter --")
    run_filter(config_name, out_file=filt)

    print("\n-- Step 2: station means --")
    run_means(in_file=filt, out_file=means)

    print("\n-- Step 3: drift correction --")
    run_drift(in_file=means, out_file=corr)

    print("\n-- Step 4: LSQ drift correction --")
    run_lsq(config_name)


def run_decay():
    """Drift-correct the exponential-decay gravity estimates."""
    from station_decay import main as run_station_decay

    sep = "-" * 60
    print(f"\n{sep}\n  CONFIG: decay\n{sep}")

    print("\n-- Step 1: exponential decay fit --")
    run_station_decay(plot=False)   # saves station_means_decay.csv, skips plots

    print("\n-- Step 2: drift correction --")
    run_drift(
        in_file  = PROC_DIR / "station_means_decay.csv",
        out_file = PROC_DIR / "drift_corrected_decay.csv",
    )

    print("\n-- Step 3: LSQ drift correction --")
    run_lsq("decay")


if __name__ == "__main__":
    for name in CONFIGS:
        run(name)
    
    run_decay_success = True
    try:
        run_decay()
    except Exception:
        run_decay_success = False

    print(f"\n{'-'*60}")
    print(f"  All {len(CONFIGS)} configs complete.")
    if run_decay_success:
        print(f"  Decay config complete.")
    
    print(f"{'-'*60}")


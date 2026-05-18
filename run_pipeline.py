"""
Run the full gravimetry processing pipeline for every filtering configuration.

Steps per config
----------------
  filter_gravimetry  → filtered_gravimetry_{name}.csv
  station_means      → station_means_{name}.csv
  drift_correction   → drift_corrected_{name}.csv

To add a new configuration, edit the CONFIGS dict in filter_gravimetry.py.
"""

from pathlib import Path
from filter_gravimetry import main as run_filter, CONFIGS
from station_means     import main as run_means
from drift_correction  import main as run_drift

DATA = Path(__file__).resolve().parents[1] / "Data/Gravimetry"


def run(config_name):
    filt  = DATA / f"filtered_gravimetry_{config_name}.csv"
    means = DATA / f"station_means_{config_name}.csv"
    corr  = DATA / f"drift_corrected_{config_name}.csv"

    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  CONFIG: {config_name}")
    print(sep)

    print("\n── Step 1: filter ──")
    run_filter(config_name, out_file=filt)

    print("\n── Step 2: station means ──")
    run_means(in_file=filt, out_file=means)

    print("\n── Step 3: drift correction ──")
    run_drift(in_file=means, out_file=corr)


if __name__ == "__main__":
    for name in CONFIGS:
        run(name)

    print(f"\n{'─'*60}")
    print(f"  All {len(CONFIGS)} configs complete.")
    print(f"{'─'*60}")

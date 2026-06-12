"""
Export all non-base stations with GNSS data for free-air, Bouguer and terrain corrections.

One row per measurement visit -- co-located stations at slightly different GNSS
positions are kept as separate rows so their individual coordinates are preserved.

Output
------
    Data/Gravimetry/Processed/stations_for_corrections.csv
"""

import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grav_utils import PROC_DIR

df = pd.read_csv(PROC_DIR / "lsq_drift_decay.csv")

export = (df[df["Easting"].notna()]
          [["Line", "Station",
            "Easting", "Northing", "Elevation",
            "HorizErr", "VertErr"]]
          .sort_values(["Line", "Station"])
          .reset_index(drop=True))

out = PROC_DIR / "stations_for_corrections.csv"
export.to_csv(out, index=False, float_format="%.6f")
print(f"Exported {len(export)} measurements -> {out.name}")

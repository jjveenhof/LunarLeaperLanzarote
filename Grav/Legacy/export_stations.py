"""QUARANTINED 2026-08-12 -- finished one-off, not in any chain.

One-time export of the gravity station list for QGIS. The export it produced is already
in the QGIS project; nothing reads this script and no thesis figure depends on it.
Kept (not deleted) because it records exactly how that layer was made.
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

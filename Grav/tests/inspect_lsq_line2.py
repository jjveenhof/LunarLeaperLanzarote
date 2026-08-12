"""DIAGNOSTIC, not a test -- prints the Line 2 LSQ solution for eyeballing.

Renamed from `test_drift_correction_lsq.py` on 2026-08-12. It was named like a test but
contains no assertion and cannot fail: it reads live pipeline output and prints it, so it
passed no matter what the solver did. That name gave false confidence about coverage.

The actual test of this module is `test_solve_line.py`, which solves a synthetic network
with a known answer and asserts exact recovery.

Run:  python Tests/inspect_lsq_line2.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/Grav/
from drift_correction_lsq import assign_loops, assign_locations, solve_line
from grav_utils import BASE, PROC_DIR       # one definition of the project paths

df = pd.read_csv(PROC_DIR / "station_gravity_decay.csv",
                 dtype={"Time_first": str, "Date": str})
df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time_first"],
                                format="%Y/%m/%d %H:%M:%S")

# Check Line 2
line2 = df[df["Line"] == 2].copy()
result_loops = assign_loops(line2)

print(result_loops[["Station", "StationType", "Time_first", "t_line_min",
                    "loop_id", "t0_min"]].to_string(index=False))

result_locs = assign_locations(result_loops)

print(result_locs[["Station", "StationType", "loc_id", "Easting", "Northing"]]
      .sort_values("loc_id")
      .to_string(index=False))


result_df, loop_df, chi2_red = solve_line(result_locs)

print(f"chi2_red = {chi2_red:.5f}\n")

print("Loop parameters:")
print(loop_df.to_string(index=False))

print("\nStation results (sorted by Station):")
print(result_df[["Station", "StationType", "loc_id", "loop_id",
                 "Grav_est", "Grav_lsq", "SE_lsq", "residual"]]
      .sort_values("Station")
      .to_string(index=False))

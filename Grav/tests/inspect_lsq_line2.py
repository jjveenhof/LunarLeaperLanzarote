import pandas as pd
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/Grav/
from drift_correction_lsq import assign_loops, assign_locations, solve_line

BASE = Path(__file__).resolve().parents[3]   # thesis root
df = pd.read_csv(BASE / "Data/Gravimetry/Processed/station_gravity_decay.csv",
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

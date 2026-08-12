"""QUARANTINED 2026-08-12 -- finished one-off, not in any chain.

Printed per-station occupation durations to check consistency within loops. The question
it answered is settled and recorded; nothing imports it.
"""
import pandas as pd
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/Grav for grav_utils
from grav_utils import BASE, PROC_DIR             # one definition of the project paths

df = pd.read_csv(PROC_DIR / "station_gravity_decay.csv",
                 dtype={"Time_first": str, "Time_last": str, "Date": str})

df["t_first"] = pd.to_datetime(df["Date"] + " " + df["Time_first"],
                               format="%Y/%m/%d %H:%M:%S")
df["t_last"]  = pd.to_datetime(df["Date"] + " " + df["Time_last"],
                               format="%Y/%m/%d %H:%M:%S")
df["duration_s"] = (df["t_last"] - df["t_first"]).dt.total_seconds()

for line, ldf in df.groupby("Line"):
    print(f"\n=== Line {line} ===")
    print(f"{'Station':>8}  {'Type':>8}  {'Duration (s)':>12}  {'n_readings':>10}")
    print("-" * 48)
    for _, row in ldf.sort_values("t_first").iterrows():
        print(f"  S{int(row['Station']):>4}   {row['StationType']:>8}  "
              f"{int(row['duration_s']):>10}  {int(row['n_readings']):>10}")

    print(f"\n  Summary by type:")
    for stype, grp in ldf.groupby("StationType"):
        d = grp["duration_s"]
        print(f"    {stype:>8}:  mean={d.mean():.0f}s  "
              f"min={d.min():.0f}s  max={d.max():.0f}s  "
              f"range={d.max()-d.min():.0f}s")

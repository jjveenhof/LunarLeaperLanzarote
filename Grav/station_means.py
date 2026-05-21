"""
Compute weighted mean gravity per station from the filtered readings.

Input
-----
  Data/Gravimetry/filtered_gravimetry.csv   filtered per-reading dataset

Output
------
  Data/Gravimetry/station_means.csv   one row per station

Method
------
  For each station, readings are combined using inverse-variance weighting:

    w_i      = 1 / SE_i^2  = Dur_i / SD_i^2
    Grav_w   = sum(w_i * Grav_i) / sum(w_i)
    SE_wmean = 1 / sqrt(sum(w_i))

  Readings with SE_i = NaN (Dur = 0) are excluded from the weighted mean.
  Stations with no valid readings after exclusion are dropped entirely.
"""

import numpy as np
import pandas as pd
from pathlib import Path

BASE       = Path(__file__).resolve().parents[2]
PROC_DIR   = BASE / "Data/Gravimetry/Processed"
FILT_FILE  = PROC_DIR / "filtered_gravimetry.csv"
OUT_FILE   = PROC_DIR / "station_means.csv"


def weighted_mean(grp):
    valid = grp["SE_i"].notna() & (grp["SE_i"] > 0)
    g = grp[valid]
    if g.empty:
        return None

    w        = 1.0 / g["SE_i"]**2
    grav_w   = (w * g["Grav"]).sum() / w.sum()
    se_wmean = 1.0 / np.sqrt(w.sum())

    return pd.Series({
        "Grav_wmean":  grav_w,
        "SE_wmean":    se_wmean,
        "n_readings":  len(g),
        "Temp_mean":   g["Temp"].mean(),
        "Date":        g["Date"].iloc[0],
        "Time_first":  g["Time"].iloc[0],
        "Time_last":   g["Time"].iloc[-1],
    })


def main(in_file=None, out_file=None):
    if in_file  is None: in_file  = FILT_FILE
    if out_file is None: out_file = OUT_FILE
    in_file, out_file = Path(in_file), Path(out_file)

    print(f"Reading {in_file.name} ...")
    df = pd.read_csv(in_file, dtype={"Time": str, "Date": str})
    print(f"  {len(df)} readings across {df.groupby(['Line', 'Station']).ngroups} stations")

    # Metadata columns that are constant per station, take first value
    meta_cols = ["Easting", "Northing", "Elevation", "HorizErr", "VertErr",
                 "StationType", "Notes"]
    meta = df.groupby(["Line", "Station"])[meta_cols].first()

    stats = (
        df.sort_values("Time")
          .groupby(["Line", "Station"])
          .apply(weighted_mean, include_groups=False)
          .dropna(how="all")
    )

    result = meta.join(stats).reset_index()
    result["Line"]       = result["Line"].astype(int)
    result["Station"]    = result["Station"].astype(int)
    result["n_readings"] = result["n_readings"].astype(int)
    result = result.sort_values(["Line", "Station"]).reset_index(drop=True)

    cols = [
        "Line", "Station",
        "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
        "Grav_wmean", "SE_wmean", "n_readings",
        "Temp_mean", "Date", "Time_first", "Time_last",
        "StationType", "Notes",
    ]
    result[cols].to_csv(out_file, index=False, float_format="%.6f")

    print(f"\nSaved -> {out_file.name}")
    preview_cols = ["Line", "Station", "Easting", "Northing", "Elevation",
                    "Grav_wmean", "SE_wmean", "n_readings", "StationType"]
    print(f"\nPreview (first 5 rows):")
    with pd.option_context("display.width", 120, "display.float_format", "{:.4f}".format):
        print(result[preview_cols].head(5).to_string(index=False))

    print(f"\nSummary:")
    print(f"  Stations: {len(result)}")
    print(f"  Median readings per station: {result['n_readings'].median():.0f}")
    print(f"  Median SE_wmean: {result['SE_wmean'].median()*1000:.4f} microGal")


if __name__ == "__main__":
    main()


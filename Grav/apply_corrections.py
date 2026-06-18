"""
Apply standard gravity corrections to LSQ anomalies.

Corrections applied relative to the base station, so the output
remains a relative anomaly (consistent with g_base = 0 datum).

  Free-air correction  : FAC  = +0.3086 * dh                         mGal
  Latitude correction  : LAT  = g_normal(phi_base) - g_normal(phi_k)  mGal
  Bouguer correction   : BC   = -0.0419 * RHO * dh                   mGal

  Simple Bouguer anomaly  : SBA = Grav_lsq + FAC + LAT + BC

Normal gravity uses the WGS84 Somigliani formula. Latitude is converted
from UTM Easting/Northing (EPSG:4083, REGCAN95 / UTM zone 28N) using pyproj.
The latitude reference per line is the per-day mean of base station latitudes,
consistent with the elevation reference.

Elevation is taken from the GNSS column 'Elevation', which contains orthometric
heights (above the geoid) in the REGCAN95 datum, with a geoid model applied
in Leica Captivate on the CS20.

Input
-----
    Data/Gravimetry/Processed/lsq_drift_decay.csv

Output
------
    Data/Gravimetry/Processed/bouguer_anomaly_decay_rho{X}.csv

Usage
-----
    python apply_corrections.py            # default rho = 1.875 g/cm3
    python apply_corrections.py 2.0
    python apply_corrections.py 1.8 2.0 2.5  # run for multiple rho values
"""

import sys
import pandas as pd
import numpy as np
from pyproj import Transformer

from grav_utils import (PROC_DIR, FAC_GRAD, BOUGUER_K, RHO_DEFAULT,
                        normal_gravity, sba_file)

# UTM zone 28N (REGCAN95) to geographic
UTM_TO_GEO = Transformer.from_crs("EPSG:4083", "EPSG:4258", always_xy=True)


def main(rho=RHO_DEFAULT):
    df = pd.read_csv(PROC_DIR / "lsq_drift_decay.csv")

    # -- Latitude from UTM -----------------------------------------------------
    has_gnss = df["Easting"].notna() & df["Northing"].notna()
    _, lat = UTM_TO_GEO.transform(
        df.loc[has_gnss, "Easting"].values,
        df.loc[has_gnss, "Northing"].values
    )
    df.loc[has_gnss, "lat_deg"] = lat
    df["g_normal"] = normal_gravity(df["lat_deg"])   # NaN where no GNSS

    # -- Per-day base reference (elevation + latitude) -------------------------
    base_daily = (df[df["StationType"] == "base"]
                  .dropna(subset=["Elevation"])
                  .groupby(["Line", "Date"])
                  .agg(h_base=("Elevation", "mean"),
                       se_h_base=("VertErr",
                                  lambda v: np.sqrt((v**2).sum()) / len(v)),
                       g_normal_base=("g_normal", "mean"))
                  .reset_index())

    df = df.merge(base_daily, on=["Line", "Date"], how="left")

    missing = df[df["h_base"].isna()][["Line", "Date"]].drop_duplicates()
    if not missing.empty:
        print(f"WARNING: no base elevation for:\n{missing.to_string(index=False)}")

    df["dh"]    = df["Elevation"] - df["h_base"]
    df["SE_dh"] = np.sqrt(df["VertErr"]**2 + df["se_h_base"]**2)

    n_missing = df["dh"].isna().sum()
    if n_missing:
        print(f"WARNING: {n_missing} stations have no elevation -- corrections set to NaN")

    elev_grad = FAC_GRAD - BOUGUER_K * rho

    df["FAC"] =  FAC_GRAD  * df["dh"]
    df["LAT"] =  df["g_normal_base"] - df["g_normal"]   # positive moving north
    df["BC"]  = -BOUGUER_K * rho * df["dh"]

    # Base station is the datum: all corrections are zero by definition
    is_base = df["StationType"] == "base"
    df.loc[is_base, ["dh", "FAC", "LAT", "BC"]] = 0.0

    df["SBA"]    = df["Grav_lsq"] + df["FAC"] + df["LAT"] + df["BC"]

    df["SE_elev"] = elev_grad * df["SE_dh"]
    df.loc[is_base, "SE_elev"] = 0.0
    df["SE_SBA"]  = np.sqrt(df["SE_lsq"]**2 + df["SE_elev"]**2)

    out_cols = [
        "Line", "loc_id", "Station", "StationType",
        "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
        "Grav_lsq", "SE_lsq",
        "dh", "SE_elev",
        "FAC", "LAT", "BC",
        "SBA", "SE_SBA",
    ]
    out = df[out_cols].sort_values(["Line", "loc_id", "Station"]).reset_index(drop=True)

    out_file = sba_file(rho)
    out.to_csv(out_file, index=False, float_format="%.6f")
    print(f"Saved -> {out_file.name}")
    print(f"  RHO = {rho} g/cm3")
    print(f"  FAC_GRAD = {FAC_GRAD} mGal/m")
    print(f"  BOUGUER_K = {BOUGUER_K:.5f} x {rho} x dh mGal")
    print(f"\nMax |dh|:    {df['dh'].abs().max():.3f} m")
    print(f"Max |FAC|:   {df['FAC'].abs().max():.4f} mGal")
    print(f"Max |LAT|:   {df['LAT'].abs().max():.4f} mGal")
    print(f"Max |BC|:    {df['BC'].abs().max():.4f} mGal")
    print(f"Max |SBA - Grav_lsq|: {(df['SBA'] - df['Grav_lsq']).abs().max():.4f} mGal")


if __name__ == "__main__":
    rho_values = [float(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else [RHO_DEFAULT]
    for rho in rho_values:
        main(rho)

"""
Apply standard gravity corrections to LSQ anomalies.

Corrections applied relative to the base station elevation, so the output
remains a relative anomaly (consistent with g_base = 0 datum).

  Free-air correction  : FAC  = +0.3086 * (h_k - h_base)          mGal
  Bouguer correction   : BC   = -0.0419 * RHO * (h_k - h_base)    mGal
  Terrain correction   : TC   = from collaborator (placeholder = 0)

  Simple Bouguer anomaly  : SBA = Grav_lsq + FAC + BC
  Complete Bouguer anomaly: CBA = Grav_lsq + FAC + BC + TC

Elevation is taken from the GNSS column 'Elevation', which contains orthometric
heights (above the geoid) in the REGCAN95 datum (Canary Islands, tied to
ETRS89/GRS80), with a geoid model applied in Leica Captivate on the CS20.
For relative corrections the geoid undulation cancels in dh = h_station - h_base,
but having orthometric heights is also correct for absolute Bouguer work.

Input
-----
    Data/Gravimetry/Processed/lsq_corrected_decay.csv

Output
------
    Data/Gravimetry/Processed/bouguer_anomaly_decay.csv

Usage
-----
    python apply_corrections.py
"""

import pandas as pd
import numpy as np
from pathlib import Path

BASE     = Path(__file__).resolve().parents[2]
PROC_DIR = BASE / "Data/Gravimetry/Processed"

RHO        = 2.0          # g/cm3 -- assumed bulk density of rock column

# Free-air gradient: dg/dh = -2g/R (standard geodetic value, valid at all latitudes)
# g ~ 9.807 m/s2, R ~ 6371 km -> 2*9.807/6371000 = 3.079e-6 m/s2/m = 0.3079 mGal/m
# The standard 0.3086 includes the ellipsoidal correction; at Lanzarote (29N) ~0.3085
FAC_GRAD   = 0.3086       # mGal/m

# Bouguer slab factor: g_slab = 2*pi*G * (rho_SI) * h, converted to mGal
# 2*pi * G         = 2 * pi * 6.674e-11        = 4.194e-10  m3 kg-1 s-2 m-1
# rho conversion   = 1e3                        kg/m3 per g/cm3
# mGal conversion  = 1e5                        mGal per m/s2
# combined         = 4.194e-10 * 1e3 * 1e5      = 0.04194 mGal m-1 per g/cm3
G_NEWTON   = 6.674e-11    # m3 kg-1 s-2
BOUGUER_K  = 2 * np.pi * G_NEWTON * 1e3 * 1e5       # = 0.04192 mGal m-1 per g/cm3
ELEV_GRAD  = FAC_GRAD - BOUGUER_K * RHO              # net dCBA/dh (mGal/m)


def main():
    df = pd.read_csv(PROC_DIR / "lsq_corrected_decay.csv")

    # Base station elevation per line per day -- RTK bias cancels within a day since
    # field stations are always measured between base station visits on the same day.
    # Using the daily mean avoids mixing elevations from different RTK sessions.
    base_daily = (df[df["StationType"] == "base"]
                  .dropna(subset=["Elevation"])
                  .groupby(["Line", "Date"])
                  .agg(h_base=("Elevation", "mean"),
                       se_h_base=("VertErr",
                                  lambda v: np.sqrt((v**2).sum()) / len(v)))
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

    df["FAC"]    =  FAC_GRAD  * df["dh"]
    df["BC"]     = -BOUGUER_K * RHO * df["dh"]
    df["TC"]     =  0.0       # placeholder -- fill with collaborator values

    # Base station is the datum: all corrections are zero by definition
    is_base = df["StationType"] == "base"
    df.loc[is_base, ["dh", "SE_elev", "FAC", "BC", "TC"]] = 0.0

    df["SBA"]    = df["Grav_lsq"] + df["FAC"] + df["BC"]
    df["CBA"]    = df["SBA"] + df["TC"]

    df["SE_elev"] = ELEV_GRAD * df["SE_dh"]
    df["SE_CBA"]  = np.sqrt(df["SE_lsq"]**2 + df["SE_elev"]**2)

    out_cols = [
        "Line", "loc_id", "Station", "StationType",
        "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
        "Grav_lsq", "SE_lsq",
        "dh", "SE_elev",
        "FAC", "BC", "TC",
        "SBA", "CBA", "SE_CBA",
    ]
    out = df[out_cols].sort_values(["Line", "loc_id", "Station"]).reset_index(drop=True)

    out_file = PROC_DIR / "bouguer_anomaly_decay.csv"
    out.to_csv(out_file, index=False, float_format="%.6f")
    print(f"Saved -> {out_file.name}")
    print(f"  RHO = {RHO} g/cm3")
    print(f"  Free-air gradient = {FAC_GRAD} mGal/m")
    print(f"  Bouguer factor    = {BOUGUER_K:.5f} x RHO x dh mGal")
    print(f"\nElevation range: {df['Elevation'].min():.2f} -- {df['Elevation'].max():.2f} m")
    print(f"Max |dh|:              {df['dh'].abs().max():.2f} m")
    print(f"Max |FAC|:             {df['FAC'].abs().max():.3f} mGal")
    print(f"Max |BC|:              {df['BC'].abs().max():.3f} mGal")
    print(f"Max |SBA - Grav_lsq|: {(df['SBA'] - df['Grav_lsq']).abs().max():.3f} mGal")


if __name__ == "__main__":
    main()

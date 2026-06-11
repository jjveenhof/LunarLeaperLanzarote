"""
Integrate colleague's gravity corrections with our LSQ anomalies.

Two output files:

  1. bouguer_anomaly_decay_colleague.csv
       Uses colleague's FA and BA corrections entirely, plus his terrain correction.
       CBA = Grav_lsq + (FA_k - FA_base) + (BA_k - BA_base) + (TC_k - TC_base)
       Colleague used rho = 1.875 g/cm3. Terrain correction in mGal.

  2. bouguer_anomaly_decay_rho{X}_with_TC.csv
       Uses our relative FAC + BC (from apply_corrections.py output), but replaces
       the placeholder TC=0 with the colleague's terrain correction.
       CBA = SBA + (TC_k - TC_base)

In both cases corrections are applied relative to the per-line per-day base mean,
consistent with apply_corrections.py and the Grav_lsq = 0 datum at the base.

Input
-----
    Data/Gravimetry/Processed/LL_gravity_corrections.csv     (colleague)
    Data/Gravimetry/Processed/lsq_corrected_decay.csv        (our LSQ)
    Data/Gravimetry/Processed/bouguer_anomaly_decay_rho{X}.csv  (our SBA)

Usage
-----
    python integrate_corrections.py          # default rho = 1.875
    python integrate_corrections.py 2.0
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

BASE     = Path(__file__).resolve().parents[2]
PROC_DIR = BASE / "Data/Gravimetry/Processed"

TC_FILE  = PROC_DIR / "LL_gravity_corrections.csv"
LSQ_FILE = PROC_DIR / "lsq_corrected_decay.csv"

rho     = float(sys.argv[1]) if len(sys.argv) > 1 else 1.875
rho_str = f"{rho:.3f}".rstrip("0").rstrip(".").replace(".", "p")
SBA_FILE = PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str}.csv"

# -- Load data -----------------------------------------------------------------
tc  = pd.read_csv(TC_FILE)
lsq = pd.read_csv(LSQ_FILE)
sba = pd.read_csv(SBA_FILE)

# Merge colleague corrections onto LSQ data by (Line, Station)
df = lsq.merge(
    tc[["Line", "Station", "FA_correction", "BA_correction", "Terrain_correction"]],
    on=["Line", "Station"],
    how="left"
)

n_matched = df["FA_correction"].notna().sum()
n_total   = len(df)
print(f"Matched {n_matched}/{n_total} stations to colleague corrections")

missing = df[df["FA_correction"].isna()][["Line", "Station", "StationType"]].drop_duplicates()
if not missing.empty:
    print(f"No colleague correction for:\n{missing.to_string(index=False)}")

# -- Per-line per-day base reference -- consistent with apply_corrections.py
# RTK bias cancels within a day; mixing days would reintroduce it.
base_ref = (df[df["StationType"] == "base"]
            .dropna(subset=["FA_correction"])
            .groupby(["Line", "Date"])[["FA_correction", "BA_correction", "Terrain_correction"]]
            .mean()
            .rename(columns={
                "FA_correction":      "FA_base",
                "BA_correction":      "BA_base",
                "Terrain_correction": "TC_base",
            })
            .reset_index())

df = df.merge(base_ref, on=["Line", "Date"], how="left")

# Add Date to sba (not in SBA file) so we can merge per-day TC_base
sba2 = sba.merge(lsq[["Line", "Station", "Date"]].drop_duplicates(),
                 on=["Line", "Station"], how="left")
sba2 = sba2.merge(
    df[["Line", "Date", "Station", "Terrain_correction", "TC_base"]].drop_duplicates(),
    on=["Line", "Date", "Station"],
    how="left"
)

# -- Option 1: full colleague corrections -------------------------------------
df["FAC"] = df["FA_correction"] - df["FA_base"]
df["BC"]  = df["BA_correction"] - df["BA_base"]
df["dTC"] = df["Terrain_correction"] - df["TC_base"]

df["CBA"] = df["Grav_lsq"] + df["FAC"] + df["BC"] + df["dTC"]

out1_cols = [
    "Line", "loc_id", "Station", "StationType",
    "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
    "Grav_lsq", "SE_lsq",
    "FAC", "BC", "dTC",
    "CBA",
]
out1 = df[out1_cols].sort_values(["Line", "loc_id", "Station"]).reset_index(drop=True)
f1   = PROC_DIR / "bouguer_anomaly_decay_colleague.csv"
out1.to_csv(f1, index=False, float_format="%.6f")
print(f"\nSaved -> {f1.name}  (full colleague corrections)")

# -- Option 2: our SBA + colleague TC -----------------------------------------
sba2["dTC"] = sba2["Terrain_correction"] - sba2["TC_base"]
n_no_tc = sba2["dTC"].isna().sum()
if n_no_tc:
    print(f"WARNING: {n_no_tc} stations have no TC -- TC set to 0 for those")
sba2["CBA"] = sba2["SBA"] + sba2["dTC"].fillna(0)

out2_cols = [
    "Line", "loc_id", "Station", "StationType",
    "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
    "Grav_lsq", "SE_lsq",
    "dh", "SE_elev",
    "FAC", "BC", "dTC",
    "SBA", "SE_SBA", "CBA",
]
out2 = sba2[out2_cols].sort_values(["Line", "loc_id", "Station"]).reset_index(drop=True)
f2   = PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str}_with_TC.csv"
out2.to_csv(f2, index=False, float_format="%.6f")
print(f"Saved -> {f2.name}  (our SBA + colleague TC)")

# -- Summary -------------------------------------------------------------------
print(f"\nTerrain correction stats (mGal, relative to base):")
dTC = sba2["dTC"].dropna()
print(f"  Range: {dTC.min():.4f} to {dTC.max():.4f} mGal")
print(f"  Mean:  {dTC.mean():.4f} mGal")
print(f"  Std:   {dTC.std():.4f} mGal")

print(f"\nDifference between option 1 and option 2 (CBA_colleague - CBA_with_TC):")
merged = out1.merge(out2[["Line", "Station", "CBA"]].rename(columns={"CBA": "CBA_with_TC"}),
                    on=["Line", "Station"], how="inner")
diff   = merged["CBA"] - merged["CBA_with_TC"]
print(f"  Mean: {diff.mean():.4f} mGal")
print(f"  Std:  {diff.std():.4f} mGal")
print(f"  Max:  {diff.abs().max():.4f} mGal")

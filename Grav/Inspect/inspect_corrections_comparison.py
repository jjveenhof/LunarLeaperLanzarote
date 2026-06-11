"""
Compare our FAC/BC corrections against the colleague's FA/BA corrections.

Both are applied relative to the per-day base mean, so they are directly
comparable. Differences arise from:
  - Different Bouguer factor (G value or spherical vs infinite slab)
  - Different normal gravity formula (FA only)
  - Different rho (if applicable)

Input
-----
    Data/Gravimetry/Processed/bouguer_anomaly_decay_rho{X}.csv   (ours)
    Data/Gravimetry/Processed/LL_gravity_corrections.csv          (colleague)
    Data/Gravimetry/Processed/lsq_corrected_decay.csv             (for Date/StationType)

Usage
-----
    python inspect_corrections_comparison.py          # default rho = 1.875
    python inspect_corrections_comparison.py 2.0
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

BASE     = Path(__file__).resolve().parents[3]
PROC_DIR = BASE / "Data/Gravimetry/Processed"
SAVE_DIR = BASE / "Results/Grav/Corrections"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

rho     = float(sys.argv[1]) if len(sys.argv) > 1 else 1.875
rho_str = f"{rho:.3f}".rstrip("0").rstrip(".").replace(".", "p")

ours = pd.read_csv(PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str}.csv")
col  = pd.read_csv(PROC_DIR / "LL_gravity_corrections.csv")
lsq  = pd.read_csv(PROC_DIR / "lsq_corrected_decay.csv",
                   dtype={"Date": str})

# -- Compute colleague's relative corrections (per-day base mean) --------------
col = col.merge(lsq[["Line", "Station", "StationType", "Date"]].drop_duplicates(),
                on=["Line", "Station"], how="left")

base_ref = (col[col["StationType"] == "base"]
            .dropna(subset=["FA_correction"])
            .groupby(["Line", "Date"])[["FA_correction", "BA_correction"]]
            .mean()
            .rename(columns={"FA_correction": "FA_base", "BA_correction": "BA_base"})
            .reset_index())

col = col.merge(base_ref, on=["Line", "Date"], how="left")
col["FAC_col"] = col["FA_correction"] - col["FA_base"]
col["BC_col"]  = col["BA_correction"] - col["BA_base"]

# -- Merge ours and colleague on (Line, Station) --------------------------------
df = ours.merge(
    col[["Line", "Station", "FAC_col", "BC_col"]],
    on=["Line", "Station"], how="inner"
)
df = df[df["StationType"] != "base"].dropna(subset=["FAC", "FAC_col"])

# Our FAC + LAT combined matches what the colleague includes in his dFA
df["FAC_total"] = df["FAC"] + df["LAT"].fillna(0)
df["dFAC"] = df["FAC_total"] - df["FAC_col"]
df["dBC"]  = df["BC"] - df["BC_col"]

# -- Figures -------------------------------------------------------------------
lines  = sorted(df["Line"].unique())
colors = plt.cm.tab10(np.linspace(0, 0.4, len(lines)))
lc     = {l: c for l, c in zip(lines, colors)}

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle(f"Correction comparison  [rho = {rho} g/cm3]",
             fontsize=12, fontweight="bold")

ax_fac_sc, ax_bc_sc   = axes[0]
ax_fac_diff, ax_bc_diff = axes[1]

# -- Scatter: our FAC vs colleague FAC ----------------------------------------
for line, grp in df.groupby("Line"):
    ax_fac_sc.scatter(grp["FAC_col"], grp["FAC_total"], s=30, color=lc[line],
                      label=f"Line {line}", zorder=3)
lim = max(df[["FAC_total", "FAC_col"]].abs().max().max() * 1.1, 0.01)
ax_fac_sc.plot([-lim, lim], [-lim, lim], "k--", linewidth=0.8, label="1:1")
ax_fac_sc.set_xlabel("Colleague FAC + LAT (mGal)")
ax_fac_sc.set_ylabel("Our FAC + LAT (mGal)")
ax_fac_sc.set_title("Free-air + latitude correction")
ax_fac_sc.legend(fontsize=7)
ax_fac_sc.grid(True, alpha=0.25, linestyle="--")

# -- Scatter: our BC vs colleague BC ------------------------------------------
for line, grp in df.groupby("Line"):
    ax_bc_sc.scatter(grp["BC_col"], grp["BC"], s=30, color=lc[line],
                     label=f"Line {line}", zorder=3)
lim = max(df[["BC", "BC_col"]].abs().max().max() * 1.1, 0.01)
ax_bc_sc.plot([-lim, lim], [-lim, lim], "k--", linewidth=0.8, label="1:1")
ax_bc_sc.set_xlabel("Colleague BC (mGal)")
ax_bc_sc.set_ylabel("Our BC (mGal)")
ax_bc_sc.set_title("Bouguer correction")
ax_bc_sc.legend(fontsize=7)
ax_bc_sc.grid(True, alpha=0.25, linestyle="--")

# -- Difference per station: FAC ----------------------------------------------
x = np.arange(len(df))
for line, grp in df.groupby("Line"):
    idx = df.index.get_indexer(grp.index)
    ax_fac_diff.bar(idx, grp["dFAC"], color=lc[line], label=f"Line {line}")
ax_fac_diff.axhline(0, color="black", linewidth=0.8, linestyle="--")
ax_fac_diff.set_ylabel("Our (FAC+LAT) - Colleague FAC (mGal)")
ax_fac_diff.set_title(f"FAC+LAT difference  mean={df['dFAC'].mean():.4f}  std={df['dFAC'].std():.4f} mGal")
ax_fac_diff.set_xlabel("Station index")
ax_fac_diff.legend(fontsize=7)
ax_fac_diff.grid(True, alpha=0.25, linestyle="--", axis="y")

# -- Difference per station: BC -----------------------------------------------
for line, grp in df.groupby("Line"):
    idx = df.index.get_indexer(grp.index)
    ax_bc_diff.bar(idx, grp["dBC"], color=lc[line], label=f"Line {line}")
ax_bc_diff.axhline(0, color="black", linewidth=0.8, linestyle="--")
ax_bc_diff.set_ylabel("Our BC - Colleague BC (mGal)")
ax_bc_diff.set_title(f"BC difference  mean={df['dBC'].mean():.4f}  std={df['dBC'].std():.4f} mGal")
ax_bc_diff.set_xlabel("Station index")
ax_bc_diff.legend(fontsize=7)
ax_bc_diff.grid(True, alpha=0.25, linestyle="--", axis="y")

plt.tight_layout()
save_path = SAVE_DIR / f"corrections_comparison_rho{rho_str}.png"
fig.savefig(save_path, dpi=150, bbox_inches="tight")
print(f"Saved -> {save_path.name}")

# -- Print summary -------------------------------------------------------------
print(f"\nFAC+LAT comparison (our - colleague):")
print(f"  mean = {df['dFAC'].mean():.5f} mGal")
print(f"  std  = {df['dFAC'].std():.5f} mGal")
print(f"  max  = {df['dFAC'].abs().max():.5f} mGal")
print(f"\nBC comparison (our - colleague):")
print(f"  mean = {df['dBC'].mean():.5f} mGal")
print(f"  std  = {df['dBC'].std():.5f} mGal")
print(f"  max  = {df['dBC'].abs().max():.5f} mGal")

plt.show()

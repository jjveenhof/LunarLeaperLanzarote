"""
Visualise Bouguer anomaly profiles -- one figure per Line.

Auto-detects which anomaly column to plot:
  CBA   (Complete Bouguer Anomaly, with terrain correction)  -- preferred
  SBA   (Simple Bouguer Anomaly, no terrain correction)      -- fallback

SE column must match anomaly: CBA -> SE_CBA, SBA -> SE_SBA. No SE = no error bars.

Usage
-----
    python visualise_CBA.py                                      # default rho=2.0 SBA file
    python visualise_CBA.py 1.875                               # SBA file rho=1.875
    python visualise_CBA.py bouguer_anomaly_decay_colleague.csv # any file by name
    python visualise_CBA.py bouguer_anomaly_decay_rho1p875_with_TC.csv
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.ticker as mticker
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from visualise_lines import along_profile_distance

BASE     = Path(__file__).resolve().parents[2]
PROC_DIR = BASE / "Data/Gravimetry/Processed"

# Accept either a rho value or a filename
arg = sys.argv[1] if len(sys.argv) > 1 else "1.875"
try:
    rho     = float(arg)
    rho_str = f"{rho:.3f}".rstrip("0").rstrip(".").replace(".", "p")
    INPUT   = PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str}.csv"
except ValueError:
    INPUT   = PROC_DIR / arg

INVERT_LINES = {4}


def location_positions(line_df):
    return (line_df[line_df["Easting"].notna()]
            .groupby("loc_id")[["Easting", "Northing"]]
            .mean())


def plot_line(ax, line_df, line_id, g_col, se_col, title_suffix):
    plot_df = line_df[line_df["StationType"] != "base"].copy()
    if plot_df.empty:
        return

    loc_pos = location_positions(plot_df)
    loc_rep = loc_pos.reset_index()
    loc_rep["Station"] = loc_rep["loc_id"]
    loc_rep = along_profile_distance(loc_rep)
    dist_map = loc_rep.set_index("loc_id")["dist"].to_dict()

    plot_df["dist"] = plot_df["loc_id"].map(dist_map)

    if line_id in INVERT_LINES:
        plot_df["dist"] = plot_df["dist"].max() - plot_df["dist"]

    for loc_id, loc_grp in plot_df.groupby("loc_id"):
        dist = loc_grp["dist"].iloc[0]
        if pd.isna(dist):
            continue

        g  = loc_grp[g_col].iloc[0]
        se = loc_grp[se_col].iloc[0] if se_col else None

        ax.errorbar(dist, g, yerr=se,
                    fmt="o", color="black",
                    markersize=6, capsize=4 if se else 0,
                    linewidth=1.2, elinewidth=1.2,
                    zorder=5)
        ax.annotate(f"P{int(loc_id)}",
                    (dist, g + (se or 0)),
                    fontsize=6, ha="center", va="bottom",
                    xytext=(0, 4), textcoords="offset points",
                    color="black", zorder=6)

    ax.set_title(f"Line {line_id}  [{title_suffix}]", fontsize=11, fontweight="bold")
    ax.set_xlabel("Distance along profile (m)")
    ax.set_ylabel(f"{g_col} (mGal)")

    if line_id in {2, 3, 5}:
        ax.text(0.01, 0.97, "S", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top", ha="left")
        ax.text(0.99, 0.97, "N", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top", ha="right")

    ax.grid(True, alpha=0.25, linestyle="--")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
    label = f"{g_col} +/- {se_col}" if se_col else f"{g_col} (no SE available)"
    ax.legend(handles=[
        mlines.Line2D([], [], marker="o", color="black", linestyle="None",
                      markersize=6, label=label),
    ], fontsize=7, loc="best")


def main():
    print(f"Reading {INPUT.name} ...")
    df = pd.read_csv(INPUT, dtype={"Date": str})

    # Auto-detect anomaly column; SE column must match (CBA->SE_CBA, SBA->SE_SBA)
    g_col  = "CBA" if "CBA" in df.columns else "SBA"
    se_col = f"SE_{g_col}" if f"SE_{g_col}" in df.columns else None

    print(f"  Plotting: {g_col}  +/-  {se_col}")
    print(f"  {df[df['StationType'] != 'base'].groupby(['Line','loc_id']).ngroups} "
          f"unique locations across Lines {sorted(df['Line'].unique())}")

    fig_dir = BASE / "Results/Grav/Bouguer"
    fig_dir.mkdir(parents=True, exist_ok=True)
    stem = INPUT.stem

    for line_id in sorted(df["Line"].unique()):
        fig, ax = plt.subplots(figsize=(13, 5))
        plot_line(ax, df[df["Line"] == line_id].copy(),
                  line_id, g_col, se_col, stem)
        fig.tight_layout()
        save_path = fig_dir / f"{stem}_line{line_id}.png"
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved -> {save_path.name}")

    plt.show()


if __name__ == "__main__":
    main()

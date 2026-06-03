"""
Visualise Simple Bouguer Anomaly (SBA) profiles -- one figure per Line.

Input
-----
    Data/Gravimetry/Processed/bouguer_anomaly_decay.csv

Each subplot shows
    * (black circle) -- SBA +/- SE_CBA per unique physical location
    P-number annotated above each marker.

Usage
-----
    python visualise_CBA.py          # default rho = 2.0
    python visualise_CBA.py 2.5     # rho = 2.5
"""

import sys
import numpy as np

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.ticker as mticker
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from visualise_lines import along_profile_distance

BASE     = Path(__file__).resolve().parents[2]
PROC_DIR = BASE / "Data/Gravimetry/Processed"

rho     = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
rho_str = f"{rho:.1f}".replace(".", "p")
DEFAULT = PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str}.csv"

INVERT_LINES = {4}


def location_positions(line_df):
    return (line_df[line_df["Easting"].notna()]
            .groupby("loc_id")[["Easting", "Northing"]]
            .mean())


def plot_line(ax, line_df, line_id):
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
        max_dist = plot_df["dist"].max()
        plot_df["dist"] = max_dist - plot_df["dist"]

    for loc_id, loc_grp in plot_df.groupby("loc_id"):
        dist  = loc_grp["dist"].iloc[0]
        if pd.isna(dist):
            continue

        sba    = loc_grp["SBA"].iloc[0]
        se_cba = loc_grp["SE_CBA"].iloc[0]

        ax.errorbar(dist, sba, yerr=se_cba,
                    fmt="o", color="black",
                    markersize=6, capsize=4,
                    linewidth=1.2, elinewidth=1.2,
                    zorder=5)
        ax.annotate(f"P{int(loc_id)}",
                    (dist, sba + se_cba),
                    fontsize=6, ha="center", va="bottom",
                    xytext=(0, 4), textcoords="offset points",
                    color="black", zorder=6)

    ax.set_title(f"Line {line_id}  [rho = {rho} g/cm3]", fontsize=11, fontweight="bold")
    ax.set_xlabel("Distance along profile (m)")
    ax.set_ylabel("Simple Bouguer Anomaly (mGal)")

    if line_id in {2, 3, 5}:
        ax.text(0.01, 0.97, "S", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top", ha="left")
        ax.text(0.99, 0.97, "N", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top", ha="right")

    ax.grid(True, alpha=0.25, linestyle="--")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
    ax.legend(handles=[
        mlines.Line2D([], [], marker="o", color="black", linestyle="None",
                      markersize=6, label="SBA +/- SE_CBA"),
    ], fontsize=7, loc="best")


def main():
    path = DEFAULT

    print(f"Reading {path.name} ...")
    df = pd.read_csv(path, dtype={"Date": str})
    print(f"  {df[df['StationType'] != 'base'].groupby(['Line','loc_id']).ngroups} "
          f"unique locations across Lines {sorted(df['Line'].unique())}")

    fig_dir = BASE / "Results/Grav/Bouguer"
    fig_dir.mkdir(parents=True, exist_ok=True)

    for line_id in sorted(df["Line"].unique()):
        fig, ax = plt.subplots(figsize=(13, 5))
        plot_line(ax, df[df["Line"] == line_id].copy(), line_id)
        fig.tight_layout()
        save_path = fig_dir / f"SBA_rho{rho_str}_line{line_id}.png"
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved -> {save_path.name}")

    plt.show()


if __name__ == "__main__":
    main()

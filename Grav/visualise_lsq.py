"""
Visualise LSQ drift-corrected gravity profiles -- one figure per Line.

Input
-----
    Data/Gravimetry/lsq_corrected_{name}.csv   (default: lsq_corrected_drop5.csv)
    Pass a different filename as a command-line argument.

Each subplot shows
    * (large, grey)   -- LSQ estimate g_k +/- SE_lsq per unique physical location
    . (small, coloured by loop) -- individual drift-corrected measurements
                                  (= Grav_est - drift - offset = g_k + residual)
      The spread of the dots around the grey marker is the actual fit quality
      at that location.
    Station numbers annotate the individual dots.

Usage
-----
    python visualise_lsq.py                         # uses default file
    python visualise_lsq.py lsq_corrected_drop0.csv
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from visualise_lines import along_profile_distance

BASE      = Path(__file__).resolve().parents[2]
DATA_DIR  = BASE / "Data/Gravimetry"
PROC_DIR  = BASE / "Data/Gravimetry/Processed"
DEFAULT   = PROC_DIR / "lsq_corrected_decay.csv"

LOOP_CMAP   = plt.cm.tab10
INVERT_LINES = {4}


# -- Per-location mean GNSS position -------------------------------------------

def location_positions(line_df):
    """
    For each loc_id, compute the mean Easting/Northing across all stations.
    Returns a DataFrame indexed by loc_id with columns Easting, Northing.
    """
    return (line_df[line_df["Easting"].notna()]
            .groupby("loc_id")[["Easting", "Northing"]]
            .mean())


# -- Plot one line --------------------------------------------------------------

def plot_line(ax, line_df, line_id):
    # Exclude base stations from the profile (same as visualise_lines.py)
    plot_df = line_df[line_df["StationType"] != "base"].copy()
    if plot_df.empty:
        return

    # Compute profile distances using mean GNSS position per location
    loc_pos = location_positions(plot_df)
    # Build a representative-position DataFrame for distance calculation
    loc_rep = loc_pos.reset_index()
    loc_rep["Station"] = loc_rep["loc_id"]      # along_profile_distance needs this column
    loc_rep = along_profile_distance(loc_rep)   # adds "dist" column
    dist_map = loc_rep.set_index("loc_id")["dist"].to_dict()

    plot_df["dist"] = plot_df["loc_id"].map(dist_map)

    if line_id in INVERT_LINES:
        max_dist = plot_df["dist"].max()
        plot_df["dist"] = max_dist - plot_df["dist"]

    loops    = sorted(plot_df["loop_id"].dropna().unique())
    loop_map = {l: i for i, l in enumerate(loops)}

    # -- One pass per location -------------------------------------------------
    for loc_id, loc_grp in plot_df.groupby("loc_id"):
        dist = loc_grp["dist"].iloc[0]
        if pd.isna(dist):
            continue

        # All stations at this location share the same g_k and SE_lsq
        g_k    = loc_grp["Grav_lsq"].iloc[0]
        se_lsq = loc_grp["SE_lsq"].iloc[0]

        # Individual drift-corrected measurements: g_k + residual
        # Draw these first so the hollow estimate marker sits on top
        rows_with_loop = loc_grp[loc_grp["loop_id"].notna()]
        for _, row in rows_with_loop.iterrows():
            j      = loop_map.get(row["loop_id"], 0)
            color  = LOOP_CMAP(int(j) % 10)
            g_corr = row["Grav_lsq"] + row["residual"]

            ax.plot(dist, g_corr, "x", color=color,
                    markersize=8, markeredgewidth=1.8, zorder=6, alpha=0.9)
            # Alternate labels left/right by loop index so they don't stack
            right = (j % 2 == 0)
            ax.annotate(str(int(row["Station"])),
                        (dist, g_corr),
                        fontsize=7,
                        ha="left" if right else "right",
                        va="center",
                        xytext=(6 if right else -6, 0),
                        textcoords="offset points",
                        color=color, zorder=6)

        # Filled black estimate marker with SE error bar
        ax.errorbar(dist, g_k, yerr=se_lsq,
                    fmt="o", color="black",
                    markersize=6, capsize=4,
                    linewidth=1.2, elinewidth=1.2,
                    zorder=5)
        ax.annotate(f"P{int(loc_id)}",
                    (dist, g_k + se_lsq),
                    fontsize=6, ha="center", va="bottom",
                    xytext=(0, 4), textcoords="offset points",
                    color="black", zorder=7)

    ax.set_title(f"Line {line_id}", fontsize=11, fontweight="bold")
    ax.set_xlabel("Distance along profile (m)")
    ax.set_ylabel("Gravity anomaly (mGal)")

    if line_id in {2, 3, 5}:
        ax.text(0.01, 0.97, "S", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top", ha="left")
        ax.text(0.99, 0.97, "N", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top", ha="right")
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))

    # Legend
    loop_handles = [
        mpatches.Patch(color=LOOP_CMAP(loop_map[l] % 10), label=f"Loop {int(l)}")
        for l in loops
    ]
    symbol_handles = [
        mlines.Line2D([], [], marker="o", color="black", linestyle="None",
                      markersize=6, label="g_k +/- SE_lsq"),
        mlines.Line2D([], [], marker="x", color="steelblue", linestyle="None",
                      markersize=8, markeredgewidth=1.8,
                      label="Individual drift-corrected meas."),
    ]
    ax.legend(handles=symbol_handles + loop_handles, fontsize=7, ncol=2, loc="best")


# -- Main ----------------------------------------------------------------------

def main(filepath=None):
    path = Path(filepath) if filepath else (
        PROC_DIR / sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    )

    print(f"Reading {path.name} ...")
    df = pd.read_csv(path, dtype={"Time_first": str, "Date": str})
    print(f"  {df.groupby(['Line','loc_id']).ngroups} unique locations across "
          f"Lines {sorted(df['Line'].unique())}")

    fig_dir = BASE / "Results/Grav/LSQ"
    fig_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem

    for line_id in sorted(df["Line"].unique()):
        fig, ax = plt.subplots(figsize=(13, 5))
        plot_line(ax, df[df["Line"] == line_id].copy(), line_id)
        fig.tight_layout()
        save_path = fig_dir / f"{stem}_line{line_id}.png"
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved -> {save_path.name}")

    plt.show()


if __name__ == "__main__":
    main()


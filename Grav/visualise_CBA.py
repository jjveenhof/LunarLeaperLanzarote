"""
Visualise Bouguer anomaly profiles -- one figure per Line.

Auto-detects which anomaly column to plot:
  CBA   (Complete Bouguer Anomaly, with terrain correction)  -- preferred
  SBA   (Simple Bouguer Anomaly, no terrain correction)      -- fallback

SE column must match anomaly: CBA -> SE_CBA, SBA -> SE_SBA. No SE = no error bars.

Usage
-----
    python visualise_CBA.py                                      # default rho=1.875 SBA file
    python visualise_CBA.py 2.0                                 # SBA file rho=2.0
    python visualise_CBA.py bouguer_anomaly_decay_colleague.csv # any file by name
    python visualise_CBA.py bouguer_anomaly_decay_rho1p875_with_TC.csv

    --se-sba   When plotting CBA, draw error bars from SE_SBA instead of SE_CBA.
               Off by default. The SBA SE does NOT include terrain-correction
               uncertainty, so these bars understate the true CBA error -- use
               only for presentation/illustration, never as a stated CBA SE.
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.ticker as mticker
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grav_utils import along_profile_distance
from grav_utils import BASE, PROC_DIR, RHO_DEFAULT, sba_file

# Strip flags before positional parse
USE_SBA_SE = "--se-sba" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]

# Accept either a rho value or a filename
arg = args[0] if args else str(RHO_DEFAULT)
try:
    INPUT = sba_file(float(arg))
except ValueError:
    INPUT = PROC_DIR / arg

INVERT_LINES = {4}

# Per-line colours matching the QGIS map styling (Code/QGIS/CLAUDE.md)
LINE_COLORS = {2: "#0099FF", 3: "#FF5C00", 5: "#00CC80"}
DEFAULT_COLOR = "black"


def location_positions(line_df):
    return (line_df[line_df["Easting"].notna()]
            .groupby("loc_id")[["Easting", "Northing"]]
            .mean())


def plot_line(ax, line_df, line_id, g_col, se_col, title_suffix, se_label=None):
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

    color = LINE_COLORS.get(line_id, DEFAULT_COLOR)

    for loc_id, loc_grp in plot_df.groupby("loc_id"):
        dist = loc_grp["dist"].iloc[0]
        if pd.isna(dist):
            continue

        g  = loc_grp[g_col].iloc[0]
        se = loc_grp[se_col].iloc[0] if se_col else None

        ax.errorbar(dist, g, yerr=se,
                    fmt="o", color=color,
                    markersize=6, capsize=4 if se else 0,
                    linewidth=1.2, elinewidth=1.2,
                    zorder=5)
        ax.annotate(f"P{int(loc_id)}",
                    (dist, g + (se or 0)),
                    fontsize=6, ha="center", va="bottom",
                    xytext=(0, 4), textcoords="offset points",
                    color=color, zorder=6)

    ax.set_title(f"Line {line_id}  [{title_suffix}]", fontsize=11, fontweight="bold")
    ax.set_xlabel("Distance along profile (m)")
    ax.set_ylabel(f"{g_col} (mGal)")

    if line_id in {2, 3, 5}:
        ax.invert_xaxis()      # plot N->S (N left) to match the GPR sections
        ax.text(0.01, 0.97, "N", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top", ha="left")
        ax.text(0.99, 0.97, "S", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top", ha="right")

    ax.grid(True, alpha=0.25, linestyle="--")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
    if se_col:
        label = f"{g_col} +/- {se_label or se_col}"
    else:
        label = f"{g_col} (no SE available)"
    ax.legend(handles=[
        mlines.Line2D([], [], marker="o", color=color, linestyle="None",
                      markersize=6, label=label),
    ], fontsize=7, loc="best")


def main():
    print(f"Reading {INPUT.name} ...")
    df = pd.read_csv(INPUT, dtype={"Date": str})

    # Auto-detect anomaly column; SE column must match (CBA->SE_CBA, SBA->SE_SBA)
    g_col  = "CBA" if "CBA" in df.columns else "SBA"
    se_col = f"SE_{g_col}" if f"SE_{g_col}" in df.columns else None

    # Opt-in override: borrow SBA's SE for CBA error bars (presentation only).
    se_label = None
    if USE_SBA_SE and g_col == "CBA":
        if "SE_SBA" not in df.columns:
            sys.exit(f"ERROR: --se-sba requested but {INPUT.name} has no SE_SBA column.")
        se_col = "SE_SBA"
        se_label = "SE"  # keep the plot legend generic, no on-plot disclaimer
        print("  !! --se-sba: drawing CBA error bars from SE_SBA.")
        print("  !! These bars EXCLUDE terrain-correction uncertainty and")
        print("  !! understate the true CBA error. Presentation use only.")

    print(f"  Plotting: {g_col}  +/-  {se_col}")
    print(f"  {df[df['StationType'] != 'base'].groupby(['Line','loc_id']).ngroups} "
          f"unique locations across Lines {sorted(df['Line'].unique())}")

    fig_dir = BASE / "Results/Grav/Bouguer"
    fig_dir.mkdir(parents=True, exist_ok=True)
    stem = INPUT.stem

    for line_id in sorted(df["Line"].unique()):
        fig, ax = plt.subplots(figsize=(13, 5))
        plot_line(ax, df[df["Line"] == line_id].copy(),
                  line_id, g_col, se_col, stem, se_label=se_label)
        fig.tight_layout()
        save_path = fig_dir / f"{stem}_line{line_id}.png"
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved -> {save_path.name}")

    plt.show()


if __name__ == "__main__":
    main()

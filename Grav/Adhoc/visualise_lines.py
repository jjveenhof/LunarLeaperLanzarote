"""
LEGACY -- visualises the simple (linear) drift correction output, which is no
longer part of the default pipeline. Use visualise_lsq.py for the LSQ branch.
Regenerate the input with: python run_pipeline.py --with-simple-drift

Visualise drift-corrected gravity profiles -- one panel per Line.

Input
-----
  Data/Gravimetry/Processed/simple_drift_{name}.csv

Each panel shows
  - Drift-corrected gravity with SE error bars
  - Colour per measurement loop
  - Marker shape per station type  (* base  ^ tie  * regular)
  - X-axis: signed distance along the line's principal axis (metres)
    so the profile reads left-to-right regardless of orientation.
  - Stations without GNSS coordinates are interpolated onto the axis.
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib.ticker as mticker
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grav_utils import BASE, PROC_DIR, along_profile_distance

CORR_FILE = PROC_DIR / "simple_drift_decay.csv"

# -- Styling -------------------------------------------------------------------
LOOP_CMAP   = plt.cm.tab10
MARKERS     = {"base": "s", "tie": "^", "regular": "o"}
MARKERSIZES = {"base": 8,   "tie": 8,   "regular": 6}
LABELS      = {"base": "Base", "tie": "Tie", "regular": "Regular"}

# Lines whose profile x-axis should be flipped
INVERT_LINES = {4}



# -- Plot ----------------------------------------------------------------------

def plot_line(ax, line_df, line_id):
    # Base stations are drift correction anchors, not survey points -- exclude from profile
    plot_df = line_df[line_df["StationType"] != "base"].copy()

    plot_df = along_profile_distance(plot_df)
    loop_ids = sorted(plot_df["loop_id"].dropna().unique())

    def _plot_group(grp, color):
        grp = grp[grp["dist"].notna() & grp["Grav_corr"].notna()]
        if grp.empty:
            return
        stype = grp["StationType"].iloc[0]
        ax.errorbar(
            grp["dist"], grp["Grav_corr"],
            yerr=grp["SE_corr"],
            fmt=MARKERS.get(stype, "o"),
            color=color,
            markersize=MARKERSIZES.get(stype, 6),
            capsize=3, linewidth=0.8, elinewidth=0.8,
            zorder=3,
        )
        for _, row in grp.iterrows():
            ax.annotate(str(int(row["Station"])),
                        (row["dist"], row["Grav_corr"]),
                        fontsize=8, ha="center", va="bottom",
                        xytext=(10, 0), textcoords="offset points",
                        color='black', zorder=4)

    for loop_id in loop_ids:
        color = LOOP_CMAP(int(loop_id) % 10)
        loop  = plot_df[plot_df["loop_id"] == loop_id]
        for _, grp in loop.groupby("StationType"):
            _plot_group(grp.copy(), color)
        # Add a single dummy errorbar for the legend entry
        ax.errorbar([], [], label=f"Loop {int(loop_id)}", color=color,
                    fmt="o", markersize=MARKERSIZES["regular"])

    # Transition stations (not in any loop)
    orphans = plot_df[plot_df["loop_id"].isna() & plot_df["Grav_corr"].notna()]
    for _, grp in orphans.groupby("StationType"):
        _plot_group(grp.copy(), "grey")

    ax.set_title(f"Line {line_id}", fontsize=11, fontweight="bold")
    ax.set_xlabel("Distance along profile (m)")
    ax.set_ylabel("Gravity (mGal)")
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))

    if line_id in INVERT_LINES:
        ax.invert_xaxis()

    # -- Legend: loops by colour, types by marker ------------------------------
    loop_handles = []
    seen_loops   = set()
    type_handles = [
        mlines.Line2D([], [], marker=m, color="dimgrey", linestyle="None",
                      markersize=MARKERSIZES[t], label=LABELS[t])
        for t, m in MARKERS.items() if t != "base"
    ]
    for loop_id in loop_ids:
        if loop_id in seen_loops:
            continue
        seen_loops.add(loop_id)
        loop_handles.append(
            mpatches.Patch(color=LOOP_CMAP(int(loop_id) % 10),
                           label=f"Loop {int(loop_id)}")
        )
    ax.legend(handles=loop_handles + type_handles,
              fontsize=7, ncol=2, loc="best")


# -- Main ----------------------------------------------------------------------

def main(filepath=None):
    path = Path(filepath) if filepath else CORR_FILE
    df   = pd.read_csv(path, dtype={"Time_first": str, "Date": str})
    lines   = sorted(df["Line"].unique())
    fig_dir = BASE / "Results/Grav/Simple drift correction"
    fig_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem

    for line_id in lines:
        fig, ax = plt.subplots(figsize=(12, 5))
        plot_line(ax, df[df["Line"] == line_id].copy(), line_id)
        fig.tight_layout()
        save_path = fig_dir / f"{stem}_line{line_id}.png"
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved -> {save_path.name}")

    plt.show()


if __name__ == "__main__":
    main()


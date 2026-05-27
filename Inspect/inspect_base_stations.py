"""
Inspect base station measurements across all lines.

Two panels per line:
  Left  -- Individual raw CG-5 readings at every base station over time,
            coloured by station number. Shows within-day drift and noise.
  Right -- LSQ residuals for base station observations per loop.
            Shows how well the linear drift model captures each loop's base.
            A flat zero line = perfect model; scatter = unmodelled drift.
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from pathlib import Path

BASE     = Path(__file__).resolve().parents[2]
PROC_DIR = BASE / "Data/Gravimetry/Processed"
SAVE_DIR = BASE / "Analysis/Grav"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

LOOP_CMAP    = plt.cm.tab10
STATION_CMAP = plt.cm.Set1

# -- Load data -----------------------------------------------------------------
filt = pd.read_csv(PROC_DIR / "filtered_gravimetry_drop0.csv",
                   dtype={"Time": str, "Date": str})
filt["datetime"] = pd.to_datetime(filt["Date"] + " " + filt["Time"],
                                  format="%Y/%m/%d %H:%M:%S")

lsq = pd.read_csv(PROC_DIR / "lsq_corrected_decay.csv",
                  dtype={"Time_first": str, "Date": str})
lsq["datetime"] = pd.to_datetime(lsq["Date"] + " " + lsq["Time_first"],
                                 format="%Y/%m/%d %H:%M:%S")

lines = sorted(filt["Line"].unique())
n_lines = len(lines)

fig, axes = plt.subplots(n_lines, 2,
                          figsize=(16, n_lines * 5.0),
                          squeeze=False,
                          constrained_layout=True)
fig.suptitle("Base station inspection -- all lines", fontsize=13, fontweight="bold", y=1.01)

for row_idx, line_id in enumerate(lines):
    ax_raw  = axes[row_idx, 0]
    ax_res  = axes[row_idx, 1]

    # -- Left: individual raw readings at base stations -----------------------
    base_filt = filt[(filt["Line"] == line_id) &
                     (filt["StationType"] == "base")].copy()

    t0 = base_filt["datetime"].min()
    base_filt["t_h"] = (base_filt["datetime"] - t0).dt.total_seconds() / 3600

    stations = sorted(base_filt["Station"].unique())
    sta_map  = {s: i for i, s in enumerate(stations)}

    for station, grp in base_filt.groupby("Station"):
        color = STATION_CMAP(sta_map[station] % 9)
        ax_raw.errorbar(grp["t_h"], grp["Grav"],
                        yerr=grp["SE_i"],
                        fmt="o", color=color, markersize=4,
                        capsize=2, elinewidth=0.8, linewidth=0,
                        label=f"S{station}", zorder=3)

    ax_raw.set_title(f"Line {line_id} -- raw base readings", fontsize=10)
    ax_raw.set_xlabel("Time since first reading (h)")
    ax_raw.set_ylabel("Gravity (mGal)")
    ax_raw.yaxis.set_major_formatter(plt.matplotlib.ticker.FormatStrFormatter("%.3f"))
    ax_raw.grid(True, alpha=0.25, linestyle="--")
    ax_raw.legend(fontsize=7, ncol=2, loc="best")

    # -- Right: LSQ residuals at base stations per loop -----------------------
    base_lsq = lsq[(lsq["Line"] == line_id) &
                   (lsq["StationType"] == "base")].copy()

    t0_lsq = base_lsq["datetime"].min()
    base_lsq["t_h"] = (base_lsq["datetime"] - t0_lsq).dt.total_seconds() / 3600

    loops    = sorted(base_lsq["loop_id"].dropna().unique())
    loop_map = {l: i for i, l in enumerate(loops)}

    for _, row in base_lsq.iterrows():
        if pd.isna(row["loop_id"]):
            continue
        j     = loop_map[row["loop_id"]]
        color = LOOP_CMAP(j % 10)
        resid_microGal = row["residual"] * 1000
        ax_res.scatter(row["t_h"], resid_microGal,
                       color=color, s=50, zorder=3,
                       label=f"Loop {int(row['loop_id'])}")

    ax_res.axhline(0, color="black", linewidth=1.0, linestyle="--", zorder=2)
    ax_res.set_title(f"Line {line_id} -- base residuals per loop", fontsize=10)
    ax_res.set_xlabel("Time since first reading (h)")
    ax_res.set_ylabel("Residual (microGal)")
    ax_res.grid(True, alpha=0.25, linestyle="--")

    # Deduplicate legend entries
    handles, labels = ax_res.get_legend_handles_labels()
    seen = {}
    for h, l in zip(handles, labels):
        if l not in seen:
            seen[l] = h
    ax_res.legend(seen.values(), seen.keys(), fontsize=7, loc="best")

save_path = SAVE_DIR / "base_station_inspection.png"
fig.savefig(save_path, dpi=150, bbox_inches="tight")
print(f"Saved -> {save_path}")
plt.show()

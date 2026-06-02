"""
Inspect base station measurements across all lines.

Two rows, one column per line:
  Top    -- g_inf (Grav_est from decay fit) +/- SE_est per base station over
             time. One point per station; shows the settled gravity estimate.
  Bottom -- LSQ residuals for base station observations per loop.
             Shows how well the linear drift model captures each loop's base.
             A flat zero line = perfect model; scatter = unmodelled drift.
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

BASE     = Path(__file__).resolve().parents[3]
PROC_DIR = BASE / "Data/Gravimetry/Processed"
SAVE_DIR = BASE / "Results/Grav/LSQ/Stats"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

LOOP_CMAP = plt.cm.tab10

# -- Load data -----------------------------------------------------------------
# station_means_decay.csv: one row per station; Grav_est = g_inf from decay fit
means = pd.read_csv(PROC_DIR / "station_means_decay.csv",
                    dtype={"Time_first": str, "Date": str})
means["datetime"] = pd.to_datetime(means["Date"] + " " + means["Time_first"],
                                   format="%Y/%m/%d %H:%M:%S")

# lsq_corrected_decay.csv: LSQ residuals per station/loop
lsq = pd.read_csv(PROC_DIR / "lsq_corrected_decay.csv",
                  dtype={"Time_first": str, "Date": str})
lsq["datetime"] = pd.to_datetime(lsq["Date"] + " " + lsq["Time_first"],
                                 format="%Y/%m/%d %H:%M:%S")

lines   = sorted(means["Line"].unique())
n_lines = len(lines)

fig, axes = plt.subplots(2, n_lines,
                          figsize=(n_lines * 6, 10),
                          squeeze=False,
                          constrained_layout=True)
fig.suptitle("Base station inspection -- all lines", fontsize=13, fontweight="bold")

res_axes = []
raw_axes = []

for col_idx, line_id in enumerate(lines):
    ax_raw  = axes[0, col_idx]
    ax_res  = axes[1, col_idx]
    res_axes.append(ax_res)
    raw_axes.append(ax_raw)

    # -- Top: g_inf per base station -------------------------------------------
    base_means = means[(means["Line"] == line_id) &
                       (means["StationType"] == "base")].copy()

    t0 = base_means["datetime"].min()
    base_means["t_h"] = (base_means["datetime"] - t0).dt.total_seconds() / 3600

    for _, mrow in base_means.iterrows():
        ax_raw.errorbar(mrow["t_h"], mrow["Grav_est"],
                        yerr=mrow["SE_est"],
                        fmt="o", color="steelblue", markersize=6,
                        capsize=4, elinewidth=1.2, linewidth=0,
                        zorder=3)
        ax_raw.annotate(f"S{int(mrow['Station'])}",
                        (mrow["t_h"], mrow["Grav_est"]),
                        fontsize=7, ha="left", va="bottom",
                        xytext=(4, 3), textcoords="offset points",
                        color="black", zorder=4)

    ax_raw.set_title(f"Line {line_id} -- base g_inf", fontsize=10)
    ax_raw.set_xlabel("Time since first reading (h)")
    ax_raw.set_ylabel("Gravity (mGal)")
    ax_raw.yaxis.set_major_formatter(plt.matplotlib.ticker.FormatStrFormatter("%.3f"))
    ax_raw.grid(True, alpha=0.25, linestyle="--")

    # -- Bottom: LSQ residuals at base stations per loop -----------------------
    # Colored by loop; station annotated on each point
    base_lsq = lsq[(lsq["Line"] == line_id) &
                   (lsq["StationType"] == "base")].copy()

    t0_lsq = base_lsq["datetime"].min()
    base_lsq["t_h"] = (base_lsq["datetime"] - t0_lsq).dt.total_seconds() / 3600

    loops    = sorted(base_lsq["loop_id"].dropna().unique())
    loop_map = {l: i for i, l in enumerate(loops)}

    for _, row in base_lsq.iterrows():
        if pd.isna(row["loop_id"]):
            continue
        color = LOOP_CMAP(loop_map[row["loop_id"]] % 10)
        resid_microGal = row["residual"] * 1000
        ax_res.scatter(row["t_h"], resid_microGal,
                       color=color, s=50, zorder=3,
                       label=f"Loop {int(row['loop_id'])}")
        ax_res.annotate(f"S{int(row['Station'])}",
                        (row["t_h"], resid_microGal),
                        fontsize=7, ha="left", va="bottom",
                        xytext=(4, 3), textcoords="offset points",
                        color="black", zorder=4)

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

def share_ylim(axes, symmetric=False):
    """Set a common y range across a list of axes using their autoscaled limits."""
    lo = min(ax.get_ylim()[0] for ax in axes)
    hi = max(ax.get_ylim()[1] for ax in axes)
    if symmetric:
        bound = max(abs(lo), abs(hi))
        ylim = (-bound, bound)
        for ax in axes:
            ax.set_ylim(ylim)
    else:
        span = max(ax.get_ylim()[1] - ax.get_ylim()[0] for ax in axes)
        for ax in axes:
            mid = sum(ax.get_ylim()) / 2
            ax.set_ylim(mid - span / 2, mid + span / 2)

share_ylim(raw_axes, symmetric=False)
share_ylim(res_axes, symmetric=True)

save_path = SAVE_DIR / "base_station_inspection_horiz.png"
fig.savefig(save_path, dpi=150, bbox_inches="tight")
print(f"Saved -> {save_path}")
plt.show()

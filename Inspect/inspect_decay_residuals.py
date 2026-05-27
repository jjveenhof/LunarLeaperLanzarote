"""
Test script: plot |g_i - g_inf| on a log scale for each settling station.

If the decay model is correct, |g_i - g_inf| = |A| * exp(-t/tau), so points
should fall on a straight line. Deviations indicate model inadequacy.

Error bars: sqrt(SE_i^2 + SE(g_inf)^2)
  - SE_i       : per-reading measurement uncertainty (independent per point)
  - SE(g_inf)  : fitted asymptote uncertainty (same shift for all points)
Lower bars are capped just above zero to stay on the log axis.

Only settling stations are shown (settled ones have A ~ 0, not useful here).
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Grav"))
from station_decay import fit_station, decay_model, SIGNIFICANCE_THRESHOLD, FILT_FILE

BASE     = Path(__file__).resolve().parents[2]
SAVE_DIR = BASE / "Analysis/Grav"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(FILT_FILE, dtype={"Time": str, "Date": str})

for line_id, line_df in df.groupby("Line"):
    settling = []
    for station in sorted(line_df["Station"].unique()):
        grp   = line_df[line_df["Station"] == station].sort_values("Time").reset_index(drop=True)
        t_abs = pd.to_datetime(grp["Date"] + " " + grp["Time"], format="%Y/%m/%d %H:%M:%S")
        t_min = (t_abs - t_abs.iloc[0]).dt.total_seconds() / 60
        se    = grp["SE_i"].fillna(grp["SE_i"].mean())
        grav  = grp["Grav"]

        g_inf, se_g_inf, A, se_A, tau, converged = fit_station(t_min, grav, se)
        settled = (not converged) or (abs(A) < SIGNIFICANCE_THRESHOLD * se_A)
        if settled:
            continue
        settling.append((station, t_min.values, grav.values, se.values,
                         g_inf, se_g_inf, A, tau))

    if not settling:
        print(f"Line {line_id}: no settling stations, skipping.")
        continue

    n     = len(settling)
    ncols = min(6, n)
    nrows = int(np.ceil(n / ncols))

    fig, axes = plt.subplots(nrows, ncols,
                              figsize=(ncols * 3.0, nrows * 3.2),
                              squeeze=False)
    fig.suptitle(f"Line {line_id} -- |g - $g_\\infty$| (log scale)\n"
                 "Straight line = exponential decay is a good fit.",
                 fontsize=11)

    for idx, (station, t_min, grav, se, g_inf, se_g_inf, A, tau) in enumerate(settling):
        ax = axes[idx // ncols][idx % ncols]

        resid     = grav - g_inf
        abs_resid = np.abs(resid)
        SE_ri     = np.sqrt(se**2 + se_g_inf**2)

        # Cap lower bar so it doesn't reach zero on the log axis
        lower_err = np.minimum(abs_resid * 0.999, SE_ri)
        upper_err = SE_ri

        pos = (resid > 0) & (abs_resid > 0)
        neg = (resid < 0) & (abs_resid > 0)

        ax.errorbar(t_min[pos], abs_resid[pos],
                    yerr=[lower_err[pos], upper_err[pos]],
                    fmt="o", color="steelblue", markersize=4,
                    capsize=3, elinewidth=1.2, linewidth=0, zorder=3)
        ax.errorbar(t_min[neg], abs_resid[neg],
                    yerr=[lower_err[neg], upper_err[neg]],
                    fmt="v", color="tomato", markersize=4,
                    capsize=3, elinewidth=1.2, linewidth=0, zorder=3)

        t_dense = np.linspace(0, t_min.max(), 200)
        ax.plot(t_dense, np.abs(A) * np.exp(-t_dense / tau),
                color="tab:green", linewidth=1.2, linestyle="--", zorder=2)

        ax.set_yscale("log")
        ax.set_title(f"S{station}  A={A*1000:.1f} mGal/1000, $\\tau$={tau:.1f} min",
                     fontsize=7)
        ax.set_xlabel("Time (min)", fontsize=7)
        ax.set_ylabel("|g - $g_\\infty$| (mGal)", fontsize=7)
        ax.tick_params(labelsize=6)
        ax.grid(True, which="both", alpha=0.2)

    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    legend_handles = [
        mlines.Line2D([], [], marker="o", color="steelblue", linestyle="None",
                      markersize=5, label="$g > g_\\infty$"),
        mlines.Line2D([], [], marker="v", color="tomato", linestyle="None",
                      markersize=5, label="$g < g_\\infty$"),
        mlines.Line2D([], [], color="tab:green", linewidth=1.2, linestyle="--",
                      label="$|A|\\,e^{-t/\\tau}$ (model)"),
    ]
    fig.text(0.5, 0.005,
             "Error bars: $\\sqrt{\\mathrm{SE}_i^2 + \\mathrm{SE}(g_\\infty)^2}$",
             ha="center", fontsize=7, color="dimgrey")
    fig.legend(handles=legend_handles, loc="lower center", ncol=3,
               fontsize=8, frameon=True,
               bbox_to_anchor=(0.5, 0.04), bbox_transform=fig.transFigure)

    plt.tight_layout(rect=[0, 0.09, 1, 0.97])
    save_path = SAVE_DIR / f"decay_residuals_line{line_id}.png"
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Saved -> {save_path.name}")

plt.show()

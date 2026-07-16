"""
Four hand-picked decay-fit panels in a single row, for the appendix figure that
explains the settling/decay model. Reuses station_decay.fit_station and the exact
per-panel styling of the full per-line grids (station_decay.plot_line), so this is
just a curated 1x4 excerpt with ONE shared legend.

Stations (in order), chosen to span the settled<->settling spectrum:
    L5 S0   clearly settled
    L3 S17  dubiously settled
    L5 S28  dubiously unsettled, poorer decay fit
    L5 S1   clearly unsettled, good decay fit

Run:  python Adhoc/decay_examples.py
Out:  Results/Grav/Decay fitting/decay_examples.png
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import station_decay as sd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # Code/ for plot_utils
from plot_utils import save_figure

PICKS = [(5, 0), (3, 17), (5, 28), (5, 1)]      # (line, station), left -> right
OUT = sd.BASE / "Results/Grav/Decay fitting/decay_examples.png"

# Author the figure at the width it occupies on the page: \includegraphics[width=L]
# scales the WHOLE figure (text included) by L/W. Thesis \linewidth = 6.1 in, placed
# full-width -> W = 6.1. LARGER W -> text shrinks on the page; SMALLER W -> text grows.
FIG_W_IN = 6.1
FIG_H_IN = 5.4      # figure height (in); SMALLER -> shorter figure (avoids spilling onto its own page)
NROWS, NCOLS = 2, 2   # panel grid; PICKS fills it row-major (reading order)


def draw_panel(ax, grp):
    """One station panel -- copy of station_decay.plot_line's per-station body."""
    grp = grp.sort_values("Time").reset_index(drop=True)
    t_abs = pd.to_datetime(grp["Date"] + " " + grp["Time"],
                           format="%Y/%m/%d %H:%M:%S")
    t_min = (t_abs - t_abs.iloc[0]).dt.total_seconds() / 60
    grav = grp["Grav"]
    se = grp["SE_i"].fillna(grp["SE_i"].mean())

    g_inf, se_g_inf, A, se_A, tau, converged = sd.fit_station(t_min, grav, se)
    settled = ((not converged) or (abs(A) < sd.SIGNIFICANCE_THRESHOLD * se_A)
               or (tau < sd.TAU_MIN))
    fit_color = "grey" if settled else "tab:green"
    label_color = "red" if not converged else "black"

    ax.errorbar(t_min, grav, yerr=se, fmt="o", color="steelblue", markersize=3,
                capsize=2, linewidth=0.6, elinewidth=0.6, zorder=3)
    t_dense = np.linspace(0, t_min.max(), 200)
    ax.plot(t_dense, sd.decay_model(t_dense, g_inf, A, tau),
            color=fit_color, linewidth=1.2, zorder=2)

    w = 1.0 / se ** 2
    g_wmean = (w * grav).sum() / w.sum()
    se_wmean = 1.0 / np.sqrt(w.sum())

    ax.axhline(g_inf, color=fit_color, linewidth=0.9, linestyle="--", alpha=0.8)
    if not settled:
        ax.axhspan(g_inf - se_g_inf, g_inf + se_g_inf, color="tab:green",
                   alpha=0.15, zorder=1)
    else:
        ax.axhline(g_wmean, color="darkorange", linewidth=0.9, linestyle=":",
                   alpha=0.9)
        ax.axhspan(g_wmean - se_wmean, g_wmean + se_wmean, color="darkorange",
                   alpha=0.15, zorder=1)

    display_g = g_wmean if settled else g_inf
    display_se = se_wmean if settled else se_g_inf
    line_id, station = int(grp["Line"].iloc[0]), int(grp["Station"].iloc[0])
    # No explicit fontsizes: inherit the rcParams defaults so titles / ticks / labels
    # match the axis offset text (which the thesis width renders at the right size).
    ax.set_title(f"L{line_id} S{station}\n"
                 f"$g_\\infty$={display_g:.3f} $\\pm$ {display_se:.3f} mGal",
                 color=label_color, pad=4)
    ax.set_xlabel("t (minutes)")
    # Shorten y-ticks: pull the repeated integer part into one offset label so the
    # ticks show only the deviation. FORCE the offset to this panel's rounded mean so
    # EVERY panel offsets (matplotlib's auto-offset skipped the ~5468 one).
    fmt = mticker.ScalarFormatter()
    fmt.set_useOffset(round(float(grav.mean())))
    ax.yaxis.set_major_formatter(fmt)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
    ax.margins(y=0.18)


def main():
    df = pd.read_csv(sd.FILT_FILE, dtype={"Time": str, "Date": str})
    fig, axes = plt.subplots(NROWS, NCOLS, figsize=(FIG_W_IN, FIG_H_IN))
    axflat = axes.flat

    for ax, (line, station) in zip(axflat, PICKS):
        grp = df[(df["Line"] == line) & (df["Station"] == station)]
        if grp.empty:
            raise SystemExit(f"no readings for L{line} S{station}")
        draw_panel(ax, grp)

    # Same y-span for all panels, each centred on its own data (as in plot_line).
    span = max(ax.get_ylim()[1] - ax.get_ylim()[0] for ax in axes.flat)
    for ax in axes.flat:
        mid = sum(ax.get_ylim()) / 2
        ax.set_ylim(mid - span / 2, mid + span / 2)

    # y-axis label on the left column only (shared meaning across the row).
    for i, ax in enumerate(axes.flat):
        if i % NCOLS == 0:
            ax.set_ylabel("g (mGal)")

    legend_elements = [
        Line2D([0], [0], marker="o", color="steelblue", linestyle="None",
               markersize=4, label="Readings +/- SE"),
        Line2D([0], [0], color="tab:green", linewidth=1.2,
               label="Decay fit (settling)"),
        Line2D([0], [0], color="tab:green", linewidth=0.9, linestyle="--",
               label="$g_\\infty$ (settling)"),
        mpatches.Patch(color="tab:green", alpha=0.25,
                       label="+/- SE($g_\\infty$) (settling)"),
        Line2D([0], [0], color="grey", linewidth=1.2, label="Flat fit (settled)"),
        Line2D([0], [0], color="grey", linewidth=0.9, linestyle="--",
               label="$g_\\infty$ (settled)"),
        Line2D([0], [0], color="darkorange", linewidth=0.9, linestyle=":",
               label="Weighted mean (settled)"),
        mpatches.Patch(color="darkorange", alpha=0.3,
                       label="+/- SE(mean) (settled)"),
    ]
    # rect bottom = space reserved for the legend; smaller -> plots extend lower,
    # closer to the legend (reduces the legend-to-plot gap).
    # h_pad: vertical gap between the two plot rows (SMALLER -> rows closer).
    # rect bottom: band reserved for the legend (SMALLER -> plots drop lower, closer
    # to the legend). Both tightened to keep the figure off its own page.
    plt.tight_layout(rect=[0, 0.13, 1, 1.0], w_pad=1.4, h_pad=0.6)
    # Pin the legend to the plot block's width (columns expand to fill it) so the
    # legend overhang no longer sets the figure width -- the axes do. 2 columns so
    # the long labels don't overlap (4 would collide at this width).
    left = min(ax.get_position().x0 for ax in axes.flat)
    right = max(ax.get_position().x1 for ax in axes.flat)
    fig.legend(handles=legend_elements, loc="lower center", ncol=2, frameon=True,
               mode="expand", bbox_to_anchor=(left, 0.01, right - left, 0.15))
    fig.savefig(OUT, dpi=150, bbox_inches="tight")            # titled browse PNG
    thesis_path, _ = save_figure(fig, OUT.stem, "Grav", vector=True)  # title-free PDF
    print(f"saved browse -> {OUT.relative_to(sd.BASE)}")
    print(f"saved thesis -> {thesis_path}")


if __name__ == "__main__":
    main()

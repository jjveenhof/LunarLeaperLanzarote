"""
Forest plot: gravimetric tube cross-sectional area for every inversion config
(line x shape x truncation) against the LiDAR ground truth.

Values are from invert_tube.py with the FINAL GPR geometry (2026-07-01):
L3 ceiling 3.5 / floor 14.3 m (v 0.125); L5 ceiling 10.5 m (v 0.11, circle-only).
Areas are 1-SE totals (data + picks + velocity + detrend in quadrature).
If the inversion is re-run, update RESULTS below.
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from pathlib import Path
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))   # Code/ for plot_utils
from plot_utils import save_figure

BASE = Path(__file__).resolve().parents[3]
FIG = BASE / "Results/Grav/Inversion"

# (line, shape, truncation, area m^2, 1-SE m^2)
RESULTS = [
    (3, "ellipse", "inf", 188, 23),
    (3, "circle",  "inf", 216, 30),
    (3, "ellipse", "15",  205, 27),
    (3, "circle",  "15",  260, 47),
    (3, "ellipse", "10",  221, 32),
    (3, "circle",  "10",  308, 57),
    (5, "circle",  "inf", 196, 36),
]
LIDAR = {3: 203, 5: 182}                        # ground-truth area per line (m^2)

TRUNC_COLOR = {"inf": "#00A0A0", "15": "#FF9500", "10": "#E03030"}
TRUNC_LABEL = {"inf": "infinite (2-D)", "15": "truncated 15 m", "10": "truncated 10 m"}
MARK = {"circle": "o", "ellipse": "s"}
TRUTH = "#9400D3"


def main():
    # Order (top -> bottom): Line 3 all circles then all ellipses, each by
    # increasing truncation (infinite, 15 m, 10 m); Line 5 last.
    shape_order = {"circle": 0, "ellipse": 1}
    trunc_order = {"inf": 0, "15": 1, "10": 2}
    lines = [3, 5]
    ys, rows, labels, spans = [], [], [], {}
    y = 0
    for li in lines:
        y0 = y
        entries = sorted((x for x in RESULTS if x[0] == li),
                         key=lambda r: (shape_order[r[1]], trunc_order[r[2]]))
        for r in entries:
            ys.append(y); rows.append(r)
            labels.append(f"L{li}  {r[1]}, {TRUNC_LABEL[r[2]]}")
            y += 1
        spans[li] = (y0, y - 1)
        y += 1                                   # gap between lines

    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    # LiDAR truth reference per line group
    for li, (a, b) in spans.items():
        ax.plot([LIDAR[li]] * 2, [a - 0.45, b + 0.45], color=TRUTH, lw=2.4,
                ls="--", zorder=2)
        ax.text(LIDAR[li], b + 0.55, f"LiDAR {LIDAR[li]} m$^2$", color=TRUTH,
                ha="center", va="bottom", fontsize=8, fontweight="bold")
    # estimates
    for yi, (li, shape, tr, area, se) in zip(ys, rows):
        ax.errorbar(area, yi, xerr=se, fmt=MARK[shape], color=TRUNC_COLOR[tr],
                    capsize=4, markersize=8, elinewidth=1.6, zorder=4,
                    markeredgecolor="0.2", markeredgewidth=0.5)

    ax.set_yticks(ys)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()                            # first row on top
    ax.set_xlabel("tube cross-sectional area (m$^2$)  =  volume per metre")
    ax.set_title("Gravimetric area vs LiDAR ground truth -- all configs",
                 fontweight="bold")
    ax.grid(True, axis="x", alpha=0.25, ls="--")
    ax.margins(y=0.08)

    # legends: truncation (colour) + shape (marker) + truth
    trunc_h = [mlines.Line2D([], [], marker="o", ls="none", color=TRUNC_COLOR[k],
                             markersize=8, label=TRUNC_LABEL[k])
               for k in ("inf", "15", "10")]
    shape_h = [mlines.Line2D([], [], marker=MARK[s], ls="none", color="0.4",
                             markersize=8, label=s) for s in ("circle", "ellipse")]
    truth_h = [mlines.Line2D([], [], color=TRUTH, lw=2.4, ls="--", label="LiDAR truth")]
    ax.legend(handles=trunc_h + shape_h + truth_h, fontsize=8, loc="lower right",
              ncol=1, framealpha=0.9)

    fig.tight_layout()
    out = FIG / "area_summary.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    save_figure(fig, out.stem, "Inversion", vector=True)   # title-free thesis PDF
    print(f"  saved -> {out.relative_to(BASE)}")


if __name__ == "__main__":
    main()

"""
Forest plot: gravimetric tube cross-sectional area for every inversion config
(line x shape x truncation) against the LiDAR ground truth.

Reads the inversion ARTIFACTS written by run_inversion.py -- it does not run the
inversion and carries no transcribed numbers. Areas are the artifact `area`; the error
bar is the MONTE CARLO SE (SD of the artifact's posterior ensemble areas), which is the
quantity reported in the thesis table `tab:inversion-results`.

Until 2026-08-11 this script held a hand-typed RESULTS table whose SEs predated the
2026-07-29 velocity_sigma 0.010 -> 0.015 change, so the figure showed error bars ~25%
tighter than the thesis. Reading the artifacts is what stops that recurring; do not
reintroduce literals here. Missing artifacts are SKIPPED with a printed note rather than
back-filled from memory -- regenerate them instead:

    python run_inversion.py --line 3 --truncate inf 10 15
    python run_inversion.py --line 5

Geometry lives in invert_tube.LINE_PRESETS (FINAL 2026-07-16, both lines migrated at
v 0.125): L3 ceiling 3.8 / floor 14.6 m; L5 ceiling 8.6 m (circle-only).
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
import invert_tube as it
import inversion_io as io

BASE = it.BASE                                   # paths via grav_utils (one definition)
FIG = it.FIG

# Which cases to show, in no particular order (the plot sorts them). Each is looked up
# as an artifact; any case without one is skipped, never substituted.
CASES = [
    (3, "ellipse", "inf"),
    (3, "circle",  "inf"),
    (3, "ellipse", "15"),
    (3, "circle",  "15"),
    (3, "ellipse", "10"),
    (3, "circle",  "10"),
    (5, "circle",  "inf"),
]
LIDAR = {3: 203, 5: 182}                        # ground-truth area per line (m^2)


def load_results():
    """Return [(line, shape, trunc, area, mc_se), ...] for every case with an artifact.

    The SE is the SD of the ensemble areas -- the same MC quantity the thesis quotes,
    NOT the analytic `area_se_tot` budget (they differ by a few m^2, and a reader who
    checks the figure against the table must find the same number)."""
    rows, missing = [], []
    for line, shape, tr in CASES:
        truncate = None if tr == "inf" else float(tr)
        try:
            d = io.load_artifact(line, shape, truncate)
        except FileNotFoundError:
            missing.append((line, shape, tr))
            continue
        # ensemble rows are (size, x0, ceiling, floor); area is derived, not stored.
        # Same recipe as sweep_density.nominal_se() -- keep the two in step.
        areas = np.array([it.area_of(shape, s, c, f) for (s, _x, c, f) in d["ensemble"]])
        mc_se = float(areas.std(ddof=1))
        rows.append((line, shape, tr, float(d["area"]), mc_se))

    for line, shape, tr in missing:
        print(f"  SKIPPED L{line} {shape} trunc={tr} -- no artifact "
              f"({io.artifact_path(line, shape, None if tr == 'inf' else float(tr)).name})")
    if not rows:
        raise SystemExit("No inversion artifacts found -- run run_inversion.py first.")
    return rows

TRUNC_COLOR = {"inf": "#00A0A0", "15": "#FF9500", "10": "#E03030"}
TRUNC_LABEL = {"inf": "infinite (2-D)", "15": "truncated 15 m", "10": "truncated 10 m"}
MARK = {"circle": "o", "ellipse": "s"}
TRUTH = "#9400D3"


def main():
    results = load_results()

    # Order (top -> bottom): Line 3 all circles then all ellipses, each by
    # increasing truncation (infinite, 15 m, 10 m); Line 5 last.
    shape_order = {"circle": 0, "ellipse": 1}
    trunc_order = {"inf": 0, "15": 1, "10": 2}
    lines = sorted({r[0] for r in results})
    ys, rows, labels, spans = [], [], [], {}
    y = 0
    for li in lines:
        y0 = y
        entries = sorted((x for x in results if x[0] == li),
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
    shown_tr = {r[2] for r in rows}
    shown_sh = {r[1] for r in rows}
    trunc_h = [mlines.Line2D([], [], marker="o", ls="none", color=TRUNC_COLOR[k],
                             markersize=8, label=TRUNC_LABEL[k])
               for k in ("inf", "15", "10") if k in shown_tr]
    shape_h = [mlines.Line2D([], [], marker=MARK[s], ls="none", color="0.4",
                             markersize=8, label=s)
               for s in ("circle", "ellipse") if s in shown_sh]
    truth_h = [mlines.Line2D([], [], color=TRUTH, lw=2.4, ls="--", label="LiDAR truth")]
    ax.legend(handles=trunc_h + shape_h + truth_h, fontsize=8, loc="lower right",
              ncol=1, framealpha=0.9)

    fig.tight_layout()
    # Echo the plotted numbers so they can be checked against tab:inversion-results
    # without opening the figure.
    print("  plotted (area +/- MC SE, m^2):")
    for li, shape, tr, area, se in rows:
        print(f"    L{li} {shape:<7s} trunc={tr:<3s}  {area:5.0f} +/- {se:4.1f}")

    out = FIG / "area_summary.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    save_figure(fig, out.stem, "Inversion", vector=True)   # title-free thesis PDF
    print(f"  saved -> {out.relative_to(BASE)}")


if __name__ == "__main__":
    main()

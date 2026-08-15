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

    python plot_area_summary.py                  # thesis figure, all configs
    python plot_area_summary.py --no-truncated   # untruncated (2-D) cases only

`--no-truncated` keeps only the infinite-extent cases and writes a SEPARATE
`area_summary_untruncated.{png,pdf}` into Results. It deliberately does not call
save_figure(), because that writes into the frozen thesis clone -- the default,
no-flag run remains the only thing that touches the submitted figure.
"""

import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from matplotlib.path import Path as _MPath
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


def load_results(cases=CASES):
    """Return [(line, shape, trunc, area, mc_se), ...] for every case with an artifact.

    The SE is the SD of the ensemble areas -- the same MC quantity the thesis quotes,
    NOT the analytic `area_se_tot` budget (they differ by a few m^2, and a reader who
    checks the figure against the table must find the same number)."""
    rows, missing = [], []
    for line, shape, tr in cases:
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

# --- knobs for the --no-truncated variant only (the thesis figure is frozen) ---------
# Blank slots inserted between the L3 and L5 groups. SMALLER = groups closer together.
GROUP_GAP = 0.45
# Vertical squash of the ellipse marker, so "ellipse" is drawn as an actual ellipse
# rather than a square. SMALLER = flatter marker; 1.0 would be a circle.
ELLIPSE_ASPECT = 0.6
_UNIT = _MPath.unit_circle()
ELLIPSE_MARKER = _MPath(_UNIT.vertices * [1.0, ELLIPSE_ASPECT], _UNIT.codes)
MARK_ELL = {"circle": "o", "ellipse": ELLIPSE_MARKER}


def main(untruncated=False):
    cases = [c for c in CASES if c[2] == "inf"] if untruncated else CASES
    results = load_results(cases)

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
            # with truncation filtered out, every row would carry the same suffix
            labels.append(f"L{li}  {r[1]}" if untruncated
                          else f"L{li}  {r[1]}, {TRUNC_LABEL[r[2]]}")
            y += 1
        spans[li] = (y0, y - 1)
        y += GROUP_GAP if untruncated else 1     # gap between lines

    AREA_LABEL = ("tube cross-sectional area (m$^2$)" if untruncated
                  else "tube cross-sectional area (m$^2$)  =  volume per metre")
    fig, ax = plt.subplots(figsize=(6.8, 5.5) if untruncated else (9.5, 5.5))

    if untruncated:
        # Vertical layout: category on x, area on y. Colour encodes the SURVEY LINE
        # (it.LINE_COLORS, the QGIS map palette used by every other gravity plot);
        # with truncation filtered out, colour is free to carry that instead.
        for li, (a, b) in spans.items():
            ax.plot([a - 0.45, b + 0.45], [LIDAR[li]] * 2, color=TRUTH, lw=2.4,
                    ls="--", zorder=2)
            # number only, set beside the right end of the line rather than on it,
            # sized to match the axis labels
            ax.text(b + 0.55, LIDAR[li], f"{LIDAR[li]} m$^2$", color=TRUTH,
                    ha="left", va="center", fontweight="bold",
                    fontsize=plt.rcParams["axes.labelsize"])
        for xi, (li, shape, tr, area, se) in zip(ys, rows):
            ax.errorbar(xi, area, yerr=se, ls="none", marker=MARK_ELL[shape],
                        color=it.LINE_COLORS[li],
                        capsize=4, markersize=9, elinewidth=1.6, zorder=4,
                        markeredgecolor="0.2", markeredgewidth=0.5)
        ax.set_xticks(ys)
        ax.set_xticklabels(labels)
        ax.set_ylabel(AREA_LABEL)
        ax.grid(True, axis="y", alpha=0.25, ls="--")
        ax.margins(x=0.12)
        # keep the right-hand truth labels inside the axes
        _x0, _x1 = ax.get_xlim()
        ax.set_xlim(_x0, _x1 + 0.45)
    else:
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
        ax.invert_yaxis()                        # first row on top
        ax.set_xlabel(AREA_LABEL)
        ax.grid(True, axis="x", alpha=0.25, ls="--")
        ax.margins(y=0.08)

    ax.set_title("Resolved cross-sectional area vs LiDAR ground truth"
                 if untruncated else
                 "Gravimetric area vs LiDAR ground truth -- all configs",
                 fontweight="bold")

    # legends: colour (truncation, or survey line) + shape (marker) + truth
    shown_tr = {r[2] for r in rows}
    shown_sh = {r[1] for r in rows}
    if untruncated:
        color_h = [mlines.Line2D([], [], marker="o", ls="none",
                                 color=it.LINE_COLORS[li], markersize=8,
                                 label=f"Line {li}") for li in lines]
    else:
        # colour only carries information when more than one truncation level is shown
        color_h = [] if len(shown_tr) < 2 else [
            mlines.Line2D([], [], marker="o", ls="none", color=TRUNC_COLOR[k],
                          markersize=8, label=TRUNC_LABEL[k])
            for k in ("inf", "15", "10") if k in shown_tr]
    marks = MARK_ELL if untruncated else MARK
    shape_h = [mlines.Line2D([], [], marker=marks[s], ls="none", color="0.4",
                             markersize=8, label=s)
               for s in ("circle", "ellipse") if s in shown_sh]
    truth_h = [mlines.Line2D([], [], color=TRUTH, lw=2.4, ls="--", label="LiDAR truth")]
    ax.legend(handles=color_h + shape_h + truth_h, fontsize=8,
              loc="upper right" if untruncated else "lower right",
              ncol=1, framealpha=0.9)

    fig.tight_layout()
    # Echo the plotted numbers so they can be checked against tab:inversion-results
    # without opening the figure.
    print("  plotted (area +/- MC SE, m^2):")
    for li, shape, tr, area, se in rows:
        print(f"    L{li} {shape:<7s} trunc={tr:<3s}  {area:5.0f} +/- {se:4.1f}")

    stem = "area_summary_untruncated" if untruncated else "area_summary"
    out = FIG / f"{stem}.png"
    # 300 dpi for the variant: PowerPoint cannot place a PDF, so the PNG is the
    # slide asset and gets scaled up on screen.
    fig.savefig(out, dpi=300 if untruncated else 150, bbox_inches="tight")
    if untruncated:
        # NOT a thesis figure -- the thesis clone is frozen, so no save_figure() call.
        # Vector copy lands beside the PNG for use in slides.
        fig.savefig(FIG / f"{stem}.pdf", bbox_inches="tight")
        print(f"  saved -> {(FIG / (stem + '.pdf')).relative_to(BASE)}")
    else:
        save_figure(fig, out.stem, "Inversion", vector=True)   # title-free thesis PDF
    print(f"  saved -> {out.relative_to(BASE)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Forest plot of inverted tube area against the LiDAR ground truth.")
    ap.add_argument("--no-truncated", action="store_true",
                    help="show only the untruncated (infinite 2-D) cases; writes a "
                         "separate area_summary_untruncated figure and leaves the "
                         "frozen thesis figure untouched")
    args = ap.parse_args()
    main(untruncated=args.no_truncated)

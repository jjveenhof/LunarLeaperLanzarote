"""
Standalone per-mode chi2 misfit surface (was Figure 1 of invert_tube.run_mode) --
one figure per (line, mode), thesis width. The compact three-panel version is
plot_misfit_row.py; this is the individual PNG kept for per-figure use.

Reads the precomputed artifact (run_inversion.py); it never runs the grid search.
Colour = Delta chi2 RESCALED by the reduced chi-square (max(1, chi2_nu)), and the
white contours are the 1 SE / 2 SE levels (rescaled Delta chi2 = 1, 4), whose
projection onto each axis IS the reported +/-1 SE / +/-2 SE for that parameter --
the SAME convention as plot_misfit_row.py, so the two figures are consistent.

Run:  python run_inversion.py                 # once, to (re)build the artifacts
      python plot_misfit.py --line 3 [--modes circle ellipse] [--truncate 10]
"""

import argparse
import numpy as np
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))   # Code/ for plot_utils
from plot_utils import save_figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import invert_tube as it
import inversion_io as io


def draw(line, mode, truncate):
    a = io.load_artifact(line, mode, truncate)
    sizes, x0s, chi2 = a["sizes"], a["x0s"], a["chi2"]
    size_lbl = "radius r (m)" if mode == "circle" else "half-width a (m)"
    tag = "" if truncate is None else f"_trunc{int(truncate)}"
    ttl = "" if truncate is None else f"  [tube truncated at {truncate:.0f} m]"
    lev = max(1.0, a["chi2red"])                        # rescale so reduced chi2 = 1
    dchi = (chi2 - chi2.min()) / lev                     # rescaled -> shared scale

    fig, ax = plt.subplots(figsize=(6.1, 4.6))          # thesis \linewidth
    im = ax.pcolormesh(x0s, sizes, dchi, cmap="viridis_r", vmax=30, shading="auto")
    # 1 SE / 2 SE contours: rescaled Delta chi2 = 1, 4. Their projection onto each
    # axis IS the reported +/-1 SE / +/-2 SE for that parameter (single-parameter
    # Delta chi2), matching plot_misfit_row.py.
    ax.contour(x0s, sizes, dchi, levels=[1.0, 4.0], colors="w", linewidths=1.0)
    ax.plot(a["x0"], a["size"], "r*", markersize=14)
    ax.set_xlabel(r"tube centre $x_0$ (m)")
    ax.set_ylabel(size_lbl)
    ax.set_title(rf"Line {line} {mode}: $\chi^2-\chi^2_{{min}}$ surface "
                 rf"(white = 1 SE, 2 SE){ttl}", fontweight="bold")
    fig.colorbar(im, ax=ax, label=r"$\Delta\chi^2/\chi^2_\nu$")
    fig.tight_layout()
    out = it.FIG / f"invert_line{line}_{mode}{tag}.png"
    fig.savefig(out, dpi=140)
    if not tag:   # untruncated run == the thesis figure
        save_figure(fig, f"invert_line{line}_{mode}", "Inversion", vector=True)
    plt.close(fig)
    print(f"  saved -> {out.relative_to(it.BASE)}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--line", type=int, default=3, choices=sorted(it.LINE_PRESETS))
    p.add_argument("--modes", nargs="+", choices=["circle", "ellipse"], default=None)
    p.add_argument("--truncate", default="inf", help="pit distance (m) or 'inf'")
    args = p.parse_args()
    truncate = None if args.truncate.lower() in ("inf", "none") else float(args.truncate)
    modes = tuple(args.modes) if args.modes else it.LINE_PRESETS[args.line]["modes"]
    for mode in modes:
        draw(args.line, mode, truncate)


if __name__ == "__main__":
    main()

"""
The three chi2 misfit surfaces (L3 circle, L5 circle, L3 ellipse) at thesis width --
a compact alternative to the per-mode surfaces from invert_tube.py (which stay as the
individual PNGs). The two CIRCLE panels share a y-axis (both are tube radius r on the
same grid); the ellipse (half-width a) sits on its own row below, so no panel is
squished and the y-labels never collide.

Each panel is one line+shape's dense grid search over (size, x0), with a DC offset
fitted analytically at every node. Colour = Delta chi2 RESCALED by the reduced
chi-square (max(1, chi2_nu)), so the panels -- which have different chi2_nu -- share
ONE colour scale and one colorbar; the white contours are then the fixed joint
68% / 95% levels (Delta chi2 = 2.30, 6.17) for two parameters.

Run:  python plot_misfit_row.py
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))   # Code/ for plot_utils
from plot_utils import save_figure

import invert_tube as it

FIG_W_IN, FIG_H_IN = 6.1, 4.4      # thesis \linewidth; two rows of panels
SIZE_YLIM = (1.0, 20.0)            # common size-axis range (m); one scale for radius r
                                   # and half-width a (crops the ellipse's empty top)
# Inter-panel spacing -- TUNE THESE to taste. LOWER = rows/cols closer. Beyond a point
# the row gap is set by L5's x-axis label + the panel titles, not by these values.
MISFIT_HPAD = 0.0                  # inches of padding around the axes (rows + edges)
MISFIT_HSPACE = 0.0                # extra height fraction between the two rows


def configure(line):
    """Point invert_tube's module globals at this line's preset (no truncation)."""
    pre = it.LINE_PRESETS[line]
    it.LINE = line
    it.CEILING0 = pre["ceiling"]
    it.FLOOR0 = pre["floor"] or 16.0
    it.TRUNCATE_D = None
    return pre


def draw_panel(ax, line, mode, letter, show_ylabel=True, show_xlabel=True):
    """Draw one rescaled chi2 surface on ax; return its pcolormesh handle."""
    configure(line)
    sx, d, se = it.load_line(line)
    sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
    xmin = sx[np.argmin(d)]
    x0s = np.arange(xmin - 20, xmin + 20, 0.5)
    res = it.invert(mode, sx, d, se, it.CEILING0, it.FLOOR0, sizes, x0s)
    lev = max(1.0, res["chi2red"])                     # rescale so reduced chi2 = 1
    dchi = (res["chi2"] - res["chi2"].min()) / lev      # rescaled -> shared colour scale
    im = ax.pcolormesh(x0s, sizes, dchi, cmap="viridis_r", vmax=30, shading="auto")
    # 1 SE / 2 SE contours: rescaled Delta chi2 = 1, 4. Their projection onto each
    # axis IS the reported +/-1 SE / +/-2 SE for that parameter (single-parameter
    # Delta chi2, consistent with the SE read off the profiled curve in invert_tube).
    ax.contour(x0s, sizes, dchi, levels=[1.0, 4.0], colors="w", linewidths=0.8)
    ax.plot(res["x0"], res["size"], "r*", ms=9)
    if show_xlabel:
        ax.set_xlabel(r"$x_0$ (m)")
    if show_ylabel:
        ax.set_ylabel("radius r (m)" if mode == "circle" else "half-width a (m)")
    ax.set_title(f"({letter}) L{line} {mode}",   # chi2_nu lives in the results table
                 fontsize=9, fontweight="bold")
    return im


def main():
    # 2x2: two circles on the top row (shared radius y-axis), ellipse bottom-left,
    # colorbar in the free bottom-right cell. constrained_layout stops label clipping.
    fig = plt.figure(figsize=(FIG_W_IN, FIG_H_IN), constrained_layout=True)
    # Tighten the inter-row gap: the L3 column shares its x-axis (no label between the
    # rows), so only L5's x-label needs clearance -- drop the extra vertical padding.
    fig.set_constrained_layout_pads(w_pad=0.03, h_pad=MISFIT_HPAD,
                                    wspace=0.04, hspace=MISFIT_HSPACE)
    gs = fig.add_gridspec(2, 2)
    ax_c3 = fig.add_subplot(gs[0, 0])
    ax_c5 = fig.add_subplot(gs[0, 1], sharey=ax_c3)    # same quantity (radius r)
    ax_e = fig.add_subplot(gs[1, 0], sharex=ax_c3)     # both L3 -> same x0 grid

    im = draw_panel(ax_c3, 3, "circle", "a", show_xlabel=False)
    ax_c3.tick_params(labelbottom=False)               # x shared with L3 ellipse below
    draw_panel(ax_c5, 5, "circle", "b", show_ylabel=False)
    ax_c5.tick_params(labelleft=False)                 # y shared -> ticks on the left only
    draw_panel(ax_e, 3, "ellipse", "c")

    # Same y (size) scale on all three so radius r and half-width a compare directly.
    ax_c3.set_ylim(*SIZE_YLIM)                          # ax_c5 follows (shared y)
    ax_e.set_ylim(*SIZE_YLIM)

    cbax = fig.add_subplot(gs[1, 1])                   # free corner -> colorbar
    cbax.axis("off")
    # A tall colorbar placed inside the empty cell (inset), so it fills the corner's
    # vertical space (~ell panel height) instead of a thin bar with slack around it.
    cax = cbax.inset_axes([0.20, 0.05, 0.05, 0.90])    # [x, y, w, h] in cell fractions
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(r"$\Delta\chi^2/\chi^2_\nu$", fontsize=8)
    cb.ax.tick_params(labelsize=8)

    out = it.FIG / "misfit_row.png"
    fig.savefig(out, dpi=150)
    save_figure(fig, "misfit_row", "Inversion", vector=True)
    print(f"saved -> {out.relative_to(it.BASE)}")


if __name__ == "__main__":
    main()

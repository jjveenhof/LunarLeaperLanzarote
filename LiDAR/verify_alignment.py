"""
verify_alignment.py -- before/after checks for the La Corona junction alignment.

Two input modes:
  * ASC (default): the three re-aligned CloudCompare ASCII exports
    (PF_ref_after / PF_stitch_after / PF_tube_after), already in the aligned frame.
        python verify_alignment.py
  * LAS (baseline): a single LAS holding all subsets with an Original_cloud_index
    scalar field, read via las_tools (laspy cannot parse these clouds' points).
        python verify_alignment.py --las path/to/cloud.las

Outputs, for whichever subsets are present:
  * nearest-neighbour residuals between the moving subset and its reference, reported
    by distance threshold (isolates the genuine overlap when one cloud extends past
    the other) and low percentiles;
  * a 2x2 figure: TOP (XY) plan, projected SIDE (E-Z), and two THIN-SLICE
    cross-sections (E-Z at a fixed Northing, N-Z at a fixed Easting) that reveal tilt.

CRS: EPSG:4083 (REGCAN95 / UTM zone 28N).
Baseline (pre-alignment) idx2->idx0 residual was ~ mean 8.7 m / median 5.6 m.

Split 2026-08-11 (phase-2 refactor): data loading + residual() moved to
verify_alignment_io.py, so the plotting/CLI here can be read without the loader
internals. See that module for the ASC/LAS/GENTE cloud-set definitions.
"""
import os
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure

from verify_alignment_io import (
    ASC_DIR, GENTE_FILES, GENTE_BBOX, GENTE_CMAP_LABELS,
    load_asc, load_asc_rtk, load_asc_before, load_las, load_gente, residual,
)

# --- cross-section cut locations (EPSG:4083) ---------------------------------
SLICE_N = 3227164.0   # E-Z section: keep points within +-SLICE_HALF of this Northing
SLICE_E = 650636.0    # N-Z section: keep points within +-SLICE_HALF of this Easting
# (chosen relative to the cave, then carried through the -9.17 E / +1.27 N RTK pin
#  and rounded to whole m, so the slabs stay put over the georef-corrected cloud)
SLICE_HALF = 1.5      # slab half-thickness (m)

GENTE_SLICE_N = 3227540.0   # cuts cross at the jameo centre where jameo + tunnel
GENTE_SLICE_E = 649690.0    # (+ drone) all coincide -- the skylight/pit
GENTE_SLICE_HALF = 2.5


def _compass(ax, left, right):
    """Label the two ends of a cross-section's horizontal axis with compass directions."""
    kw = dict(transform=ax.transAxes, fontsize=8, fontweight="bold",
              va="top", color="0.3")
    ax.text(0.01, 0.97, left, ha="left", **kw)
    ax.text(0.99, 0.97, right, ha="right", **kw)


def _scatter(ax, label, P, col, cols, sparse, base_s, base_a, cmap_labels=frozenset()):
    """One layer onto one panel; sparse (RTK) layers get bold markers, cmap layers
    (drone) are coloured by elevation, other dense clouds a subsampled flat scatter."""
    x, y = P[:, cols[0]], P[:, cols[1]]
    if label in sparse:
        return ax.scatter(x, y, s=6, c=col, marker="x", linewidths=0.6,
                          zorder=6, label=label)
    s = max(1, len(P) // 40000)
    if label in cmap_labels:
        return ax.scatter(x[::s], y[::s], s=base_s, c=P[::s, 2], cmap="viridis",
                          alpha=base_a, linewidths=0)
    return ax.scatter(x[::s], y[::s], s=base_s, c=col, alpha=base_a,
                      linewidths=0, label=f"{label} n={len(P)}")


def _legend_handles(layers, sparse):
    """Fixed-size legend proxies (else markerscale blows up the sparse 'x' markers)."""
    from matplotlib.lines import Line2D
    return [Line2D([0], [0], color=col, ls="none",
                   marker=("x" if l in sparse else "o"),
                   ms=5, mew=(1.5 if l in sparse else 0),
                   label=(l if l in sparse else f"{l} n={len(P)}"))
            for l, P, col in layers]


def _plan_panel(ax, layers, sparse, cmap_labels, title, xlim, ylim,
                cuts=None, legend=False, panel_label=None):
    """TOP (XY) plan of the layers, fixed limits so BEFORE/AFTER frame identically."""
    for label, P, col in layers:
        _scatter(ax, label, P, col, (0, 1), sparse, 0.2, 0.5, cmap_labels)
    if cuts is not None:
        sn, se, _ = cuts                # se=None -> only the W-E cut is drawn
        if sn is not None:
            ax.axhline(sn, color="k", lw=1, ls="--")
        if se is not None:
            ax.axvline(se, color="k", lw=1, ls="--")
    ax.set_xlim(xlim); ax.set_ylim(ylim); ax.set_aspect("equal")
    if legend:
        ax.legend(handles=_legend_handles(layers, sparse), loc="best")
    ax.set_title(title); ax.set_xlabel("E"); ax.set_ylabel("N")
    if panel_label:
        ax.text(-0.13, 1.06, panel_label, transform=ax.transAxes,
                fontweight="bold", fontsize=10, va="bottom", ha="left")


def _slab_title(kind, coord, val, half):
    """Cross-section slab title. The thesis font (cmr10 via plot_utils) mangles literal
    '|' and '<', so express the slab via mathtext ($\\pm$) and plain wording instead."""
    return f"{kind} section, {coord}={val:.0f} m  ($\\pm${half:.1f} m slab)"


def _slice_window(layer_sets, fcol, fval, half, pcol, exclude):
    """Narrow x-window (of column pcol) spanning the non-excluded clouds' points that
    fall in the slice |coord[fcol]-fval|<half, pooled over layer_sets (before+after).
    Used to frame a cross-section tight to the cave, not the full plan width."""
    lo, hi = np.inf, -np.inf
    for layers in layer_sets:
        for label, P, _ in layers:
            if label in exclude:
                continue
            m = np.abs(P[:, fcol] - fval) < half
            if m.any():
                lo = min(lo, P[m, pcol].min()); hi = max(hi, P[m, pcol].max())
    if not np.isfinite(lo):
        return None
    pad = 0.08 * (hi - lo) + 2.0
    return (lo - pad, hi + pad)


def _section_panel(ax, layers, sparse, cmap_labels, fcol, fval, half, pcols,
                   title, compass):
    """Thin-slab cross-section: keep pts with |coord[fcol]-fval|<half, plot pcols."""
    for label, P, col in layers:
        m = np.abs(P[:, fcol] - fval) < half
        if m.any():
            _scatter(ax, label, P[m], col, pcols, sparse, 0.4, 0.7, cmap_labels)
    ax.set_aspect("equal"); ax.set_title(title)
    # labelpad drops the axis word below the auto offset multiplier (else they collide
    # on the narrow PF section panels)
    ax.set_xlabel("E" if pcols[0] == 0 else "N", labelpad=10)
    ax.set_ylabel("Z")
    # force the abbreviated "+6.49e5" offset label (matplotlib's auto threshold misses
    # the ~100 m windows and prints full 6-digit coords, overcrowding the axis)
    fmt = mticker.ScalarFormatter(); fmt.set_useOffset(True); fmt._offset_threshold = 2
    ax.xaxis.set_major_formatter(fmt)


def plot(layers, out_png, slice_n=SLICE_N, slice_e=SLICE_E, slice_half=SLICE_HALF,
         sparse=frozenset(), cmap_labels=frozenset(), suptitle=None,
         before_layers=None, plan_extent=None, wide_labels=frozenset(),
         section_style="row"):
    # authored at ~page width (linewidth 6.1 in) per the supervisor's figure-sizing
    # rule, so \includegraphics does not shrink the text; fonts are true page pt.
    style = {"font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
             "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7}
    with plt.rc_context(style):
        if before_layers is not None:
            xlim, ylim = plan_extent
            cuts = (slice_n, slice_e, slice_half)
            if section_style == "stacked":
                # Gente: plan row, then FULL-WIDTH W-E and S-N section rows stacked, so
                # the RTK datum shows in-section. Tight vertical spacing.
                fig, axs = plt.subplots(3, 2, figsize=(6.1, 4.8),
                                        gridspec_kw={"height_ratios": [2.6, 0.45, 0.45]})
                _plan_panel(axs[0, 0], before_layers, sparse, cmap_labels,
                            "", xlim, ylim, cuts=cuts, panel_label="a)")
                _plan_panel(axs[0, 1], layers, sparse, cmap_labels, "",
                            xlim, ylim, cuts=cuts, legend=True, panel_label="b)")
                _section_panel(axs[1, 0], before_layers, sparse, cmap_labels, 1,
                               slice_n, slice_half, (0, 2), "W-E", ("W", "E"))
                _section_panel(axs[1, 1], layers, sparse, cmap_labels, 1, slice_n,
                               slice_half, (0, 2), "W-E", ("W", "E"))
                _section_panel(axs[2, 0], before_layers, sparse, cmap_labels, 0,
                               slice_e, slice_half, (1, 2), "N-S", ("N", "S"))
                _section_panel(axs[2, 1], layers, sparse, cmap_labels, 0, slice_e,
                               slice_half, (1, 2), "N-S", ("N", "S"))
                # anchor W-E content to the BOTTOM of its cell and N-S to the TOP, so the
                # two sections sit close together while the map<->W-E gap opens up.
                for row, xwin in ((1, xlim), (2, ylim)):   # full-width sections
                    zlo = min(axs[row, 0].get_ylim()[0], axs[row, 1].get_ylim()[0])
                    zhi = max(axs[row, 0].get_ylim()[1], axs[row, 1].get_ylim()[1])
                    for a in (axs[row, 0], axs[row, 1]):
                        a.set_xlim(xwin); a.set_ylim(zlo, zhi)
                        a.set_anchor("S" if row == 1 else "N")
                axs[0, 0].set_anchor("N"); axs[0, 1].set_anchor("N")   # lift maps up
                axs[2, 0].invert_xaxis(); axs[2, 1].invert_xaxis()   # N-S: N on the left
                for left, right in ((axs[1, 0], axs[1, 1]), (axs[2, 0], axs[2, 1])):
                    right.sharey(left)   # before/after share Z
                    right.tick_params(labelleft=False); right.set_ylabel("")
            else:
                # PF: plans span 2 cols; the four sections in one row, framed tight to
                # the cave (not the full plan width).
                fig = plt.figure(figsize=(6.1, 4.0))
                gs = fig.add_gridspec(2, 4, height_ratios=[1.4, 1])
                axpb = fig.add_subplot(gs[0, 0:2])
                axpa = fig.add_subplot(gs[0, 2:4])
                _plan_panel(axpb, before_layers, sparse, cmap_labels, "",
                            xlim, ylim, cuts=cuts, panel_label="a)")
                _plan_panel(axpa, layers, sparse, cmap_labels, "",
                            xlim, ylim, cuts=cuts, legend=True, panel_label="b)")
                axpb.set_anchor("S"); axpa.set_anchor("S")   # sink plans toward sections
                axbWE, axbSN = fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])
                axaWE, axaSN = fig.add_subplot(gs[1, 2]), fig.add_subplot(gs[1, 3])
                _section_panel(axbWE, before_layers, sparse, cmap_labels, 1, slice_n,
                               slice_half, (0, 2), "W-E", ("W", "E"))
                _section_panel(axaWE, layers, sparse, cmap_labels, 1, slice_n,
                               slice_half, (0, 2), "W-E", ("W", "E"))
                _section_panel(axbSN, before_layers, sparse, cmap_labels, 0, slice_e,
                               slice_half, (1, 2), "N-S", ("N", "S"))
                _section_panel(axaSN, layers, sparse, cmap_labels, 0, slice_e,
                               slice_half, (1, 2), "N-S", ("N", "S"))
                excl = sparse | wide_labels
                wewin = _slice_window([before_layers, layers], 1, slice_n, slice_half,
                                      0, excl) or xlim
                snwin = _slice_window([before_layers, layers], 0, slice_e, slice_half,
                                      1, excl) or ylim
                for a in (axbWE, axaWE):
                    a.set_xlim(wewin)
                for a in (axbSN, axaSN):
                    a.set_xlim(snwin); a.invert_xaxis()   # N-S: N on the left
                secax = (axbWE, axaWE, axbSN, axaSN)
                zlo = min(a.get_ylim()[0] for a in secax)
                zhi = max(a.get_ylim()[1] for a in secax)
                for a in secax:
                    a.set_ylim(zlo, zhi); a.set_anchor("N")
                for a in (axaWE, axbSN, axaSN):      # all sections share one Z axis
                    a.sharey(axbWE)
                for a in (axbSN, axaSN):             # Z ticks only at each pair's start
                    a.tick_params(labelleft=False); a.set_ylabel("")
            if suptitle:
                fig.suptitle(suptitle, fontsize=10, fontweight="bold")
            fig.tight_layout(h_pad=0.25)
            if section_style == "row":       # PF: each W-E/N-S pair spans its map width
                gap = 0.035                   # small gap between the two sections
                for plan, we, ns in ((axpb, axbWE, axbSN), (axpa, axaWE, axaSN)):
                    pp = plan.get_position()
                    band = we.get_subplotspec().get_position(fig)   # section row y-band
                    w = (pp.width - gap) / 2.0
                    we.set_position([pp.x0, band.y0, w, band.height])
                    ns.set_position([pp.x0 + w + gap, band.y0, w, band.height])
                    we.set_anchor("N"); ns.set_anchor("N")
        else:
            fig, axs = plt.subplots(2, 2, figsize=(16, 13))
            if suptitle:
                fig.suptitle(suptitle, fontsize=15, fontweight="bold")
            for label, P, col in layers:               # (0,0) TOP XY
                _scatter(axs[0, 0], label, P, col, (0, 1), sparse, 2, 0.5, cmap_labels)
            xlim, ylim = axs[0, 0].get_xlim(), axs[0, 0].get_ylim()
            _plan_panel(axs[0, 0], [], sparse, cmap_labels, "TOP (XY)", xlim, ylim,
                        cuts=(slice_n, slice_e, slice_half), legend=False)
            axs[0, 0].legend(handles=_legend_handles(layers, sparse), loc="best")
            for label, P, col in layers:               # (0,1) SIDE E-Z projected
                _scatter(axs[0, 1], label, P, col, (0, 2), sparse, 2, 0.4, cmap_labels)
            axs[0, 1].set_aspect("equal")
            axs[0, 1].set_title("SIDE projected (E-Z, all pts)")
            axs[0, 1].set_xlabel("E"); axs[0, 1].set_ylabel("Z")
            _section_panel(axs[1, 0], layers, sparse, cmap_labels, 1, slice_n,
                           slice_half, (0, 2), _slab_title("E-Z", "N", slice_n,
                           slice_half), ("W", "E"))
            _section_panel(axs[1, 1], layers, sparse, cmap_labels, 0, slice_e,
                           slice_half, (1, 2), _slab_title("N-Z", "E", slice_e,
                           slice_half), ("S", "N"))
            fig.tight_layout()

        fig.savefig(out_png, dpi=450, bbox_inches="tight")
        save_figure(fig, os.path.splitext(os.path.basename(out_png))[0],
                    "Appendices/Lidar reregistering", vector=False, dpi=450)  # thesis PNG
        print("saved", os.path.abspath(out_png))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--las", metavar="CLOUD.las",
                    help="baseline mode: single LAS with Original_cloud_index")
    ap.add_argument("--gente", action="store_true",
                    help="Jameo de la Gente re-georef check (corrected clouds + RTK)")
    ap.add_argument("--step", type=int, default=1, help="LAS subsample step")
    ap.add_argument("-o", "--out", help="output PNG path")
    args = ap.parse_args()

    sparse = frozenset()
    sn, se, sh = SLICE_N, SLICE_E, SLICE_HALF
    suptitle = None
    before_layers = None
    plan_extent = None
    if args.gente:
        layers, before_layers, pairs, sparse = load_gente()
        sn, se, sh = GENTE_SLICE_N, GENTE_SLICE_E, GENTE_SLICE_HALF
        plan_extent = ((GENTE_BBOX[0], GENTE_BBOX[1]), (GENTE_BBOX[2], GENTE_BBOX[3]))
        suptitle = ("Jameo de la Gente coregistration check")
        out = args.out or os.path.join(GENTE_FILES[0][1].rsplit("\\", 2)[0],
                                       "Reregistered clouds", "gente_check.png")
    elif args.las:
        layers, pairs = load_las(args.las, step=args.step)
        out = args.out or os.path.splitext(args.las)[0] + "_check.png"
    else:
        layers, pairs = load_asc()
        before_layers = load_asc_before()   # None if the misaligned crop is absent
        if before_layers is not None:
            rtk = load_asc_rtk()            # RTK rim + plumb datum on both plots
            layers = layers + rtk
            before_layers = before_layers + rtk
            sparse = frozenset(lbl for lbl, _, _ in rtk)
            allp = np.vstack([P[:, :2] for _, P, _ in layers + before_layers])
            m = 15.0
            plan_extent = ((allp[:, 0].min() - m, allp[:, 0].max() + m),
                           (allp[:, 1].min() - m, allp[:, 1].max() + m))
            suptitle = "Puerta Falsa junction re-registration"
        out = args.out or os.path.join(ASC_DIR, "alignment_check.png")

    by = {label: P for label, P, _ in layers}
    for label, P, _ in layers:
        print(f"{label}: n={len(P)}  E[{P[:,0].min():.1f},{P[:,0].max():.1f}] "
              f"N[{P[:,1].min():.1f},{P[:,1].max():.1f}] Z[{P[:,2].min():.1f},{P[:,2].max():.1f}]")
    print()
    for mover, ref in pairs:
        if mover in by and ref in by:
            residual(by[mover], by[ref], f"{mover}->{ref}")

    cmap_labels = GENTE_CMAP_LABELS if args.gente else frozenset()
    wide_labels = {"Topo drone"} if args.gente else frozenset()   # wide context: don't
    section_style = "stacked" if args.gente else "row"            # let it size sections
    plot(layers, out, slice_n=sn, slice_e=se, slice_half=sh, sparse=sparse,
         cmap_labels=cmap_labels, suptitle=suptitle, before_layers=before_layers,
         plan_extent=plan_extent, wide_labels=wide_labels, section_style=section_style)


if __name__ == "__main__":
    main()

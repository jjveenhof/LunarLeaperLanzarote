"""
Free-depth grid search -- how well does GRAVITY ALONE constrain the tube?

The main inversion FIXES the ceiling (and, for the ellipse, the floor) from the GPR
picks and fits only (size, x0). That prior is what makes the problem well posed, but it
invites the obvious question: how much of the answer is the gravity data, and how much
is the pick? This script drops the depth prior and searches (ceiling, R, x0) with the DC
baseline floated, so the classic gravity depth-size trade-off is exposed rather than
assumed away.

Method: `chi2_surface` already takes `ceiling` as an argument, so the existing, validated
2-D (size, x0) search is simply run at every ceiling on a grid and stacked into a cube.
Nothing in the engine changes. dof = n - 4 (ceiling, size, x0, DC offset).

Reading the result:
  * Profiling x0 out (min over x0) leaves chi2(ceiling, size), which maps 1-1 to
    chi2(ceiling, area) since area = pi*R^2 at fixed ceiling -- so the map is plotted
    directly in the (ceiling depth, area) plane, the two quantities that matter.
  * The valley is expected to be BROAD but NOT flat: for a 2-D cylinder the anomaly
    WIDTH carries the depth and the amplitude carries R^2/z, so gravity has weak --
    not zero -- depth resolution. Do not oversell this as "unconstrained".
  * Marginal intervals come from profiling to one axis and cutting at Delta chi2 <=
    kappa^2, kappa^2 = max(1, chi2_nu) -- the SAME chi2-rescaled rule the main
    inversion uses for its data channel, so the numbers are comparable.

The deliverable is the TIGHTENING: "gravity alone constrains the ceiling to +/-X m and
the area to +/-Y m^2; adding the GPR pick reduces these to +/-x and +/-y." That turns the
subjective pick from an unexamined assumption into a quantified contribution.

Writes Results/Grav/Inversion/freedepth_line{N}.npz (compute) and freedepth.png (plot).
Compute is detached from plotting, as elsewhere: --no-compute replots from the npz.

Run:  python freedepth.py                  # both lines, compute + plot
      python freedepth.py --no-compute     # replot from stored cubes
"""

import argparse
import numpy as np
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))   # Code/ for plot_utils
from plot_utils import save_figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import invert_tube as it
import run_inversion as drv
import grav_utils as _gu               # for the LiDAR schema check

LINES = (3, 5)
CEIL_GRID = np.arange(1.0, 40.01, 0.25)      # free ceiling depth (m below surface)
# L5's valley is open at the deep end, so the old 25 m cap cut the posterior off at the
# grid edge rather than where the data stop supporting it. Extended to 40 m (2026-08-01)
# so the drawn model ensemble is not truncated by my own grid. Display range is separate:
# Misfit-plate x-range, PER LINE (display only; the cube runs to 40 m on both). L5 is
# widened to show the open tail; L3 keeps its original range so that figure is unchanged.
# The two panels are given widths proportional to their spans (see plate()), so metres
# per inch is IDENTICAL in both -- a wider window, not a stretched one.
CEIL_XLIM = {3: (1.0, 25.0), 5: (1.0, 40.0)}
C_GPR, C_BEST, C_LIDAR = "#0072B2", "#C1272D", "#9400D3"


def cfg_for(line):
    return it.cfg_for(line, slope_se=drv.slope_se_of(line))


def compute(line):
    """chi2 cube over (ceiling, R, x0) for the circle model, profiled to (ceiling, R).

    The FULL cube is stored alongside the profiled surface. The misfit plate only needs
    `prof`, but drawing actual models (plot_freedepth_terrain.py) needs x0 as well, and
    x0 is exactly what profiling throws away. The cube is ~12 MB per line, which is
    nothing next to re-running an 84 s search whenever a model has to be drawn.
    """
    cfg = cfg_for(line)
    sx, d, se = it.load_line(line)
    sizes = it.RADIUS_GRID
    x0s = it.x0_grid(sx, d)
    cube = np.empty((len(CEIL_GRID), len(sizes), len(x0s)))
    for i, c in enumerate(CEIL_GRID):
        cube[i] = it.chi2_surface("circle", sx, d, se, c, 16.0, sizes, x0s, cfg)
    prof = cube.min(axis=2)                             # marginalise x0 by profiling
    dof = len(d) - 4                                    # ceiling, size, x0, DC
    out = it.FIG / f"freedepth_line{line}.npz"
    np.savez(out, ceilings=CEIL_GRID, sizes=sizes, prof=prof, dof=dof,
             areas=np.pi * sizes ** 2, cube=cube, x0s=x0s)
    print(f"  saved -> {out.relative_to(it.BASE)}")
    return out


def interval(axis_vals, chi2_1d, kappa2):
    """Delta chi2 <= kappa^2 interval on a profiled 1-D curve (None if it runs off)."""
    m = (chi2_1d - chi2_1d.min()) <= kappa2
    lo, hi = axis_vals[m].min(), axis_vals[m].max()
    return (None if np.isclose(lo, axis_vals[0]) else lo,
            None if np.isclose(hi, axis_vals[-1]) else hi)


def analyse(line):
    z = np.load(it.FIG / f"freedepth_line{line}.npz")
    ceil, sizes, prof, dof = z["ceilings"], z["sizes"], z["prof"], int(z["dof"])
    areas = z["areas"]
    chi2min = prof.min()
    kappa2 = max(1.0, chi2min / dof)                    # same rescaling as the main fit
    i, j = np.unravel_index(np.argmin(prof), prof.shape)
    # marginals: profile to each axis
    ceil_lo, ceil_hi = interval(ceil, prof.min(axis=1), kappa2)
    area_lo, area_hi = interval(areas, prof.min(axis=0), kappa2)
    # GRID-LIMIT GUARD. Past some depth the best-fitting radius runs into the top of
    # RADIUS_GRID; beyond that the profiled chi2 is an artefact of the grid ending, not
    # of the data disagreeing, and it fakes an upper bound on the ceiling. (L5: the
    # radius caps at 19.9 m from ceiling ~39 m, which is exactly where the "1 sigma
    # upper bound" appeared.) Find the shallowest capped ceiling and refuse to report
    # any bound at or beyond it.
    capped = np.argmin(prof, axis=1) == len(sizes) - 1
    ceil_cap = float(ceil[capped][0]) if capped.any() else None
    if ceil_cap is not None and ceil_hi is not None and ceil_hi >= ceil_cap:
        ceil_hi = None                                  # not a real bound
    return dict(ceil=ceil, areas=areas, sizes=sizes, prof=prof, dof=dof, kappa2=kappa2,
                chi2min=chi2min, best_ceil=ceil[i], best_area=areas[j],
                best_size=sizes[j], ceil_cap=ceil_cap,
                ceil_lo=ceil_lo, ceil_hi=ceil_hi, area_lo=area_lo, area_hi=area_hi)


def lidar_ceiling(line):
    """Depth of the LiDAR cave ceiling below the surface, if the CSV is present."""
    f = it.lidar_file(line)
    if not f.exists():
        return None
    import terrain_common as tc      # library, not the plotting script (was a lazy
    xs, zs, _, proj = tc.gravity_profile(line)   # import of plot_model_terrain)
    _gu.check_lidar_schema(f)      # cross-folder contract: fail loudly, not silently
    L = np.genfromtxt(f, delimiter=",", names=True)
    lx, lz = proj(L["easting"], L["northing"]), L["z"]
    return float(np.interp(lx[np.argmax(lz)], xs, zs) - lz.max())


SIZE_YLIM = (1.0, 20.0)       # radius axis -- SAME range as plot_misfit_row, so the
                              # free-depth maps compare directly with the fixed-depth ones
# Panel box + colorbar geometry (figure fractions). CB_X moves the bar RIGHT; its
# bottom/height are tied to the panel box below, so the bar always matches the y-axis.
BOX_L, BOX_R, BOX_B, BOX_T = 0.10, 0.84, 0.30, 0.90
CB_X, CB_W = 0.885, 0.025


def plate(res, out):
    """(ceiling, radius) misfit maps, one panel per line, with the priors marked."""
    # Panel widths proportional to the plotted ceiling span -> the same metres-per-inch
    # on both panels, so L5's wider window does not read as a different scale.
    spans = [CEIL_XLIM[l][1] - CEIL_XLIM[l][0] for l in LINES]
    fig, axes = plt.subplots(1, 2, figsize=(6.1, 2.6),
                             gridspec_kw=dict(width_ratios=spans))
    for ax, line in zip(axes, LINES):
        r = res[line]
        dchi = (r["prof"] - r["prof"].min()) / r["kappa2"]     # rescaled, as elsewhere
        im = ax.pcolormesh(r["ceil"], r["sizes"], dchi.T, cmap="viridis_r",
                           vmax=30, shading="auto")
        # 1 SE / 2 SE contours (single-parameter Delta chi2 = 1, 4), matching the
        # convention of plot_misfit_row / plot_misfit.
        ax.contour(r["ceil"], r["sizes"], dchi.T, levels=[1.0, 4.0], colors="w",
                   linewidths=0.8)
        ax.plot(r["best_ceil"], r["best_size"], "*", color=C_BEST, ms=10,
                mec="k", mew=0.4, zorder=5)
        ax.axvline(it.LINE_PRESETS[line]["ceiling"], color=C_GPR, ls="--", lw=1.1)
        lid = lidar_ceiling(line)
        if lid:
            ax.axvline(lid, color=C_LIDAR, ls=":", lw=1.4)
        ax.set_ylim(*SIZE_YLIM)
        ax.set_xlim(*CEIL_XLIM[line])    # display only; the cube runs to 40 m on both
        ax.set_xlabel(r"ceiling depth $c$ (m)")
        # x0 is PROFILED OUT (min over x0 at every node), not sliced at a fixed value:
        # the correct marginalisation, and the same rule the main inversion uses.
        ax.set_title(rf"L{line} circle ($x_0$ profiled)", fontsize=10, fontweight="bold")
    axes[0].set_ylabel(r"radius $r$ (m)")
    axes[1].tick_params(labelleft=False)
    handles = [Line2D([], [], color=C_BEST, marker="*", ms=9, ls="none"),
               Line2D([], [], color=C_GPR, ls="--", lw=1.1),
               Line2D([], [], color=C_LIDAR, ls=":", lw=1.4)]
    fig.legend(handles, ["gravity-only best fit", "GPR ceiling pick", "LiDAR ceiling"],
               loc="lower center", ncol=3, fontsize=8, frameon=True,
               bbox_to_anchor=(0.45, 0.0))
    fig.subplots_adjust(bottom=BOX_B, left=BOX_L, right=BOX_R, top=BOX_T, wspace=0.08)
    # Colorbar on its own axes so it clears the panels and spans exactly the y-axis.
    cax = fig.add_axes([CB_X, BOX_B, CB_W, BOX_T - BOX_B])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(r"$\Delta\chi^2/\chi^2_\nu$", fontsize=8)
    cb.ax.tick_params(labelsize=8)
    fig.savefig(out, dpi=140)
    save_figure(fig, out.stem, "Inversion", vector=True)
    plt.close(fig)
    print(f"\n  saved -> {out.relative_to(it.BASE)}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-compute", action="store_true", help="replot from stored cubes")
    args = p.parse_args()

    if not args.no_compute:
        for line in LINES:
            print(f"Line {line}: free-depth search over {len(CEIL_GRID)} ceilings ...")
            compute(line)

    res = {l: analyse(l) for l in LINES}
    print("\n=== gravity ALONE (no GPR depth prior), circle model ===")
    for line in LINES:
        r = res[line]
        gpr = it.LINE_PRESETS[line]["ceiling"]
        lid = lidar_ceiling(line)
        f = lambda v: "unbounded" if v is None else f"{v:.1f}"
        print(f"  Line {line}: best ceiling {r['best_ceil']:.1f} m, area "
              f"{r['best_area']:.0f} m^2 | chi2_nu {r['chi2min']/r['dof']:.2f}")
        cap = ("" if r["ceil_cap"] is None
               else f"  [radius grid caps from {r['ceil_cap']:.1f} m -> no deeper bound]")
        print(f"      ceiling 1sigma: {f(r['ceil_lo'])} - {f(r['ceil_hi'])} m "
              f"(GPR pick {gpr:.1f}" + (f", LiDAR ceiling {lid:.1f}" if lid else "") + ")"
              + cap)
        print(f"      area    1sigma: {f(r['area_lo'])} - {f(r['area_hi'])} m^2")
    # The tightening: gravity-alone DATA interval vs the GPR-constrained data channel.
    # Compared like-for-like (data only) -- the constrained total SE also carries the
    # pick/velocity/detrend channels, which have no counterpart in the free-depth run.
    import inversion_io as io
    print("\n=== what the GPR depth prior buys (area, data channel only) ===")
    for line in LINES:
        r = res[line]
        a = io.load_artifact(line, "circle")
        free = ("unbounded" if None in (r["area_lo"], r["area_hi"])
                else f"+/-{(r['area_hi']-r['area_lo'])/2:.0f}")
        print(f"  Line {line}: gravity alone {free} m^2  ->  with GPR pick "
              f"+/-{a['area_se_data']:.0f} m^2")
    plate(res, it.FIG / "freedepth.png")
    return res


if __name__ == "__main__":
    main()

"""
Free-depth twin of plot_model_terrain.py: detrended-CBA fit (top) stacked on the tube
cross-section under the real measured surface (bottom), with the posterior ensemble
drawn faintly in BOTH panels. Deliberately the same layout, colours, markers and
legend style as the constrained figure, so the two can be read side by side.

THE ONE THING THAT IS NOT THE SAME -- and the whole point of the figure -- is where
the ensemble comes from:

  constrained (plot_model_terrain.py) : sample_ensemble() perturbs the INPUTS -- GPR
      picks, migration velocity, detrend slope, data noise -- and refits. An
      input-perturbation posterior.
  free depth (this script)            : the depth prior is GONE, so there are no picks
      or velocity to perturb. Draws are taken from the stored chi2 CUBE itself,
      weight ~ exp(-Delta chi2 / 2 kappa^2) with kappa^2 = max(1, chi2_nu) -- the SAME
      rescaling the 1SE/2SE contours in freedepth.py use. A data-misfit posterior.

So the two clouds are NOT comparable spreads: this one shows what the gravity data
alone allow, the other shows what the constrained inputs allow. Say so in the caption.
The upside of drawing from the cube is that this ensemble is exactly the object the
contours in freedepth.png already display -- the two figures cannot disagree.

CAVEAT (L5): its valley is open at the deep end and the recovered radius runs into the
top of RADIUS_GRID beyond ~39 m ceiling, so nodes at that cap are excluded from the
draw (they are unconverged, not merely unlikely). Even so, the L5 spread is bounded by
the search grid rather than by the data -- an honest statement of non-uniqueness, not a
measured interval. L3 is unaffected: its posterior closes well inside every grid.

Run:  python freedepth.py                          # once, to build the cubes
      python plot_freedepth_terrain.py --line 3
      python plot_freedepth_terrain.py --line 5 --ensemble 300
"""

import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.legend_handler import HandlerTuple

import invert_tube as it
import freedepth as fd
import grav_utils as _gu               # for the LiDAR schema check
import terrain_common as pmt              # shared styling + data helpers (library only)
from plot_utils import save_figure        # was reached via plot_model_terrain
from forward_polygon import ellipse_vertices

# GPR pick reference line: OFF. The pick constrains nothing here, and showing it invited
# the reader to compare it with a posterior it played no part in. Set True to bring the
# thin blue reference line back.
SHOW_GPR_PICK = False
GPR_LW = 0.9                     # thin on purpose; the constrained figure uses 1.2 + band

# Depth (m below the local surface at x0) at which the bottom panel is CUT. The ensemble
# is deliberately allowed to run out of the frame rather than the frame being grown to
# contain it: on L5 no upper bound on the ceiling depth exists, so a cloud that spills
# off the bottom says that honestly -- the same way the valley runs off the edge of the
# misfit plate. None = frame the whole ensemble (L3 closes, so it needs no cut).
# LARGER = more of the cloud visible and a taller panel; SMALLER = tighter crop.
DEPTH_CLIP = {3: None, 5: 55.0}

MODE = "circle"                  # freedepth.py searches the circle model only
SEED = 12345                     # reproducible draws


def draw_ensemble(line, n, rng):
    """Sample n (ceiling, R, x0) triples from the stored chi2 cube.

    Weight ~ exp(-Delta chi2 / 2 kappa^2) over every grid node, i.e. a posterior with
    flat priors on the three parameters across the searched grid. Nodes whose radius
    sits at the top of the size grid are dropped: there the search never converged, so
    their chi2 is a grid artefact (see the module docstring).
    """
    z = np.load(it.FIG / f"freedepth_line{line}.npz")
    cube, ceil, sizes, x0s = z["cube"], z["ceilings"], z["sizes"], z["x0s"]
    kappa2 = max(1.0, float(cube.min()) / int(z["dof"]))
    w = np.exp(-(cube - cube.min()) / (2.0 * kappa2))
    w[:, -1, :] = 0.0                       # drop the unconverged size-grid edge
    flat = w.ravel()
    idx = rng.choice(flat.size, size=n, p=flat / flat.sum())
    ic, isz, ix = np.unravel_index(idx, cube.shape)
    return ceil[ic], sizes[isz], x0s[ix]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--line", type=int, default=3, choices=sorted(it.LINE_PRESETS))
    p.add_argument("--ensemble", type=int, default=300,
                   help="number of posterior tube samples drawn faintly (0=off)")
    p.add_argument("--no-band", action="store_true",
                   help="omit the filled +/-1 SE envelope")
    args = p.parse_args()

    cfg = fd.cfg_for(args.line)
    res = fd.analyse(args.line)
    sx, d, se = it.load_line(args.line)
    xs, zs, typ, proj = pmt.gravity_profile(args.line)
    surf = lambda x: np.interp(x, xs, zs)
    col = pmt.LINE_COLORS.get(args.line, "0.1")
    wts = 1.0 / se ** 2
    rng = np.random.default_rng(SEED)

    size0, ceil0 = res["best_size"], res["best_ceil"]
    # best-fit x0 at the best (ceiling, size) node -- the cube keeps it, unlike prof.
    z = np.load(it.FIG / f"freedepth_line{args.line}.npz")
    cube, x0s = z["cube"], z["x0s"]
    ic = int(np.argmin(np.abs(z["ceilings"] - ceil0)))
    isz = int(np.argmin(np.abs(z["sizes"] - size0)))
    x0 = float(x0s[int(np.argmin(cube[ic, isz]))])
    surf0 = float(surf(x0))
    c_best = it.fit_offset(it.forward(MODE, size0, x0, ceil0, 16.0, sx, cfg), d, wts)[0]
    xd = np.linspace(float(xs.min()), float(xs.max()), 400)

    gpr = pmt.gpr_surface(args.line, proj, xs, zs)
    surf_x, surf_y = (gpr[0], gpr[1]) if gpr is not None else (xs, zs)

    def outline(size, xx, c, npts=200):
        a, b, depth = it.shape_params(MODE, size, c, 16.0)
        vv = ellipse_vertices(a, b, xx, depth, n=npts)
        vx, vz = vv[:, 0], surf(xx) - vv[:, 1]
        return np.append(vx, vx[0]), np.append(vz, vz[0])

    lf = it.lidar_file(args.line)
    _gu.check_lidar_schema(lf)     # cross-folder contract: fail loudly, not silently
    Ld = np.genfromtxt(lf, delimiter=",", names=True) if lf.exists() else None

    # ---- same canvas construction as plot_model_terrain -----------------------
    TOP_H_IN, W_IN = 1.5, 6.1
    M_L, M_R, M_B, M_T, GAP = 0.75, 0.72, 0.5, 0.28, 0.12
    YM_TOP, YM_BOT = 4.0, 6.0
    LEG_KW = dict(fontsize=6.5, labelspacing=0.25, handlelength=1.5,
                  handletextpad=0.5, borderpad=0.35, framealpha=0.9)

    fig = plt.figure()
    ax = fig.add_axes([0.1, 0.1, 0.8, 0.45])                   # terrain (bottom)
    ax_top = fig.add_axes([0.1, 0.60, 0.8, 0.30], sharex=ax)   # anomaly (top)

    ax.plot(surf_x, surf_y, "-", color="0.2", lw=1.8, zorder=4, label="surface")
    for t in ("regular", "tie", "base"):
        sel = typ == t
        if sel.any():
            ax.plot(xs[sel], zs[sel], pmt.STN_MARKER[t], color=col,
                    ms=pmt.STN_SIZE[t], mec="0.2", mew=0.5, ls="none", zorder=5,
                    label=f"{t} station")

    ens, ens_anom = [], []
    if args.ensemble > 0:
        ec, es, ex0 = draw_ensemble(args.line, args.ensemble, rng)
        print(f"  drew {len(ec)} models from the chi2 cube "
              f"(ceiling {ec.min():.1f}-{ec.max():.1f} m, r {es.min():.1f}-{es.max():.1f} m)")
        for cc, ss, xx in zip(ec, es, ex0):
            gx, gz = outline(ss, xx, cc, 160)
            ax.plot(gx, gz, color="0.3", lw=0.5, alpha=0.06, zorder=2)
            ens.append((gx, gz))
            off = it.fit_offset(it.forward(MODE, ss, xx, cc, 16.0, sx, cfg), d, wts)[0]
            ens_anom.append(it.forward(MODE, ss, xx, cc, 16.0, xd, cfg) + off)
        ax.plot([], [], color="0.35", lw=1.4, alpha=0.7,
                label="ensemble from data only")

    if not args.no_band and ens:
        _, _, dbest = it.shape_params(MODE, size0, ceil0, 16.0)
        (ix, iz), (ox, oz) = pmt.posterior_envelope(ens, x0, surf0 - dbest)
        ax.plot(ox, oz, color="k", lw=1.0, ls=(0, (4, 3)), zorder=6,
                label=r"$\pm$1 SE envelope")
        ax.plot(ix, iz, color="k", lw=1.0, ls=(0, (4, 3)), zorder=6)

    bxx, bzz = outline(size0, x0, ceil0, 240)
    ax.plot(bxx, bzz, color="k", lw=2.4, zorder=7, label="gravity-only best fit")

    if SHOW_GPR_PICK:
        cp = it.LINE_PRESETS[args.line]["ceiling"]
        ax.axhline(surf0 - cp, color=pmt.PICK_C, ls="-", lw=GPR_LW, zorder=3)
        ax.text(0.012, surf0 - cp, f"GPR pick ({cp:.1f} m, not used)",
                transform=ax.get_xaxis_transform(), va="bottom", ha="left",
                fontsize=8, color=pmt.PICK_C,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7))

    if Ld is not None:
        lx, lz = proj(Ld["easting"], Ld["northing"]), Ld["z"]
        ax.plot(lx, lz, color=pmt.LIDAR_COLOR, lw=1, zorder=8, label="LiDAR")

    # ---- top panel ------------------------------------------------------------
    for ga in ens_anom:
        ax_top.plot(xd, ga, color="0.3", lw=0.5, alpha=0.06, zorder=2)
    for t in ("regular", "tie"):
        sel = typ == t
        if sel.any():
            ax_top.errorbar(xs[sel], d[sel], yerr=se[sel], fmt=pmt.STN_MARKER[t],
                            color=col, ms=pmt.STN_SIZE[t], mec="0.2", mew=0.5,
                            ls="none", capsize=2, elinewidth=1.0, zorder=5)
    ax_top.plot(xd, it.forward(MODE, size0, x0, ceil0, 16.0, xd, cfg) + c_best,
                "-", color="k", lw=2.0, zorder=6, label="best fit")
    if ens_anom:
        ax_top.plot([], [], color="0.35", lw=1.4, alpha=0.7,
                    label="ensemble from data only")
    ax_top.plot([], [], pmt.STN_MARKER["regular"], color=col, mec="0.2", mew=0.5,
                ls="none", label=r"detrended CBA $\pm$ SE")
    ax_top.axhline(c_best, color="0.6", lw=0.8, ls=":", zorder=1)
    ax_top.set_ylabel("Detrended CBA (mGal)")
    ax_top.grid(True, alpha=0.25, ls="--")
    ax_top.tick_params(labelbottom=False)
    ax_top.legend(loc="lower right", **LEG_KW)
    ax_top.text(0.075, 0.95, "N", transform=ax_top.transAxes, ha="left", va="top",
                fontweight="bold", fontsize=11, color="0.3")
    ax_top.text(0.994, 0.95, "S", transform=ax_top.transAxes, ha="right", va="top",
                fontweight="bold", fontsize=11, color="0.3")

    if pmt.PANEL_LETTERS:
        bbx = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8)
        ax_top.text(*pmt.PANEL_LETTER_XY, pmt.PANEL_LETTERS[0],
                    transform=ax_top.transAxes, bbox=bbx, **pmt.PANEL_LETTER_KW)
        ax.text(*pmt.PANEL_LETTER_XY, pmt.PANEL_LETTERS[1], transform=ax.transAxes,
                bbox=bbx, **pmt.PANEL_LETTER_KW)

    # ---- window: frame to the drawn ensemble, not just the best fit -----------
    fy_bot = [min(z_.min() for _, z_ in ens)] if ens else [surf0 - 40]
    fy_top = [surf0, float(surf_y.max())]
    if Ld is not None:
        fy_bot.append(float(Ld["z"].min())); fy_top.append(float(Ld["z"].max()))
    xlo = min(float(surf_x.min()), float(xs.min()))
    xhi = max(float(surf_x.max()), float(xs.max()))
    xpad = 0.02 * (xhi - xlo)
    ax.set_xlim(xlo - xpad, xhi + xpad)
    # Cut the panel at DEPTH_CLIP and let the ensemble run out of the bottom, rather
    # than growing the frame to hold it (see DEPTH_CLIP).
    clip = DEPTH_CLIP.get(args.line)
    ybot = surf0 - clip if clip is not None else min(fy_bot) - YM_BOT
    ax.set_ylim(ybot, max(fy_top) + YM_TOP)

    ax.set_aspect("equal")
    ax.set_xlabel("distance along profile (m)")
    ax.set_ylabel("elevation (m)")
    ax.yaxis.set_label_position("right")
    ax.yaxis.tick_right()
    ax.grid(True, alpha=0.25, ls="--")
    handles, labels = ax.get_legend_handles_labels()
    if SHOW_GPR_PICK:
        handles.append(Line2D([], [], color=pmt.PICK_C, lw=GPR_LW))
        labels.append("GPR pick (reference)")
    ax.legend(handles, labels, loc="lower right",
              handler_map={tuple: HandlerTuple(ndivide=None)}, **LEG_KW)

    xspan = abs(np.subtract(*ax.get_xlim()))
    yspan = abs(np.subtract(*ax.get_ylim()))
    axes_w_in = W_IN - M_L - M_R
    bot_h_in = axes_w_in * yspan / xspan
    H_IN = M_B + bot_h_in + GAP + TOP_H_IN + M_T
    fig.set_size_inches(W_IN, H_IN)
    ax.set_position([M_L / W_IN, M_B / H_IN, axes_w_in / W_IN, bot_h_in / H_IN])
    ax_top.set_position([M_L / W_IN, (M_B + bot_h_in + GAP) / H_IN,
                         axes_w_in / W_IN, TOP_H_IN / H_IN])
    secax = ax.secondary_yaxis("left", functions=(lambda e: surf0 - e,
                                                  lambda dd: surf0 - dd))
    secax.set_ylabel("depth at tube centre (m)")
    ax_top.set_title(f"Line {args.line}, {MODE}, depth free", fontweight="bold")

    out = it.FIG / f"freedepth_terrain_line{args.line}.png"
    fig.savefig(out, dpi=150)
    save_figure(fig, out.stem, "Inversion", vector=True, tight=False)
    plt.close(fig)
    print(f"  saved -> {out.relative_to(it.BASE)}")


if __name__ == "__main__":
    main()

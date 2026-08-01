"""
Combined inversion figure: the detrended-CBA fit (top) stacked on the best-fit tube
cross-section under the REAL measured surface (bottom), sharing the along-profile
x-axis. The bottom panel is true-scale, ready to overlay a LiDAR cross-section as
ground truth. The SAME posterior ensemble is drawn faintly in both panels -- tube
outlines below, their forward gravity anomalies above -- so the data-fit spread and
the geometry spread are visibly one uncertainty. (The chi2 misfit surface is a
separate figure, invert_tube.py.)

The gravity profile crosses the tube, so the inverted circle/ellipse IS the tube
cross-section in the vertical plane of the profile -- the same plane a LiDAR slice
along the profile azimuth would give. In the bottom panel we draw:
  - the measured ground surface (GNSS elevations, REGCAN95 orthometric),
  - the best-fit circle and ellipse (from invert_tube), anchored at the local
    surface above the fitted tube centre x0 (the forward model assumes a flat top,
    so the tube is referenced to the surface elevation at x0),
  - the GPR ceiling/floor pick depths,
  - [optional] a LiDAR cross-section if a CSV is present (see LIDAR_CSV below).

Axes are equal-aspect so shapes are undistorted for direct comparison.

LiDAR overlay: reads  Data/LiDAR/lidar_line{LINE}.csv  (grav_utils.lidar_file), with
columns  x,z,easting,northing  where
    easting,northing = absolute REGCAN95 coords of each cave-outline vertex
    z = elevation (m, REGCAN95 orthometric height)
    x = legacy along-profile distance (no longer used; we project E,N ourselves)
i.e. the cave outline sampled in the vertical plane of the gravity line. The E,N
are projected onto the same profile axis as the gravity 'dist', so the overlay is
co-registered regardless of the distance-origin convention. (Ask the LiDAR expert
to slice along the line and include easting/northing per vertex.)

Reads precomputed artifacts (run_inversion.py) for the best fit, uncertainty budget
and posterior ensemble; it never runs the grid search or the Monte Carlo itself. The
cheap forward-model evaluations for the drawn curves use the artifact's stored InvCfg.

Run:  python run_inversion.py                       # once, to (re)build the artifacts
      python plot_model_terrain.py --line 3 [--truncate 10] [--modes circle ellipse]
"""

import argparse
import numpy as np
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))   # Code/ for plot_utils
from plot_utils import save_figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.legend_handler import HandlerTuple
from pathlib import Path

import invert_tube as it
import inversion_io as io
from forward_polygon import ellipse_vertices

CORR = it.BASE / "Data/Gravimetry/Processed/LL_gravity_corrections.csv"
WITHTC = it.BASE / "Data/Gravimetry/Processed/bouguer_anomaly_decay_rho1p875_with_TC.csv"
GPR_GNSS = it.BASE / "Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv"
HERE = Path(__file__).resolve().parent

# Match the rest of the gravity plots: per-line QGIS palette + station-type marker
# (base square, tie triangle, regular circle). Model curves stay black, as in the
# invert_tube best-fit plots, so they read as "model" not "data".
LINE_COLORS = {2: "#0099FF", 3: "#FF5C00", 5: "#00CC80"}
STN_MARKER = {"base": "s", "tie": "v", "regular": "o"}
STN_SIZE = {"base": 7, "tie": 5, "regular": 5}   # tie matches regular (was 8: too big, hid error bars)
FIT_LS = {"circle": "-", "ellipse": "--"}
LIDAR_COLOR = "#9400D3"        # ground truth: violet, distinct from orange/green
                               # stations, black model curves and grey terrain
PICK_C = "#0072B2"             # GPR pick: solid blue line + band (not the dashed envelope)

# Panel letters baked into the figure (LaTeX sees one image; it cannot label the two
# stacked panels separately). a) = top anomaly panel, b) = bottom cross-section panel.
PANEL_LETTERS = ("a)", "b)")   # (top, bottom); set to None to switch the letters off
PANEL_LETTER_XY = (0.014, 0.965)   # axes-fraction pos from top-left; move if it crowds N
PANEL_LETTER_KW = dict(fontsize=12, fontweight="bold", va="top", ha="left", zorder=10)

def gravity_profile(line):
    """Gravity stations for a line: along-profile dist, elevation (GNSS, matched
    from the corrections file on E/N), plus the profile origin O and unit
    direction u so other datasets can be projected onto the same dist axis."""
    det = np.genfromtxt(it.DET, delimiter=",", names=True)
    m = det["Line"] == line
    dist, E, N, loc = (det["dist"][m], det["Easting"][m], det["Northing"][m],
                       det["loc_id"][m])
    corr = np.genfromtxt(CORR, delimiter=",", names=True)
    elev = np.array([corr["Elevation"][np.argmin((corr["Easting"] - e) ** 2
                                                  + (corr["Northing"] - n) ** 2)]
                     for e, n in zip(E, N)])
    # Station type (base/tie/regular) by (Line, loc_id) from the corrected file.
    w = np.genfromtxt(WITHTC, delimiter=",", names=True, dtype=None, encoding="utf-8")
    wm = w["Line"] == line
    wloc, wtype = w["loc_id"][wm], np.array([str(x) for x in w["StationType"][wm]])
    typ = np.array([wtype[np.where(wloc == lid)[0][0]] if lid in wloc else "regular"
                    for lid in loc])
    o = np.argsort(dist)
    dist, E, N, elev, typ = dist[o], E[o], N[o], elev[o], typ[o]
    # The gravity 'dist' is an exact linear (straight-axis PCA) projection of E,N,
    # so recover that map by regression and reuse it to put any other dataset on
    # the SAME axis (lines are straight to <1.5 m, so this is well posed).
    coef, *_ = np.linalg.lstsq(np.column_stack([E, N, np.ones_like(E)]), dist,
                               rcond=None)
    proj = lambda e, n: coef[0] * e + coef[1] * n + coef[2]
    return dist, elev, typ, proj


def posterior_envelope(outlines, cx, cz, nth=181, lo=16, hi=84):
    """Inner/outer +/-1 sigma (16th-84th percentile) envelope of a family of
    closed outlines, as radial percentiles about a common centre (cx, cz). This
    derives the band FROM the samples, so it agrees with the cloud everywhere --
    it shows the pick/velocity spread at the ceiling/floor and the lateral (x0)
    spread, unlike an at-fixed-geometry size scaling. Star-shaped about the centre
    is assumed (fine for the near-concentric tube family). Returns two closed
    curves (inner, outer)."""
    thg = np.linspace(-np.pi, np.pi, nth)
    R = np.empty((len(outlines), nth))
    for i, (xx, zz) in enumerate(outlines):
        th = np.arctan2(zz - cz, xx - cx)
        r = np.hypot(xx - cx, zz - cz)
        o = np.argsort(th)
        ths, rs = th[o], r[o]
        the = np.concatenate([ths - 2 * np.pi, ths, ths + 2 * np.pi])
        re = np.concatenate([rs, rs, rs])
        R[i] = np.interp(thg, the, re)
    rlo, rhi = np.percentile(R, lo, axis=0), np.percentile(R, hi, axis=0)
    return ((cx + rlo * np.cos(thg), cz + rlo * np.sin(thg)),
            (cx + rhi * np.cos(thg), cz + rhi * np.sin(thg)))


def gpr_surface(line, proj, xs, zs):
    """Dense GPR-line surface: the clean GNSS points of the GPR line (identified
    by the 'Line' column) projected onto the SAME straight axis as the gravity
    'dist' (via proj), so the two are exactly co-registered. Returns (dist, elev,
    rms-vs-stations) or None -- the RMS is a genuine independent cross-check."""
    if not GPR_GNSS.exists():
        return None
    g = np.genfromtxt(GPR_GNSS, delimiter=",", names=True, dtype=None,
                      encoding="utf-8")
    m = g["Line"] == line
    if not np.any(m):
        return None
    dist = proj(g["Easting"][m], g["Northing"][m])
    elev = g["Elevation"][m]
    o = np.argsort(dist)
    dist, elev = dist[o], elev[o]
    rms = np.sqrt(np.nanmean((np.interp(xs, dist, elev) - zs) ** 2))
    return dist, elev, rms


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--line", type=int, default=3, choices=sorted(it.LINE_PRESETS))
    p.add_argument("--truncate", default="inf",
                   help="pit distance (m) or 'inf' (default)")
    p.add_argument("--modes", nargs="+", choices=["circle", "ellipse"],
                   default=None)
    p.add_argument("--ensemble", type=int, default=300,
                   help="number of posterior tube samples drawn faintly (0=off)")
    p.add_argument("--no-band", action="store_true",
                   help="omit the filled +/-1 SE envelope")
    args = p.parse_args()

    # ---- load the precomputed artifacts (run_inversion.py) -------------------
    # One artifact per (line, mode, truncation). The plot never runs the inversion
    # or the Monte Carlo -- it reads best fit, budget, ensemble and the stored InvCfg
    # (velocity/pick sigmas etc.) so the drawn forward curves match the compute run.
    truncate = None if args.truncate.lower() in ("inf", "none") else float(args.truncate)
    pre = it.LINE_PRESETS[args.line]
    modes = tuple(args.modes) if args.modes else pre["modes"]
    art, cfgs = {}, {}
    for mode in modes:
        art[mode] = io.load_artifact(args.line, mode, truncate)
        cfgs[mode] = io.cfg_of(art[mode])
    # ceiling is common across modes for a line; floor differs (ellipse only). The
    # per-mode picks live in each artifact and are read where the shape is drawn.
    ceil = art[modes[0]]["ceiling"]

    sx, d, se = it.load_line(args.line)
    xs, zs, typ, proj = gravity_profile(args.line)
    surf = lambda x: np.interp(x, xs, zs)
    col = LINE_COLORS.get(args.line, "0.1")

    def plot_stations():
        # base square / tie triangle / regular circle, all in the line colour.
        for t in ("regular", "tie", "base"):
            sel = typ == t
            if sel.any():
                ax.plot(xs[sel], zs[sel], STN_MARKER[t], color=col,
                        ms=STN_SIZE[t], mec="0.2", mew=0.5, ls="none", zorder=5,
                        label=f"{t} station")

    gpr = gpr_surface(args.line, proj, xs, zs)
    if gpr is not None:
        gd, ge, rms = gpr
        surf_x, surf_y = gd, ge                        # dense GPR-line surface
        print(f"  GPR-line GNSS projected, RMS vs gravity stations = {rms*100:.1f} cm")
    else:
        surf_x, surf_y = xs, zs
        print("  (no GPR topo file; using gravity station elevations only)")

    def outline(mode, size, x0, c, f, npts=200):
        a, b, depth = it.shape_params(mode, size, c, f)
        vv = ellipse_vertices(a, b, x0, depth, n=npts)
        vx, vz = vv[:, 0], surf(x0) - vv[:, 1]         # x, absolute elevation
        return np.append(vx, vx[0]), np.append(vz, vz[0])   # closed

    lidar = it.lidar_file(args.line)
    Ld = np.genfromtxt(lidar, delimiter=",", names=True) if lidar.exists() else None

    # ---- ONE FIGURE PER SHAPE: anomaly (top) + terrain section (bottom), -----
    # sharing the along-profile x-axis (supervisor's design). The SAME posterior
    # ensemble is drawn faintly in BOTH panels -- tube outlines below, their forward
    # gravity anomalies above -- so the data-fit spread and the geometry spread read
    # as one and the same uncertainty.
    TOP_H_IN = 1.5                 # anomaly-strip height (in); raise for a taller strip
    W_IN = 6.1                     # thesis \linewidth; the bottom stays true-scale
    M_L, M_R, M_B, M_T, GAP = 0.75, 0.72, 0.5, 0.28, 0.12   # margins/gap (inches)
    YM_TOP = 4.0                   # vertical pad above the section (m)
    YM_BOT_DEFAULT = 10.0          # pad below the section (m); per-fit overrides below
    YM_BOT_BY = {(3, "circle"): 8.0,     # per-fit bottom pad (user-tuned, m):
                 (3, "ellipse"): 12.0,   #   L3 circle -2, L3 ellipse +2,
                 (5, "circle"): 2.0}     #   L5 circle -10 (deepest point at the edge)
    LEG_KW = dict(fontsize=6.5, labelspacing=0.25, handlelength=1.5,   # compact legends
                  handletextpad=0.5, borderpad=0.35, framealpha=0.9)
    for mode in modes:
        a, cfg = art[mode], cfgs[mode]
        size0, x0, se_tot = a["size"], a["x0"], a["se_tot"]
        floor = a["floor"]                            # per-mode (ellipse) pick depth
        surf0 = float(surf(x0))
        wts = 1.0 / se ** 2
        c_best = a["baseline"]        # best-fit DC offset, computed by run_inversion.py
        xd = np.linspace(float(xs.min()), float(xs.max()), 400)   # dense anomaly x

        # Two stacked axes; positions are finalised after the limits are known so the
        # bottom panel can stay equal-aspect (true scale) while the top is a strip.
        fig = plt.figure()
        ax = fig.add_axes([0.1, 0.1, 0.8, 0.45])                   # terrain (bottom)
        ax_top = fig.add_axes([0.1, 0.60, 0.8, 0.30], sharex=ax)   # anomaly (top)

        # ================= bottom panel: terrain + tube cross-section ==========
        ax.plot(surf_x, surf_y, "-", color="0.2", lw=1.8, zorder=4,
                label="surface")
        plot_stations()

        # faint posterior ensemble = the family of solutions (neutral grey). Collect
        # the outlines (for the envelope) AND each sample's forward anomaly (top panel).
        ens, ens_anom = [], []
        ensemble = a["ensemble"] if args.ensemble > 0 else []
        if len(ensemble):
            print(f"  drawing {len(ensemble)} {mode} tubes from the artifact ensemble ...")
            for (s, xx, cc, ff) in ensemble:
                ex, ez = outline(mode, s, xx, cc, ff, 160)
                ax.plot(ex, ez, color="0.3", lw=0.5, alpha=0.06, zorder=2)
                ens.append((ex, ez))
                # matching forward anomaly, own DC offset fit to the REAL data, so the
                # top panel shows the spread of model predictions against fixed data.
                off = it.fit_offset(it.forward(mode, s, xx, cc, ff, sx, cfg), d, wts)[0]
                ens_anom.append(it.forward(mode, s, xx, cc, ff, xd, cfg) + off)
            ax.plot([], [], color="0.35", lw=1.4, alpha=0.7,   # legend proxy
                    label="posterior samples")

        # +/-1 sigma envelope = the 16-84 pct contour OF THE SAMPLES (black dashed),
        # so it agrees with the cloud: spread at the picks + lateral x0 variation.
        if not args.no_band and ens:
            _, _, dbest = it.shape_params(mode, size0, ceil, floor)
            (ix, iz), (ox, oz) = posterior_envelope(ens, x0, surf0 - dbest)
            ax.plot(ox, oz, color="k", lw=1.0, ls=(0, (4, 3)), zorder=6,
                    label=r"$\pm$1 SE envelope")
            ax.plot(ix, iz, color="k", lw=1.0, ls=(0, (4, 3)), zorder=6)

        # best-fit model outline: solid black on top.
        bxx, bzz = outline(mode, size0, x0, ceil, floor, 240)
        ax.plot(bxx, bzz, color="k", lw=2.4, zorder=7,
                label=f"best-fit {mode}")   # size + area now live in the results table

        # GPR pick depths (SOLID BLUE) + their own depth-uncertainty band.
        # sigma_d = sqrt(sigma_pick^2 + (ceil*sigma_v/v)^2) combines picking noise and
        # the common-mode velocity depth SHIFT -- the SAME channels sample_ensemble
        # perturbs, so this band NESTS inside the posterior envelope at the ceiling/
        # floor (a consistency check, NOT a second independent uncertainty). The
        # velocity term uses the CEILING depth for BOTH picks (the tube slides rigidly
        # with the overburden; the air-gap-corrected void height is v_air-fixed), so
        # the floor band is NOT inflated by its own depth. Solid blue so it never reads
        # as the black-dashed envelope.
        vel_shift = ceil * cfg.velocity_sigma / cfg.velocity   # common-mode, ceiling-driven
        picks = [(ceil, "GPR ceiling")] + ([(floor, "GPR floor")]
                                           if mode == "ellipse" else [])
        for i, (dp, name) in enumerate(picks):
            sigma_d = float(np.hypot(cfg.sigma_pick, vel_shift))
            ax.axhspan(surf0 - dp - sigma_d, surf0 - dp + sigma_d, color=PICK_C,
                       alpha=0.13, zorder=1)
            ax.axhline(surf0 - dp, color=PICK_C, ls="-", lw=1.2, zorder=3)
            ax.text(0.012, surf0 - dp, f"{name} ({dp:.1f} $\\pm$ {sigma_d:.1f} m)",
                    transform=ax.get_xaxis_transform(), va="bottom", ha="left",
                    fontsize=8, color=PICK_C, bbox=dict(boxstyle="round,pad=0.15",
                    fc="white", ec="none", alpha=0.7))

        # LiDAR ground-truth overlay.
        if Ld is not None:
            # Project the LiDAR vertices onto the SAME profile axis as the gravity
            # 'dist' (proj applied to the CSV's easting/northing), exactly as the GPR
            # surface is projected -- co-registered regardless of distance convention.
            lx, lz = proj(Ld["easting"], Ld["northing"]), Ld["z"]
            area_lidar = 0.5 * abs(np.dot(lx, np.roll(lz, -1))
                                   - np.dot(lz, np.roll(lx, -1)))
            ax.plot(lx, lz, color=LIDAR_COLOR, lw=1, zorder=8,
                    label="LiDAR")   # LiDAR area now in the results table

        # ================= top panel: detrended residual + fits ================
        for ga in ens_anom:
            ax_top.plot(xd, ga, color="0.3", lw=0.5, alpha=0.06, zorder=2)
        # data, styled by station type to match the markers directly below it.
        for t in ("regular", "tie"):
            sel = typ == t
            if sel.any():
                ax_top.errorbar(xs[sel], d[sel], yerr=se[sel], fmt=STN_MARKER[t],
                                color=col, ms=STN_SIZE[t], mec="0.2", mew=0.5,
                                ls="none", capsize=2, elinewidth=1.0, zorder=5)
        ax_top.plot(xd, it.forward(mode, size0, x0, ceil, floor, xd, cfg) + c_best,
                    "-", color="k", lw=2.0, zorder=6, label="best fit")
        if ens_anom:
            ax_top.plot([], [], color="0.35", lw=1.4, alpha=0.7,
                        label="posterior anomalies")
        ax_top.plot([], [], STN_MARKER["regular"], color=col, mec="0.2", mew=0.5,
                    ls="none", label=r"detrended CBA $\pm$ SE")
        ax_top.axhline(c_best, color="0.6", lw=0.8, ls=":", zorder=1)
        ax_top.set_ylabel("Detrended CBA (mGal)")
        ax_top.grid(True, alpha=0.25, ls="--")
        ax_top.tick_params(labelbottom=False)          # x-labels only on the bottom
        ax_top.legend(loc="lower right", **LEG_KW)
        # N/S once, on the top panel (the x-axis is shared). N is shifted right of
        # the a) panel letter so the two do not overlap in the top-left corner.
        ax_top.text(0.075, 0.95, "N", transform=ax_top.transAxes, ha="left",
                    va="top", fontweight="bold", fontsize=11, color="0.3")
        ax_top.text(0.994, 0.95, "S", transform=ax_top.transAxes, ha="right",
                    va="top", fontweight="bold", fontsize=11, color="0.3")

        # panel letters baked in (a) top, b) bottom); white bbox keeps them legible
        # over the grid. Reference the two panels separately from the LaTeX text.
        if PANEL_LETTERS:
            bbx = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8)
            ax_top.text(*PANEL_LETTER_XY, PANEL_LETTERS[0], transform=ax_top.transAxes,
                        bbox=bbx, **PANEL_LETTER_KW)
            ax.text(*PANEL_LETTER_XY, PANEL_LETTERS[1], transform=ax.transAxes,
                    bbox=bbx, **PANEL_LETTER_KW)

        # ---- window: full profile laterally; framed to the section vertically.
        _, bb, depth = it.shape_params(mode, size0, ceil, floor)
        fy_bot = [surf0 - (depth + bb + se_tot)]
        fy_top = [surf0, float(surf_y.max())]
        if Ld is not None:
            fy_bot.append(float(Ld["z"].min())); fy_top.append(float(Ld["z"].max()))
        xlo = min(float(surf_x.min()), float(xs.min()))
        xhi = max(float(surf_x.max()), float(xs.max()))
        xpad = 0.02 * (xhi - xlo)
        ym_bot = YM_BOT_BY.get((args.line, mode), YM_BOT_DEFAULT)
        ytop, ybot = max(fy_top) + YM_TOP, min(fy_bot) - ym_bot
        ax.set_xlim(xlo - xpad, xhi + xpad)            # shared -> ax_top follows
        ax.set_ylim(ybot, ytop)

        ttl = "" if truncate is None else f"  [truncated at {truncate:.0f} m]"
        ax.set_aspect("equal")
        ax.set_xlabel("distance along profile (m)")
        ax.set_ylabel("elevation (m)")                 # REGCAN95 on the right
        ax.yaxis.set_label_position("right")
        ax.yaxis.tick_right()
        ax.grid(True, alpha=0.25, ls="--")
        # Combined line+band handle for the GPR pick (legend shows BOTH the solid
        # blue line and its translucent uncertainty band as one entry).
        handles, labels = ax.get_legend_handles_labels()
        handles.append((Line2D([], [], color=PICK_C, lw=1.2),
                        mpatches.Patch(color=PICK_C, alpha=0.13)))
        labels.append(r"GPR pick $\pm$ SE")
        ax.legend(handles, labels, loc="lower right",
                  handler_map={tuple: HandlerTuple(ndivide=None)}, **LEG_KW)

        # ---- size the canvas so the equal-aspect bottom box fills its width, then
        # stack the fixed-height anomaly strip above it (both share the x extent).
        xspan = abs(np.subtract(*ax.get_xlim()))
        yspan = abs(np.subtract(*ax.get_ylim()))
        axes_w_in = W_IN - M_L - M_R
        bot_h_in = axes_w_in * yspan / xspan           # equal-aspect -> box aspect = data
        H_IN = M_B + bot_h_in + GAP + TOP_H_IN + M_T
        fig.set_size_inches(W_IN, H_IN)
        ax.set_position([M_L / W_IN, M_B / H_IN, axes_w_in / W_IN, bot_h_in / H_IN])
        ax_top.set_position([M_L / W_IN, (M_B + bot_h_in + GAP) / H_IN,
                             axes_w_in / W_IN, TOP_H_IN / H_IN])
        # depth axis on the terrain panel, added after positioning so it tracks the box.
        secax = ax.secondary_yaxis("left", functions=(lambda e: surf0 - e,
                                                       lambda dd: surf0 - dd))
        secax.set_ylabel("depth at tube centre (m)")
        ax_top.set_title(f"Line {args.line}, {mode}{ttl}", fontweight="bold")

        trunc = "" if truncate is None else f"_trunc{int(truncate)}"
        out = it.FIG / f"terrain_model_line{args.line}_{mode}{trunc}.png"
        fig.savefig(out, dpi=150)
        if not trunc:   # untruncated run == the thesis figure
            # tight=False: the figure is pre-sized so the equal-aspect box fills the
            # canvas; bbox_inches="tight" would re-fit it and blow up the page.
            save_figure(fig, out.stem, "Inversion", vector=True, tight=False)
        plt.close(fig)
        print(f"  saved -> {out.relative_to(it.BASE)}")


if __name__ == "__main__":
    main()

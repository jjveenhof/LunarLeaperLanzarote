"""
Best-fit tube cross-section drawn under the REAL measured surface, in true scale,
ready to overlay a LiDAR cross-section as ground truth.

The gravity profile crosses the tube, so the inverted circle/ellipse IS the tube
cross-section in the vertical plane of the profile -- the same plane a LiDAR slice
along the profile azimuth would give. We draw:
  - the measured ground surface (GNSS elevations, REGCAN95 orthometric),
  - the best-fit circle and ellipse (from invert_tube), anchored at the local
    surface above the fitted tube centre x0 (the forward model assumes a flat top,
    so the tube is referenced to the surface elevation at x0),
  - the GPR ceiling/floor pick depths,
  - [optional] a LiDAR cross-section if a CSV is present (see LIDAR_CSV below).

Axes are equal-aspect so shapes are undistorted for direct comparison.

LiDAR overlay: drop a CSV next to this script named  lidar_line{LINE}.csv  with
columns  x,z  where
    x = distance along the gravity profile (m), same origin as our 'dist'
    z = elevation (m, REGCAN95 orthometric height)
i.e. the cave outline sampled in the vertical plane of the gravity line. It is
then plotted directly on top. (Ask the LiDAR expert to slice along the line; the
line's station coordinates are in the detrended CSV / corrections file.)

Run:  python plot_model_terrain.py --line 3 [--truncate 10] [--modes circle ellipse]
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
STN_SIZE = {"base": 7, "tie": 8, "regular": 5}
FIT_LS = {"circle": "-", "ellipse": "--"}
LIDAR_COLOR = "#9400D3"        # ground truth: violet, distinct from orange/green
                               # stations, black model curves and grey terrain
PICK_C = "#0072B2"             # GPR pick: solid blue line + band (not the dashed envelope)


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
    p.add_argument("--seed", type=int, default=0, help="RNG seed for the ensemble")
    args = p.parse_args()

    # ---- configure the imported inversion module ----------------------------
    it.LINE = args.line
    pre = it.LINE_PRESETS[args.line]
    it.CEILING0 = pre["ceiling"]
    it.FLOOR0 = pre["floor"] or 16.0
    it.TRUNCATE_D = None if args.truncate.lower() in ("inf", "none") \
        else float(args.truncate)
    modes = tuple(args.modes) if args.modes else pre["modes"]
    ceil, floor = it.CEILING0, it.FLOOR0
    # uncertainty-channel constants (needed for the band + ensemble; the terrain
    # plot must set these, else it.* keeps its Line-3 module defaults).
    it.VELOCITY = pre["velocity"]
    it.VELOCITY_SIGMA = pre["velocity_sigma"]
    it.SIGMA_PICK = 1.0                               # GPR pick 1-sigma (m)
    if it.TREND.exists():
        tp = np.genfromtxt(it.TREND, delimiter=",", names=True)
        r = tp[tp["Line"] == args.line]
        it.SLOPE_SE = float(r["slope_se"][0]) if len(r) else 0.0
    else:
        it.SLOPE_SE = 0.0

    sx, d, se = it.load_line(args.line)
    xmin = sx[np.argmin(d)]
    x0s = np.arange(xmin - 20, xmin + 20, 0.5)
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

    # ---- best fit + shared uncertainty budget per shape (reuse the inversion)-
    fits, unc = {}, {}
    for mode in modes:
        sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
        fits[mode] = it.invert(mode, sx, d, se, ceil, floor, sizes, x0s)
        unc[mode] = it.size_area_se(mode, sx, d, se, fits[mode], ceil, floor, sizes)

    gpr = gpr_surface(args.line, proj, xs, zs)
    if gpr is not None:
        gd, ge, rms = gpr
        surf_x, surf_y = gd, ge                        # dense GPR-line surface
        print(f"  GPR-line GNSS projected, RMS vs gravity stations = {rms*100:.1f} cm")
    else:
        surf_x, surf_y = xs, zs
        print("  (no GPR topo file; using gravity station elevations only)")

    rng = np.random.default_rng(args.seed)

    def outline(mode, size, x0, c, f, npts=200):
        a, b, depth = it.shape_params(mode, size, c, f)
        vv = ellipse_vertices(a, b, x0, depth, n=npts)
        vx, vz = vv[:, 0], surf(x0) - vv[:, 1]         # x, absolute elevation
        return np.append(vx, vx[0]), np.append(vz, vz[0])   # closed

    lidar = HERE / f"lidar_line{args.line}.csv"
    Ld = np.genfromtxt(lidar, delimiter=",", names=True) if lidar.exists() else None

    # ---- ONE FIGURE PER SHAPE (circle / ellipse), so each stays uncrowded ----
    for mode in modes:
        res, u = fits[mode], unc[mode]
        size0, x0, se_tot = res["size"], res["x0"], u["se_tot"]
        surf0 = float(surf(x0))
        fig, ax = plt.subplots(figsize=(12, 5.0))
        ax.plot(surf_x, surf_y, "-", color="0.2", lw=1.8, zorder=4,
                label="surface (GNSS)")
        plot_stations()

        # faint posterior ensemble = the family of solutions (neutral grey), and
        # collect the outlines to build the envelope from the SAME samples.
        ens = []
        if args.ensemble > 0:
            print(f"  sampling {args.ensemble} {mode} tubes ...")
            for (s, xx, cc, ff) in it.sample_ensemble(mode, sx, d, se, ceil, floor,
                                                      args.ensemble, rng):
                ex, ez = outline(mode, s, xx, cc, ff, 160)
                ax.plot(ex, ez, color="0.3", lw=0.5, alpha=0.06, zorder=2)
                ens.append((ex, ez))
            ax.plot([], [], color="0.35", lw=1.4, alpha=0.7,   # legend proxy
                    label="posterior samples")

        # +/-1 sigma envelope = the 16-84 pct contour OF THE SAMPLES (black dashed),
        # so it agrees with the cloud: spread at the picks + lateral x0 variation.
        if not args.no_band and ens:
            _, _, dbest = it.shape_params(mode, size0, ceil, floor)
            (ix, iz), (ox, oz) = posterior_envelope(ens, x0, surf0 - dbest)
            ax.plot(ox, oz, color="k", lw=1.0, ls=(0, (4, 3)), zorder=6,
                    label=r"$\pm1\sigma$ envelope (68%)")
            ax.plot(ix, iz, color="k", lw=1.0, ls=(0, (4, 3)), zorder=6)

        # best-fit model: solid black on top.
        bxx, bzz = outline(mode, size0, x0, ceil, floor, 240)
        lbl = "R" if mode == "circle" else "a"
        ax.plot(bxx, bzz, color="k", lw=2.4, zorder=7,
                label=f"{mode}: {lbl} {size0:.1f} m, "
                      f"{u['area']:.0f} $\\pm$ {u['area_se_tot']:.0f} m$^2$")

        # GPR pick depths (SOLID BLUE) + their own depth-uncertainty band.
        # sigma_d = sqrt(sigma_pick^2 + (d*sigma_v/v)^2) combines picking noise and
        # common-mode velocity scaling -- the SAME channels sample_ensemble perturbs,
        # so this band NESTS inside the posterior envelope at the ceiling/floor (a
        # consistency check, NOT a second independent uncertainty). Solid blue so it
        # never reads as the black-dashed envelope.
        dv_frac = it.VELOCITY_SIGMA / it.VELOCITY
        picks = [(ceil, "GPR ceiling")] + ([(floor, "GPR floor")]
                                           if mode == "ellipse" else [])
        for i, (dp, name) in enumerate(picks):
            sigma_d = float(np.hypot(it.SIGMA_PICK, dp * dv_frac))
            ax.axhspan(surf0 - dp - sigma_d, surf0 - dp + sigma_d, color=PICK_C,
                       alpha=0.13, zorder=1)
            ax.axhline(surf0 - dp, color=PICK_C, ls="-", lw=1.2, zorder=3)
            ax.text(0.012, surf0 - dp, f"{name} ({dp:.1f} $\\pm$ {sigma_d:.1f} m)",
                    transform=ax.get_xaxis_transform(), va="bottom", ha="left",
                    fontsize=8, color=PICK_C, bbox=dict(boxstyle="round,pad=0.15",
                    fc="white", ec="none", alpha=0.7))

        # LiDAR ground-truth overlay.
        if Ld is not None:
            lx, lz = Ld["x"], Ld["z"]
            area_lidar = 0.5 * abs(np.dot(lx, np.roll(lz, -1))
                                   - np.dot(lz, np.roll(lx, -1)))
            ax.plot(lx, lz, color=LIDAR_COLOR, lw=2.6, zorder=8,
                    label=f"LiDAR ({area_lidar:.0f} m$^2$)")

        # ---- window: full profile laterally; framed to the section vertically.
        _, bb, depth = it.shape_params(mode, size0, ceil, floor)
        fy_bot = [surf0 - (depth + bb + se_tot)]
        fy_top = [surf0, float(surf_y.max())]
        if Ld is not None:
            fy_bot.append(float(Ld["z"].min())); fy_top.append(float(Ld["z"].max()))
        YM = 4.0
        xlo = min(float(surf_x.min()), float(xs.min()))
        xhi = max(float(surf_x.max()), float(xs.max()))
        xpad = 0.02 * (xhi - xlo)
        ytop, ybot = max(fy_top) + YM, min(fy_bot) - YM
        ax.set_xlim(xlo - xpad, xhi + xpad)
        ax.set_ylim(ybot, ytop)

        ttl = "" if it.TRUNCATE_D is None else f"  [truncated at {it.TRUNCATE_D:.0f} m]"
        ax.set_aspect("equal")
        ax.set_xlabel("distance along profile (m)")
        ax.set_ylabel("elevation (m)")                 # REGCAN95 on the right
        ax.yaxis.set_label_position("right")
        ax.yaxis.tick_right()
        secax = ax.secondary_yaxis("left", functions=(lambda e: surf0 - e,
                                                       lambda dd: surf0 - dd))
        secax.set_ylabel("depth below surface at tube centre (m)")
        ax.set_title(f"Line {args.line}: best-fit {mode} in measured terrain{ttl}",
                     fontweight="bold")
        # Combined line+band handle for the GPR pick (so the legend shows BOTH the
        # solid blue line and its translucent uncertainty band as one entry).
        handles, labels = ax.get_legend_handles_labels()
        handles.append((Line2D([], [], color=PICK_C, lw=1.2),
                        mpatches.Patch(color=PICK_C, alpha=0.13)))
        labels.append(r"GPR pick $\pm\,\sigma_d$")
        ax.legend(handles, labels, fontsize=8, loc="lower right",
                  handler_map={tuple: HandlerTuple(ndivide=None)})
        ax.grid(True, alpha=0.25, ls="--")
        # Plot N->S (N on the left) to match the GPR sections.
        ax.invert_xaxis()
        ax.text(0.006, 0.97, "N", transform=ax.transAxes, ha="left", va="top",
                fontweight="bold", fontsize=13, color="0.3")
        ax.text(0.994, 0.97, "S", transform=ax.transAxes, ha="right", va="top",
                fontweight="bold", fontsize=13, color="0.3")
        # Size the figure so the equal-aspect axes fill it (no vertical slack).
        xspan = abs(np.subtract(*ax.get_xlim()))
        yspan = abs(np.subtract(*ax.get_ylim()))
        Lf, Rf, Bf, Tf = 0.09, 0.90, 0.14, 0.88        # axes position (fig fractions)
        W = 13.0
        fig.set_size_inches(W, W * (Rf - Lf) * yspan / xspan / (Tf - Bf))
        fig.subplots_adjust(left=Lf, right=Rf, bottom=Bf, top=Tf)
        trunc = "" if it.TRUNCATE_D is None else f"_trunc{int(it.TRUNCATE_D)}"
        out = it.FIG / f"terrain_model_line{args.line}_{mode}{trunc}.png"
        fig.savefig(out, dpi=150)
        if not trunc:   # untruncated run == the thesis figure
            save_figure(fig, out.stem, "Inversion", vector=True)
        plt.close(fig)
        print(f"  saved -> {out.relative_to(it.BASE)}")


if __name__ == "__main__":
    main()

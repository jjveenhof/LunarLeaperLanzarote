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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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

    # ---- best fit per shape (reusing the inversion) -------------------------
    fits = {}
    for mode in modes:
        sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
        fits[mode] = it.invert(mode, sx, d, se, ceil, floor, sizes, x0s)

    # ---- figure -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 5.0))
    gpr = gpr_surface(args.line, proj, xs, zs)
    if gpr is not None:
        gd, ge, rms = gpr
        surf_x, surf_y = gd, ge              # dense GPR-line surface (drawn + filled)
        ax.plot(gd, ge, "-", color="0.25", lw=1.8, zorder=4, label="surface (GNSS)")
        print(f"  GPR-line GNSS projected, RMS vs gravity stations = {rms*100:.1f} cm")
    else:
        surf_x, surf_y = xs, zs
        ax.plot(xs, zs, "-", color="0.25", lw=2.0, zorder=4, label="surface (GNSS)")
        print("  (no GPR topo file; using gravity station elevations only)")
    plot_stations()

    for mode in modes:
        res = fits[mode]
        a, b, depth = it.shape_params(mode, res["size"], ceil, floor)
        x0 = res["x0"]
        v = ellipse_vertices(a, b, x0, depth, n=240)
        vx, vz = v[:, 0], surf(x0) - v[:, 1]          # depth -> absolute elevation
        vx = np.append(vx, vx[0]); vz = np.append(vz, vz[0])
        lbl = "R" if mode == "circle" else "a"
        ax.plot(vx, vz, color="k", lw=2.2, ls=FIT_LS[mode], zorder=6,
                label=f"{mode}: {lbl} {res['size']:.1f} m, "
                      f"{it.area_of(mode, res['size'], ceil, floor):.0f} m$^2$")

    # GPR pick depths under the fitted centre (use the circle's x0 if present)
    x0r = fits.get("circle", fits[modes[0]])["x0"]
    surf0 = float(surf(x0r))                     # surface elevation above the tube
    picks = [(ceil, "GPR ceiling"), (floor, "GPR floor")] if "ellipse" in modes \
        else [(ceil, "GPR ceiling")]
    for i, (depth_pick, name) in enumerate(picks):
        ax.axhline(surf0 - depth_pick, color="0.45", ls="--", lw=1.1, zorder=2,
                   label="GPR pick (ceiling/floor)" if i == 0 else "_nolegend_")
        # x in axes fraction (left edge), y in data -> robust to the x-axis flip.
        ax.text(0.012, surf0 - depth_pick, f"{name} ({depth_pick:.1f} m)",
                transform=ax.get_xaxis_transform(), va="bottom", ha="left",
                fontsize=8, color="0.25",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7))

    # ---- optional LiDAR ground-truth overlay --------------------------------
    lidar = HERE / f"lidar_line{args.line}.csv"
    if lidar.exists():
        L = np.genfromtxt(lidar, delimiter=",", names=True)
        lx, lz = L["x"], L["z"]
        # shoelace area of the closed LiDAR outline (m^2)
        area_lidar = 0.5 * abs(np.dot(lx, np.roll(lz, -1)) - np.dot(lz, np.roll(lx, -1)))
        ax.plot(lx, lz, color=LIDAR_COLOR, lw=2.6, zorder=7,
                label=f"LiDAR ({area_lidar:.0f} m$^2$)")
        print(f"  overlaid LiDAR -> {lidar.name} (area {area_lidar:.0f} m^2)")
    else:
        print(f"  (no LiDAR file yet; drop '{lidar.name}' with columns x,z to overlay)")

    # ---- window: full profile (all gravity + topo data); vertical extent
    # framed to the section (surface + tube/LiDAR), rock fills to the axis bottom.
    fy_bot, fy_top = [], [surf0, float(surf_y.max())]
    for mode in modes:
        _, b, depth = it.shape_params(mode, fits[mode]["size"], ceil, floor)
        fy_bot.append(surf0 - (depth + b))               # tube bottom elevation
    if lidar.exists():
        fy_bot.append(float(L["z"].min())); fy_top.append(float(L["z"].max()))
    YM = 4.0
    xlo = min(float(surf_x.min()), float(xs.min()))
    xhi = max(float(surf_x.max()), float(xs.max()))
    xpad = 0.02 * (xhi - xlo)
    ytop, ybot = max(fy_top) + YM, min(fy_bot) - YM
    ax.set_xlim(xlo - xpad, xhi + xpad)
    ax.set_ylim(ybot, ytop)
    # rock fill: surface down to the axis bottom -> no floating edge at a random depth
    ax.fill_between(surf_x, surf_y, ybot, color="0.88", zorder=0)

    ttl = "" if it.TRUNCATE_D is None else f"  [tube truncated at {it.TRUNCATE_D:.0f} m]"
    ax.set_aspect("equal")
    ax.set_xlabel("distance along profile (m)")
    # Elevation (REGCAN95) on the right; depth below the tube surface on the left.
    ax.set_ylabel("elevation (m)")
    ax.yaxis.set_label_position("right")
    ax.yaxis.tick_right()
    secax = ax.secondary_yaxis("left", functions=(lambda e: surf0 - e,
                                                  lambda d: surf0 - d))
    secax.set_ylabel("depth below surface at tube centre (m)")
    ax.set_title(f"Line {args.line}: best-fit tube in measured terrain{ttl}",
                 fontweight="bold")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(True, alpha=0.25, ls="--")
    # Plot N->S (N on the left) to match the GPR sections; dist stays S->N.
    ax.invert_xaxis()
    ax.text(0.006, 0.97, "N", transform=ax.transAxes, ha="left", va="top",
            fontweight="bold", fontsize=13, color="0.3")
    ax.text(0.994, 0.97, "S", transform=ax.transAxes, ha="right", va="top",
            fontweight="bold", fontsize=13, color="0.3")
    # Size the figure so the equal-aspect axes fill it (kills the vertical slack
    # that equal aspect + a too-tall figure would otherwise leave as big margins).
    xspan = abs(np.subtract(*ax.get_xlim()))
    yspan = abs(np.subtract(*ax.get_ylim()))
    L, R, B, T = 0.09, 0.90, 0.14, 0.88          # axes position (figure fractions)
    W = 13.0
    fig.set_size_inches(W, W * (R - L) * yspan / xspan / (T - B))
    fig.subplots_adjust(left=L, right=R, bottom=B, top=T)
    tag = "" if it.TRUNCATE_D is None else f"_trunc{int(it.TRUNCATE_D)}"
    out = it.FIG / f"terrain_model_line{args.line}{tag}.png"
    fig.savefig(out, dpi=150)
    print(f"  saved -> {out.relative_to(it.BASE)}")


if __name__ == "__main__":
    main()

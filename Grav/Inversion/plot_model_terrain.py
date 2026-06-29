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
GPR_GNSS = it.BASE / "Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv"
HERE = Path(__file__).resolve().parent
COLORS = {"circle": "#FF5C00", "ellipse": "#0066CC"}


def gravity_profile(line):
    """Gravity stations for a line: along-profile dist, elevation (GNSS, matched
    from the corrections file on E/N), plus the profile origin O and unit
    direction u so other datasets can be projected onto the same dist axis."""
    det = np.genfromtxt(it.DET, delimiter=",", names=True)
    m = det["Line"] == line
    dist, E, N = det["dist"][m], det["Easting"][m], det["Northing"][m]
    corr = np.genfromtxt(CORR, delimiter=",", names=True)
    elev = np.array([corr["Elevation"][np.argmin((corr["Easting"] - e) ** 2
                                                  + (corr["Northing"] - n) ** 2)]
                     for e, n in zip(E, N)])
    o = np.argsort(dist)
    dist, E, N, elev = dist[o], E[o], N[o], elev[o]
    O = np.array([E[0], N[0]])
    u = np.array([E[-1] - E[0], N[-1] - N[0]])
    u = u / np.hypot(*u)
    return dist, elev, O, u


def gpr_surface(line, O, u, xs, zs):
    """Dense GPR-line surface: the clean GNSS points of the GPR line (identified
    by the 'Line' column) projected by their real coordinates onto the gravity
    profile axis -- dist = (P - O).u. Returns (dist, elev, rms-vs-stations) or
    None. The RMS is a genuine cross-check now (independent coordinate sources)."""
    if not GPR_GNSS.exists():
        return None
    g = np.genfromtxt(GPR_GNSS, delimiter=",", names=True, dtype=None,
                      encoding="utf-8")
    m = g["Line"] == line
    if not np.any(m):
        return None
    P = np.column_stack([g["Easting"][m], g["Northing"][m]])
    dist = (P - O) @ u
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
    xs, zs, O, u = gravity_profile(args.line)
    surf = lambda x: np.interp(x, xs, zs)

    # ---- best fit per shape (reusing the inversion) -------------------------
    fits = {}
    for mode in modes:
        sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
        fits[mode] = it.invert(mode, sx, d, se, ceil, floor, sizes, x0s)

    # ---- figure -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 5.5))
    gpr = gpr_surface(args.line, O, u, xs, zs)
    if gpr is not None:
        gd, ge, rms = gpr
        # dense GPR-line GNSS surface is the drawn surface; rock fill beneath it.
        floor_z = ge.min() - max(floor, 20) - 5
        ax.fill_between(gd, ge, floor_z, color="0.88", zorder=0)
        ax.plot(gd, ge, "-", color="0.25", lw=1.8, zorder=4,
                label="GPR-line surface (GNSS, dense)")
        ax.plot(xs, zs, "o", color="0.1", ms=5, zorder=5,
                label=f"gravity stations (GNSS)  [GPR-vs-stn RMS {rms*100:.0f} cm]")
        print(f"  GPR-line GNSS projected, RMS vs gravity stations = {rms*100:.1f} cm")
    else:
        floor_z = zs.min() - max(floor, 20) - 5
        ax.fill_between(xs, zs, floor_z, color="0.88", zorder=0)
        ax.plot(xs, zs, "o-", color="0.25", lw=2.0, ms=5, zorder=4,
                label="measured surface (gravity stations)")
        print("  (no GPR topo file; using gravity station elevations only)")

    for mode in modes:
        res = fits[mode]
        a, b, depth = it.shape_params(mode, res["size"], ceil, floor)
        x0 = res["x0"]
        v = ellipse_vertices(a, b, x0, depth, n=240)
        vx, vz = v[:, 0], surf(x0) - v[:, 1]          # depth -> absolute elevation
        vx = np.append(vx, vx[0]); vz = np.append(vz, vz[0])
        lbl = "R" if mode == "circle" else "a"
        ax.plot(vx, vz, color=COLORS[mode], lw=2.2, zorder=5,
                label=f"{mode} fit ({lbl}={res['size']:.1f} m, "
                      f"area {it.area_of(mode, res['size'], ceil, floor):.0f} m$^2$)")

    # GPR pick depths under the fitted centre (use the circle's x0 if present)
    x0r = fits.get("circle", fits[modes[0]])["x0"]
    for depth_pick, name in [(ceil, "GPR ceiling"),
                             (floor, "GPR floor")] if "ellipse" in modes \
            else [(ceil, "GPR ceiling")]:
        ax.axhline(surf(x0r) - depth_pick, color="0.55", ls=":", lw=1.0, zorder=2)
        ax.text(xs.min(), surf(x0r) - depth_pick, f" {name} ({depth_pick:.0f} m)",
                va="bottom", ha="left", fontsize=8, color="0.4")

    # ---- optional LiDAR ground-truth overlay --------------------------------
    lidar = HERE / f"lidar_line{args.line}.csv"
    if lidar.exists():
        L = np.genfromtxt(lidar, delimiter=",", names=True)
        ax.plot(L["x"], L["z"], color="k", lw=2.4, ls="--", zorder=6,
                label="LiDAR cross-section")
        print(f"  overlaid LiDAR -> {lidar.name}")
    else:
        print(f"  (no LiDAR file yet; drop '{lidar.name}' with columns x,z to overlay)")

    ttl = "" if it.TRUNCATE_D is None else f"  [tube truncated at {it.TRUNCATE_D:.0f} m]"
    ax.set_aspect("equal")
    ax.set_xlabel("distance along profile (m)")
    ax.set_ylabel("elevation (m, REGCAN95)")
    ax.set_title(f"Line {args.line}: best-fit tube in measured terrain{ttl}",
                 fontweight="bold")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(True, alpha=0.25, ls="--")
    fig.tight_layout()
    tag = "" if it.TRUNCATE_D is None else f"_trunc{int(it.TRUNCATE_D)}"
    out = it.FIG / f"terrain_model_line{args.line}{tag}.png"
    fig.savefig(out, dpi=150)
    print(f"  saved -> {out.relative_to(it.BASE)}")


if __name__ == "__main__":
    main()

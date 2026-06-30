"""
slice_tube.py -- slice a LiDAR tube export in the vertical plane of a gravity line
and write the cross-section outline + area for the Grav inversion overlay.

The gravity profile crosses the tube obliquely; per the Grav session's request we
slice ALONG the line's vertical plane (a thin slab around it), NOT perpendicular to
the tube axis, so the LiDAR outline is "stretched" the same way the 2-D gravity
model is. We project the slab points onto (dist-along-line, absolute elevation),
then trace a closed outline by angular binning about the centroid (median wall
radius per bin -- robust to the slab's scatter) and integrate its area (shoelace).

Output: Code/Grav/Inversion/lidar_line{N}.csv  with columns  x,z
  x = distance from the dist=0 end of the gravity line (m)
  z = absolute REGCAN95 orthometric elevation (m)
plus the printed cross-sectional area (m^2).

Slice geometry (EPSG:4083 / REGCAN95 UTM 28N), from QandA.md:
  Line 3: origin (650620.7, 3227095.7), azimuth 353.6 deg
  Line 5: origin (649766.8, 3227446.2), azimuth 358.3 deg

Run: python slice_tube.py --line 5 --xyz "PATH/to/export.txt" [--halfwidth 1.0]
"""
import argparse
import numpy as np
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
GRAV_INV = BASE / "Code/Grav/Inversion"

LINE_GEOM = {
    3: dict(origin=(650620.7, 3227095.7), azimuth=353.6),
    5: dict(origin=(649766.8, 3227446.2), azimuth=358.3),
}


def project_to_line(E, N, origin, azimuth_deg):
    """Project E,N onto the line: along-line dist (u, from north-azimuth) and
    perpendicular offset (n)."""
    O = np.asarray(origin, float)
    az = np.deg2rad(azimuth_deg)
    u = np.array([np.sin(az), np.cos(az)])     # along-line unit (azimuth from N)
    nrm = np.array([u[1], -u[0]])              # perpendicular unit
    rel = np.column_stack([E, N]) - O
    return rel @ u, rel @ nrm


def outline_by_angle(x, z, nbins=180):
    """Trace a closed outline of a ring of (x,z) wall points: for each angular bin
    about the centroid take the median radius (the wall), return ordered polygon
    vertices (x,z). Robust to scatter from the finite slab thickness."""
    cx, cz = np.median(x), np.median(z)
    th = np.arctan2(z - cz, x - cx)
    r = np.hypot(x - cx, z - cz)
    edges = np.linspace(-np.pi, np.pi, nbins + 1)
    bx, bz = [], []
    for i in range(nbins):
        m = (th >= edges[i]) & (th < edges[i + 1])
        if not m.any():
            continue
        rb = np.median(r[m])                   # wall radius in this sector
        tb = 0.5 * (edges[i] + edges[i + 1])
        bx.append(cx + rb * np.cos(tb))
        bz.append(cz + rb * np.sin(tb))
    return np.array(bx), np.array(bz)


def polygon_area(x, z):
    """Shoelace area of a closed polygon (vertices in order)."""
    return 0.5 * abs(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--line", type=int, required=True, choices=sorted(LINE_GEOM))
    p.add_argument("--xyz", required=True, help="ASCII export: cols 0,1,2 = E,N,Z")
    p.add_argument("--halfwidth", type=float, default=1.0,
                   help="slab half-width about the line plane (m)")
    p.add_argument("--nbins", type=int, default=180)
    p.add_argument("--no-write", action="store_true",
                   help="report only, do not write the CSV")
    args = p.parse_args()

    geom = LINE_GEOM[args.line]
    d = np.loadtxt(args.xyz, usecols=(0, 1, 2))
    dist, perp = project_to_line(d[:, 0], d[:, 1], geom["origin"], geom["azimuth"])
    m = np.abs(perp) < args.halfwidth
    x, z = dist[m], d[m, 2]
    print(f"  Line {args.line}: {m.sum()} pts in +/-{args.halfwidth} m slab")
    print(f"    dist [{x.min():.1f}, {x.max():.1f}] m  (centre {np.median(x):.1f} m)")
    print(f"    elev [{z.min():.1f}, {z.max():.1f}] m REGCAN95")

    ox, oz = outline_by_angle(x, z, args.nbins)
    area = polygon_area(ox, oz)
    print(f"    cross-sectional AREA = {area:.0f} m^2  ({len(ox)} outline vertices)")

    if not args.no_write:
        # close the polygon for a clean drawn loop
        cx = np.append(ox, ox[0])
        cz = np.append(oz, oz[0])
        out = GRAV_INV / f"lidar_line{args.line}.csv"
        np.savetxt(out, np.column_stack([cx, cz]), delimiter=",",
                   header="x,z", comments="", fmt="%.4f")
        print(f"    wrote -> {out.relative_to(BASE)}")


if __name__ == "__main__":
    main()

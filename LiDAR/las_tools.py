"""
las_tools.py -- minimal, dependency-light readers for the La Corona LiDAR exports.

Why raw byte reading: the site clouds (cloud 1..4 in LaCorona.bin) carry duplicate
"C2C absolute distances" scalar fields that break laspy's full point parsing. We only
need X/Y/Z and the "Original cloud index" scalar field, so we read those directly from
the LAS point records by byte offset and apply the header scale/offset.

CRS of the data: EPSG:4083 (REGCAN95 / UTM zone 28N).

Usage:
    from las_tools import read_las_xyz_oci
    x, y, z, oci = read_las_xyz_oci("path/to/cloud.las")          # full res
    x, y, z, oci = read_las_xyz_oci("path/to/cloud.las", step=10) # every 10th point
"""
import struct
import numpy as np

try:
    import laspy  # only used to locate the Original-cloud-index byte offset
except ImportError:
    laspy = None


def _oci_offset(path):
    """Return (offset_within_extra_block, extra_block_size) for 'Original cloud index',
    or (None, extra_block_size) if absent. Requires laspy for header parsing."""
    if laspy is None:
        return None, 0
    with laspy.open(path) as fh:
        extra = [d for d in fh.header.point_format.dimensions if not d.is_standard]
    eblk = sum(d.num_bytes for d in extra)
    cum = 0
    for d in extra:
        if d.name.strip() == "Original cloud index":
            return cum, eblk
        cum += d.num_bytes
    return None, eblk


def read_las_xyz_oci(path, step=1, max_points=None):
    """Read X,Y,Z (scaled, in CRS units) and the Original cloud index (int) from a LAS.

    step: take every Nth point. max_points: if set, overrides step to roughly cap output.
    Returns (x, y, z, oci) as numpy arrays; oci is None if the field is absent.
    Works for LAS 1.2-1.4 point records (X,Y,Z are the first 3 int32 fields).
    """
    off_oci, eblk = _oci_offset(path)
    with open(path, "rb") as fb:
        b = fb.read()
    off_pts = int.from_bytes(b[96:100], "little")
    pt_len = int.from_bytes(b[105:107], "little")
    n = int.from_bytes(b[107:111], "little")
    sx, sy, sz = struct.unpack_from("<3d", b, 131)
    ox, oy, oz = struct.unpack_from("<3d", b, 155)
    if max_points is not None and n > max_points:
        step = max(1, n // max_points)
    raw = np.frombuffer(b, np.uint8, count=n * pt_len, offset=off_pts).reshape(n, pt_len)
    if step > 1:
        raw = raw[::step]
    x = raw[:, 0:4].copy().view(np.int32).ravel() * sx + ox
    y = raw[:, 4:8].copy().view(np.int32).ravel() * sy + oy
    z = raw[:, 8:12].copy().view(np.int32).ravel() * sz + oz
    oci = None
    if off_oci is not None:
        base = pt_len - eblk + off_oci
        oci = np.round(raw[:, base:base + 4].copy().view(np.float32).ravel()).astype(int)
    return x, y, z, oci


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        x, y, z, oci = read_las_xyz_oci(p, max_points=500000)
        print(p)
        print(f"  n(read)={len(x)} X[{x.min():.1f},{x.max():.1f}] "
              f"Y[{y.min():.1f},{y.max():.1f}] Z[{z.min():.1f},{z.max():.1f}]")
        if oci is not None:
            u, c = np.unique(oci, return_counts=True)
            print("  Original cloud index counts:", dict(zip(u.tolist(), c.tolist())))

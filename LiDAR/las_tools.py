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
            # read_las_xyz_oci below reinterprets these 4 bytes as float32 (the format
            # every cloud in this project has used) -- if a future export stores the
            # index at a different width, fail loud here instead of silently misreading
            # the wrong number of bytes as the field.
            assert d.num_bytes == 4, (
                f"'Original cloud index' is {d.num_bytes} bytes wide in {path}, "
                f"expected 4 (float32). read_las_xyz_oci's np.float32 view assumes 4 -- "
                f"update it before trusting oci from this file.")
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
    assert b[0:4] == b"LASF", (
        f"{path}: no LASF magic at byte 0 -- not a LAS file, or this reader's fixed "
        f"header byte offsets (assumed LAS 1.2-1.4 public header block) do not apply.")
    fmt_id = b[104]
    off_pts = int.from_bytes(b[96:100], "little")
    pt_len = int.from_bytes(b[105:107], "little")
    n = int.from_bytes(b[107:111], "little")
    sx, sy, sz = struct.unpack_from("<3d", b, 131)
    ox, oy, oz = struct.unpack_from("<3d", b, 155)
    # X,Y,Z are the first 3 int32 fields in every standard LAS point format (0-10), so
    # fmt_id itself does not gate correctness here -- but pt_len and n do, since a wrong
    # header offset (e.g. a non-LAS-1.2-1.4 file this reader was never meant to handle)
    # would otherwise silently misread point boundaries rather than erroring.
    assert pt_len >= 12, (
        f"{path}: point record length {pt_len} B is smaller than the 12 B needed for "
        f"X,Y,Z alone (point format id {fmt_id}) -- header offsets look wrong for this file.")
    assert off_pts + n * pt_len <= len(b), (
        f"{path}: header claims {n} points x {pt_len} B starting at byte {off_pts}, "
        f"which needs {off_pts + n * pt_len} B but the file is only {len(b)} B -- "
        f"header offsets look wrong for this file (format id {fmt_id}).")
    if off_oci is not None:
        assert off_oci + 4 <= eblk, (
            f"{path}: 'Original cloud index' offset {off_oci} + 4 B overruns the "
            f"{eblk} B extra-dimensions block -- header parsing disagrees with the "
            f"raw record layout.")
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

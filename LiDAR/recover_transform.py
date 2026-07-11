"""
recover_transform.py -- recover the net rigid 4x4 of a moved LiDAR cloud from a
before/after pair of CloudCompare ASCII exports.

The Jameo de la Gente re-registration moved idx5 (Tunnel) and idx6 (Jameo) by a
sequence of coarse + ICP steps whose logged matrices live in mixed CC frames and
cannot be safely multiplied. Instead we recover ONE net 4x4 directly from the
point positions: before (session-start) -> after (final).

CC ASCII exports carry the per-point scalar fields unchanged through a rigid move,
so a point's scalar signature is an exact identity key linking the same physical
point in the two files (robust to edge-cropping / reordering / subsetting between
them). We match on those columns, then solve the rigid transform by Kabsch.

Columns (CC ASCII): 0,1,2 = X,Y,Z ; 6 = Original cloud index ; 7.. = scalar fields.
We key on a few scalar columns (default 7,8,9,10,11 -- C2C distance + components),
which are unique per point and invariant under the move.

Usage:
  python recover_transform.py --before Gente_jameo_before.txt --after Gente_jameo_after.txt --label Jameo
"""
import argparse
import numpy as np


def kabsch(P, Q):
    """Rigid transform mapping P -> Q (no scaling). Returns (R, t, rms)."""
    cp, cq = P.mean(0), Q.mean(0)
    H = (P - cp).T @ (Q - cq)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1, 1, d])
    R = Vt.T @ D @ U.T
    t = cq - R @ cp
    rms = np.sqrt(np.mean(np.sum((Q - (P @ R.T + t)) ** 2, axis=1)))
    return R, t, rms


def load(path, keycols):
    raw = np.loadtxt(path)
    xyz = raw[:, 0:3]
    key = raw[:, keycols]
    return xyz, key


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--keycols", type=int, nargs="+", default=[7, 8, 9, 10, 11])
    p.add_argument("--round", type=int, default=4, help="decimals to round keys")
    args = p.parse_args()

    bx, bk = load(args.before, args.keycols)
    ax, ak = load(args.after, args.keycols)

    # hash scalar signatures -> match same physical point in both files
    def keymap(keys):
        d = {}
        for i, k in enumerate(np.round(keys, args.round)):
            d[tuple(k)] = i               # last wins on the rare dup; fine
        return d
    bmap = keymap(bk)
    bi, ai = [], []
    for j, k in enumerate(np.round(ak, args.round)):
        i = bmap.get(tuple(k))
        if i is not None:
            bi.append(i); ai.append(j)
    bi, ai = np.array(bi), np.array(ai)
    P, Q = bx[bi], ax[ai]
    print(f"  {args.label}: {len(P)} matched pts "
          f"(before {len(bx)}, after {len(ax)})")

    R, t, rms = kabsch(P, Q)
    M = np.eye(4); M[:3, :3] = R; M[:3, 3] = t
    ang = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
    tilt_x = np.degrees(np.arctan2(-R[2, 1], R[2, 2]))
    tilt_y = np.degrees(np.arctan2(R[2, 0], np.hypot(R[2, 1], R[2, 2])))

    print(f"  Kabsch fit RMS = {rms*100:.2f} cm  over {len(P)} pairs")
    print(f"  net translation (m): ({t[0]:+.3f}, {t[1]:+.3f}, {t[2]:+.3f})  "
          f"|horiz| = {np.hypot(t[0], t[1]):.3f}")
    print(f"  Z-rotation (about vertical): {ang:+.4f} deg")
    print(f"  residual tilt: about-E {tilt_x:+.3f} deg, about-N {tilt_y:+.3f} deg")
    print("  net 4x4 (before -> after, true EPSG:4083 coords):")
    for r in M:
        print("    " + "  ".join(f"{v: .9f}" for v in r))


if __name__ == "__main__":
    main()

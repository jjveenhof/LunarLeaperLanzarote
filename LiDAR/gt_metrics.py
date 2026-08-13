"""gt_metrics.py -- registration-quality metrics for the two measured jameos, on the
three beats used in the thesis:

  [1] HOW FAR OFF   the correction the ground-truth tunnel underwent (Z-rotation +
                    per-point displacement); captures Puerta Falsa's ~51 deg swing and
                    La Gente's ~7 m shift on one footing.
  [2] TIE TO CONTROL  residual of the registered cloud to the independent survey
                    (RTK rim at PF; drone surface + RTK datum at La Gente).
  [3] INTERNAL FIT  surface agreement of the tunnel to the cloud it locked onto.

Also generates tab:lidar-vertical-budget (main.tex) -- the VERTICAL BUDGET print block
per site: the per-link |median dz| along the registration chain (tunnel -> bridge ->
reference/surface -> RTK) plus their RSS. This is the ONLY calculated table LiDAR owns;
its 7 cells (3 links + RSS, both sites) all trace to this script's own output, so it
cannot go stale silently -- re-run and compare against main.tex if in doubt.

Cloud roles:
  tunnel (ground truth) = tube idx1 (PF) / Tunnel idx5 (La Gente)  -- what we slice.
  reference it locked onto = stitch idx2 (PF) / Jameo idx6 (La Gente).
  independent control = RTK rim (PF); drone surface, itself on RTK, (La Gente).

Metric notes (why the definitions are what they are):
  * A 3-D nearest-neighbour to a broad/sparse surface is blind to horizontal slides and
    carries a horizontal point-spacing penalty. So:
      - "how far off" is measured as the actual point displacement (rotation-aware),
        not a surface NN;
      - the drone<->RTK datum tie is measured as a VERTICAL offset (RTK minus a local
        plane fit through the drone), which removes the ~0.7 m spacing floor that the
        plain 3-D NN reports.
  * Frame-safe transforms: PF tube before/after share point order (verified by a rigid
    fit RMS ~ 0); La Gente clouds are matched by their invariant scalar signature
    (as in recover_transform.py) then fit with Kabsch.

Run with the env python (see Code/README.md); reads the exported clouds under
'LiDAR La Corona/Reregistered clouds' and '.../Clouds to reconstruct transformations'.
"""
import os
import sys
import numpy as np
from numpy.linalg import lstsq
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # Code/LiDAR
import verify_alignment as V
from recover_transform import kabsch

# Point clouds are DATA, outside the Code/ git repo: derive the project root from this
# file's location (Code/LiDAR/ -> Code/ -> project root) rather than hardcoding it, so
# the project folder can be moved or handed over without editing source.
DOCS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "LiDAR La Corona")
REREG = os.path.join(DOCS, "Reregistered clouds")
RECON = os.path.join(DOCS, "Clouds to reconstruct transformations")


# --------------------------------------------------------------------------- io
def load_cols(path, cols):
    """Selected columns from a CloudCompare ASCII export ('//' header + count line)."""
    rows = []
    for ln in open(path):
        ln = ln.strip()
        if not ln or ln.startswith("//"):
            continue
        p = ln.split()
        if len(p) < max(cols) + 1:
            continue
        try:
            rows.append([float(p[c]) for c in cols])
        except ValueError:
            continue
    return np.asarray(rows)


def nnd(P, Q):
    d, _ = cKDTree(Q).query(P)
    return d


# ---------------------------------------------------------------------- beats
def beat1_how_far_off(name, before_xyz, after_xyz, R, t):
    ang = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
    d = np.linalg.norm(before_xyz @ R.T + t - before_xyz, axis=1)
    print(f"  [1] HOW FAR OFF  ({name})")
    print(f"      Z-rotation {ang:+.2f} deg, centroid shift "
          f"{np.linalg.norm(after_xyz.mean(0) - before_xyz.mean(0)):.2f} m")
    print(f"      per-point displacement: median {np.median(d):.2f} m, "
          f"p95 {np.percentile(d, 95):.1f} m, max {d.max():.1f} m")


def beat3_internal_fit(name, mover_a, ref_a, thr=1.0):
    d = nnd(mover_a, ref_a)
    do = d[d < thr]
    print(f"  [3] INTERNAL FIT ({name}, overlap<{thr:g}m, {100*(d<thr).mean():.0f}% of pts)")
    print(f"      median {np.median(do):.3f} m, mean {do.mean():.3f} m, "
          f"RMS {np.sqrt((do**2).mean()):.3f} m")


def vertical_budget(site, links):
    """Print the per-link |median dz| chain + its RSS -- generates
    tab:lidar-vertical-budget (main.tex) so the table cannot go stale silently.
    links: list of (label, dz array) in registration order (tunnel -> ... -> RTK)."""
    print(f"  VERTICAL BUDGET ({site}) -- generates tab:lidar-vertical-budget")
    medians = []
    for label, dz in links:
        med = np.median(np.abs(dz))
        medians.append(med)
        print(f"      {label:<22} |median dz| = {med:.3f} m  (bias {np.median(dz):+.3f} m, n={len(dz)})")
    rss = np.sqrt(np.sum(np.square(medians)))
    print(f"      {'combined (RSS)':<22} = {rss:.3f} m")


def vertical_offset_to_plane(query_xyz, surface_xyz, radius=5.0, minpts=6):
    """Signed vertical distance query_z - (local plane through surface points within
    `radius`). Removes the horizontal-spacing floor of a plain 3-D NN.

    ONLY valid where `surface_xyz` is a locally smooth, near-horizontal SHEET (the La
    Gente drone ground surface). Do NOT use it against a cave edge/wall: at the Puerta
    Falsa jameo the RTK trace is the lip of a vertical shaft, the 'nearby' cave points
    are the shaft walls, and the plane fit is meaningless (returns ~4-5 m). For a sharp
    feature like that, use vertical_offset_at_feature() instead."""
    tree = cKDTree(surface_xyz[:, :2])
    resid = []
    for p in query_xyz:
        idx = tree.query_ball_point(p[:2], radius)
        if len(idx) < minpts:
            continue
        S = surface_xyz[idx]
        c, *_ = lstsq(np.c_[S[:, 0], S[:, 1], np.ones(len(S))], S[:, 2], rcond=None)
        resid.append(p[2] - (c[0] * p[0] + c[1] * p[1] + c[2]))
    return np.asarray(resid)


def vertical_offset_at_feature(query_xyz, feature_xyz):
    """Vertical component of the nearest-neighbour offset from each query point to a
    sharp feature (e.g. RTK rim trace -> LiDAR shaft edge). Use where no local plane
    exists. The 3-D NN there is dominated by along-feature point spacing, so its
    VERTICAL component is the honest datum residual."""
    d, i = cKDTree(feature_xyz).query(query_xyz)
    dz = query_xyz[:, 2] - feature_xyz[i, 2]
    return d, dz


def nn_vertical(P, Q, thr=1.0):
    """Vertical + horizontal components of the nearest-neighbour offset from mover P
    to reference Q, restricted to the genuine-overlap points (3-D NN < thr). Used for
    the registration-chain links in tab:lidar-vertical-budget where neither a local
    plane (vertical_offset_to_plane) nor a single sharp feature
    (vertical_offset_at_feature) applies -- both P and Q are dense point clouds."""
    d, i = cKDTree(Q).query(P)
    ov = d < thr
    dz = P[ov, 2] - Q[i[ov], 2]
    dh = np.hypot(P[ov, 0] - Q[i[ov], 0], P[ov, 1] - Q[i[ov], 1])
    return dz, dh, ov.mean()


# ---------------------------------------------------------------- Puerta Falsa
def puerta_falsa():
    print("#" * 74 + "\n# PUERTA FALSA\n" + "#" * 74)
    after, _ = V.load_asc()
    before = V.load_asc_before()
    A = {l: P for l, P, _ in after}
    B = {l: P for l, P, _ in before}

    bt, at = B["tube"], A["tube"]
    R, t, rms = kabsch(bt, at)          # same-order pairing; RMS ~0 confirms it
    print(f"  (tube order check: rigid-fit RMS on paired rows = {rms:.4f} m -> "
          f"{'OK' if rms < 0.1 else 'SCRAMBLED, do not trust'})")
    beat1_how_far_off("tube idx1", bt, at, R, t)

    rtk = load_cols(os.path.join(REREG, "PuertaFalsa_edge_RTK.xyz"), [0, 1, 2])
    cave = np.vstack([A["ref"], A["stitch"], A["tube"]])
    d, dz_rtk = vertical_offset_at_feature(rtk, cave)   # rim is a shaft edge, not a plane
    print(f"  [2] TIE TO CONTROL (RTK rim {len(rtk)} pts -> LiDAR shaft edge)")
    print(f"      3-D NN: median {np.median(d):.3f} m (mostly along-rim spacing)")
    print(f"      vertical: |median| {np.median(np.abs(dz_rtk)):.3f} m, "
          f"bias {np.median(dz_rtk):+.3f} m, std {dz_rtk.std():.3f} m")

    beat3_internal_fit("tube->stitch", A["tube"], A["stitch"])

    # tab:lidar-vertical-budget: the registration chain tunnel -> bridge -> reference
    # -> RTK, one vertical-dz link at a time (green/yellow/blue = tube/stitch/ref, the
    # figure-legend colours). tube->stitch and blue->RTK reuse the beats above (same
    # NN definitions); stitch->blue is the one link no other beat computes.
    dz_ts, _, _ = nn_vertical(A["tube"], A["stitch"])
    dz_sb, _, _ = nn_vertical(A["stitch"], A["ref"])
    vertical_budget("Puerta Falsa", [
        ("tube -> stitch (green->yellow)", dz_ts),
        ("stitch -> blue (yellow->blue)",  dz_sb),
        ("blue -> RTK (blue->RTK)",        dz_rtk),
    ])


# ------------------------------------------------------------- Jameo de la Gente
def la_gente():
    print("#" * 74 + "\n# JAMEO DE LA GENTE\n" + "#" * 74)
    # [1] tunnel before -> after via invariant scalar-signature match, then Kabsch
    tb = load_cols(os.path.join(RECON, "Gente_tunnel_before.txt"), [0, 1, 2, 7, 8, 9, 10, 11])
    ta = load_cols(os.path.join(REREG, "Gente_tunnel_after.txt"), [0, 1, 2, 7, 8, 9, 10, 11])
    bmap = {tuple(np.round(k, 4)): i for i, k in enumerate(tb[:, 3:8])}
    bi, ai = [], []
    for j, k in enumerate(np.round(ta[:, 3:8], 4)):
        i = bmap.get(tuple(k))
        if i is not None:
            bi.append(i); ai.append(j)
    bxyz, axyz = tb[np.array(bi), :3], ta[np.array(ai), :3]
    R, t, rms = kabsch(bxyz, axyz)
    print(f"  (matched {len(bxyz)} tunnel pts; rigid-fit RMS = {rms*100:.3f} cm)")
    beat1_how_far_off("Tunnel idx5", bxyz, axyz, R, t)

    # [2] chain: jameo <- drone (surface NN) <- RTK (vertical datum offset)
    after_g, _, _, _ = V.load_gente()
    Ag = {l: P for l, P, _ in after_g}
    print("  [2] TIE TO CONTROL (chain: jameo <- drone <- RTK; RTK does not reach jameo)")
    jam, drone = Ag["Jameo"], Ag["Topo drone"]
    e0, e1 = np.percentile(jam[:, 0], [1, 99]) + [-3, 3]
    n0, n1 = np.percentile(jam[:, 1], [1, 99]) + [-3, 3]
    dfp = drone[(drone[:, 0] >= e0) & (drone[:, 0] <= e1)
                & (drone[:, 1] >= n0) & (drone[:, 1] <= n1)]
    dj = nnd(dfp, jam)
    print(f"      drone -> jameo surface (over footprint): median {np.median(dj):.2f} m "
          f"(n={len(dj)})")
    # drone <-> RTK: VERTICAL offset (plain 3-D NN is spacing-floored ~0.7 m)
    dz_rtk = {}
    for lab in ("Gente_rtk_L5.xyz", "Gente_rtk_L2.xyz"):
        rtk = load_cols(os.path.join(REREG, lab), [0, 1, 2])
        r = vertical_offset_to_plane(rtk, drone)
        dz_rtk[lab[10:12]] = r
        print(f"      RTK {lab[10:12]} vs drone plane (vertical): "
              f"median {np.median(r):+.3f} m, |median| {np.median(np.abs(r)):.3f} m, "
              f"std {r.std():.3f} m  (n={len(r)}/{len(rtk)})")

    beat3_internal_fit("Tunnel->Jameo", Ag["Tunnel"], Ag["Jameo"])

    # tab:lidar-vertical-budget: the registration chain tunnel -> bridge -> surface ->
    # RTK (green/yellow/blue = Tunnel/Jameo/drone, the figure-legend colours). L5's RTK
    # tie is used for the third link -- L5 is this site's gravity line; L2 above is a
    # secondary cross-check, not part of the chain the L5 cross-section depends on.
    dz_tj, _, _ = nn_vertical(Ag["Tunnel"], Ag["Jameo"])
    dz_jd, _, _ = nn_vertical(dfp, Ag["Jameo"])
    vertical_budget("La Gente (L5)", [
        ("Tunnel -> Jameo (green->yellow)", dz_tj),
        ("Jameo -> drone (yellow->blue)",   dz_jd),
        ("drone -> RTK L5 (blue->RTK)",     dz_rtk["L5"]),
    ])


if __name__ == "__main__":
    puerta_falsa()
    print()
    la_gente()

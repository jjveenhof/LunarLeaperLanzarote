"""
verify_alignment_io.py -- data loading and residual statistics for the Puerta Falsa /
La Gente re-registration checks. Split out of verify_alignment.py (phase-2 refactor,
2026-08-11) so the loaders + residual stats can be read/extended without wading through
the ~220 lines of multi-panel plotting code that consume them; see verify_alignment.py
for the CLI and figure generation.

Three cloud sets, three loader groups:
  * ASC (Puerta Falsa, default mode): the three re-aligned CloudCompare ASCII exports
    (PF_ref_after / PF_stitch_after / PF_tube_after) plus the misaligned 'before' crop
    and the RTK rim datum.
  * LAS (baseline / diagnostic): a single LAS holding all subsets with an
    Original_cloud_index scalar field, read via las_tools (laspy cannot parse these
    clouds' points).
  * GENTE (Jameo de la Gente): corrected Tunnel/Jameo + drone surface + RTK lines,
    each with a 'before' (pre-move) counterpart for the movers.

CRS: EPSG:4083 (REGCAN95 / UTM zone 28N).
Baseline (pre-alignment) idx2->idx0 residual was ~ mean 8.7 m / median 5.6 m.
"""
import os
import numpy as np

# Point clouds are DATA: they live outside the Code/ git repo, in the project root two
# levels up from this file (Code/LiDAR/ -> Code/ -> project root). Derived, never
# hardcoded, so the project folder can be moved or handed over without editing source.
_LIDAR_DATA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "LiDAR La Corona")

# --- ASC mode: the three aligned exports -------------------------------------
ASC_DIR = os.path.join(_LIDAR_DATA, "Reregistered clouds")
ASC_FILES = [  # (label, filename, colour)
    ("ref",    "PF_ref_after.txt",    "tab:blue"),
    ("stitch", "PF_stitch_after.txt", "gold"),
    ("tube",   "PF_tube_after.txt",   "green"),
]
ASC_PAIRS = [("stitch", "ref"), ("tube", "stitch")]   # (mover, reference) for residuals

# --- LAS mode: subsets by Original_cloud_index -------------------------------
LAS_NAMES = {0: "blue idx0", 1: "dark green idx1", 2: "light green idx2"}
LAS_COLS  = {0: "tab:blue", 1: "darkgreen", 2: "limegreen"}
LAS_PAIRS = [("light green idx2", "blue idx0"), ("dark green idx1", "light green idx2")]

# --- GENTE mode: Jameo de la Gente re-georef check ---------------------------
# Corrected LiDAR (Tunnel idx5 + Jameo idx6) vs the RTK surface datum (+ optional
# corrected drone crop). Unlike Puerta Falsa (internal blue-reference), this site
# was fit to EXTERNAL truth, so the check is: Tunnel<->Jameo agree at the pit
# throat, and both sit correctly under the RTK surface / on the drone.
_DOCS = _LIDAR_DATA
GENTE_FILES = [  # (label, path, colour, is_sparse)
    # role-based colours, matching the Puerta Falsa check (truth<-bridge<-mover):
    #   drone surface = blue  (truth,  like PF_ref)
    #   Jameo         = gold  (bridge, like PF_stitch)
    #   Tunnel        = green (mover,  like PF_tube)
    ("Jameo",       _DOCS + r"\Clouds to reconstruct transformations\Gente_jameo_after.txt",
     "gold", False),
    ("Tunnel",      _DOCS + r"\Reregistered clouds\Gente_tunnel_after.txt",
     "green", False),
    ("Topo drone",  _DOCS + r"\Reregistered clouds\Gente_topo.xyz",
     "tab:blue", False),     # optional -- skipped if absent
    ("RTK L5",      _DOCS + r"\Reregistered clouds\Gente_rtk_L5.xyz", "k", True),
    ("RTK L2",      _DOCS + r"\Reregistered clouds\Gente_rtk_L2.xyz", "0.35", True),
]
GENTE_PAIRS = [("Tunnel", "Jameo"),             # internal: pit-throat overlap
               ("Topo drone", "Jameo"),         # surface fit: jameo vs drone it was
                                                 # registered to (dense ref = real sep)
               ("RTK L5", "Topo drone"),        # datum: drone should sit on RTK
               ("RTK L2", "Topo drone")]        # (only run if drone present)
GENTE_BBOX = (649575.0, 649875.0, 3227405.0, 3227665.0)   # E_min,E_max,N_min,N_max --
# focuses the check on the pit/jameo/RTK zone (the full tunnel is ~450 m long)
GENTE_CMAP_LABELS = set()   # (elevation-cmap layers; unused -- flat role colours)
GENTE_BEFORE_PATHS = {      # 'before' (pre-Jameo-move) positions of the movers
    "Jameo":  _DOCS + r"\Clouds to reconstruct transformations\Gente_jameo_before.txt",
    "Tunnel": _DOCS + r"\Clouds to reconstruct transformations\Gente_tunnel_before.txt",
}   # fixed clouds (drone, RTK) are identical before/after in plan view


def load_asc_xyz(path):
    """X Y Z (first three columns) from a CloudCompare ASCII export
    ('//' header line, then a lone point-count line, then data)."""
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            parts = line.split()
            if len(parts) < 3:        # the lone point-count line
                continue
            try:
                rows.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError:
                continue
    a = np.asarray(rows)
    return a[:, :3]


def load_asc():
    layers = []
    for label, fn, col in ASC_FILES:
        P = load_asc_xyz(os.path.join(ASC_DIR, fn))
        layers.append((label, P, col))
    return layers, ASC_PAIRS


# Puerta Falsa RTK truth (sparse), added to both before & after plots as the datum.
ASC_RTK = [("RTK rim", "PuertaFalsa_edge_RTK.xyz", "k")]


def load_asc_rtk():
    out = []
    for label, fn, col in ASC_RTK:
        p = os.path.join(ASC_DIR, fn)
        if not os.path.exists(p):
            print(f"  (skip missing {label}: {fn})"); continue
        out.append((label, np.atleast_2d(load_asc_xyz(p)), col))
    return out


# Puerta Falsa 'before': the misaligned originals, one crop split by Original cloud
# index (col 6) -> ref(idx0)/stitch(idx2)/tube(idx1), same labels/colours as load_asc.
ASC_BEFORE_FILE = os.path.join(ASC_DIR, "PF_junction_before.txt")
ASC_BEFORE_IDX = [(0, "ref", "tab:blue"), (2, "stitch", "gold"), (1, "tube", "green")]


def load_asc_before():
    """Misaligned idx0/1/2 for the Puerta Falsa before/after, or None if absent."""
    if not os.path.exists(ASC_BEFORE_FILE):
        return None
    rows = []
    for ln in open(ASC_BEFORE_FILE):
        p = ln.split()
        if len(p) < 7:
            continue
        try:
            rows.append([float(x) for x in p[:7]])
        except ValueError:
            continue
    a = np.array(rows)
    layers = []
    for idx, label, col in ASC_BEFORE_IDX:
        m = np.round(a[:, 6]) == idx
        if m.any():
            layers.append((label, a[m, :3], col))
    return layers


def load_las(path, indices=(0, 1, 2), step=1):
    from las_tools import read_las_xyz_oci
    x, y, z, oci = read_las_xyz_oci(path, step=step)
    layers = []
    for k in indices:
        m = (oci == k) if oci is not None else np.ones(len(x), bool)
        if m.sum() == 0:
            continue
        layers.append((LAS_NAMES.get(k, str(k)),
                       np.c_[x[m], y[m], z[m]], LAS_COLS.get(k, "k")))
    return layers, LAS_PAIRS


def _load_bbox(label, path, col):
    """Load X,Y,Z of one cloud, cropped to GENTE_BBOX. None if missing/empty."""
    if not os.path.exists(path):
        print(f"  (skip missing {label}: {os.path.basename(path)})"); return None
    P = np.loadtxt(path, usecols=(0, 1, 2))
    e0, e1, n0, n1 = GENTE_BBOX
    m = (P[:, 0] >= e0) & (P[:, 0] <= e1) & (P[:, 1] >= n0) & (P[:, 1] <= n1)
    P = P[m]
    if len(P) == 0:
        print(f"  (skip {label}: no points in bbox)"); return None
    return (label, P, col)


def load_gente():
    """Corrected 'after' clouds + their 'before' (pre-move) positions + RTK datum.
    Returns (after, before, pairs, sparse). Fixed clouds (drone, RTK) are the same
    in both lists; only the movers (Jameo, Tunnel) differ (before = Original*)."""
    after, before, sparse = [], [], set()
    for label, path, col, is_sparse in GENTE_FILES:
        a = _load_bbox(label, path, col)
        if a is None:
            continue
        after.append(a)
        if is_sparse:
            sparse.add(label)
        b = _load_bbox(label, GENTE_BEFORE_PATHS.get(label, path), col)
        before.append(b if b is not None else a)
    have = {l for l, _, _ in after}
    pairs = [(m, r) for m, r in GENTE_PAIRS if m in have and r in have]
    return after, before, pairs, sparse


def residual(P, Q, label):
    """NN distance from mover P to reference Q, characterised by the genuine-overlap
    points (within small thresholds) plus low percentiles. Robust when P extends
    well past Q (those far points are not meant to overlap)."""
    try:
        from scipy.spatial import cKDTree
    except ImportError:
        print("scipy not available; skipping residual"); return
    dist, _ = cKDTree(Q).query(P)
    for thr in (0.3, 0.5, 1.0):
        sel = dist <= thr
        m = dist[sel].mean() if sel.any() else float("nan")
        r = np.sqrt(np.mean(dist[sel] ** 2)) if sel.any() else float("nan")
        print(f"{label:>18}  within {thr:>3} m: {100*sel.mean():5.1f}% of pts, "
              f"mean NN={m:.3f} m, RMS={r:.3f} m")
    p = np.percentile(dist, [5, 10, 20])
    print(f"{label:>18}  percentiles  p5={p[0]:.3f} p10={p[1]:.3f} p20={p[2]:.3f} m  (n={len(P)})\n")

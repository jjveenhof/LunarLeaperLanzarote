"""
verify_alignment.py -- before/after checks for the La Corona junction alignment.

Two input modes:
  * ASC (default): the three re-aligned CloudCompare ASCII exports
    (ReferenceCloud / StitchMoved / TubeMoved), already in the aligned frame.
        python verify_alignment.py
  * LAS (baseline): a single LAS holding all subsets with an Original_cloud_index
    scalar field, read via las_tools (laspy cannot parse these clouds' points).
        python verify_alignment.py --las path/to/cloud.las

Outputs, for whichever subsets are present:
  * nearest-neighbour residuals between the moving subset and its reference, reported
    by distance threshold (isolates the genuine overlap when one cloud extends past
    the other) and low percentiles;
  * a 2x2 figure: TOP (XY) plan, projected SIDE (E-Z), and two THIN-SLICE
    cross-sections (E-Z at a fixed Northing, N-Z at a fixed Easting) that reveal tilt.

CRS: EPSG:4083 (REGCAN95 / UTM zone 28N).
Baseline (pre-alignment) idx2->idx0 residual was ~ mean 8.7 m / median 5.6 m.
"""
import os
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --- ASC mode: the three aligned exports -------------------------------------
ASC_DIR = (r"C:\Users\jj_ve\OneDrive - Delft University of Technology\Documents"
           r"\Thesis Lunar Leaper\LiDAR La Corona\Reregistered clouds")
ASC_FILES = [  # (label, filename, colour)
    ("ref",    "ReferenceCloud.txt", "tab:blue"),
    ("stitch", "StitchMoved.txt",    "gold"),
    ("tube",   "TubeMoved.txt",      "green"),
]
ASC_PAIRS = [("stitch", "ref"), ("tube", "stitch")]   # (mover, reference) for residuals

# --- LAS mode: subsets by Original_cloud_index -------------------------------
LAS_NAMES = {0: "blue idx0", 1: "dark green idx1", 2: "light green idx2"}
LAS_COLS  = {0: "tab:blue", 1: "darkgreen", 2: "limegreen"}
LAS_PAIRS = [("light green idx2", "blue idx0"), ("dark green idx1", "light green idx2")]

# --- cross-section cut locations (EPSG:4083) ---------------------------------
SLICE_N = 3227163.0   # E-Z section: keep points within +-SLICE_HALF of this Northing
SLICE_E = 650645.0    # N-Z section: keep points within +-SLICE_HALF of this Easting
SLICE_HALF = 1.5      # slab half-thickness (m)

# --- GENTE mode: Jameo de la Gente re-georef check ---------------------------
# Corrected LiDAR (Tunnel idx5 + Jameo idx6) vs the RTK surface datum (+ optional
# corrected drone crop). Unlike Puerta Falsa (internal blue-reference), this site
# was fit to EXTERNAL truth, so the check is: Tunnel<->Jameo agree at the pit
# throat, and both sit correctly under the RTK surface / on the drone.
_DOCS = (r"C:\Users\jj_ve\OneDrive - Delft University of Technology\Documents"
         r"\Thesis Lunar Leaper\LiDAR La Corona")
GENTE_FILES = [  # (label, path, colour, is_sparse)
    # role-based colours, matching the Puerta Falsa check (truth<-bridge<-mover):
    #   drone surface = blue  (truth, like ReferenceCloud)
    #   Jameo         = gold  (bridge, like StitchMove)
    #   Tunnel        = green (mover,  like TubeMove)
    ("Jameo",       _DOCS + r"\Clouds to reconstruct transformations\Jameo.txt",
     "gold", False),
    ("Tunnel",      _DOCS + r"\Reregistered clouds\TunnelLaGente_corrected.xyz",
     "green", False),
    ("Topo drone",  _DOCS + r"\Reregistered clouds\TopoLaGente.xyz",
     "tab:blue", False),     # optional -- skipped if absent
    ("RTK L5",      _DOCS + r"\Reregistered clouds\Line5_GNSS_RTK.xyz", "k", True),
    ("RTK L2",      _DOCS + r"\Reregistered clouds\Line2_GNSS_RTK.xyz", "0.35", True),
]
GENTE_PAIRS = [("Tunnel", "Jameo"),             # internal: pit-throat overlap
               ("Topo drone", "Jameo"),         # surface fit: jameo vs drone it was
                                                 # registered to (dense ref = real sep)
               ("RTK L5", "Topo drone"),        # datum: drone should sit on RTK
               ("RTK L2", "Topo drone")]        # (only run if drone present)
GENTE_SLICE_N = 3227540.0   # cuts cross at the jameo centre where jameo + tunnel
GENTE_SLICE_E = 649690.0    # (+ drone) all coincide -- the skylight/pit
GENTE_SLICE_HALF = 2.5
# focus the check on the pit/jameo/RTK zone (the full tunnel is ~450 m long)
GENTE_BBOX = (649600.0, 649850.0, 3227420.0, 3227650.0)   # E_min,E_max,N_min,N_max
GENTE_CMAP_LABELS = set()   # (elevation-cmap layers; unused -- flat role colours)


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


def load_gente():
    """Corrected Gente clouds + RTK datum (+ drone if exported). Returns
    (layers, pairs, sparse_labels). Missing optional files are skipped."""
    layers, sparse = [], set()
    for label, path, col, is_sparse in GENTE_FILES:
        if not os.path.exists(path):
            print(f"  (skip missing {label}: {os.path.basename(path)})")
            continue
        P = np.loadtxt(path, usecols=(0, 1, 2))
        e0, e1, n0, n1 = GENTE_BBOX
        m = (P[:, 0] >= e0) & (P[:, 0] <= e1) & (P[:, 1] >= n0) & (P[:, 1] <= n1)
        P = P[m]
        if len(P) == 0:
            print(f"  (skip {label}: no points in bbox)"); continue
        layers.append((label, P, col))
        if is_sparse:
            sparse.add(label)
    have = {l for l, _, _ in layers}
    pairs = [(m, r) for m, r in GENTE_PAIRS if m in have and r in have]
    return layers, pairs, sparse


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


def _compass(ax, left, right):
    """Label the two ends of a cross-section's horizontal axis with compass directions."""
    kw = dict(transform=ax.transAxes, fontsize=11, fontweight="bold",
              va="top", color="0.3")
    ax.text(0.01, 0.97, left, ha="left", **kw)
    ax.text(0.99, 0.97, right, ha="right", **kw)


def _scatter(ax, label, P, col, cols, sparse, base_s, base_a, cmap_labels=frozenset()):
    """One layer onto one panel; sparse (RTK) layers get bold markers, cmap layers
    (drone) are coloured by elevation, other dense clouds a subsampled flat scatter."""
    x, y = P[:, cols[0]], P[:, cols[1]]
    if label in sparse:
        return ax.scatter(x, y, s=32, c=col, marker="x", linewidths=1.3,
                          zorder=6, label=label)
    s = max(1, len(P) // 40000)
    if label in cmap_labels:
        return ax.scatter(x[::s], y[::s], s=base_s, c=P[::s, 2], cmap="viridis",
                          alpha=base_a, linewidths=0)
    return ax.scatter(x[::s], y[::s], s=base_s, c=col, alpha=base_a,
                      linewidths=0, label=f"{label} n={len(P)}")


def plot(layers, out_png, slice_n=SLICE_N, slice_e=SLICE_E, slice_half=SLICE_HALF,
         sparse=frozenset(), cmap_labels=frozenset(), suptitle=None):
    fig, axs = plt.subplots(2, 2, figsize=(16, 13))
    if suptitle:
        fig.suptitle(suptitle, fontsize=14, fontweight="bold")

    # (0,0) TOP XY
    for label, P, col in layers:
        _scatter(axs[0, 0], label, P, col, (0, 1), sparse, 2, 0.5, cmap_labels)
    # mark where the two cross-sections are cut (with their +-slice_half slab)
    xlim, ylim = axs[0, 0].get_xlim(), axs[0, 0].get_ylim()
    axs[0, 0].axhspan(slice_n - slice_half, slice_n + slice_half, color="k", alpha=0.12)
    axs[0, 0].axhline(slice_n, color="k", lw=1, ls="--")
    axs[0, 0].axvspan(slice_e - slice_half, slice_e + slice_half, color="k", alpha=0.12)
    axs[0, 0].axvline(slice_e, color="k", lw=1, ls="--")
    axs[0, 0].text(xlim[0], slice_n, " E-Z cut", va="bottom", ha="left", fontsize=8)
    axs[0, 0].text(slice_e, ylim[1], "N-Z cut ", va="top", ha="right", rotation=90, fontsize=8)
    axs[0, 0].set_xlim(xlim); axs[0, 0].set_ylim(ylim)
    axs[0, 0].set_aspect("equal")
    # fixed-size legend handles (else markerscale blows up the sparse 'x' markers)
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], color=col, ls="none",
                      marker=("x" if label in sparse else "o"),
                      ms=7, mew=(1.6 if label in sparse else 0),
                      label=(label if label in sparse else f"{label} n={len(P)}"))
               for label, P, col in layers]
    axs[0, 0].legend(handles=handles, loc="best")
    axs[0, 0].set_title("TOP (XY)"); axs[0, 0].set_xlabel("E"); axs[0, 0].set_ylabel("N")

    # (0,1) projected SIDE E-Z (all points)
    for label, P, col in layers:
        _scatter(axs[0, 1], label, P, col, (0, 2), sparse, 2, 0.4, cmap_labels)
    axs[0, 1].set_aspect("equal")
    axs[0, 1].set_title("SIDE projected (E-Z, all pts)")
    axs[0, 1].set_xlabel("E"); axs[0, 1].set_ylabel("Z")

    # (1,0) E-Z cross-section at fixed Northing
    for label, P, col in layers:
        m = np.abs(P[:, 1] - slice_n) < slice_half
        if m.any():
            _scatter(axs[1, 0], label, P[m], col, (0, 2), sparse, 4, 0.7, cmap_labels)
    axs[1, 0].set_aspect("equal")
    axs[1, 0].set_title(f"CROSS-SECTION E-Z (|N-{slice_n:.0f}|<{slice_half:.1f} m)")
    axs[1, 0].set_xlabel("E"); axs[1, 0].set_ylabel("Z")
    _compass(axs[1, 0], "W", "E")

    # (1,1) N-Z cross-section at fixed Easting
    for label, P, col in layers:
        m = np.abs(P[:, 0] - slice_e) < slice_half
        if m.any():
            _scatter(axs[1, 1], label, P[m], col, (1, 2), sparse, 4, 0.7, cmap_labels)
    axs[1, 1].set_aspect("equal")
    axs[1, 1].set_title(f"CROSS-SECTION N-Z (|E-{slice_e:.0f}|<{slice_half:.1f} m)")
    axs[1, 1].set_xlabel("N"); axs[1, 1].set_ylabel("Z")
    _compass(axs[1, 1], "S", "N")

    fig.tight_layout(); fig.savefig(out_png, dpi=130, bbox_inches="tight")
    print("saved", os.path.abspath(out_png))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--las", metavar="CLOUD.las",
                    help="baseline mode: single LAS with Original_cloud_index")
    ap.add_argument("--gente", action="store_true",
                    help="Jameo de la Gente re-georef check (corrected clouds + RTK)")
    ap.add_argument("--step", type=int, default=1, help="LAS subsample step")
    ap.add_argument("-o", "--out", help="output PNG path")
    args = ap.parse_args()

    sparse = frozenset()
    sn, se, sh = SLICE_N, SLICE_E, SLICE_HALF
    suptitle = None
    if args.gente:
        layers, pairs, sparse = load_gente()
        sn, se, sh = GENTE_SLICE_N, GENTE_SLICE_E, GENTE_SLICE_HALF
        suptitle = ("Jameo de la Gente coregistration check")
        out = args.out or os.path.join(GENTE_FILES[0][1].rsplit("\\", 2)[0],
                                       "Reregistered clouds", "gente_check.png")
    elif args.las:
        layers, pairs = load_las(args.las, step=args.step)
        out = args.out or os.path.splitext(args.las)[0] + "_check.png"
    else:
        layers, pairs = load_asc()
        out = args.out or os.path.join(ASC_DIR, "alignment_check.png")

    by = {label: P for label, P, _ in layers}
    for label, P, _ in layers:
        print(f"{label}: n={len(P)}  E[{P[:,0].min():.1f},{P[:,0].max():.1f}] "
              f"N[{P[:,1].min():.1f},{P[:,1].max():.1f}] Z[{P[:,2].min():.1f},{P[:,2].max():.1f}]")
    print()
    for mover, ref in pairs:
        if mover in by and ref in by:
            residual(by[mover], by[ref], f"{mover}->{ref}")

    cmap_labels = GENTE_CMAP_LABELS if args.gente else frozenset()
    plot(layers, out, slice_n=sn, slice_e=se, slice_half=sh, sparse=sparse,
         cmap_labels=cmap_labels, suptitle=suptitle)


if __name__ == "__main__":
    main()

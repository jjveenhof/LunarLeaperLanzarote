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

CRS: EPSG:4083 (REGCAN95 / UTM zone 27N).
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
        print(f"{label:>18}  within {thr:>3} m: {100*sel.mean():5.1f}% of pts, mean NN={m:.3f} m")
    p = np.percentile(dist, [5, 10, 20])
    print(f"{label:>18}  percentiles  p5={p[0]:.3f} p10={p[1]:.3f} p20={p[2]:.3f} m  (n={len(P)})\n")


def _compass(ax, left, right):
    """Label the two ends of a cross-section's horizontal axis with compass directions."""
    kw = dict(transform=ax.transAxes, fontsize=11, fontweight="bold",
              va="top", color="0.3")
    ax.text(0.01, 0.97, left, ha="left", **kw)
    ax.text(0.99, 0.97, right, ha="right", **kw)


def plot(layers, out_png):
    fig, axs = plt.subplots(2, 2, figsize=(16, 13))

    # (0,0) TOP XY
    for label, P, col in layers:
        s = max(1, len(P) // 40000)
        axs[0, 0].scatter(P[::s, 0], P[::s, 1], s=2, c=col, alpha=0.5,
                          linewidths=0, label=f"{label} n={len(P)}")
    # mark where the two cross-sections are cut (with their +-SLICE_HALF slab)
    xlim, ylim = axs[0, 0].get_xlim(), axs[0, 0].get_ylim()
    axs[0, 0].axhspan(SLICE_N - SLICE_HALF, SLICE_N + SLICE_HALF, color="k", alpha=0.12)
    axs[0, 0].axhline(SLICE_N, color="k", lw=1, ls="--")
    axs[0, 0].axvspan(SLICE_E - SLICE_HALF, SLICE_E + SLICE_HALF, color="k", alpha=0.12)
    axs[0, 0].axvline(SLICE_E, color="k", lw=1, ls="--")
    axs[0, 0].text(xlim[0], SLICE_N, " E-Z cut", va="bottom", ha="left", fontsize=8)
    axs[0, 0].text(SLICE_E, ylim[1], "N-Z cut ", va="top", ha="right", rotation=90, fontsize=8)
    axs[0, 0].set_xlim(xlim); axs[0, 0].set_ylim(ylim)
    axs[0, 0].set_aspect("equal"); axs[0, 0].legend(markerscale=6)
    axs[0, 0].set_title("TOP (XY)"); axs[0, 0].set_xlabel("E"); axs[0, 0].set_ylabel("N")

    # (0,1) projected SIDE E-Z (all points)
    for label, P, col in layers:
        s = max(1, len(P) // 40000)
        axs[0, 1].scatter(P[::s, 0], P[::s, 2], s=2, c=col, alpha=0.4, linewidths=0)
    axs[0, 1].set_aspect("equal")
    axs[0, 1].set_title("SIDE projected (E-Z, all pts)")
    axs[0, 1].set_xlabel("E"); axs[0, 1].set_ylabel("Z")

    # (1,0) E-Z cross-section at fixed Northing
    for label, P, col in layers:
        m = np.abs(P[:, 1] - SLICE_N) < SLICE_HALF
        axs[1, 0].scatter(P[m, 0], P[m, 2], s=4, c=col, alpha=0.7, linewidths=0)
    axs[1, 0].set_aspect("equal")
    axs[1, 0].set_title(f"CROSS-SECTION E-Z (|N-{SLICE_N:.0f}|<{SLICE_HALF:.1f} m)")
    axs[1, 0].set_xlabel("E"); axs[1, 0].set_ylabel("Z")
    _compass(axs[1, 0], "W", "E")

    # (1,1) N-Z cross-section at fixed Easting
    for label, P, col in layers:
        m = np.abs(P[:, 0] - SLICE_E) < SLICE_HALF
        axs[1, 1].scatter(P[m, 1], P[m, 2], s=4, c=col, alpha=0.7, linewidths=0)
    axs[1, 1].set_aspect("equal")
    axs[1, 1].set_title(f"CROSS-SECTION N-Z (|E-{SLICE_E:.0f}|<{SLICE_HALF:.1f} m)")
    axs[1, 1].set_xlabel("N"); axs[1, 1].set_ylabel("Z")
    _compass(axs[1, 1], "S", "N")

    fig.tight_layout(); fig.savefig(out_png, dpi=130, bbox_inches="tight")
    print("saved", os.path.abspath(out_png))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--las", metavar="CLOUD.las",
                    help="baseline mode: single LAS with Original_cloud_index")
    ap.add_argument("--step", type=int, default=1, help="LAS subsample step")
    ap.add_argument("-o", "--out", help="output PNG path")
    args = ap.parse_args()

    if args.las:
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

    plot(layers, out)


if __name__ == "__main__":
    main()

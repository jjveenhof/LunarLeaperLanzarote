"""
plot_petal_migration_map.py
THESIS figure: plan-view map of the flower-petal trajectories with the
sub-segments used for 2-D migration highlighted.

Each petal's full track is drawn thin in its own colour; the migrated
sub-segments (SEGMENTS, imported from plot_petal_migration_3d so the map and the
3D plot can never drift apart) are overdrawn thick. Line 3 and the pit (jameo)
rim are shown faded for spatial context. Styled for the thesis via plot_utils
(Computer Modern, vector PDF).

Usage:
    python plot_petal_migration_map.py
Output:
    Results/GPR/Migration/petal_migration_map.png  (+ title-free thesis PDF)
"""

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plot_flowerpetal_3d as fp
from plot_petal_migration_3d import SEGMENTS, L3_LINES
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure

HERE    = Path(__file__).parent
OUT_DIR = HERE / '../../Results/GPR/Migration'

# All petals share the map palette's flower-petal pink (QGIS L4/FP colour);
# individual petals are told apart by their FP1/FP2/FP3 labels, not by colour.
PETAL_PINK = '#FF4DB8'
PETAL_COLOUR = {
    'FlowerPetal1_50MHz': PETAL_PINK,
    'FlowerPetal2_50MHz': PETAL_PINK,
    'FlowerPetal3_50MHz': PETAL_PINK,
}
PETAL_LABEL = {'FlowerPetal1_50MHz': 'FP1',
               'FlowerPetal2_50MHz': 'FP2',
               'FlowerPetal3_50MHz': 'FP3'}

L3_COLOUR  = '#FF5C00'   # L3's colour in the QGIS maps (orange-red)
LABEL_FS   = 8      # feature-label font size (FP + L3 share it)
TRACK_LW   = 1.0    # full-trajectory line width (thin)
SEG_LW     = 3.2    # migrated-segment line width (thick highlight)
TRACK_A    = 0.40   # full-trajectory alpha (faded so highlights stand out)
FIG_W      = 4.3    # inches; smaller -> annotations relatively bigger at linewidth
X_MARGIN_FRAC = 0.25  # side whitespace as a fraction of the E-W data span; larger = wider


def petal_track(prof):
    """(east, north, dist_along) for a petal, geometry reconciled to the data."""
    with np.load(str(fp.PROC_DIR / (prof['key'] + '_processed.npz'))) as f:
        dist_axis = f['dist_axis'].astype(np.float64)
    gnss_df = fp.load_gnss_fp(fp.GNSS_FP)
    east_fn, north_fn, elev_fn = fp.build_track_interps(
        gnss_df, prof['gnss_line'], prof['metre'])
    gnss_m = dist_axis + prof['offset']
    east, north, _elev = fp.reconcile_geometry(
        prof['key'], east_fn(gnss_m), north_fn(gnss_m), elev_fn(gnss_m))
    seg = np.hypot(np.diff(east), np.diff(north))
    dist_along = np.concatenate([[0.0], np.cumsum(seg)])
    return east, north, dist_along


def line3_track(key):
    with np.load(str(fp.PROC_DIR / (key + '_processed.npz'))) as f:
        dist_axis = f['dist_axis'].astype(np.float64)
    prof = next(p for p in fp.PROFILES if p['key'] == key)
    gnss_df = fp.load_gnss_lines(fp.GNSS_LINES)
    east_fn, north_fn, elev_fn = fp.build_track_interps(
        gnss_df, prof['gnss_line'], prof['metre'])
    gnss_m = dist_axis + prof['offset']
    east, north, _elev = fp.reconcile_geometry(
        key, east_fn(gnss_m), north_fn(gnss_m), elev_fn(gnss_m))
    return east, north


def main():
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_W))

    all_east = []   # collected to set a tight x-limit (less side whitespace)

    # pit (jameo) rim for context (dashed)
    edge = fp.load_edge(fp.GNSS_FP)
    if edge is not None:
        ax.plot(edge['east'], edge['north'], color='0.35', lw=1.3,
                ls='dashed', zorder=2)
        ax.annotate('jameo rim',
                    (float(np.mean(edge['east'])) + 5.0, float(np.mean(edge['north']))),
                    fontsize=LABEL_FS, color='black', ha='center', va='center', zorder=2)
        all_east.extend(edge['east'])

    # Line 3 (its map colour #FF5C00; drawn THICK -- it too was migrated)
    l3e, l3n = line3_track(L3_LINES[0][0])
    ax.plot(l3e, l3n, color=L3_COLOUR, lw=SEG_LW, solid_capstyle='round', zorder=2)
    ax.annotate('L3', (l3e[-1], l3n[-1] + 20.0), fontsize=LABEL_FS, color='black',
                ha='left', va='center', zorder=2)
    all_east.extend(l3e)

    for key, segs in SEGMENTS.items():
        prof = next(p for p in fp.PROFILES if p['key'] == key)
        colour = PETAL_COLOUR[key]
        east, north, dist_along = petal_track(prof)
        all_east.extend(east)
        # full trajectory (thin, faded)
        ax.plot(east, north, color=colour, lw=TRACK_LW, alpha=TRACK_A, zorder=3)
        # migrated segments (thick highlight)
        for (s, e) in segs:
            end = float(dist_along[-1]) if e is None else float(e)
            idx = np.where((dist_along >= float(s)) & (dist_along <= end))[0]
            if idx.size < 2:
                continue
            sl = slice(int(idx[0]), int(idx[-1]) + 1)
            ax.plot(east[sl], north[sl], color=colour, lw=SEG_LW,
                    solid_capstyle='round', zorder=4)
        # petal label near the apex (farthest track point from start), to its left
        apex = int(np.argmax((east - east[0]) ** 2 + (north - north[0]) ** 2))
        ax.annotate(PETAL_LABEL[key], (east[apex], north[apex]),
                    textcoords='offset points', xytext=(-6, 0),
                    ha='right', va='center',
                    fontsize=LABEL_FS, color='black', fontweight='bold', zorder=5)

    ax.set_xlabel('Easting (m)', fontsize=9)
    ax.set_ylabel('Northing (m)', fontsize=9)
    ax.tick_params(labelsize=8)
    ax.ticklabel_format(useOffset=False, style='plain')
    # x-limit around the data (box aspect so equal scale is kept while the x-range
    # shrinks -- trims side whitespace beside the GPR lines; X_MARGIN_FRAC tunes it).
    xmin, xmax = float(np.min(all_east)), float(np.max(all_east))
    mx = X_MARGIN_FRAC * (xmax - xmin)
    ax.set_xlim(xmin - mx, xmax + mx)
    ax.set_aspect('equal', adjustable='box')

    # north arrow near the top-left, in DATA coords so "up 5 m" is exact; N to
    # the RIGHT of the arrow.
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    xr, yr = x1 - x0, y1 - y0
    n_x    = x0 + 0.10 * xr
    y_tail = y0 + 0.80 * yr + 5.0        # +5 m up
    y_head = y_tail + 0.13 * yr
    ax.annotate('', xy=(n_x, y_head), xytext=(n_x, y_tail),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.2,
                                mutation_scale=16,
                                capstyle='butt', joinstyle='miter'))   # sharp ends
    # weighted blend of tail/head (weights MUST sum to 1 -- these are absolute
    # northings, so 0.5*(a+b) is the midpoint; more weight on y_tail = a bit lower)
    ax.text(n_x + 0.03 * xr, 0.55 * y_tail + 0.45 * y_head, 'N',
            ha='left', va='center', fontsize=10, fontweight='bold')

    # CRS note in an uncrowded corner (two lines so it doesn't reach across to L3)
    ax.text(0.02, 0.02, 'REGCAN95 / UTM zone 28N\n(EPSG:4083)',
            transform=ax.transAxes, fontsize=7, color='0.3',
            ha='left', va='bottom')

    # legend: just the thin/thick meaning (petals are labelled on the plot).
    # Proxies BLACK so they don't read as the grey jameo-rim line.
    handles = [
        Line2D([0], [0], color='black', lw=TRACK_LW, label='full trajectory'),
        Line2D([0], [0], color='black', lw=SEG_LW, label='migrated segment'),
    ]
    ax.legend(handles=handles, fontsize=7, loc='upper right', frameon=False)

    fig.tight_layout()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'petal_migration_map.png'
    fig.savefig(str(out), dpi=200, bbox_inches='tight')
    thesis_path, _ = save_figure(fig, out.stem, 'GPR', vector=True, dpi=300,
                                 titles='auto')
    plt.close(fig)
    print('Saved: {}'.format(out))
    print('thesis -> {}'.format(thesis_path))


if __name__ == '__main__':
    main()

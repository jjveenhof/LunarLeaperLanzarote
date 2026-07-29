"""
plot_petal_map.py
EXPLORATION aid for the flower-petal migration: plan-view (map) of each petal
trajectory with distance-along-profile ticked off along the curve, so straight
sub-segments can be read off directly in metres.

For each petal (FP1/FP2/FP3) the processed radargram's dist_axis is mapped onto
the GNSS track (same offset + track-interp machinery as plot_flowerpetal_3d.py),
then drawn in E/N with equal aspect. Distance-along-track labels are placed every
LABEL_STEP_M metres; the start (0 m) and apex (out/back split) are marked. Line 3
is drawn faded in every panel for spatial reference.

Not a migration and not a thesis figure -- a picking aid. Read straight ranges off
it (e.g. "FP3 4-20 m"), then hand them back for the migration step.

Usage:
    python plot_petal_map.py
Output:
    Results/GPR/Migration/petal_map.png
"""

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plot_flowerpetal_3d as fp

HERE    = Path(__file__).parent
OUT_DIR = HERE / '../../Results/GPR/Migration'

PETALS = [p for p in fp.PROFILES if p.get('loop')]
LINE3  = next(p for p in fp.PROFILES if p['key'] == 'Line3_50MHz')

LABEL_STEP_M = 5.0    # spacing of distance-along-track annotations (m); smaller = denser
MARGIN_M     = 6.0    # map margin around each petal's extent (m); larger = more zoomed out


def track_xy(prof, source):
    """(dist_along_m, east, north, apex_idx) mapping the processed dist_axis onto
    the GNSS track exactly as plot_flowerpetal_3d does. source: 'fp' or 'lines'."""
    npz_path = fp.PROC_DIR / (prof['key'] + '_processed.npz')
    with np.load(str(npz_path)) as f:
        dist_axis = f['dist_axis'].astype(np.float64)

    if source == 'fp':
        gnss_df = fp.load_gnss_fp(fp.GNSS_FP)
    else:
        gnss_df = fp.load_gnss_lines(fp.GNSS_LINES)
    east_fn, north_fn, elev_fn = fp.build_track_interps(
        gnss_df, prof['gnss_line'], prof['metre'])
    gnss_m = dist_axis + prof['offset']
    east, north, _elev = fp.reconcile_geometry(
        prof['key'], east_fn(gnss_m), north_fn(gnss_m), elev_fn(gnss_m))

    seg = np.hypot(np.diff(east), np.diff(north))
    dist_along = np.concatenate([[0.0], np.cumsum(seg)])

    d2 = (east - east[0]) ** 2 + (north - north[0]) ** 2
    apex = int(np.argmax(d2))
    dtrace = float(dist_axis[1] - dist_axis[0]) if len(dist_axis) > 1 else 1.0
    apex += int(round(prof.get('split_offset_m', 0.0) / dtrace))
    apex = max(1, min(apex, len(east) - 2))
    return dist_along, east, north, apex


def annotate_distance(ax, dist_along, east, north, step_m):
    """Tick + label every `step_m` metres along the track."""
    marks = np.arange(0.0, float(dist_along[-1]) + 1e-6, step_m)
    idx = np.searchsorted(dist_along, marks)
    idx = np.clip(idx, 0, len(dist_along) - 1)
    ax.scatter(east[idx], north[idx], s=9, color='black', zorder=5)
    for m, i in zip(marks, idx):
        ax.annotate('{:.0f}'.format(m), (east[i], north[i]),
                    textcoords='offset points', xytext=(3, 3),
                    fontsize=6.5, color='black', zorder=6)


def main():
    l3_d, l3_e, l3_n, _ = track_xy(LINE3, 'lines')

    n = len(PETALS)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 4.6))
    axes = np.atleast_1d(axes)

    for ax, prof in zip(axes, PETALS):
        d, e, nth, apex = track_xy(prof, 'fp')
        # Line 3 faded for spatial reference
        ax.plot(l3_e, l3_n, color='0.75', lw=1.0, zorder=1)
        ax.annotate('Line 3', (l3_e[len(l3_e) // 2], l3_n[len(l3_n) // 2]),
                    fontsize=7, color='0.5', zorder=1)
        # out limb / back limb in two shades
        ax.plot(e[:apex + 1], nth[:apex + 1], color='#1f77b4', lw=1.4,
                zorder=2, label='out')
        ax.plot(e[apex:], nth[apex:], color='#d62728', lw=1.4,
                zorder=2, label='back')
        annotate_distance(ax, d, e, nth, LABEL_STEP_M)
        # Zoom to THIS petal's extent (+ a margin) so the loop fills the panel;
        # Line 3 is only partly visible. MARGIN_M grows the view around the petal.
        ax.set_xlim(e.min() - MARGIN_M, e.max() + MARGIN_M)
        ax.set_ylim(nth.min() - MARGIN_M, nth.max() + MARGIN_M)
        ax.scatter([e[0]], [nth[0]], s=40, marker='o', facecolor='white',
                   edgecolor='black', zorder=7)
        ax.scatter([e[apex]], [nth[apex]], s=45, marker='*', color='black',
                   zorder=7)
        ax.set_title('{}  (start o, apex *, {:.0f} m total)'.format(
            prof['label'], d[-1]), fontsize=9, loc='left')
        ax.set_xlabel('Easting (m)', fontsize=8)
        ax.set_ylabel('Northing (m)', fontsize=8)
        ax.tick_params(labelsize=7)
        ax.ticklabel_format(useOffset=False, style='plain')
        ax.set_aspect('equal', adjustable='box')
        ax.legend(fontsize=7, loc='best', frameon=False)

    fig.suptitle('Flower-petal trajectories (plan view) with distance-along-track '
                 'labels (m)', fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'petal_map.png'
    fig.savefig(str(out), dpi=160, bbox_inches='tight')
    plt.close(fig)
    print('Saved: {}'.format(out.resolve()))


if __name__ == '__main__':
    main()

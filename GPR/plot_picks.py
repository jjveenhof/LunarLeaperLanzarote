"""
plot_picks.py
Annotate the picked tube ceiling/floor on the migrated 50 MHz sections.

Fast iteration loop -- no migration is re-run, only the already-migrated NPZ is
loaded and re-plotted (seconds):
    1. edit Data/GPR/Migration/tube_picks.csv (depths and/or x_ceiling_m/x_floor_m)
    2. python plot_picks.py
    3. look at Results/GPR/Migrated/{line}_50MHz_picks.png -- repeat.

Geometry note: the migrated section's y axis is depth below the DATUM
(ref_elev), while the CSV depths are metres below the LOCAL SURFACE. The
annotation converts: y_plot = (ref_elev - elevation(x)) + depth_below_surface,
so the arrow lands on the reflector regardless of topography. Labels quote the
CSV value, i.e. depth below surface (the floor label is the APPARENT depth --
the reflector's position in a section migrated at v_rock throughout).

Display gain and clip come from the profile's params JSON (migration_gain,
clip_percentile), identical to the other report figures.

Usage:
    python plot_picks.py            # all lines in tube_picks.csv
    python plot_picks.py Line3      # one line
"""

import sys
import json
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gpr_processing import display_gain
from plot_dual_freq import (X_OFFSET_100MHZ, PICKS_CSV, PICK_PANEL_CFG, load_flip,
                            read_picks, annotate_pick, pick_entries)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure

HERE      = Path(__file__).parent
MIG_DIR   = HERE / '../../Data/GPR/Migration'
PROC_DIR  = HERE / '../../Data/GPR/Processed'
OUT_DIR   = HERE / '../../Results/GPR/Migrated'

FREQS = ['50MHz', '100MHz']   # picks (and their x positions) are DEFINED on the
                              # 50 MHz displayed axis; 100 MHz sections get the
                              # same picks with x remapped to their local axis


def pick_x_to_local(line, freq, x50_pick):
    """Map a pick x (defined on the 50 MHz displayed axis) onto this section's
    own distance axis. Identity for 50 MHz; the 100 MHz section is a sub-line
    with its own 0-based axis, placed at X_OFFSET_100MHZ (mirrored when flip_x
    is baked) -- the exact inverse of plot_dual_freq's panel placement."""
    if freq == '50MHz':
        return x50_pick
    offset = X_OFFSET_100MHZ.get(line, 0.0)
    with np.load(str(MIG_DIR / ('{}_100MHz_migrated.npz'.format(line)))) as f:
        x100 = f['dist_axis']
        x100_span = float(x100[0]) + float(x100[-1])
    if load_flip(line, '100MHz'):
        with np.load(str(MIG_DIR / ('{}_50MHz_migrated.npz'.format(line)))) as f:
            x50 = f['dist_axis']
        offset = (float(x50[0]) + float(x50[-1])) - offset - x100_span
    return x50_pick - offset


def plot_line(row, freq):
    stem = '{}_{}'.format(row['line'], freq)
    npz_path = MIG_DIR / (stem + '_migrated.npz')
    if not npz_path.exists():
        print('  [skip] {}: no migrated NPZ'.format(stem))
        return

    with np.load(str(npz_path)) as f:
        data  = f['data'].astype(np.float64)
        x     = f['dist_axis'].astype(np.float64)
        depth = f['depth_axis'].astype(np.float64)
        v     = float(f['velocity'])
        ref_elev   = float(f['ref_elev'])
        elevations = f['elevations'].astype(np.float64)

    params = {}
    params_path = PROC_DIR / (stem + '_params.json')
    if params_path.exists():
        with open(str(params_path), encoding='utf-8') as f:
            params = json.load(f)
    gain      = float(params.get('migration_gain', 0.0))
    clip_pct  = float(params.get('clip_percentile', 99.5))
    depth_max = float(params.get('depth_max', 25.0))

    if gain > 0:
        dz = float(depth[1] - depth[0])
        data = display_gain(data, 1000.0 * v / (2.0 * dz), gain)
    clip = float(np.percentile(np.abs(data), clip_pct)) or 1.0
    dmax = min(depth_max, float(depth[-1]))
    surf_depth = ref_elev - elevations          # surface depth below datum

    fig, ax = plt.subplots(figsize=(5.3, 2.4))
    ax.imshow(data, aspect='auto', cmap='seismic', vmin=-clip, vmax=clip,
              extent=[float(x[0]), float(x[-1]), float(depth[-1]), float(depth[0])],
              interpolation='nearest')
    ax.fill_between(x, 0.0, surf_depth, color='0.85', zorder=2, linewidth=0)
    ax.plot(x, surf_depth, color='k', linewidth=1.1, zorder=3)
    ax.set_ylim(dmax, 0.0)
    ax.set_ylabel('Depth (m)', fontsize=9)
    ax.set_xlabel('Distance (m)', fontsize=9)
    ax.set_title('{} -- {} migrated | v = {:.3f} m/ns | gain {:.1f} | clip {:.1f}%'.format(
        row['line'], freq.replace('MHz', ' MHz'), v, gain, clip_pct),
        fontsize=9, loc='left')
    ax.text(0.01, 0.03, 'N', transform=ax.transAxes, ha='left', va='bottom',
            fontsize=11, fontweight='bold', color='black')
    ax.text(0.99, 0.03, 'S', transform=ax.transAxes, ha='right', va='bottom',
            fontsize=11, fontweight='bold', color='black')

    # elevation twin axis (same convention as the other migrated figures)
    tax = ax.twinx()
    tax.set_ylim(ref_elev - dmax, ref_elev)
    tax.set_ylabel('Elevation (m asl)', fontsize=9)

    # --- picks: CSV depths are below LOCAL SURFACE; convert to depth below datum.
    # CSV x positions are in the 50 MHz displayed coordinate; remap for 100 MHz.
    cfg = PICK_PANEL_CFG.get((row['line'], freq), {})
    for xp_50, d_bs, label, ldx, ldy in pick_entries(row):
        xp = pick_x_to_local(row['line'], freq, xp_50)
        if not (float(x[0]) <= xp <= float(x[-1])):
            print('    [note] {}: pick x={} maps outside this section -- skipped'.format(
                stem, xp_50))
            continue
        y = float(np.interp(xp, x, surf_depth)) + d_bs
        if y > dmax:
            print('    [note] {}: pick at {:.1f} m below datum is below the {:.0f} m '
                  'crop -- skipped'.format(stem, y, dmax))
            continue
        annotate_pick(ax, xp, y, label, float(x[0]), float(x[-1]),
                      float(x[0]), float(x[-1]), cfg=cfg, label_dx=ldx, label_dy=ldy)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / (stem + '_picks.png')
    fig.savefig(str(out), dpi=180, bbox_inches='tight')
    save_figure(fig, out.stem, 'GPR', vector=True)   # title-free thesis PDF
    plt.close(fig)
    print('  {} -> {}'.format(stem, out.name))


def main():
    ap = argparse.ArgumentParser(description='Annotate tube picks on migrated sections.')
    ap.add_argument('lines', nargs='*', help='line names as in tube_picks.csv (default: all)')
    args = ap.parse_args()

    rows = read_picks()
    if args.lines:
        rows = [r for r in rows if r['line'] in args.lines]
    if not rows:
        sys.exit('No matching rows in ' + str(PICKS_CSV.resolve()))
    for row in rows:
        for freq in FREQS:
            plot_line(row, freq)


if __name__ == '__main__':
    main()

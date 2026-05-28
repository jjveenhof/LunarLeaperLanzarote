"""
plot_dual_freq.py
Plot 50 MHz (top) and 100 MHz (bottom) profiles for the same line, stacked
vertically at the same spatial and depth scale.

The 100 MHz profile is positioned at its correct metre location on the line
so the two panels are spatially aligned.

Usage:
    python plot_dual_freq.py Line2
    python plot_dual_freq.py Line3
    python plot_dual_freq.py Line5
    python plot_dual_freq.py Line3 --stage topo       # topo-corrected data
    python plot_dual_freq.py Line3 --stage processed  # processed only
    python plot_dual_freq.py Line3 --velocity 0.11    # override velocity
    python plot_dual_freq.py Line3 --clip 95          # clip percentile
"""

import argparse
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

# ---- PATHS -------------------------------------------------------------------
HERE     = Path(__file__).parent
DATA_GPR = HERE / '../../Data/GPR'
OUT_DIR  = HERE / '../../Results/GPR/DualFreq'

# x-offset (metres): where the 100 MHz back antenna sat on the full line.
# Line2: both lines share the same start.
# Line3: 100 MHz section starts at metre 60.
# Line5: 100 MHz starts at metre 30 (profile already reversed in GPRFieldVisual).
X_OFFSET_100MHZ = {
    'Line2': 0.0,
    'Line3': 60.0,
    'Line5': 30.0,
}

V_DEFAULT = 0.13    # m/ns
CMAP      = 'seismic'
# ------------------------------------------------------------------------------


def find_npz(line, freq, stage):
    """
    Locate the NPZ for a given line, frequency, and processing stage.
    stage: 'topo' | 'processed' | 'stitched'
    Returns Path or None.
    """
    suffixes = {
        'topo':      ('Topo',      '_topo.npz'),
        'processed': ('Processed', '_processed.npz'),
        'stitched':  ('Stitched',  '_raw.npz'),
    }
    subdir, suffix = suffixes[stage]
    stem = '{}_{}'.format(line, freq)
    return (DATA_GPR / subdir / (stem + suffix))


def find_best(line, freq):
    """Return the best available NPZ, preferring topo > processed > stitched."""
    for stage in ('topo', 'processed', 'stitched'):
        p = find_npz(line, freq, stage)
        if p.exists():
            return p, stage
    return None, None


def load_npz(path):
    with np.load(str(path)) as npz:
        data      = npz['data'].astype(np.float64)
        dist_axis = npz['dist_axis'].astype(np.float64)
        time_axis = npz['time_axis'].astype(np.float64)
    return data, dist_axis, time_axis


def make_figure(line, stage_override, velocity, clip_pct, save_path):
    # --- find files ---
    if stage_override:
        p50  = find_npz(line, '50MHz',  stage_override)
        p100 = find_npz(line, '100MHz', stage_override)
        stage50 = stage100 = stage_override
        if not p50.exists():
            sys.exit('Not found: ' + str(p50))
        if not p100.exists():
            sys.exit('Not found: ' + str(p100))
    else:
        p50,  stage50  = find_best(line, '50MHz')
        p100, stage100 = find_best(line, '100MHz')
        if p50 is None:
            sys.exit('No 50 MHz data found for ' + line)
        if p100 is None:
            sys.exit('No 100 MHz data found for ' + line)

    print('50 MHz  ({}) : {}'.format(stage50,  p50.name))
    print('100 MHz ({}) : {}'.format(stage100, p100.name))

    d50,  x50,  t50  = load_npz(p50)
    d100, x100, t100 = load_npz(p100)

    # --- depth axes ---
    z50  = t50  * velocity / 2.0   # one-way depth (m)
    z100 = t100 * velocity / 2.0

    x_offset = X_OFFSET_100MHZ.get(line, 0.0)

    # --- common axis limits ---
    x_min = min(float(x50[0]),  x_offset + float(x100[0]))
    x_max = max(float(x50[-1]), x_offset + float(x100[-1]))
    z_max = float(z50[-1])   # 50 MHz sets the depth limit (deeper penetration)

    # --- colour limits (independent per panel) ---
    clip50  = np.percentile(np.abs(d50),  clip_pct)
    clip100 = np.percentile(np.abs(d100), clip_pct)

    # --- figure layout ---
    # Height ratio: proportional to each profile's depth so the vertical scale
    # (metres per pixel) is the same in both panels.
    depth50  = float(z50[-1])
    depth100 = float(z100[-1])
    ratio    = depth50 / depth100 if depth100 > 0 else 1.0

    fig_width  = 14.0
    panel_h    = 3.5          # height in inches for 100 MHz panel
    fig_height = panel_h * ratio + panel_h + 0.8   # top + bottom + spacing

    fig = plt.figure(figsize=(fig_width, fig_height))
    gs  = gridspec.GridSpec(
        2, 2,
        figure=fig,
        height_ratios=[ratio, 1.0],
        width_ratios=[0.97, 0.03],
        hspace=0.08,
        wspace=0.02,
    )

    ax50  = fig.add_subplot(gs[0, 0])
    ax100 = fig.add_subplot(gs[1, 0], sharex=ax50)
    cax50  = fig.add_subplot(gs[0, 1])
    cax100 = fig.add_subplot(gs[1, 1])

    # --- extents for imshow ---
    # extent = [left, right, bottom, top] where bottom > top (depth increases down)
    ext50  = [float(x50[0]),
              float(x50[-1]),
              float(z50[-1]),
              float(z50[0])]
    ext100 = [x_offset + float(x100[0]),
              x_offset + float(x100[-1]),
              float(z100[-1]),
              float(z100[0])]

    im50 = ax50.imshow(
        d50, aspect='auto', cmap=CMAP,
        vmin=-clip50, vmax=clip50,
        extent=ext50,
        interpolation='nearest',
    )
    im100 = ax100.imshow(
        d100, aspect='auto', cmap=CMAP,
        vmin=-clip100, vmax=clip100,
        extent=ext100,
        interpolation='nearest',
    )

    # --- axis limits (same x for both; y proportional to depth) ---
    ax50.set_xlim(x_min, x_max)
    ax50.set_ylim(z_max, 0)
    ax100.set_xlim(x_min, x_max)
    ax100.set_ylim(depth100, 0)

    # shade the region outside the 100 MHz data extent
    ax100.axvspan(x_min, ext100[0], color='0.88', zorder=0)
    ax100.axvspan(ext100[1], x_max, color='0.88', zorder=0)

    # --- labels ---
    ax50.set_ylabel('Depth (m)  [v = {:.3f} m/ns]'.format(velocity), fontsize=9)
    ax100.set_ylabel('Depth (m)', fontsize=9)
    ax100.set_xlabel('Distance (m)', fontsize=9)
    plt.setp(ax50.get_xticklabels(), visible=False)

    ax50.set_title(
        '{} -- 50 MHz ({})'.format(line, stage50),
        fontsize=10, loc='left'
    )
    ax100.set_title(
        '{} -- 100 MHz ({})  |  offset {:.0f} m'.format(line, stage100, x_offset),
        fontsize=10, loc='left'
    )

    # --- colourbars ---
    plt.colorbar(im50,  cax=cax50,  label='Ampl.')
    plt.colorbar(im100, cax=cax100, label='Ampl.')

    # --- save ---
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if save_path is None:
        save_path = OUT_DIR / '{}_dual_freq_{}.png'.format(line, stage50)
    save_path = Path(save_path).resolve()
    print('Saving to: ' + str(save_path))
    plt.savefig(str(save_path), dpi=180, bbox_inches='tight')
    plt.close(fig)
    print('Done.')


def main():
    parser = argparse.ArgumentParser(
        description='Plot 50/100 MHz GPR profiles for the same line at equal scale.'
    )
    parser.add_argument('line', choices=['Line2', 'Line3', 'Line5'],
                        nargs='?', default=None,
                        help='Which line to plot (omit to plot all)')
    parser.add_argument('--stage', choices=['topo', 'processed', 'stitched'],
                        default=None,
                        help='Processing stage to load (default: best available)')
    parser.add_argument('--velocity', type=float, default=V_DEFAULT,
                        help='Wave velocity in m/ns (default: {})'.format(V_DEFAULT))
    parser.add_argument('--clip', type=float, default=98.0,
                        help='Amplitude clip percentile (default: 98)')
    parser.add_argument('--out', type=str, default=None,
                        help='Output PNG path (default: auto)')
    args = parser.parse_args()

    lines    = [args.line] if args.line else ['Line2', 'Line3', 'Line5']
    out_path = Path(args.out) if args.out else None
    for line in lines:
        make_figure(line, args.stage, args.velocity, args.clip, out_path)


if __name__ == '__main__':
    main()

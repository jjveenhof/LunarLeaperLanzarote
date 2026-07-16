"""
plot_processing_steps.py
One figure showing every processing step of a profile, stacked top to bottom:
raw input first, then a panel after each step that actually ran (skipped steps
-- e.g. whitening/SVD when off -- get no panel). Built for the supervisors'
"show every processing step for one line" request.

Reuses the real pipeline: segment time-zero pre-alignment + apply_processing
(with capture=...) on the raw stitched NPZ and the saved params JSON, so the
panels are exactly the intermediates the pipeline produces -- not a re-
implementation.

Display: per-panel display gain (params gain_exponent) and percentile clip
(params clip_percentile), flip_x applied so North is left, N/S labels on the
bottom panel. Amplitudes are display-gained for visibility; the underlying
processing is gain-free (see gpr_processing docstring).

Usage:
    python plot_processing_steps.py                # default: Line3_50MHz
    python plot_processing_steps.py Line5_50MHz
Output:
    Results/GPR/Steps/{stem}_processing_steps.png (+ title-free thesis PDF)
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
import segment_tzero as seg_tz
from gpr_processing import apply_processing, display_gain
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure

HERE       = Path(__file__).parent
STITCH_DIR = HERE / '../../Data/GPR/Stitched'
PROC_DIR   = HERE / '../../Data/GPR/Processed'
OUT_DIR    = HERE / '../../Results/GPR/Steps'

CMAP = 'seismic'

# Steps plotted UNGAINED and UNCLIPPED (symmetric true-amplitude scale): the
# early steps are about acquisition state (DC level, sign, trace equalisation),
# where gain/clip would just amplify the wow. From dewow onward the panels get
# the params display gain + percentile clip like every other report figure.
UNGAINED_STEPS = {'raw', 'polarity', 'normalize'}


def step_title(label, params):
    """Panel title: step name + the parameters that step used."""
    if label == 'raw':
        return 'raw (stitched)'
    if label == 'polarity':
        return 'polarity flip (convention: harmonised to FlowerPetals)'
    if label == 'normalize':
        end = params.get('norm_end_ns')
        return 'trace normalisation (RMS window {:.0f}-{:.0f} ns)'.format(
            float(params.get('norm_start_ns', 50.0)),
            float(end) if end is not None else float('nan'))
    if label == 'dewow':
        return 'dewow (running mean, window {} samples)'.format(
            int(params['dewow_window']))
    if label == 'tzero':
        return 'time-zero shift ({:+.2f} samples) + trim'.format(
            float(params.get('tzero_shift', 0.0)))
    if label == 'crop':
        return 'crop to {:.0f} ns'.format(float(params['max_time_ns']))
    if label == 'whiten':
        return 'spectral whitening (window {} bins)'.format(
            int(params['whiten_window']))
    if label == 'bandpass':
        return 'bandpass {:.0f}-{:.0f} MHz (Butterworth, order 4)'.format(
            float(params['bandpass_low']), float(params['bandpass_high']))
    if label == 'svd':
        return 'SVD removal (first {} component(s))'.format(int(params['n_svd']))
    return label


def make_figure(stem):
    raw_npz  = STITCH_DIR / (stem + '_raw.npz')
    raw_json = STITCH_DIR / (stem + '_raw.json')
    params_p = PROC_DIR / (stem + '_params.json')
    for p in (raw_npz, raw_json, params_p):
        if not p.exists():
            sys.exit('Not found: ' + str(p))

    with np.load(str(raw_npz)) as npz:
        data      = npz['data'].astype(np.float64)
        dist_axis = npz['dist_axis'].astype(np.float64)
        time_axis = npz['time_axis'].astype(np.float64)
    with open(str(raw_json), encoding='utf-8') as f:
        info = json.load(f)
    with open(str(params_p), encoding='utf-8') as f:
        params = json.load(f)

    # exactly the pipeline path: segment pre-alignment, then apply_processing
    data = seg_tz.align_segments(data, info, verbose=False)
    sfreq = info['samples'] / info['Total_time_window'] * 1000   # MHz
    steps = []
    apply_processing(data, time_axis, sfreq, params, capture=steps)

    gain_exp = float(params.get('gain_exponent', 0.0))
    clip_pct = float(params.get('clip_percentile', 99.5))
    flip_x   = bool(params.get('flip_x', False))

    n = len(steps)
    fig, axes = plt.subplots(n, 1, figsize=(6.1, 1.2 * n + 0.5), sharex=True)
    axes = np.atleast_1d(axes)

    for i, (ax, (label, d, t)) in enumerate(zip(axes, steps)):
        disp = d[:, ::-1] if flip_x else d
        if label in UNGAINED_STEPS:
            clip = float(np.max(np.abs(disp))) or 1.0     # true amplitudes
            note = 'ungained'
        else:
            disp = display_gain(disp, sfreq, gain_exp)
            clip = float(np.percentile(np.abs(disp), clip_pct)) or 1.0
            note = 'gain {:.1f}, clip {:.1f}%'.format(gain_exp, clip_pct)
        ax.imshow(disp, aspect='auto', cmap=CMAP, vmin=-clip, vmax=clip,
                  extent=[float(dist_axis[0]), float(dist_axis[-1]),
                          float(t[-1]), float(t[0])],
                  interpolation='nearest')
        ax.set_ylabel('TWT (ns)', fontsize=8)
        ax.tick_params(labelsize=8)
        ax.set_title('{}) {} [{}]'.format(chr(ord('a') + i),
                     step_title(label, params), note),
                     fontsize=8, loc='left')

    axes[-1].set_xlabel('Distance (m)', fontsize=8)
    if flip_x:
        axes[-1].text(0.01, 0.05, 'N', transform=axes[-1].transAxes, ha='left',
                      va='bottom', fontsize=10, fontweight='bold')
        axes[-1].text(0.99, 0.05, 'S', transform=axes[-1].transAxes, ha='right',
                      va='bottom', fontsize=10, fontweight='bold')
    # pretty label: "Line3_50MHz" -> "Line3 -- 50 MHz" (raw underscores render as
    # a raised mark in Computer Modern)
    _p = stem.split('_')
    pretty = '{} -- {}'.format(_p[0], _p[1].replace('MHz', ' MHz')) \
        if len(_p) == 2 else stem
    fig.suptitle('{} processing steps'.format(pretty), fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.985], h_pad=0.35)   # tight inter-panel gap

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / (stem + '_processing_steps.png')
    fig.savefig(str(out), dpi=180, bbox_inches='tight')
    thesis_path, _ = save_figure(fig, out.stem, 'GPR', vector=True, dpi=300,
                                 titles='auto')   # keep per-panel step titles
    plt.close(fig)
    print('Saved: {}'.format(out))
    print('thesis -> {}'.format(thesis_path))


def main():
    ap = argparse.ArgumentParser(description='Stacked figure of all processing '
                                             'steps for one profile.')
    ap.add_argument('stem', nargs='?', default='Line3_50MHz',
                    help='profile stem (default Line3_50MHz)')
    args = ap.parse_args()
    make_figure(args.stem)


if __name__ == '__main__':
    main()

"""
plot_l2_svd_whiten.py
Trial figure: does SVD/eigenimage removal or spectral whitening fix the Line2
100 MHz spectral notches (~75, ~160 MHz -- hardware artifact from the pulsEKKO
antenna housing; see Code/GPR/CLAUDE.md Current Focus, and
plot_l2_spectral_diagnostics.py for the baseline notch evidence)?

Both are OFF in the saved Line2_100MHz params (n_svd=0, whiten_window=0), so
this script re-runs the real pipeline (segment pre-alignment + apply_processing
on the raw stitched NPZ) with each knob trialled on top of the saved params,
one at a time. Not a proposal to change the saved params -- purely a check of
whether either treatment helps, for the appendix.

Top row: mean-trace amplitude spectrum (same machinery as
plot_l2_spectral_diagnostics.py -- FFT of the mean trace, linear, normalised to
own max), baseline vs each trial. Bottom row: the three radargrams themselves
(display-gained per params, each clipped at its own percentile) for a visual
check of side effects (does either treatment introduce artifacts / erase real
signal?).

Trial values are module constants below -- retune and rerun if a different
value should be shown.

Usage:
    python plot_l2_svd_whiten.py
"""

import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import segment_tzero as seg_tz
from gpr_processing import apply_processing, display_gain
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure

HERE       = Path(__file__).parent
STITCH_DIR = HERE / '../../Data/GPR/Stitched'
PROC_DIR   = HERE / '../../Data/GPR/Processed'
OUT_DIR    = HERE / '../../Results/GPR/Spectral'

STEM = 'Line2_100MHz'

TRIAL_N_SVD         = 1   # components removed; higher = more aggressive (risks real signal)
TRIAL_WHITEN_WINDOW = 5   # smoothing bins; lower = flatter spectrum (more aggressive)

FMAX_MHZ = 300.0   # crop displayed spectrum to this frequency (matches diagnostics script)
CMAP     = 'seismic'
NOTCH_FREQS_MHZ = [75.0, 160.0]   # approx L2 100MHz hardware notches (see CLAUDE.md);
                                  # guide lines on the mean-spectrum panels only


def mean_trace_spectrum(data, dt_ns):
    """FFT of the MEAN TRACE -- matches plot_l2_spectral_diagnostics.py exactly."""
    n_s  = data.shape[0]
    spec = np.abs(np.fft.rfft(data.mean(axis=1)))
    freq = np.fft.rfftfreq(n_s, d=dt_ns) * 1000.0   # cycles/ns (GHz) -> MHz
    return spec, freq


def run_variant(data, time_axis, sfreq, base_params, **overrides):
    params = dict(base_params)
    params.update(overrides)
    processed, t_out = apply_processing(data, time_axis, sfreq, params)
    return processed, t_out, params


def make_figure():
    raw_npz  = STITCH_DIR / (STEM + '_raw.npz')
    raw_json = STITCH_DIR / (STEM + '_raw.json')
    params_p = PROC_DIR / (STEM + '_params.json')
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
        base_params = json.load(f)

    data  = seg_tz.align_segments(data, info, verbose=False)
    sfreq = info['samples'] / info['Total_time_window'] * 1000   # MHz

    base, t_base, p_base = run_variant(data, time_axis, sfreq, base_params)
    svd,  t_svd,  p_svd  = run_variant(data, time_axis, sfreq, base_params,
                                        n_svd=TRIAL_N_SVD)
    whit, t_whit, p_whit = run_variant(data, time_axis, sfreq, base_params,
                                        whiten_window=TRIAL_WHITEN_WINDOW)

    # --- mean-trace spectra, linear, own-max normalised ---
    dt = float(t_base[1] - t_base[0])
    sB, fB = mean_trace_spectrum(base, dt)
    sS, fS = mean_trace_spectrum(svd,  float(t_svd[1] - t_svd[0]))
    sW, fW = mean_trace_spectrum(whit, float(t_whit[1] - t_whit[0]))
    nB, nS, nW = sB / (sB.max() or 1.0), sS / (sS.max() or 1.0), sW / (sW.max() or 1.0)

    gain_exp = float(base_params.get('gain_exponent', 0.0))
    clip_pct = float(base_params.get('clip_percentile', 99.5))

    fig = plt.figure(figsize=(7.2, 7.6))
    gs = gridspec.GridSpec(2, 6, height_ratios=[1.0, 1.25], hspace=0.40, wspace=0.9)

    # --- top row: spectrum comparisons ---
    ax_a = fig.add_subplot(gs[0, 0:3])
    ax_a.plot(fB, nB, color='#7f7f7f', lw=1.3, label='baseline (SVD off)')
    ax_a.plot(fS, nS, color='#d62728', lw=1.3,
              label='SVD removed (n={})'.format(TRIAL_N_SVD))
    for nf in NOTCH_FREQS_MHZ:
        ax_a.axvline(nf, color='black', lw=0.8, ls='dashed', zorder=1)
    ax_a.set_xlim(0, FMAX_MHZ)
    ax_a.set_ylim(0, 1.08)
    ax_a.set_xlabel('Frequency (MHz)', fontsize=9)
    ax_a.set_ylabel('Normalised amplitude', fontsize=9)
    ax_a.set_title('a) Mean spectrum -- SVD removal', fontsize=9, loc='left')
    ax_a.legend(fontsize=7, loc='upper right', frameon=False)
    ax_a.tick_params(labelsize=8)

    ax_b = fig.add_subplot(gs[0, 3:6])
    ax_b.plot(fB, nB, color='#7f7f7f', lw=1.3, label='baseline (whiten=0)')
    ax_b.plot(fW, nW, color='#1f77b4', lw=1.3,
              label='whitened (window={})'.format(TRIAL_WHITEN_WINDOW))
    for nf in NOTCH_FREQS_MHZ:
        ax_b.axvline(nf, color='black', lw=0.8, ls='dashed', zorder=1)
    ax_b.set_xlim(0, FMAX_MHZ)
    ax_b.set_ylim(0, 1.08)
    ax_b.set_xlabel('Frequency (MHz)', fontsize=9)
    ax_b.set_title('b) Mean spectrum -- spectral whitening', fontsize=9, loc='left')
    ax_b.legend(fontsize=7, loc='upper right', frameon=False)
    ax_b.tick_params(labelsize=8)

    # --- bottom row: the three radargrams, own-percentile clip each. Baseline and
    # SVD-removed get the params display gain like every other report figure;
    # whitening already flattens the amplitude spectrum (that's what it does), so
    # the time-based display gain has nothing left to compensate for and just
    # blows up trailing noise -- shown ungained.
    panels = [('c) baseline', base, t_base, True),
              ('d) SVD removed', svd, t_svd, True),
              ('e) whitened (ungained)', whit, t_whit, False)]
    axes_r = [fig.add_subplot(gs[1, 0:2])]
    axes_r.append(fig.add_subplot(gs[1, 2:4], sharey=axes_r[0]))
    axes_r.append(fig.add_subplot(gs[1, 4:6], sharey=axes_r[0]))

    for ax, (title, d, t, gained) in zip(axes_r, panels):
        disp = display_gain(d, sfreq, gain_exp) if gained else d
        clip = float(np.percentile(np.abs(disp), clip_pct)) or 1.0
        ax.imshow(disp, aspect='auto', cmap=CMAP, vmin=-clip, vmax=clip,
                  extent=[float(dist_axis[0]), float(dist_axis[-1]),
                          float(t[-1]), float(t[0])],
                  interpolation='nearest')
        ax.set_title(title, fontsize=9, loc='left')
        ax.set_xlabel('Distance (m)', fontsize=9)
        ax.tick_params(labelsize=8)
    axes_r[0].set_ylabel('TWT (ns)', fontsize=9)
    plt.setp(axes_r[1].get_yticklabels(), visible=False)
    plt.setp(axes_r[2].get_yticklabels(), visible=False)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'Line2_svd_whiten_trial.png'
    fig.savefig(str(out), dpi=180, bbox_inches='tight')
    thesis_path, _ = save_figure(fig, out.stem, 'GPR', vector=True, dpi=300,
                                 titles='auto')
    plt.close(fig)
    print('Saved: {}'.format(out))
    print('thesis -> {}'.format(thesis_path))


if __name__ == '__main__':
    make_figure()

"""
plot_l2_spectral_diagnostics.py
Diagnoses the Line2 100 MHz spectral notches (~75, ~160 MHz -- hardware artifact
from the pulsEKKO antenna housing, not geology; see Code/GPR/CLAUDE.md Current
Focus) against a normal 100 MHz line (Line3) for the thesis appendix.

Machinery matches GPRProcessing.ipynb's "Mean proc." / "f,x Processed" panels
exactly (same QC cell that builds the live preview figure), so this is the same
evidence the notebook shows, not a re-derivation that could quietly differ:
  - data: the saved PROCESSED NPZ (post full apply_processing pipeline at the
    profile's saved params -- dewow, tzero, bandpass, etc; NOT raw, NOT gained
    -- gain is display-only and the notebook's spectra are computed pre-gain).
  - (a) mean amplitude spectrum: FFT of the MEAN TRACE (average traces in the
    time domain FIRST, then one FFT) -- np.fft.rfft(data.mean(axis=1)), exactly
    the notebook's sp_p. This is NOT the same as averaging per-trace spectra:
    time-domain averaging is close to coherent across traces (same antenna
    response every shot), so it suppresses incoherent noise BEFORE the FFT and
    a fixed-frequency hardware notch stays sharp; mean(|FFT|) never gets that
    cancellation (triangle inequality: mean(|FFT|) >= |FFT(mean)| always) and
    washes narrow notches out. LINEAR amplitude normalised to each curve's own
    max (0-1), matching the notebook -- not dB.
  - (b) f-x diagrams: per-trace |FFT| (no trace-averaging -- there's no
    coherent-average shortcut for a per-x view), LINEAR amplitude clipped at
    the notebook's F_X_CLIP_PCT (98th percentile) per panel.

No notch frequencies are marked on the figure -- read them off by eye.

Usage:
    python plot_l2_spectral_diagnostics.py
"""

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure

HERE     = Path(__file__).parent
PROC_DIR = HERE / '../../Data/GPR/Processed'
OUT_DIR  = HERE / '../../Results/GPR/Spectral'

LINE_A, FREQ_A, LABEL_A = 'Line2', '100MHz', 'Line2 -- 100 MHz (notched)'
LINE_B, FREQ_B, LABEL_B = 'Line3', '100MHz', 'Line3 -- 100 MHz (normal)'

FMAX_MHZ     = 300.0   # crop the displayed spectrum to this frequency (matches notebook)
F_X_CLIP_PCT = 98.0    # f-x linear colour clip percentile (matches notebook)


def load_processed(line, freq):
    stem = '{}_{}'.format(line, freq)
    p = PROC_DIR / (stem + '_processed.npz')
    if not p.exists():
        sys.exit('Not found: ' + str(p) + ' (run run_pipeline.py first)')
    with np.load(str(p)) as npz:
        data = npz['data'].astype(np.float64)
        t    = npz['time_axis'].astype(np.float64)
        x    = npz['dist_axis'].astype(np.float64)
    return data, t, x


def mean_trace_spectrum(data, dt_ns):
    """FFT of the MEAN TRACE (average in time domain first) -- matches the
    notebook's np.fft.rfft(np.mean(proc_ng, axis=1)) exactly."""
    n_s  = data.shape[0]
    spec = np.abs(np.fft.rfft(data.mean(axis=1)))
    freq = np.fft.rfftfreq(n_s, d=dt_ns) * 1000.0   # cycles/ns (GHz) -> MHz
    return spec, freq


def per_trace_spectrum(data, dt_ns):
    """Per-trace |rFFT| (n_freq, n_traces) and its frequency axis (MHz) -- for
    the f-x diagram, which needs the per-x resolution mean_trace_spectrum discards."""
    n_s  = data.shape[0]
    spec = np.abs(np.fft.rfft(data, axis=0))
    freq = np.fft.rfftfreq(n_s, d=dt_ns) * 1000.0
    return spec, freq


def make_figure():
    dA, tA, xA = load_processed(LINE_A, FREQ_A)
    dB, tB, xB = load_processed(LINE_B, FREQ_B)
    dtA = float(tA[1] - tA[0])
    dtB = float(tB[1] - tB[0])

    # (a) coherent mean-trace spectrum, linear amplitude norm to own max (0-1)
    meanA, mfreqA = mean_trace_spectrum(dA, dtA)
    meanB, mfreqB = mean_trace_spectrum(dB, dtB)
    normA = meanA / (meanA.max() or 1.0)
    normB = meanB / (meanB.max() or 1.0)

    # (b) per-trace spectra for the f-x view (no coherent-average shortcut here)
    specA, freqA = per_trace_spectrum(dA, dtA)
    specB, freqB = per_trace_spectrum(dB, dtB)

    fig = plt.figure(figsize=(6.1, 6.0))
    gs = gridspec.GridSpec(2, 2, height_ratios=[1.0, 1.1], hspace=0.38, wspace=0.10)

    # --- (a) mean amplitude spectrum, both lines overlaid ---
    axm = fig.add_subplot(gs[0, :])
    axm.plot(mfreqA, normA, color='#d62728', lw=1.3, label=LABEL_A)
    axm.plot(mfreqB, normB, color='#1f77b4', lw=1.3, label=LABEL_B)
    axm.set_xlim(0, FMAX_MHZ)
    axm.set_ylim(0, 1.08)
    axm.set_xlabel('Frequency (MHz)', fontsize=9)
    axm.set_ylabel('Normalised amplitude', fontsize=9)
    axm.set_title('a) Mean amplitude spectrum (processed, all traces)', fontsize=9, loc='left')
    axm.legend(fontsize=7, loc='upper right', frameon=False)
    axm.tick_params(labelsize=8)

    # --- (b) f-x diagrams, linear amplitude, own-percentile clip (per notebook) ---
    fmaskA = freqA <= FMAX_MHZ
    fmaskB = freqB <= FMAX_MHZ
    fxA, fxB = specA[fmaskA], specB[fmaskB]
    clipA = np.percentile(fxA, F_X_CLIP_PCT)
    clipB = np.percentile(fxB, F_X_CLIP_PCT)

    axfA = fig.add_subplot(gs[1, 0])
    axfB = fig.add_subplot(gs[1, 1], sharey=axfA)
    imA = axfA.imshow(fxA, aspect='auto', cmap='inferno', vmin=0, vmax=clipA,
                      origin='lower',
                      extent=[float(xA[0]), float(xA[-1]), 0, FMAX_MHZ])
    imB = axfB.imshow(fxB, aspect='auto', cmap='inferno', vmin=0, vmax=clipB,
                      origin='lower',
                      extent=[float(xB[0]), float(xB[-1]), 0, FMAX_MHZ])

    axfA.set_title('b) ' + LABEL_A, fontsize=9, loc='left')
    axfB.set_title(LABEL_B, fontsize=9, loc='left')
    axfA.set_xlabel('Distance (m)', fontsize=9)
    axfB.set_xlabel('Distance (m)', fontsize=9)
    axfA.set_ylabel('Frequency (MHz)', fontsize=9)
    plt.setp(axfB.get_yticklabels(), visible=False)
    axfA.tick_params(labelsize=8)
    axfB.tick_params(labelsize=8)

    cbA = fig.colorbar(imA, ax=axfA, fraction=0.046, pad=0.02)
    cbA.ax.tick_params(labelsize=7)
    cbB = fig.colorbar(imB, ax=axfB, fraction=0.046, pad=0.02)
    cbB.set_label('amplitude (clip {:.0f}pct)'.format(F_X_CLIP_PCT), fontsize=8)
    cbB.ax.tick_params(labelsize=7)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'Line2_spectral_diagnostics.png'
    fig.savefig(str(out), dpi=180, bbox_inches='tight')
    thesis_path, _ = save_figure(fig, out.stem, 'GPR', vector=True, dpi=300,
                                 titles='auto')
    plt.close(fig)
    print('Saved: {}'.format(out))
    print('thesis -> {}'.format(thesis_path))


if __name__ == '__main__':
    make_figure()

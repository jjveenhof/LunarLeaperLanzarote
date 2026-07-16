"""
gpr_processing.py
Core GPR processing pipeline, shared by GPRProcessing.ipynb and run_pipeline.py.

Import:
    from gpr_processing import apply_processing

Call signature:
    processed, time_axis_out = apply_processing(data, time_axis, sfreq, params)

Parameters
----------
data          : ndarray (n_samples, n_traces)
time_axis     : ndarray (n_samples,)  in ns
sfreq         : float  sampling frequency in MHz
params        : dict -- keys and defaults below:

    polarity       int       default +1     acquisition convention (Tx/Rx swap);
                                            -1 flips the global sign
    dewow_window   int       required
    tzero_shift    float     default 0.0
    bandpass_low   float     required (MHz)
    bandpass_high  float     required (MHz)
    normalize      bool      default False
    norm_start_ns  float     default 50.0 (start of norm window in ns)
    norm_end_ns    float|None default None (end of norm window in ns; None = full trace)
    max_time_ns    float|None default None (no crop)
    whiten_window  int       default 0      smoothed whitening window (bins); 0 = off
    n_svd          int       default 0      SVD components to remove; 0 = off

Processing order
----------------
polarity -> normalize -> dewow -> time-zero shift + trim -> max-time crop ->
whitening -> bandpass -> SVD removal

Polarity is a global sign correcting the acquisition convention (the antenna
Tx/Rx were sometimes swapped, flipping recorded polarity).  It is baked into the
saved NPZ so every downstream consumer shares one convention; the chosen value
is recorded per profile in the params JSON.

Gain is NOT part of processing -- it is a display-only enhancement applied at
render time (see display_gain).  Saved NPZs therefore hold raw, un-gained
amplitudes; gain_exponent in the params JSON records the intended display gain.
"""

import numpy as np
from scipy.ndimage import shift as ndshift


def display_gain(data, sfreq, exponent):
    """
    Linear time gain for DISPLAY only: multiplies each sample by
    travel_time ** exponent (gdp 'linear' gain).  Never baked into saved data.

    data     : ndarray (n_samples, n_traces)
    sfreq    : sampling frequency in MHz
    exponent : gain exponent; <= 0 returns the data unchanged.
    """
    if exponent is None or exponent <= 0:
        return data
    from gdp.preprocessing.gain import apply_gain as _gain
    gained, _ = _gain(data, sfreq, 'linear', exponent=float(exponent))
    return gained


def apply_processing(data, time_axis, sfreq, params, capture=None):
    """See module docstring. If `capture` is a list, a ('step label', data copy,
    time-axis copy) snapshot is appended for the raw input and after each step
    that actually RAN (skipped steps leave no entry) -- used by
    plot_processing_steps.py to show the pipeline stage by stage."""
    from gdp.preprocessing.filtering import dewow as _dewow, filter_data
    from gdp.preprocessing.normalizing import normalize_data

    processed     = data.copy()
    n_orig        = processed.shape[0]
    time_axis_out = time_axis.copy()

    def _cap(label):
        if capture is not None:
            capture.append((label, processed.copy(), time_axis_out.copy()))

    _cap('raw')

    # 0. polarity convention (Tx/Rx swap): global sign, recorded per profile
    if float(params.get('polarity', 1.0)) < 0:
        processed = -processed
        _cap('polarity')

    # 1. tracewise-RMS normalisation
    if params.get('normalize', False):
        norm_start_ns = float(params.get('norm_start_ns', 50.0))
        norm_end_ns   = params.get('norm_end_ns', None)
        start_idx = int(np.searchsorted(time_axis, norm_start_ns))
        end_idx   = int(np.searchsorted(time_axis, float(norm_end_ns))) \
                    if norm_end_ns is not None else n_orig
        end_idx   = min(max(end_idx, start_idx + 1), n_orig)
        processed = normalize_data(processed, typ='tracewise-rms-window',
                                   window=(start_idx, end_idx))
        _cap('normalize')

    # 2. dewow
    processed = _dewow(processed, window_length=int(params['dewow_window']))
    _cap('dewow')

    # 3. time-zero shift + trailing-zero trim
    tzero = float(params.get('tzero_shift', 0.0))
    if tzero != 0:
        processed = ndshift(processed, (tzero, 0), order=1, mode='constant', cval=0)
        trim = max(0, -int(tzero))
        if trim > 0:
            processed     = processed[:n_orig - trim, :]
            time_axis_out = time_axis_out[:n_orig - trim]
        _cap('tzero')

    # 4. max-time crop
    max_time_ns = params.get('max_time_ns', None)
    if max_time_ns and float(max_time_ns) > 0:
        mask          = time_axis_out <= float(max_time_ns)
        processed     = processed[mask, :]
        time_axis_out = time_axis_out[mask]
        _cap('crop')

    # 5. spectral whitening (before bandpass)
    whiten_window = int(params.get('whiten_window', 0))
    if whiten_window > 0:
        from scipy.ndimage import uniform_filter1d
        n_s        = processed.shape[0]
        spec       = np.fft.rfft(processed, axis=0)
        amp_smooth = uniform_filter1d(np.abs(spec), size=whiten_window, axis=0)
        processed  = np.fft.irfft(
            spec / np.maximum(amp_smooth, 1e-15),
            n=n_s, axis=0)
        _cap('whiten')

    # 6. bandpass
    processed = filter_data(
        processed,
        (float(params['bandpass_low']), float(params['bandpass_high'])),
        sfreq, 'bandpass', N=4)
    _cap('bandpass')

    # 7. SVD removal
    n_svd = int(params.get('n_svd', 0))
    if n_svd > 0:
        from gdp.preprocessing.image_processing import remove_svd
        processed, _ = remove_svd(processed, low_s=0, high_s=n_svd)
        _cap('svd')

    return processed, time_axis_out

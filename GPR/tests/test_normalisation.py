"""
test_normalisation.py
Real pytest checks (previously a print-only demo that asserted nothing and was
never collected -- rewritten for phase-2 handover).

Locks the gdp normalisation behaviour the pipeline relies on
(see Code/GPR/README.md Conventions): `tracewise-rms-window` computes the scaling
factor from ONLY the window region and applies it to the full trace, whereas the
plain `tracewise-rms` type IGNORES the window parameter entirely.

gdp is imported normally (it is a pinned pip install in the project env); no
sys.path bootstrap is needed. See Code/GPR/README.md "External dependency".

Synthetic setup: 2 traces, each a strong early direct wave (trace 1 = 8x, trace 2
= 4x) plus an identical weak late reflection. The window covers the late times
only, so window-norm should equalise the two reflections while plain-rms should
not.
"""

import numpy as np
from gdp.preprocessing.normalizing import normalize_data

DIRECT_END = 40
N_SAMPLES = 200


def _synthetic():
    """2-trace section: unequal direct waves, identical late reflections."""
    data = np.zeros((N_SAMPLES, 2))
    t = np.arange(DIRECT_END)
    t2 = np.arange(N_SAMPLES - DIRECT_END)
    data[:DIRECT_END, 0] = 8.0 * np.sin(2 * np.pi * t / 10)   # trace 1 direct = 8
    data[:DIRECT_END, 1] = 4.0 * np.sin(2 * np.pi * t / 10)   # trace 2 direct = 4
    data[DIRECT_END:, 0] = 1.0 * np.sin(2 * np.pi * t2 / 20)  # identical late
    data[DIRECT_END:, 1] = 1.0 * np.sin(2 * np.pi * t2 / 20)  # reflections
    return data


def _rms(x):
    return float(np.sqrt(np.mean(x ** 2)))


def test_window_norm_equalises_reflections():
    """tracewise-rms-window scales from the window, so the two identical late
    reflections come out with equal RMS despite unequal direct waves."""
    data = _synthetic()
    out = normalize_data(data.copy(), typ='tracewise-rms-window',
                         window=(DIRECT_END, N_SAMPLES))
    r1 = _rms(out[DIRECT_END:, 0])
    r2 = _rms(out[DIRECT_END:, 1])
    assert abs(r1 - r2) < 1e-6, (
        'window norm should equalise identical reflections; got {} vs {}'
        .format(r1, r2))


def test_plain_rms_ignores_window():
    """plain tracewise-rms ignores the window param -- the direct wave dominates
    each trace's full-trace RMS, so the reflections are NOT equalised. This is the
    documented gotcha the pipeline avoids by using tracewise-rms-window."""
    data = _synthetic()
    out = normalize_data(data.copy(), typ='tracewise-rms',
                         window=(DIRECT_END, N_SAMPLES))
    r1 = _rms(out[DIRECT_END:, 0])
    r2 = _rms(out[DIRECT_END:, 1])
    assert abs(r1 - r2) > 0.05, (
        'plain tracewise-rms should NOT equalise (window ignored); got {} vs {}'
        .format(r1, r2))

"""
test_apply_processing.py
Golden-master + invariant coverage for gpr_processing.apply_processing -- the core
of the whole GPR pipeline, previously untested (phase-2 F4).

- Regression lock: a fixed synthetic radargram + fixed params must reproduce a
  stored reference array (refs/apply_processing_ref.npz) within tolerance. Any
  numeric change to the processing chain (or the pinned gdp) trips this.
- Invariants that need no reference: the `capture=` stage labels match the enabled
  steps, a polarity flip negates the trace exactly, and the max-time crop trims to
  the expected sample count.

Regenerate the reference deliberately (only when a change is intended and reviewed):
    python tests/test_apply_processing.py --write-ref
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # Code/GPR
from gpr_processing import apply_processing

REF = Path(__file__).parent / 'refs' / 'apply_processing_ref.npz'

DT_NS = 0.8
N_SAMPLES = 500
N_TRACES = 30


def _synthetic_input():
    """Deterministic synthetic section (fixed rng): strong early direct wave,
    a mid reflector, and low noise. Returns (data, time_axis, sfreq_MHz)."""
    rng = np.random.default_rng(0)
    t = np.arange(N_SAMPLES)
    data = np.zeros((N_SAMPLES, N_TRACES))
    direct = np.exp(-((t - 20) ** 2) / (2 * 6.0 ** 2)) * np.sin(2 * np.pi * t / 8)
    refl = np.exp(-((t - 180) ** 2) / (2 * 12.0 ** 2)) * np.sin(2 * np.pi * t / 12)
    for j in range(N_TRACES):
        amp = 6.0 + 0.1 * j
        data[:, j] = amp * direct + 1.0 * refl + 0.02 * rng.standard_normal(N_SAMPLES)
    time_axis = t * DT_NS
    sfreq = 1000.0 / DT_NS   # MHz
    return data, time_axis, sfreq


def _params():
    """Fixed params exercising polarity, normalize, dewow, tzero(+trim), crop,
    bandpass. Whitening and SVD deliberately OFF (so capture must omit them)."""
    return {
        'polarity': 1,
        'normalize': True, 'norm_start_ns': 60.0, 'norm_end_ns': 320.0,
        'dewow_window': 25,
        'tzero_shift': -6.0,          # negative -> trailing-zero trim
        'max_time_ns': 300.0,         # crop
        'bandpass_low': 40.0, 'bandpass_high': 200.0,
        'whiten_window': 0, 'n_svd': 0,
    }


def _run(params=None):
    data, time_axis, sfreq = _synthetic_input()
    p = _params()
    if params:
        p.update(params)
    steps = []
    out, t_out = apply_processing(data, time_axis, sfreq, p, capture=steps)
    return out, t_out, steps


def test_regression_matches_reference():
    if not REF.exists():
        raise AssertionError('reference missing: run '
                             '`python tests/test_apply_processing.py --write-ref`')
    out, t_out, _ = _run()
    with np.load(str(REF)) as ref:
        assert out.shape == ref['data'].shape, 'shape drift {} vs {}'.format(
            out.shape, ref['data'].shape)
        assert np.allclose(out, ref['data'], rtol=1e-9, atol=1e-9), \
            'apply_processing numeric output changed vs stored reference'
        assert np.allclose(t_out, ref['time_axis'], rtol=1e-9, atol=1e-9)


def test_capture_labels_match_enabled_steps():
    _, _, steps = _run()
    labels = [lbl for (lbl, _d, _t) in steps]
    # enabled: raw + polarity? polarity=+1 so NO polarity snapshot; normalize,
    # dewow, tzero, crop, bandpass ran; whiten/svd off.
    assert labels[0] == 'raw'
    for expected in ('normalize', 'dewow', 'tzero', 'crop', 'bandpass'):
        assert expected in labels, 'missing enabled step {}'.format(expected)
    for absent in ('whiten', 'svd', 'polarity'):
        assert absent not in labels, 'unexpected step {} (should be off)'.format(absent)


def test_polarity_flip_negates_exactly():
    out_pos, _, _ = _run({'polarity': 1})
    out_neg, _, _ = _run({'polarity': -1})
    assert np.allclose(out_neg, -out_pos, rtol=1e-9, atol=1e-9), \
        'polarity=-1 must be the exact negation of polarity=+1'


def test_crop_trims_to_max_time():
    out, t_out, _ = _run()
    assert t_out.max() <= 300.0 + 1e-9, 'crop left samples past max_time_ns'
    assert out.shape[0] == t_out.shape[0], 'data/time length mismatch after crop'


def _write_ref():
    REF.parent.mkdir(parents=True, exist_ok=True)
    out, t_out, _ = _run()
    np.savez(str(REF), data=out, time_axis=t_out)
    print('wrote reference {}  shape={}'.format(REF, out.shape))


if __name__ == '__main__':
    if '--write-ref' in sys.argv:
        _write_ref()
    else:
        print('run with --write-ref to (re)generate the golden reference')

"""
Tests for topo_correction.py

Run from any directory:
    pytest Code/GPR/tests/test_topo_correction.py -v

Tests that require real data files are skipped automatically if the files
are not present (marked with @pytest.mark.skipif).
"""

import sys
import json
import tempfile
import pytest
import numpy as np
from pathlib import Path

# Make topo_correction importable from the parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))
import topo_correction as tc

# Paths to real data files
_DATA = Path(__file__).parent / '../../../Data'
GNSS_CSV    = (_DATA / 'GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv').resolve()
GNSS_FP_CSV = (_DATA / 'GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv').resolve()
PROC_DIR    = (_DATA / 'GPR/Processed').resolve()

have_gnss    = GNSS_CSV.exists()
have_gnss_fp = GNSS_FP_CSV.exists()
have_proc    = PROC_DIR.exists()


# =============================================================================
# load_gnss
# =============================================================================

@pytest.mark.skipif(not have_gnss, reason='Lines GNSS CSV not found')
def test_load_gnss_drops_empty_line_rows():
    df = tc.load_gnss(GNSS_CSV)
    # Every row must have a non-empty Line value
    assert df['Line'].notna().all()
    assert (df['Line'].astype(str).str.strip() != '').all()


@pytest.mark.skipif(not have_gnss, reason='Lines GNSS CSV not found')
def test_load_gnss_line_column_is_int():
    df = tc.load_gnss(GNSS_CSV)
    assert df['Line'].dtype in (int, 'int64', 'int32')


@pytest.mark.skipif(not have_gnss, reason='Lines GNSS CSV not found')
def test_load_gnss_inspect(capsys):
    """Print the loaded DataFrame for visual inspection. Run with: pytest -s"""
    df = tc.load_gnss(GNSS_CSV)
    with capsys.disabled():
        print('\n--- load_gnss output ({} rows) ---'.format(len(df)))
        print(df.to_string())
        print('---')


@pytest.mark.skipif(not have_gnss, reason='Lines GNSS CSV not found')
def test_load_gnss_contains_expected_lines():
    df = tc.load_gnss(GNSS_CSV)
    lines = set(df['Line'].unique())
    assert {2, 3, 5}.issubset(lines), 'Expected lines 2, 3, 5 in GNSS data'


# =============================================================================
# load_gnss_fp
# =============================================================================

@pytest.mark.skipif(not have_gnss_fp, reason='FlowerPetals GNSS CSV not found')
def test_load_gnss_fp_only_fp_lines():
    df = tc.load_gnss_fp(GNSS_FP_CSV)
    assert set(df['Line'].unique()).issubset({'FP1', 'FP2', 'FP3'})


@pytest.mark.skipif(not have_gnss_fp, reason='FlowerPetals GNSS CSV not found')
def test_load_gnss_fp_no_edge_orient_plumb():
    df = tc.load_gnss_fp(GNSS_FP_CSV)
    assert 'Edge'  not in df['Line'].values
    assert 'Orient' not in df['Line'].values
    assert 'Plumb' not in df['Line'].values


@pytest.mark.skipif(not have_gnss_fp, reason='FlowerPetals GNSS CSV not found')
def test_load_gnss_fp_all_three_petals_present():
    df = tc.load_gnss_fp(GNSS_FP_CSV)
    assert {'FP1', 'FP2', 'FP3'}.issubset(set(df['Line'].unique()))


# =============================================================================
# build_elevation_interp
# =============================================================================

@pytest.mark.skipif(not have_gnss, reason='Lines GNSS CSV not found')
def test_build_interp_line2_returns_callable():
    df = tc.load_gnss(GNSS_CSV)
    fn = tc.build_elevation_interp(df, 2)
    assert callable(fn)


@pytest.mark.skipif(not have_gnss, reason='Lines GNSS CSV not found')
def test_build_interp_line2_returns_realistic_elevations():
    df = tc.load_gnss(GNSS_CSV)
    fn = tc.build_elevation_interp(df, 2)
    # Lanzarote elevations are roughly 90-110 m asl
    elev = fn(np.array([0.0, 10.0, 30.0]))
    assert np.all(elev > 50), 'Elevations unexpectedly low'
    assert np.all(elev < 300), 'Elevations unexpectedly high'


@pytest.mark.skipif(not have_gnss, reason='Lines GNSS CSV not found')
def test_build_interp_line3_metre_column():
    df = tc.load_gnss(GNSS_CSV)
    fn = tc.build_elevation_interp(df, 3)
    elev = fn(np.array([0.0, 60.0, 110.0]))
    assert np.all(np.isfinite(elev))


@pytest.mark.skipif(not have_gnss_fp, reason='FlowerPetals GNSS CSV not found')
def test_build_interp_fp1_trailing_digit_extraction():
    df = tc.load_gnss_fp(GNSS_FP_CSV)
    fn = tc.build_elevation_interp(df, 'FP1')
    # FP1 spans roughly metres 0-82
    elev = fn(np.array([0.0, 40.0, 80.0]))
    assert np.all(np.isfinite(elev))
    assert np.all(elev > 50)


@pytest.mark.skipif(not have_gnss_fp, reason='FlowerPetals GNSS CSV not found')
def test_build_interp_fp_extrapolation_clamps():
    # Querying outside the measured range should return the endpoint value,
    # not NaN or an error (fill_value='extrapolate' is NOT used -- it clamps).
    df = tc.load_gnss_fp(GNSS_FP_CSV)
    fn = tc.build_elevation_interp(df, 'FP1')
    elev_before = fn(np.array([-10.0]))
    elev_after  = fn(np.array([200.0]))
    assert np.isfinite(elev_before[0])
    assert np.isfinite(elev_after[0])


# =============================================================================
# dist_to_gnss_metre
# =============================================================================

def _d(n=5):
    return np.linspace(0, 10, n)


def test_dist_line2_100MHz_no_offset():
    d = _d()
    result = tc.dist_to_gnss_metre('Line2_100MHz', d)
    np.testing.assert_array_equal(result, d)


def test_dist_line2_50MHz_no_offset():
    d = _d()
    result = tc.dist_to_gnss_metre('Line2_50MHz', d)
    np.testing.assert_array_equal(result, d)


def test_dist_line3_50MHz_adds_110cm():
    d = _d()
    result = tc.dist_to_gnss_metre('Line3_50MHz', d)
    np.testing.assert_allclose(result, d + 1.1)


def test_dist_line3_100MHz_offset_60m_plus_425cm():
    d = _d()
    result = tc.dist_to_gnss_metre('Line3_100MHz', d)
    np.testing.assert_allclose(result, 60.0 + d + 0.425)


def test_dist_line5_50MHz_adds_110cm():
    d = _d()
    result = tc.dist_to_gnss_metre('Line5_50MHz', d)
    np.testing.assert_allclose(result, d + 1.1)


def test_dist_line5_100MHz_forward_direction():
    d = _d()
    result = tc.dist_to_gnss_metre('Line5_100MHz', d)
    np.testing.assert_allclose(result, 30.0 + d + 0.425)


def test_dist_flowerpetal_adds_110cm():
    d = _d()
    for key in ('FlowerPetal1_50MHz', 'FlowerPetal2_50MHz', 'FlowerPetal3_50MHz'):
        result = tc.dist_to_gnss_metre(key, d)
        np.testing.assert_allclose(result, d + 1.1, err_msg=key)


def test_dist_unknown_profile_raises():
    with pytest.raises(ValueError):
        tc.dist_to_gnss_metre('NonExistent_50MHz', _d())


# =============================================================================
# apply_topo_correction
# =============================================================================

def _synthetic_radargram(n_samples=200, n_traces=10, reflector_samples=None):
    """Flat radargram with a single reflector row set to 1."""
    data = np.zeros((n_samples, n_traces))
    if reflector_samples is not None:
        for i, s in enumerate(reflector_samples):
            if 0 <= s < n_samples:
                data[s, i] = 1.0
    return data


def test_flat_terrain_no_shift():
    """Flat terrain: all elevations equal, all shifts zero, data unchanged."""
    n_traces = 8
    data      = np.random.randn(100, n_traces)
    time_axis = np.linspace(0, 100, 100)
    elevations = np.full(n_traces, 100.0)
    v = 0.1

    corrected, shifts, ref_elev = tc.apply_topo_correction(data, time_axis, elevations, v)

    assert np.all(shifts == 0)
    np.testing.assert_allclose(corrected, data, atol=1e-12)
    assert ref_elev == pytest.approx(100.0)


def test_correction_flattens_constant_absolute_reflector():
    """
    A flat reflector at constant absolute elevation should become horizontal
    after correction.

    Setup:
        v = 0.1 m/ns, dt = 1 ns/sample
        High trace: antenna at 100 m, reflector at 95 m -> depth 5 m -> sample 100
        Low trace:  antenna at  99 m, reflector at 95 m -> depth 4 m -> sample  80
    After correction the reflector should appear at sample 100 in both traces.
    """
    v         = 0.1           # m/ns
    dt        = 1.0           # ns/sample
    n_samples = 200
    n_traces  = 2

    elevations = np.array([100.0, 99.0])  # high, low
    ref_elev   = elevations.max()          # 100 m

    # place reflector at expected raw sample positions
    reflector_depth_abs = 95.0  # absolute elevation of reflector
    raw_samples = [
        int(round(2 * (elevations[i] - reflector_depth_abs) / v / dt))
        for i in range(n_traces)
    ]  # [100, 80]
    assert raw_samples == [100, 80], 'Test setup error'

    data = _synthetic_radargram(n_samples, n_traces, raw_samples)
    time_axis = np.arange(n_samples, dtype=float) * dt

    corrected, shifts, ref = tc.apply_topo_correction(data, time_axis, elevations, v)

    assert ref == pytest.approx(100.0)
    # Low trace should be shifted DOWN by 20 samples (dz = 1 m -> 20 samples)
    assert shifts[0] == 0
    assert shifts[1] == 20

    # Reflector should be at sample 100 in both traces after correction
    assert corrected[100, 0] == pytest.approx(1.0)
    assert corrected[100, 1] == pytest.approx(1.0)


def test_correction_uses_max_elevation_as_datum():
    """Trace at maximum elevation must have shift = 0."""
    n_traces   = 5
    elevations = np.array([98.0, 99.0, 102.0, 100.0, 97.0])
    data       = np.random.randn(100, n_traces)
    time_axis  = np.linspace(0, 100, 100)

    _, shifts, ref_elev = tc.apply_topo_correction(data, time_axis, elevations, v=0.1)

    assert ref_elev == pytest.approx(102.0)
    max_idx = np.argmax(elevations)
    assert shifts[max_idx] == 0


def test_correction_shifts_are_non_negative():
    """All shifts must be >= 0 (data only moves down, never up)."""
    elevations = np.array([100.0, 98.5, 101.2, 99.0])
    data       = np.random.randn(200, 4)
    time_axis  = np.linspace(0, 200, 200)

    _, shifts, _ = tc.apply_topo_correction(data, time_axis, elevations, v=0.1)
    assert np.all(shifts >= 0)


def test_correction_larger_velocity_gives_smaller_shift():
    """Higher velocity -> less time per metre -> smaller sample shift."""
    elevations = np.array([100.0, 98.0])
    data       = np.random.randn(200, 2)
    time_axis  = np.linspace(0, 200, 200)

    _, shifts_slow, _ = tc.apply_topo_correction(data, time_axis, elevations, v=0.05)
    _, shifts_fast, _ = tc.apply_topo_correction(data, time_axis, elevations, v=0.20)

    assert shifts_slow[1] > shifts_fast[1]


# =============================================================================
# Integration: correct_profile (skipped if no processed data)
# =============================================================================

def _first_processed_npz():
    """Return the first *_processed.npz in PROC_DIR, or None."""
    if not PROC_DIR.exists():
        return None
    files = sorted(PROC_DIR.glob('*_processed.npz'))
    return files[0] if files else None


@pytest.mark.skipif(
    not have_gnss or not have_gnss_fp or _first_processed_npz() is None,
    reason='Processed data or GNSS files not available'
)
def test_correct_profile_creates_output_files(tmp_path):
    """End-to-end: correct_profile writes NPZ and PNG to a temp directory."""
    # Redirect output dirs to tmp_path so we don't pollute real results
    orig_topo = tc.TOPO_DIR
    orig_fig  = tc.FIG_DIR
    tc.TOPO_DIR = tmp_path / 'Topo'
    tc.FIG_DIR  = tmp_path / 'Figs'

    try:
        npz_path = _first_processed_npz()
        gnss_lines_df = tc.load_gnss(GNSS_CSV)
        gnss_fp_df    = tc.load_gnss_fp(GNSS_FP_CSV)
        interp_cache  = {}
        tc.correct_profile(npz_path, gnss_lines_df, gnss_fp_df, interp_cache)

        npz_out = list((tmp_path / 'Topo').glob('*.npz'))
        png_out = list((tmp_path / 'Figs').glob('*.png'))
        assert len(npz_out) == 1, 'Expected one output NPZ'
        assert len(png_out) == 1, 'Expected one output PNG'

        # Check NPZ contains expected keys
        data = np.load(str(npz_out[0]))
        for key in ('data', 'dist_axis', 'time_axis', 'elevations', 'shifts', 'ref_elev'):
            assert key in data, 'Missing key: ' + key

    finally:
        tc.TOPO_DIR = orig_topo
        tc.FIG_DIR  = orig_fig

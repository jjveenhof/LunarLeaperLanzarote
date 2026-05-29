"""
run_pipeline.py
End-to-end GPR processing pipeline.

For each profile that has a saved _params.json (produced by GPRProcessing.ipynb),
this script re-applies exactly those parameters to the raw stitched data and runs
the topographic correction.  No manual interaction needed.

Prerequisites:
    - GPRProcessing.ipynb has been run at least once per profile to tune and
      save processing parameters.

Steps per profile:
    1. Load  Data/GPR/Stitched/{stem}_raw.npz  +  .json sidecar
    2. Apply processing (dewow, time-zero, bandpass, gain) from saved params
    3. Save  Data/GPR/Processed/{stem}_processed.npz  (overwrites previous)
    4. Apply topographic correction using GNSS data
    5. Save  Data/GPR/Topo/{stem}_topo.npz
           Results/GPR/Topo/{stem}_topo.png

Usage:
    python run_pipeline.py                   # all profiles with saved params
    python run_pipeline.py Line2_100MHz      # one profile
    python run_pipeline.py Line3_50MHz Line5_100MHz
"""

import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
from pathlib import Path
from scipy.ndimage import shift as ndshift

# Import topo_correction functions directly
sys.path.insert(0, str(Path(__file__).parent))
import topo_correction as tc

# ---- PATHS -------------------------------------------------------------------
HERE       = Path(__file__).parent
STITCH_DIR = HERE / '../../Data/GPR/Stitched'
PROC_DIR   = HERE / '../../Data/GPR/Processed'
# TOPO_DIR and FIG_DIR are taken from topo_correction.py
# ------------------------------------------------------------------------------


def apply_processing(data, time_axis, info, params):
    """
    Apply the processing chain to a raw data array.
    Mirrors the apply_processing() function in GPRProcessing.ipynb exactly.
    """
    from gdp.preprocessing.filtering import dewow as dewow_fn, filter_data
    from gdp.preprocessing.gain import apply_gain as apply_gain_fn
    from gdp.preprocessing.normalizing import normalize_data

    n_samples   = info['samples']
    time_window = info['Total_time_window']
    sfreq       = n_samples / time_window * 1000   # MHz

    processed = data.copy()

    n_orig        = processed.shape[0]
    time_axis_out = time_axis.copy()

    if params.get('normalize', False):
        norm_window = params.get('norm_window', None)
        win = (0, int(norm_window)) if norm_window and int(norm_window) < n_orig else (0, n_orig)
        processed = normalize_data(processed, typ='tracewise-rms', window=win)

    processed = dewow_fn(processed, window_length=params['dewow_window'])

    tzero = params['tzero_shift']
    if tzero != 0:
        processed = ndshift(processed, (tzero, 0), order=1,
                            mode='constant', cval=0)
        trim = max(0, -int(tzero))
        if trim > 0:
            processed = processed[:n_orig - trim, :]
            time_axis_out = time_axis_out[:n_orig - trim]

    max_time_ns = params.get('max_time_ns', None)
    if max_time_ns and max_time_ns > 0:
        mask          = time_axis_out <= max_time_ns
        processed     = processed[mask, :]
        time_axis_out = time_axis_out[mask]

    try:
        processed = filter_data(
            processed,
            (params['bandpass_low'], params['bandpass_high']),
            sfreq, 'bandpass', N=4
        )
    except Exception as e:
        print('    WARNING: bandpass failed: {}'.format(e))

    try:
        processed, _ = apply_gain_fn(processed, sfreq, 'linear',
                                     exponent=params['gain_exponent'])
    except Exception as e:
        print('    WARNING: gain failed: {}'.format(e))

    return processed, time_axis_out


def run_profile(stem, gnss_lines_df, gnss_fp_df, interp_cache):
    """Process one profile end-to-end."""
    raw_npz   = STITCH_DIR / (stem + '_raw.npz')
    raw_json  = STITCH_DIR / (stem + '_raw.json')
    params_json = PROC_DIR / (stem + '_params.json')

    # --- guard: params must exist ---
    if not params_json.exists():
        print('  [skip] {}: no params file -- run GPRProcessing.ipynb first'.format(stem))
        return False

    if not raw_npz.exists():
        print('  [skip] {}: raw NPZ not found ({})'.format(stem, raw_npz.name))
        return False

    print('  {}'.format(stem))

    # --- load raw ---
    with np.load(str(raw_npz)) as npz:
        data      = npz['data'].astype(np.float64)
        dist_axis = npz['dist_axis'].astype(np.float64)
        time_axis = npz['time_axis'].astype(np.float64)

    with open(str(raw_json), encoding='utf-8') as f:
        info = json.load(f)

    with open(str(params_json), encoding='utf-8') as f:
        params = json.load(f)

    print('    params: dewow={dewow_window}  tzero={tzero_shift:.2f}  '
          'bp={bandpass_low:.0f}-{bandpass_high:.0f} MHz  '
          'gain={gain_exponent:.1f}  v={velocity_mns:.3f} m/ns'.format(**params))

    # --- step 1: processing ---
    processed, time_axis_out = apply_processing(data, time_axis, info, params)

    PROC_DIR.mkdir(parents=True, exist_ok=True)
    out_proc = PROC_DIR / (stem + '_processed.npz')
    np.savez(str(out_proc), data=processed, dist_axis=dist_axis, time_axis=time_axis_out)
    print('    saved processed: {}'.format(out_proc.name))

    # --- step 2: topo correction ---
    # Use the processed NPZ path that topo_correction expects
    tc.correct_profile(out_proc, gnss_lines_df, gnss_fp_df, interp_cache)

    return True


def main(targets=None):
    # --- load GNSS ---
    if not tc.GNSS_CSV.exists():
        sys.exit('Lines GNSS CSV not found: ' + str(tc.GNSS_CSV))
    if not tc.GNSS_FP_CSV.exists():
        sys.exit('FlowerPetals GNSS CSV not found: ' + str(tc.GNSS_FP_CSV))

    gnss_lines_df = tc.load_gnss(tc.GNSS_CSV)
    gnss_fp_df    = tc.load_gnss_fp(tc.GNSS_FP_CSV)
    print('Loaded GNSS: {} line points, {} FlowerPetal points'.format(
        len(gnss_lines_df), len(gnss_fp_df)))

    # --- find profiles to process ---
    if targets:
        stems = [t.replace('_params.json', '').replace('_raw.npz', '')
                     .replace('_processed.npz', '')
                 for t in targets]
    else:
        if not PROC_DIR.exists():
            sys.exit('Processed dir not found -- run GPRProcessing.ipynb first')
        stems = sorted(
            p.name.replace('_params.json', '')
            for p in PROC_DIR.glob('*_params.json')
        )

    if not stems:
        print('No params files found in {}'.format(PROC_DIR))
        print('Run GPRProcessing.ipynb for each profile first.')
        return

    print('Profiles to process: {}\n'.format(', '.join(stems)))

    interp_cache = {}
    ok = skipped = 0
    for stem in stems:
        result = run_profile(stem, gnss_lines_df, gnss_fp_df, interp_cache)
        if result:
            ok += 1
        else:
            skipped += 1

    print('\nDone: {} processed, {} skipped.'.format(ok, skipped))


if __name__ == '__main__':
    main(sys.argv[1:] if len(sys.argv) > 1 else None)

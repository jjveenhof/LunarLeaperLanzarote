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
    2. Apply processing (dewow, time-zero, bandpass, ...) from saved params
       (gain is display-only and is NOT baked into the saved NPZ)
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

sys.path.insert(0, str(Path(__file__).parent))
import topo_correction as tc
from gpr_processing import apply_processing

# ---- PATHS -------------------------------------------------------------------
HERE       = Path(__file__).parent
STITCH_DIR = HERE / '../../Data/GPR/Stitched'
PROC_DIR   = HERE / '../../Data/GPR/Processed'
# TOPO_DIR and FIG_DIR are taken from topo_correction.py
# ------------------------------------------------------------------------------


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

    print('    dewow={}  tzero={:.2f}  bp={:.0f}-{:.0f}MHz  '
          'norm={}  whiten={}  svd={}  v={:.3f}m/ns'.format(
              params['dewow_window'],
              float(params.get('tzero_shift', 0.0)),
              float(params['bandpass_low']),
              float(params['bandpass_high']),
              params.get('normalize', False),
              params.get('whiten_window', 0),
              params.get('n_svd', 0),
              float(params['velocity_mns']),
          ))

    # --- step 1: processing ---
    sfreq = info['samples'] / info['Total_time_window'] * 1000   # MHz
    processed, time_axis_out = apply_processing(data, time_axis, sfreq, params)

    if params.get('flip_x', False):
        processed = processed[:, ::-1]
        print('    flip_x: profile reversed (North on left)')

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

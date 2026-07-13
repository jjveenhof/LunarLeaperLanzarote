"""
make_variant.py
Reprocess any profile with one or more parameter overrides and save under a
variant stem, so the result can be inspected in migration without touching the
canonical params/processed/topo files.

Creates:
  Data/GPR/Processed/{variant}_processed.npz
  Data/GPR/Processed/{variant}_params.json
  Data/GPR/Topo/{variant}_topo.npz
  Results/GPR/Topo/{variant}_topo.png

Then run the migration scan as normal:
  python migrate_velocity_scan.py --line {variant}

Usage:
  python make_variant.py --base Line5_100MHz --suffix svd1 --set n_svd=1
  python make_variant.py --base Line3_50MHz  --suffix nosvd --set n_svd=0
  python make_variant.py --base Line5_100MHz --suffix svd2bw --set n_svd=2 whiten_window=5
"""

import sys
import json
import copy
import argparse
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import topo_correction as tc
from gpr_processing import apply_processing
import segment_tzero as seg_tz

HERE       = Path(__file__).parent
STITCH_DIR = HERE / '../../Data/GPR/Stitched'
PROC_DIR   = HERE / '../../Data/GPR/Processed'


def parse_override(s):
    """Parse 'key=value' string; value is cast to int, float, or str."""
    key, raw = s.split('=', 1)
    for cast in (int, float):
        try:
            return key.strip(), cast(raw.strip())
        except ValueError:
            pass
    return key.strip(), raw.strip()


def main():
    ap = argparse.ArgumentParser(description='Reprocess a GPR profile with param overrides.')
    ap.add_argument('--base',   required=True, help='base profile stem, e.g. Line5_100MHz')
    ap.add_argument('--suffix', required=True, help='variant suffix, e.g. svd1 (appended with _)')
    ap.add_argument('--set', nargs='+', metavar='KEY=VAL', default=[],
                    help='param overrides, e.g. n_svd=1 whiten_window=5')
    args = ap.parse_args()

    base_stem = args.base
    var_stem  = '{}_{}'.format(base_stem, args.suffix)
    overrides = dict(parse_override(s) for s in args.set)

    raw_npz     = STITCH_DIR / (base_stem + '_raw.npz')
    raw_json    = STITCH_DIR / (base_stem + '_raw.json')
    params_path = PROC_DIR   / (base_stem + '_params.json')

    for p in (raw_npz, raw_json, params_path):
        if not p.exists():
            sys.exit('Not found: ' + str(p.resolve()))

    with np.load(str(raw_npz)) as npz:
        data      = npz['data'].astype(np.float64)
        dist_axis = npz['dist_axis'].astype(np.float64)
        time_axis = npz['time_axis'].astype(np.float64)

    with open(str(raw_json), encoding='utf-8') as f:
        info = json.load(f)

    with open(str(params_path), encoding='utf-8') as f:
        params = json.load(f)

    params_var = copy.deepcopy(params)
    params_var.update(overrides)
    params_var['source_file'] = base_stem + '_raw.npz'

    print('Base:     {}'.format(base_stem))
    print('Variant:  {}'.format(var_stem))
    print('Overrides:', overrides)

    # match run_pipeline: block-wise time-zero pre-alignment for stitched/patched
    # lines before processing (no-op for single-file profiles)
    data = seg_tz.align_segments(data, info, verbose=False)

    sfreq = info['samples'] / info['Total_time_window'] * 1000   # MHz
    processed, time_axis_out = apply_processing(data, time_axis, sfreq, params_var)

    # flip_x is a 2D North-left display convention baked into the NPZ; apply it here
    # exactly as run_pipeline does, so a variant of a flipped line (e.g. Line3) stays
    # consistent with its flip_x param (topo_correction reverses elevations to match).
    if params_var.get('flip_x', False):
        processed = processed[:, ::-1]
        print('    flip_x: variant reversed (North on left)')

    PROC_DIR.mkdir(parents=True, exist_ok=True)
    out_proc   = PROC_DIR / (var_stem + '_processed.npz')
    out_params = PROC_DIR / (var_stem + '_params.json')
    np.savez(str(out_proc), data=processed, dist_axis=dist_axis, time_axis=time_axis_out)
    with open(str(out_params), 'w', encoding='utf-8') as f:
        json.dump(params_var, f, indent=2)
    print('Saved: {}'.format(out_proc.name))

    gnss_lines_df = tc.load_gnss(tc.GNSS_CSV)
    gnss_fp_df    = tc.load_gnss_fp(tc.GNSS_FP_CSV)
    tc.correct_profile(out_proc, gnss_lines_df, gnss_fp_df, {})

    print('\nDone. Run migration with:')
    print('  python migrate_velocity_scan.py --line {}'.format(var_stem))


if __name__ == '__main__':
    main()

"""
segment_tzero.py
Block-wise time-zero re-registration for stitched / patched profiles.

The stitch and patch operations in GPRFieldVisual.ipynb concatenate DT1 segments
without reconciling their per-file instrument time-zero (the "TIMEZERO AT POINT"
field in each .HD header). When segments have different time-zeros, the stitched
line carries small vertical steps at the joins (worst on Petal 1, ~0.18 m at the
LINE08/LINE09 boundary). This module removes those steps: it shifts each segment's
column block along the time axis so the whole line shares ONE zero -- the zero of
the `header_source` file. Because the reference is the header_source, the single
`tzero_shift` already stored in `_params.json` (= -TZ_at_pt of header_source) stays
correct after alignment.

Inputs, all already on disk -- the DT1 waveform data is NOT needed:
  - Data/GPR/Stitched/{stem}_raw.npz + _raw.json  (the stitched array + provenance)
  - Data/GPR/Field data/<LINE>.HD                 (each segment's TIMEZERO AT POINT)

DATA SAFETY: this does NOT overwrite the raw NPZ. `--apply` writes a corrected copy
under Data/GPR/Stitched/tz_aligned/, with a sidecar that adds a `tzero_align_info`
provenance block (reference file, its TIMEZERO, and each segment's TZ + applied
shift) alongside the original stitch_info/patch_info. Default is a dry run that only
reports the per-segment shifts it would apply.

Usage:
    python segment_tzero.py                 # dry-run report, all stitched/patched lines
    python segment_tzero.py Line3_50MHz     # one profile
    python segment_tzero.py --apply         # write corrected copies to tz_aligned/

Integration (recommended, not done here): call `align_segments(data, info)` in
run_pipeline.run_profile right after loading the raw NPZ, so the raw stays pristine
and the correction is applied reproducibly before apply_processing.
"""

import sys
import json
import argparse
import numpy as np
from pathlib import Path
from scipy.ndimage import shift as ndshift

HERE       = Path(__file__).parent
STITCH_DIR = HERE / '../../Data/GPR/Stitched'
HD_DIR     = HERE / '../../Data/GPR/Field data'
OUT_DIR    = STITCH_DIR / 'tz_aligned'

_TZ_KEY = 'TIMEZERO AT POINT'


def read_tz_at_point(line_name):
    """Read TIMEZERO AT POINT (in samples) from the .HD header of a DT1 file.
    `line_name` may be 'LINE06' or 'LINE06.DT1'. Returns float or None."""
    if line_name is None:
        return None
    hd = HD_DIR / (Path(line_name).stem + '.HD')
    if not hd.exists():
        return None
    for line in hd.read_text(errors='ignore').splitlines():
        if _TZ_KEY in line.upper():
            try:
                return float(line.split('=')[1])
            except (IndexError, ValueError):
                return None
    return None


def _make_record(name, c0, c1, tz, ref_tz):
    """One block record. shift_samples = the shift APPLIED to the block (negative
    = earlier), i.e. -(tz - ref_tz). cols are 0-indexed inclusive."""
    shift = None if (tz is None or ref_tz is None) else round(-(tz - ref_tz), 3) + 0.0
    return {'line': name, 'col_start': int(c0), 'col_end': int(c1),
            'tz_at_point': tz, 'shift_samples': shift}


def segment_records(info, n_traces):
    """Per-segment/patch blocks in FINAL-array column coordinates, each tagged with
    its file's TIMEZERO and the shift needed to bring it to the header_source zero.
    Handles stitched (segment order + optional profile reversal) and patched (base
    line + sub-range replacements) profiles. Empty for single-file lines.
    Returns (records, ref_tz)."""
    ref_tz = read_tz_at_point(info.get('header_source'))
    recs   = []
    si = info.get('stitch_info')
    pi = info.get('patch_info')

    if si and si.get('applied'):
        cum, blocks = 0, []
        for seg in si['segments']:
            used = int(seg['traces_used'])
            blocks.append([cum, cum + used, seg['line']])
            cum += used
        # the whole profile was column-reversed AFTER hstack -> map ranges
        if si.get('profile_reversed'):
            blocks = [[n_traces - b, n_traces - a, name] for a, b, name in blocks]
        for a, b, name in blocks:
            recs.append(_make_record(name, a, b - 1, read_tz_at_point(name), ref_tz))

    elif pi and pi.get('applied'):
        # base line (header_source) spans everything at delta 0; each patch
        # replaces a sub-range and carries its own file's zero.
        for p in pi['patches']:
            recs.append(_make_record(p['source'],
                                     int(p['dest_trace_start']),
                                     int(p['dest_trace_end']),
                                     read_tz_at_point(p['source']), ref_tz))
    return recs, ref_tz


def align_segments(data, info, verbose=True):
    """Return a copy of `data` with each segment block shifted to the
    header_source time-zero. Fractional shifts use linear interpolation
    (order=1), matching the main time-zero step."""
    n_samp, n_tr = data.shape
    recs, ref_tz = segment_records(info, n_tr)
    out = data.astype(np.float64).copy()
    if ref_tz is None:
        if verbose:
            print('    [skip] no TIMEZERO for header_source '
                  '{}'.format(info.get('header_source')))
        return out

    for r in recs:
        s = r['shift_samples']
        if s is None or abs(s) < 1e-3:
            continue
        a, b = r['col_start'], r['col_end'] + 1
        out[:, a:b] = ndshift(out[:, a:b], (s, 0), order=1,
                              mode='constant', cval=0.0)
        if verbose:
            print('    {:<12} cols {:4d}-{:<4d}  shift {:+.2f} samples'.format(
                r['line'], r['col_start'], r['col_end'], s))
    return out


def align_info_block(info, n_traces):
    """Build the `tzero_align_info` provenance block for the sidecar -- mirrors the
    stitch_info / patch_info style so the correction is self-documenting."""
    recs, ref_tz = segment_records(info, n_traces)
    return {
        'applied':               True,
        'reference_line':        info.get('header_source'),
        'reference_tz_at_point': ref_tz,
        'note': ('each stitched/patched segment shifted along the time axis to the '
                 'reference file TIMEZERO AT POINT so the whole profile shares one '
                 'zero; shift_samples = applied shift (negative = earlier); cols are '
                 '0-indexed inclusive in the raw stitched array (same frame as '
                 'stitch_info, i.e. before any flip_x).'),
        'segments':              recs,
    }


def _load(stem):
    npz = STITCH_DIR / (stem + '_raw.npz')
    js  = STITCH_DIR / (stem + '_raw.json')
    with np.load(str(npz)) as f:
        data = f['data'].astype(np.float64)
        dist = f['dist_axis']
        time = f['time_axis']
    with open(str(js), encoding='utf-8') as f:
        info = json.load(f)
    return data, dist, time, info


def _is_stitched_or_patched(info):
    si = info.get('stitch_info')
    pi = info.get('patch_info')
    return bool((si and si.get('applied')) or (pi and pi.get('applied')))


def main():
    ap = argparse.ArgumentParser(description='Block-wise time-zero alignment for '
                                             'stitched/patched profiles.')
    ap.add_argument('stems', nargs='*',
                    help='profile stems (default: all stitched/patched lines)')
    ap.add_argument('--apply', action='store_true',
                    help='write corrected copies to Stitched/tz_aligned/ '
                         '(default: dry-run report only)')
    args = ap.parse_args()

    if args.stems:
        stems = [s.replace('_raw.json', '').replace('_raw.npz', '') for s in args.stems]
    else:
        stems = sorted(p.name.replace('_raw.json', '')
                       for p in STITCH_DIR.glob('*_raw.json'))

    if args.apply:
        OUT_DIR.mkdir(parents=True, exist_ok=True)

    n_done = 0
    for stem in stems:
        js = STITCH_DIR / (stem + '_raw.json')
        if not js.exists():
            print('{}: no sidecar, skipped'.format(stem))
            continue
        with open(str(js), encoding='utf-8') as f:
            info = json.load(f)
        if not _is_stitched_or_patched(info):
            print('{}: single file, nothing to align'.format(stem))
            continue

        data, dist, time, info = _load(stem)
        print('{}  (header_source {}, ref TZ {})'.format(
            stem, info.get('header_source'),
            read_tz_at_point(info.get('header_source'))))
        corrected = align_segments(data, info, verbose=True)

        if args.apply:
            out_npz = OUT_DIR / (stem + '_raw.npz')
            np.savez(str(out_npz), data=corrected.astype(np.float32),
                     dist_axis=dist, time_axis=time)
            info_out = dict(info)
            info_out['tzero_align_info'] = align_info_block(info, corrected.shape[1])
            with open(str(OUT_DIR / (stem + '_raw.json')), 'w', encoding='utf-8') as f:
                json.dump(info_out, f, indent=2)
            print('    -> wrote {} (+ sidecar with tzero_align_info)'.format(out_npz.name))
        n_done += 1

    print('\n{}: {} stitched/patched profile(s) {}.'.format(
        Path(__file__).name, n_done,
        'aligned + written' if args.apply else 'reported (dry run)'))


if __name__ == '__main__':
    main()

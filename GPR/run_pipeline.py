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

After processing, it regenerates the deterministic downstream outputs so a browser
refresh shows current data: dual-freq (topo), migrated NPZ/PNG + migrated dual-freq
for any profile flagged `migrate: true` (migrated at its `velocity`, with
`migration_gain`), the flowerpetal 3D HTML, and (unless --no-scans) the scan HTMLs.

Usage:
    python run_pipeline.py                   # all profiles + downstream plots
    python run_pipeline.py Line2_100MHz      # one profile + its downstream plots
    python run_pipeline.py Line3_50MHz Line5_100MHz
    python run_pipeline.py --no-scans        # skip the slow velocity-scan HTMLs
    python run_pipeline.py --no-plots        # processing + topo only, no downstream
"""

import sys
import json
import subprocess
import numpy as np
import matplotlib
matplotlib.use('Agg')
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import topo_correction as tc
import segment_tzero as seg_tz
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

    # --- step 0: block-wise time-zero pre-alignment (stitched/patched lines) ---
    # Equalise each segment to the header_source zero BEFORE the global time-zero
    # shift in apply_processing (which then works as before). No-op for single-file
    # lines. Recorded in the _topo.json as `tzero_align_info`.
    data = seg_tz.align_segments(data, info, verbose=False)

    print('    dewow={}  tzero={:.2f}  bp={:.0f}-{:.0f}MHz  '
          'norm={}  whiten={}  svd={}  v={:.3f}m/ns'.format(
              params['dewow_window'],
              float(params.get('tzero_shift', 0.0)),
              float(params['bandpass_low']),
              float(params['bandpass_high']),
              params.get('normalize', False),
              params.get('whiten_window', 0),
              params.get('n_svd', 0),
              float(params['velocity']),
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


# lines that plot_dual_freq / velocity-scan understand
DUAL_FREQ_LINES = {'Line2', 'Line3', 'Line5'}


def _load_params(stem):
    p = PROC_DIR / (stem + '_params.json')
    if not p.exists():
        return {}
    with open(str(p), encoding='utf-8') as f:
        return json.load(f)


def regenerate_downstream(stems, do_scans):
    """Re-make the deterministic downstream outputs (including HTML) so a browser
    refresh shows current data. Interactive velocity-scan HTMLs are slow and are
    only rebuilt when do_scans is True.

    Auto-regenerated: dual-freq (topo), migrated NPZ/PNG + migrated dual-freq for
    any profile flagged `migrate: true` (migrated at its `velocity`), and the
    flowerpetal 3D.
    """
    py = sys.executable

    def run(script_args, desc):
        print('  [plot] {}'.format(desc))
        subprocess.run([py, str(HERE / script_args[0])] + script_args[1:], check=False)

    # only profiles that actually produced a topo NPZ this run
    topo_stems = [s for s in stems if (tc.TOPO_DIR / (s + '_topo.npz')).exists()]
    lines = sorted({s.split('_')[0] for s in topo_stems} & DUAL_FREQ_LINES)

    print('\nDownstream plots:')

    # 1. dual-freq (topo) per line
    for L in lines:
        run(['plot_dual_freq.py', L, '--stage', 'topo'], 'dual-freq topo ' + L)

    # 2. migrated NPZ/PNG for profiles flagged migrate: true (at their velocity)
    for s in topo_stems:
        prm = _load_params(s)
        if not prm.get('migrate'):
            continue
        mv = prm.get('velocity')
        mg = prm.get('migration_gain', 0.0)
        run(['migrate_velocity_scan.py', '--line', s,
             '--pick-velocity', str(mv), '--gain', str(mg)], 'migrate ' + s)

    # 2b. migrated dual-freq where BOTH freqs of a line are flagged migrate
    for L in lines:
        p50, p100 = _load_params(L + '_50MHz'), _load_params(L + '_100MHz')
        if p50.get('migrate') and p100.get('migrate'):
            mv = p50.get('velocity')
            mg = p50.get('migration_gain', 0.0)
            run(['plot_dual_freq.py', L, '--stage', 'migrated',
                 '--velocity', str(mv), '--gain', str(mg)], 'dual-freq migrated ' + L)

    # 3. flowerpetal 3D (HTML) -- always refresh so the browser shows current data
    run(['plot_flowerpetal_3d.py'], 'flowerpetal 3D')

    # 4. velocity-scan HTMLs (slow, interactive picking tool) -- opt-in
    if do_scans:
        for s in topo_stems:
            if s.split('_')[0] in DUAL_FREQ_LINES:
                run(['migrate_velocity_scan.py', '--line', s], 'velocity scan ' + s)


def main(targets=None, do_plots=True, do_scans=True):
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
    ok_stems = []
    skipped = 0
    for stem in stems:
        if run_profile(stem, gnss_lines_df, gnss_fp_df, interp_cache):
            ok_stems.append(stem)
        else:
            skipped += 1

    print('\nDone: {} processed, {} skipped.'.format(len(ok_stems), skipped))

    if do_plots and ok_stems:
        regenerate_downstream(ok_stems, do_scans=do_scans)


if __name__ == '__main__':
    argv     = sys.argv[1:]
    do_plots = '--no-plots' not in argv
    do_scans = '--no-scans' not in argv
    targets  = [a for a in argv if not a.startswith('--')]
    main(targets or None, do_plots=do_plots, do_scans=do_scans)

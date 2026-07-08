"""
topo_correction.py
Static topographic correction for GPR profiles using GNSS elevation data.

Run from Code/GPR/ or anywhere -- paths are resolved relative to this file.

Inputs:
    Data/GPR/Processed/{stem}_processed.npz  (from GPRProcessing.ipynb)
    Data/GPR/Processed/{stem}_params.json
    Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv
    Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv

Outputs:
    Data/GPR/Topo/{stem}_topo.npz      corrected radargram + elevation track
    Results/GPR/Topo/{stem}_topo.png   elevation profile + corrected radargram

Usage:
    python topo_correction.py                        # process all
    python topo_correction.py Line2_100MHz           # one profile
"""

import sys
import numpy as np
import pandas as pd
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.ndimage import shift as ndshift
from scipy.interpolate import interp1d


# ---- PATHS -------------------------------------------------------------------
HERE      = Path(__file__).parent
GNSS_CSV     = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv'
GNSS_FP_CSV  = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv'
STITCH_DIR = HERE / '../../Data/GPR/Stitched'
PROC_DIR   = HERE / '../../Data/GPR/Processed'
TOPO_DIR   = HERE / '../../Data/GPR/Topo'
FIG_DIR    = HERE / '../../Results/GPR/Topo'

# Midpoint offsets: distance from back antenna to rig midpoint (metres)
OFFSET_50MHZ  = 1.10    # 2.2 m rig
OFFSET_100MHZ = 0.425   # 0.85 m rig

from gpr_constants import V_DEFAULT as V_FALLBACK   # m/ns used if not stored in params file
from gpr_processing import display_gain             # display-only gain for the QC PNG
# ------------------------------------------------------------------------------


PROFILE_CONFIG = {
    'Line2_100MHz': {
        'gnss_line': 2,
        'type': 'line',
        'desc': 'Line2 100MHz -- GNSS at midpoint, 0.2 m spacing',
    },
    'Line2_50MHz': {
        'gnss_line': 2,
        'type': 'line',
        'desc': 'Line2 50MHz -- interpolated from 100MHz GNSS, no offset',
    },
    'Line3_50MHz': {
        'gnss_line': 3,
        'type': 'line',
        'desc': 'Line3 50MHz -- back antenna on mark, 0-120 m, 0.5 m spacing',
    },
    'Line3_100MHz': {
        'gnss_line': 3,
        'type': 'line',
        'desc': 'Line3 100MHz -- back antenna on mark, section 60-110 m, 0.25 m spacing',
    },
    'Line5_50MHz': {
        'gnss_line': 5,
        'type': 'line',
        'desc': 'Line5 50MHz -- back antenna on mark, 0-100 m, 0.5 m spacing',
    },
    'Line5_100MHz': {
        'gnss_line': 5,
        'type': 'line',
        'desc': 'Line5 100MHz -- forward 30->80 m (reversed in GPRFieldVisual), back antenna on mark, 0.25 m spacing',
    },
    'FlowerPetal1_50MHz': {
        'gnss_line': 'FP1',
        'type': 'flowerpetal',
        'desc': 'FlowerPetal1 50MHz -- back antenna at 0 m, 2.2 m rig, 0.5 m spacing',
    },
    'FlowerPetal2_50MHz': {
        'gnss_line': 'FP2',
        'type': 'flowerpetal',
        'desc': 'FlowerPetal2 50MHz -- back antenna at 0 m, 2.2 m rig, 0.5 m spacing',
    },
    'FlowerPetal3_50MHz': {
        'gnss_line': 'FP3',
        'type': 'flowerpetal',
        'desc': 'FlowerPetal3 50MHz -- back antenna at 0 m, 2.2 m rig, 0.5 m spacing',
    },
}


def load_gnss(csv_path):
    """Load GNSS CSV, drop rows without a Line value."""
    df = pd.read_csv(csv_path)
    mask = df['Line'].notna() & (df['Line'].astype(str).str.strip() != '')
    df = df[mask].copy()
    df['Line'] = df['Line'].astype(int)
    return df


def load_gnss_fp(csv_path):
    """Load FlowerPetals GNSS CSV, keep only FP1/FP2/FP3 rows."""
    df = pd.read_csv(csv_path)
    return df[df['Line'].isin(['FP1', 'FP2', 'FP3'])].copy()


def build_elevation_interp(gnss_df, line_key):
    """Return interp1d(metre_position -> elevation) for a GNSS line.

    line_key is an int (2, 3, 5) for the Lines CSV, or a str ('FP1' etc.)
    for the FlowerPetals CSV.
    """
    sub = gnss_df[gnss_df['Line'] == line_key].copy()

    if line_key == 2:
        # No Meter column; extract trace number from FieldName GPRL1T{n}
        nums = sub['FieldName'].str.extract(r'T(\d+)', expand=False)
        sub['metre_pos'] = nums.astype(float) * 0.2
    elif isinstance(line_key, str):
        # FlowerPetal: metre is the trailing number in the FieldName
        sub['metre_pos'] = sub['FieldName'].str.extract(r'(\d+)$', expand=False).astype(float)
    else:
        sub['metre_pos'] = pd.to_numeric(sub['Meter'], errors='coerce')
        sub = sub.dropna(subset=['metre_pos'])

    sub = sub.sort_values('metre_pos')
    m = sub['metre_pos'].values
    z = sub['Elevation'].values
    return interp1d(m, z, kind='linear', bounds_error=False,
                    fill_value=(z[0], z[-1]))


def dist_to_gnss_metre(profile_key, dist_axis):
    """
    Map dist_axis (metres from profile start) to the metre coordinate
    used by the GNSS interpolator for each profile.

    Physical metre = position of the rig MIDPOINT on the line,
    referenced to the same zero as the GNSS Meter column.
    """
    d = dist_axis

    if profile_key in ('Line2_100MHz', 'Line2_50MHz'):
        # GNSS was taken at midpoint; dist_axis already reflects that
        return d.copy()

    elif profile_key == 'Line3_50MHz':
        # Back antenna on metre mark; midpoint is 1.1 m ahead
        return d + OFFSET_50MHZ

    elif profile_key == 'Line3_100MHz':
        # Profile starts at metre 60 of Line 3; back antenna on mark
        return 60.0 + d + OFFSET_100MHZ

    elif profile_key == 'Line5_50MHz':
        # Back antenna on metre mark; midpoint is 1.1 m ahead
        return d + OFFSET_50MHZ

    elif profile_key == 'Line5_100MHz':
        # Profile was reversed in GPRFieldVisual (now runs 30->80 m like the 50MHz).
        # Back antenna on mark; midpoint is 0.425 m ahead.
        return 30.0 + d + OFFSET_100MHZ

    elif profile_key in ('FlowerPetal1_50MHz', 'FlowerPetal2_50MHz', 'FlowerPetal3_50MHz'):
        # Back antenna at metre 0; midpoint is 1.1 m ahead.
        return d + OFFSET_50MHZ

    else:
        raise ValueError('Unknown profile: ' + profile_key)


def apply_topo_correction(data, time_axis, elevations, v):
    """
    Static topo correction: shift each trace to a common datum (min elevation).

    In a valley the antenna is lower, so the cave is shallower below the
    antenna and its reflection arrives earlier (higher on the radargram).
    To flatten it, shift that trace DOWN (toward later time) by the two-way
    travel time corresponding to how far the antenna is below the highest
    point on the profile.

    Reference datum = maximum elevation on the profile.
    Traces at the datum get no shift; traces below the datum are shifted down.

    Returns (corrected array, shift array in samples, reference elevation).
    """
    dt       = float(time_axis[1] - time_axis[0])   # ns per sample
    ref_elev = float(elevations.max())
    dz       = ref_elev - elevations                  # >= 0 everywhere

    shifts    = np.round(2.0 * dz / v / dt).astype(int)
    corrected = np.zeros_like(data)
    for i in range(data.shape[1]):
        corrected[:, i] = ndshift(data[:, i], shifts[i],
                                  mode='constant', cval=0.0)
    return corrected, shifts, ref_elev


def save_figure(out_path, profile_key, dist_axis, time_axis,
                corrected, elevations, v, ref_elev, gain_exp=0.0, flip_x=False,
                annotate_ns=True):
    """Single-panel topographic section: the radargram is drawn on an absolute
    elevation axis (m asl) so the surface relief sits inside the plot. The data is
    referenced to a flat datum (= max elevation) by the static shift, so the real
    surface dips below the datum -- that gap is the air overburden and is shaded."""
    fig, ax = plt.subplots(figsize=(14, 6))

    # Display-only gain (saved NPZ stays un-gained); uses the recorded view gain
    disp = corrected
    gain_note = ''
    if gain_exp and gain_exp > 0:
        sfreq = 1000.0 / float(time_axis[1] - time_axis[0])   # MHz
        disp = display_gain(corrected, sfreq, gain_exp)
        gain_note = ' | view gain {:.1f}'.format(gain_exp)

    # Map the time axis to absolute elevation: elev = ref_elev - TWT * v / 2.
    # Row 0 (time 0) is the datum (highest surface point); deeper rows are lower.
    t_max      = float(time_axis[-1])
    elev_bot   = ref_elev - t_max * v / 2.0

    clip_val = np.percentile(np.abs(disp), 99)
    im = ax.imshow(disp, aspect='auto', cmap='seismic',
                   vmin=-clip_val, vmax=clip_val,
                   extent=[dist_axis[0], dist_axis[-1], elev_bot, ref_elev])

    # surface topography drawn inside the section; shade the air above it
    ax.fill_between(dist_axis, elevations, ref_elev,
                    color='0.85', zorder=3, linewidth=0)
    ax.plot(dist_axis, elevations, color='k', linewidth=1.3, zorder=4)

    ax.set_xlim(dist_axis[0], dist_axis[-1])
    ax.set_ylim(elev_bot, ref_elev)
    ax.set_xlabel('Distance (m)')
    ax.set_ylabel('Elevation (m asl)')
    ax.set_title('{} | v = {:.3f} m/ns | topo corrected{}'.format(
        profile_key, v, gain_note))

    # N/S endpoint labels inside the section at top corners. Only meaningful for
    # the straight lines -- the flower petals curve through many azimuths (acquired
    # clockwise), so N/S is dropped there (orientation is read from the 3D plan view).
    if annotate_ns:
        ax.text(0.01, 0.99, 'N', transform=ax.transAxes,
                ha='left',  va='top', fontsize=11, fontweight='bold', color='black')
        ax.text(0.99, 0.99, 'S', transform=ax.transAxes,
                ha='right', va='top', fontsize=11, fontweight='bold', color='black')

    # right-hand axis: depth below datum (m) = ref_elev - elevation = TWT * v / 2
    tax = ax.twinx()
    tax.set_ylim(t_max * v / 2.0, 0.0)   # 0 at datum, increasing downward
    tax.set_ylabel('Depth below datum (m)')

    plt.tight_layout()
    plt.savefig(str(out_path), dpi=150)
    plt.close(fig)


def correct_profile(npz_path, gnss_lines_df, gnss_fp_df, interp_cache):
    stem = npz_path.stem                        # Line2_100MHz_processed
    base = stem.replace('_processed', '')       # Line2_100MHz

    # match profile key
    profile_key = next((k for k in PROFILE_CONFIG if k in base), None)
    if profile_key is None:
        print('  [skip] {}: no matching profile key'.format(stem))
        return

    params_path = npz_path.with_name(base + '_params.json')
    if not params_path.exists():
        print('  [skip] {}: params file missing ({})'.format(
            stem, params_path.name))
        return

    print('  {} -- {}'.format(base, PROFILE_CONFIG[profile_key]['desc']))

    with np.load(str(npz_path)) as npz:
        data      = npz['data'].astype(np.float64)
        dist_axis = npz['dist_axis'].astype(np.float64)
        time_axis = npz['time_axis'].astype(np.float64)

    with open(str(params_path), encoding='utf-8') as f:
        params = json.load(f)
    v = float(params.get('velocity', V_FALLBACK))

    # build or reuse elevation interpolator for this GNSS line
    line_key = PROFILE_CONFIG[profile_key]['gnss_line']
    gnss_df  = gnss_fp_df if PROFILE_CONFIG[profile_key]['type'] == 'flowerpetal' else gnss_lines_df
    if line_key not in interp_cache:
        interp_cache[line_key] = build_elevation_interp(gnss_df, line_key)
    elev_fn = interp_cache[line_key]

    gnss_m     = dist_to_gnss_metre(profile_key, dist_axis)
    elevations = elev_fn(gnss_m)

    if params.get('flip_x', False):
        elevations = elevations[::-1]

    corrected, shifts, ref_elev = apply_topo_correction(
        data, time_axis, elevations, v
    )

    TOPO_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out_npz  = TOPO_DIR / (base + '_topo.npz')
    out_json = TOPO_DIR / (base + '_topo.json')
    out_png  = FIG_DIR  / (base + '_topo.png')

    dt_ns    = float(time_axis[1] - time_axis[0])
    dz_range = float(elevations.max() - elevations.min())
    max_ns   = int(shifts.max()) * dt_ns

    np.savez_compressed(str(out_npz),
                        data=corrected,
                        dist_axis=dist_axis,
                        time_axis=time_axis,
                        elevations=elevations,
                        shifts=shifts,
                        ref_elev=np.array(ref_elev))

    save_figure(out_png, profile_key, dist_axis, time_axis,
                corrected, elevations, v, ref_elev,
                gain_exp=float(params.get('gain_exponent', 0.0)),
                flip_x=bool(params.get('flip_x', False)),
                annotate_ns=(PROFILE_CONFIG[profile_key]['type'] != 'flowerpetal'))

    # --- sidecar JSON: topo info + processing params + raw instrument header ---
    def _serial(v):
        if isinstance(v, (np.integer,)):  return int(v)
        if isinstance(v, (np.floating,)): return float(v)
        if isinstance(v, np.ndarray):     return v.tolist()
        return v

    # load raw sidecar (instrument header, stitch/patch provenance)
    source_file = params.get('source_file', '')
    raw_info = None
    if source_file:
        raw_json_path = STITCH_DIR / Path(source_file).with_suffix('.json')
        if raw_json_path.exists():
            with open(str(raw_json_path), encoding='utf-8') as f:
                raw_info = json.load(f)

    sidecar = {
        'topo_correction': {
            'profile_key':          profile_key,
            'gnss_csv':             GNSS_FP_CSV.name if PROFILE_CONFIG[profile_key]['type'] == 'flowerpetal'
                                    else GNSS_CSV.name,
            'velocity':             v,
            'ref_elev_m':           round(ref_elev, 4),
            'elev_range_m':         round(dz_range, 4),
            'max_shift_samples':    int(shifts.max()),
            'max_shift_ns':         round(max_ns, 3),
            'source_processed_file': npz_path.name,
        },
        'processing_params': params,
        'raw_header':        raw_info,
    }

    with open(str(out_json), 'w', encoding='utf-8') as f:
        json.dump(sidecar, f, indent=2, default=_serial)

    print('    elev range {:.2f} m | max shift {} samples ({:.1f} ns)'.format(
        dz_range, shifts.max(), max_ns))
    print('    -> {} + {} + {}'.format(out_npz.name, out_json.name, out_png.name))


def main(targets=None):
    if not GNSS_CSV.exists():
        sys.exit('GNSS CSV not found: ' + str(GNSS_CSV.resolve()))
    if not GNSS_FP_CSV.exists():
        sys.exit('FlowerPetals GNSS CSV not found: ' + str(GNSS_FP_CSV.resolve()))
    if not PROC_DIR.exists():
        sys.exit('Processed dir not found: ' + str(PROC_DIR.resolve()))

    gnss_lines_df = load_gnss(GNSS_CSV)
    gnss_fp_df    = load_gnss_fp(GNSS_FP_CSV)
    print('Loaded {} line GNSS points, {} FlowerPetal GNSS points'.format(
        len(gnss_lines_df), len(gnss_fp_df)))

    if targets:
        # accept bare stem (Line2_100MHz) or full filename
        npz_files = []
        for t in targets:
            stem = t.replace('_processed.npz', '').replace('.npz', '')
            npz_files.append(PROC_DIR / (stem + '_processed.npz'))
    else:
        npz_files = sorted(PROC_DIR.glob('*_processed.npz'))

    if not npz_files:
        print('No *_processed.npz files found in {}'.format(PROC_DIR.resolve()))
        return

    print('Found {} file(s).\n'.format(len(npz_files)))
    interp_cache = {}
    for npz_path in npz_files:
        if npz_path.exists():
            correct_profile(npz_path, gnss_lines_df, gnss_fp_df, interp_cache)
        else:
            print('  [skip] {}: file not found'.format(npz_path.name))

    print('\nDone.')


if __name__ == '__main__':
    # Pass profile stems as arguments to process only those profiles:
    #   python topo_correction.py Line2_100MHz Line3_50MHz
    # With no arguments, all *_processed.npz files are processed.
    main(sys.argv[1:] if len(sys.argv) > 1 else None)

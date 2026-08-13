"""
flowerpetal_io.py
Data layer of the flower-petal 3D viewer (split out of plot_flowerpetal_3d.py): the profile
catalogue, GNSS/LiDAR/edge/plumb loaders, track interpolators, and the curtain
geometry (petal_track / drape_curtain / split_panels). The Plotly scene builders
(make_figure / write_html) and the CLI stay in plot_flowerpetal_3d.py.

Split so the "load + place on the surface" half has one home separate from the
~300 lines of figure code. plot_flowerpetal_3d re-imports everything here, so both
`import plot_flowerpetal_3d as fp; fp.petal_track(...)` and
`from plot_flowerpetal_3d import PROFILES, load_gnss_fp, ...` keep working for the
five importer scripts unchanged.

No plotting, no NPZ writes here -- pure loaders + geometry, verbatim from the
pre-split module.
"""

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

sys.path.insert(0, str(Path(__file__).parent))
from gpr_constants import (V_DEFAULT, OFFSET_50MHZ, OFFSET_100MHZ,
                           SECTION_START_100MHZ)
from profile_geometry import reconcile_geometry

# ---- PATHS -------------------------------------------------------------------
HERE       = Path(__file__).parent
PROC_DIR   = HERE / '../../Data/GPR/Processed'
GNSS_FP    = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv'
GNSS_LINES = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv'
OUT_DIR    = HERE / '../../Results/GPR/FlowerPetals3D'
LIDAR_XYZ  = HERE / '../../LiDAR La Corona/Reregistered clouds/PF_junction_subsampled.xyz'

# OFFSET_50MHZ / OFFSET_100MHZ / SECTION_START_100MHZ imported from gpr_constants
# (centralised in phase-2 F6).

# Display-gain exponents offered as interactive buttons in the HTML.
GAIN_PRESETS = [0.0, 1.0, 2.0, 2.5, 3.0, 3.5, 4.0]

# Keep every Nth LiDAR point (1 = all). Thinning the cloud makes it less dense
# / less overwhelming when zoomed out; raise for sparser, set 1 for the full set.
LIDAR_SUBSAMPLE = 2

# Profile catalogue.  'offset' maps dist_axis (m from profile start) to the
# GNSS metre coordinate.  'metre' selects how each GNSS row's metre position is
# read.  Loops carry a (out, back) colour pair; straight lines a single colour.
PROFILES = [
    dict(key='FlowerPetal1_50MHz', label='FP1', source='fp',    gnss_line='FP1',
         metre='fieldname_tail', offset=OFFSET_50MHZ,        loop=True,
         colours=('crimson',   'darkred')),
    dict(key='FlowerPetal2_50MHz', label='FP2', source='fp',    gnss_line='FP2',
         metre='fieldname_tail', offset=OFFSET_50MHZ,        loop=True,
         colours=('royalblue', 'navy')),
    dict(key='FlowerPetal3_50MHz', label='FP3', source='fp',    gnss_line='FP3',
         metre='fieldname_tail', offset=OFFSET_50MHZ,        loop=True,
         colours=('limegreen', 'darkgreen'), split_offset_m=-1.0),
    dict(key='Line3_50MHz',  label='L3 50MHz',  source='lines', gnss_line=3,
         metre='meter_col',     offset=OFFSET_50MHZ,         loop=False,
         colours=('darkorange',)),
    dict(key='Line3_100MHz', label='L3 100MHz', source='lines', gnss_line=3,
         metre='meter_col',     offset=SECTION_START_100MHZ['Line3'] + OFFSET_100MHZ,
         loop=False, colours=('purple',)),
]
# ------------------------------------------------------------------------------


def load_gnss_fp(csv_path):
    # Deliberately duplicated in topo_correction.py (kept separate on purpose): the
    # petal list is a frozen 3-item campaign fact that can't drift, and merging
    # would invert the dependency direction (core importing from a plot-side module).
    df = pd.read_csv(csv_path)
    return df[df['Line'].isin(['FP1', 'FP2', 'FP3'])].copy()


def load_edge(csv_path):
    """Load the pit-rim 'Edge' points, ordered by their EDGE number."""
    df = pd.read_csv(csv_path)
    sub = df[df['Line'] == 'Edge'].copy()
    if sub.empty:
        return None
    sub['order'] = sub['FieldName'].str.extract(r'(\d+)$', expand=False).astype(float)
    sub = sub.sort_values('order')
    return {
        'east':  sub['Easting'].values,
        'north': sub['Northing'].values,
        'elev':  sub['Elevation'].values,
    }


def load_plumb(csv_path):
    """Load the 'Plumb' transfer point(s) used to tie the surface to the cave."""
    df = pd.read_csv(csv_path)
    sub = df[df['Line'] == 'Plumb'].copy()
    if sub.empty:
        return None
    return {
        'east':  sub['Easting'].values,
        'north': sub['Northing'].values,
        'elev':  sub['Elevation'].values,
    }


def load_gnss_lines(csv_path):
    df = pd.read_csv(csv_path)
    return df[df['Line'].notna()].copy()


def load_lidar(path):
    """
    Load a LiDAR XYZ export: first three columns are E, N, Z (EPSG:4083,
    elevation asl).  Trailing RGB / scalar-field columns are ignored.  Already
    georeferenced to the RTK frame, so no transform is applied here.
    """
    if not path.exists():
        return None
    pts = np.loadtxt(str(path), usecols=(0, 1, 2))
    pts = pts[::max(1, int(LIDAR_SUBSAMPLE))]
    return {'east': pts[:, 0], 'north': pts[:, 1], 'elev': pts[:, 2]}


def build_track_interps(gnss_df, line_key, metre_mode):
    """Return (east_fn, north_fn, elev_fn): metre_pos -> UTM / elevation."""
    sub = gnss_df[gnss_df['Line'] == line_key].copy()
    if metre_mode == 'fieldname_tail':
        sub['metre_pos'] = sub['FieldName'].str.extract(r'(\d+)$', expand=False).astype(float)
    elif metre_mode == 'meter_col':
        sub['metre_pos'] = pd.to_numeric(sub['Meter'], errors='coerce')
    else:
        raise ValueError('Unknown metre mode: ' + metre_mode)

    sub = sub.dropna(subset=['metre_pos']).sort_values('metre_pos')
    sub = sub.drop_duplicates(subset='metre_pos')   # interp1d needs strictly increasing x
    m = sub['metre_pos'].values
    e = sub['Easting'].values
    n = sub['Northing'].values
    z = sub['Elevation'].values
    kw = dict(kind='linear', bounds_error=False)
    east_fn  = interp1d(m, e, fill_value=(e[0], e[-1]), **kw)
    north_fn = interp1d(m, n, fill_value=(n[0], n[-1]), **kw)
    elev_fn  = interp1d(m, z, fill_value=(z[0], z[-1]), **kw)
    return east_fn, north_fn, elev_fn


def load_velocity(profile_key):
    """Read velocity (m/ns) from the saved params, falling back to V_DEFAULT."""
    params_path = PROC_DIR / (profile_key + '_params.json')
    if params_path.exists():
        with open(str(params_path), encoding='utf-8') as f:
            return float(json.load(f).get('velocity', V_DEFAULT))
    return V_DEFAULT


def petal_track(prof, source=None):
    """Map a profile's processed dist_axis onto its GNSS track, reconciled to the
    (flip-baked) data columns -- the composition shared by the petal map/migration
    scripts (was hand-copied 3x; phase-2 F7). `source` ('fp'|'lines') defaults to
    prof['source']. Returns a dict: dist_axis, data, time_axis, east, north, elev,
    dist_along (cumulative along-track distance, metres)."""
    src = source or prof['source']
    with np.load(str(PROC_DIR / (prof['key'] + '_processed.npz'))) as f:
        dist_axis = f['dist_axis'].astype(np.float64)
        data      = f['data'].astype(np.float64)
        time_axis = f['time_axis'].astype(np.float64)
    gnss_df = load_gnss_fp(GNSS_FP) if src == 'fp' else load_gnss_lines(GNSS_LINES)
    east_fn, north_fn, elev_fn = build_track_interps(
        gnss_df, prof['gnss_line'], prof['metre'])
    gnss_m = dist_axis + prof['offset']
    east, north, elev = reconcile_geometry(
        prof['key'], east_fn(gnss_m), north_fn(gnss_m), elev_fn(gnss_m))
    dist_along = np.concatenate(
        [[0.0], np.cumsum(np.hypot(np.diff(east), np.diff(north)))])
    return dict(dist_axis=dist_axis, data=data, time_axis=time_axis,
                east=east, north=north, elev=elev, dist_along=dist_along)


def drape_curtain(prof, east_fn, north_fn, elev_fn, velocity):
    """
    Load a processed radargram and drape it on the real surface.

    Each trace is positioned at its true GNSS elevation, with depth hanging
    straight down: Z[k, i] = elev[i] - depth[k].  This placement is the topo
    correction -- no datum, no static shift, no crop.

    Returns raw (un-gained) amplitudes plus sfreq; gain is applied per preset
    at figure-build time so it can be switched interactively in the HTML.
    """
    npz_path = PROC_DIR / (prof['key'] + '_processed.npz')
    with np.load(str(npz_path)) as f:
        data      = f['data'].astype(np.float64)        # (n_samp, n_tr)
        dist_axis = f['dist_axis'].astype(np.float64)   # (n_tr,)
        time_axis = f['time_axis'].astype(np.float64)   # (n_samp,)

    sfreq = 1000.0 / float(time_axis[1] - time_axis[0])  # MHz (samples per us)

    # Map dist_axis to GNSS metre coordinate (start offset + midpoint offset).
    # dist_axis is in acquisition order regardless of flip_x (only the DATA
    # columns were reversed at bake time), so the geometry -- not the data --
    # must be reversed to realign column i with the true track position.
    gnss_m = dist_axis + prof['offset']
    east, north, elev = reconcile_geometry(
        prof['key'], east_fn(gnss_m), north_fn(gnss_m), elev_fn(gnss_m))

    # Depth below the surface (first sample sits exactly on the surface)
    depth = (time_axis - time_axis[0]) * velocity / 2.0   # (n_samp,)

    n_samp, n_tr = data.shape
    X = np.tile(east[np.newaxis, :],  (n_samp, 1))
    Y = np.tile(north[np.newaxis, :], (n_samp, 1))
    Z = elev[np.newaxis, :] - depth[:, np.newaxis]        # (n_samp, n_tr)

    dtrace = float(dist_axis[1] - dist_axis[0]) if n_tr > 1 else 1.0

    return {
        'X': X, 'Y': Y, 'Z': Z,
        'amp': data,          # raw, un-gained; gain applied per preset in make_figure
        'sfreq': sfreq,
        'name': prof['key'], 'label': prof['label'],
        'colours': prof['colours'], 'loop': prof['loop'],
        'split_offset_m': prof.get('split_offset_m', 0.0),
        'dtrace': dtrace,
        'east': east, 'north': north, 'elev': elev,
        'z_top': float(elev.max()),
        'z_bot': float(Z.min()),
        'n_traces': n_tr,
    }


def split_panels(c, idx):
    """
    Turn a curtain into one or two display panels (geometry only).

    A loop (FlowerPetal) is split at its apex (the trace farthest from the
    start) into 'out' and 'back' limbs, each with its own colour and legend
    toggle.  A straight line is returned as a single panel.  Each panel carries
    the parent curtain index and its trace slice so the per-gain surfacecolor
    can be sliced out later.
    """
    def panel(sl, colour, label, legend_id):
        return {
            'X': c['X'][:, sl], 'Y': c['Y'][:, sl], 'Z': c['Z'][:, sl],
            'east': c['east'][sl], 'north': c['north'][sl], 'elev': c['elev'][sl],
            'colour': colour, 'label': label, 'legend_id': legend_id,
            'curtain_idx': idx, 'sl': sl,
        }

    if not c['loop']:
        return [panel(slice(None), c['colours'][0], c['label'], c['name'])]

    east, north = c['east'], c['north']
    d2   = (east - east[0]) ** 2 + (north - north[0]) ** 2
    apex = int(np.argmax(d2))
    apex += int(round(c['split_offset_m'] / c['dtrace']))   # optional nudge (m -> traces)
    apex  = max(1, min(apex, len(east) - 2))
    out_sl, back_sl = slice(0, apex + 1), slice(apex, None)

    if c['X'][:, out_sl].shape[1] < 2 or c['X'][:, back_sl].shape[1] < 2:
        return [panel(slice(None), c['colours'][0], c['label'], c['name'])]

    return [
        panel(out_sl,  c['colours'][0], c['label'] + ' out',  c['name'] + '_out'),
        panel(back_sl, c['colours'][1], c['label'] + ' back', c['name'] + '_back'),
    ]

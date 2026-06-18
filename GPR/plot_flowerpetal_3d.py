"""
plot_flowerpetal_3d.py
3D Plotly visualisation of GPR profiles along their actual GPS trajectories.

Each profile is rendered as a coloured amplitude curtain draped on the real
surface: x,y follow the GPS track, and each trace is positioned at its true
GNSS elevation with depth hanging straight down (Z = elev - depth).  This
elevation positioning IS the topographic correction -- it is mathematically
equivalent to the static datum shift in topo_correction.py, but done by
placement instead of array-shifting, so it needs no datum, no zero-fill, and
no cropping, and it preserves the real surface undulation.

The FlowerPetal lines are loops (walked out and back), so each is split at its
apex into two independently-toggleable limbs.  Line 3 is a straight profile and
is shown whole; its 50 and 100 MHz versions are both included.

Gain and clip are interactive button rows in the HTML.  Gain is display-only,
precomputed for a fixed set of exponents (saved NPZs stay un-gained); clip just
restyles the colour range.

Inputs (no topo step required):
    Data/GPR/Processed/{stem}_processed.npz   (un-shifted processed amplitudes)
    Data/GPR/Processed/{stem}_params.json     (velocity)
    Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv  (petal track + elevation)
    Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv         (line track + elevation)

Usage:
    python plot_flowerpetal_3d.py
    python plot_flowerpetal_3d.py --gain 3.0      # initial active gain button
    python plot_flowerpetal_3d.py --velocity 0.11
    python plot_flowerpetal_3d.py --clip 99
    python plot_flowerpetal_3d.py --out my_figure.html
"""

import sys
import json
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.interpolate import interp1d
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent))
from gpr_constants import V_DEFAULT
from gpr_processing import display_gain

# ---- PATHS -------------------------------------------------------------------
HERE       = Path(__file__).parent
PROC_DIR   = HERE / '../../Data/GPR/Processed'
GNSS_FP    = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv'
GNSS_LINES = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv'
OUT_DIR    = HERE / '../../Results/GPR/FlowerPetals3D'
LIDAR_XYZ  = HERE / '../../LiDAR La Corona/Reregistered clouds/PuertaFalsaClean_ExportCropSubsampled.xyz'

# Back-antenna to rig midpoint offsets (metres), matching topo_correction.py.
OFFSET_50MHZ  = 1.10    # 2.2 m rig
OFFSET_100MHZ = 0.425   # 0.85 m rig

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
         metre='meter_col',     offset=60.0 + OFFSET_100MHZ, loop=False,
         colours=('purple',)),
]
# ------------------------------------------------------------------------------


def load_gnss_fp(csv_path):
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
    """Read velocity_mns from the saved params, falling back to V_DEFAULT."""
    params_path = PROC_DIR / (profile_key + '_params.json')
    if params_path.exists():
        with open(str(params_path), encoding='utf-8') as f:
            return float(json.load(f).get('velocity_mns', V_DEFAULT))
    return V_DEFAULT


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

    # Map dist_axis to GNSS metre coordinate (start offset + midpoint offset)
    gnss_m = dist_axis + prof['offset']
    east   = east_fn(gnss_m)
    north  = north_fn(gnss_m)
    elev   = elev_fn(gnss_m)

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


def make_figure(curtains, clip_pct, gain_presets, default_gain,
                vexag=1.0, edge=None, plumb=None, lidar=None, equalize=True):
    # Geometry panels (split loops into limbs; straight lines stay whole)
    panels = []
    for i, c in enumerate(curtains):
        panels.extend(split_panels(c, i))
    n_surfs = len(panels)

    # Per-gain equalised amplitudes: eq[g] is a list (one 2D array per curtain).
    # Each profile is scaled to a common 99th percentile so different max-time
    # crops / frequencies render at comparable brightness on the shared scale.
    eq = {}
    for g in gain_presets:
        arrs = []
        for c in curtains:
            gained = display_gain(c['amp'], c['sfreq'], g)
            if equalize:
                fac = float(np.percentile(np.abs(gained), 99)) or 1.0
                gained = gained / fac
            arrs.append(gained)
        eq[g] = arrs

    def panel_surf(g):
        """Surfacecolor arrays for every panel at gain exponent g (trace order)."""
        return [eq[g][p['curtain_idx']][:, p['sl']] for p in panels]

    surf0   = panel_surf(default_gain)
    all_amp = np.concatenate([a.ravel() for a in surf0])
    vmax    = float(np.percentile(np.abs(all_amp), clip_pct))

    # Data extents (include the edge/plumb so they stay in view)
    east_parts  = [c['east']  for c in curtains]
    north_parts = [c['north'] for c in curtains]
    z_tops = [c['z_top'] for c in curtains]
    z_bots = [c['z_bot'] for c in curtains]
    for feat in (edge, plumb):
        if feat is not None:
            east_parts.append(feat['east'])
            north_parts.append(feat['north'])
            z_tops.append(float(feat['elev'].max()))
            z_bots.append(float(feat['elev'].min()))
    all_east  = np.concatenate(east_parts)
    all_north = np.concatenate(north_parts)
    dx = float(all_east.max()  - all_east.min())
    dy = float(all_north.max() - all_north.min())
    z_bot = min(z_bots)
    z_top = max(z_tops)
    dz    = max(z_top - z_bot, 1.0)

    # Padded fixed ranges -- toggling traces will NOT rescale the scene
    x_pad = max(dx * 0.05, 1.0)
    y_pad = max(dy * 0.05, 1.0)
    z_pad = max(dz * 0.05, 0.5)
    x_range = [float(all_east.min())  - x_pad, float(all_east.max())  + x_pad]
    y_range = [float(all_north.min()) - y_pad, float(all_north.max()) + y_pad]
    z_range = [z_bot - z_pad, z_top + z_pad]

    # True 1:1:1 scale: aspect ratio proportional to the displayed ranges.
    # vexag multiplies only the vertical (1.0 = no exaggeration).
    xs = x_range[1] - x_range[0]
    ys = y_range[1] - y_range[0]
    zs = z_range[1] - z_range[0]
    amax = max(xs, ys, zs)
    aspect = dict(x=xs / amax, y=ys / amax, z=(zs / amax) * vexag)

    fig = go.Figure()

    for i, p in enumerate(panels):
        show_cb = (i == 0)
        fig.add_trace(go.Surface(
            x=p['X'], y=p['Y'], z=p['Z'],
            surfacecolor=surf0[i],
            colorscale='RdBu_r',
            cmin=-vmax, cmax=vmax,
            showscale=show_cb,
            colorbar=dict(
                title='Amplitude', thickness=15, len=0.55,
                x=1.02, tickfont=dict(size=10),
            ) if show_cb else None,
            name=p['label'],
            legendgroup=p['legend_id'],
            showlegend=False,   # legend entry comes from the track line
            opacity=1.0,
            lighting=dict(ambient=1.0, diffuse=0.0, specular=0.0,
                          roughness=1.0, fresnel=0.0),
            lightposition=dict(x=0, y=0, z=1e5),
        ))

    # Track lines: one per panel, drawn along the true surface elevation
    for p in panels:
        fig.add_trace(go.Scatter3d(
            x=p['east'], y=p['north'], z=p['elev'],
            mode='lines',
            line=dict(color=p['colour'], width=5),
            name=p['label'],
            legendgroup=p['legend_id'],
            showlegend=True,
        ))

    # Pit rim: the surveyed edge where the petals terminate
    if edge is not None:
        fig.add_trace(go.Scatter3d(
            x=edge['east'], y=edge['north'], z=edge['elev'],
            mode='lines+markers',
            line=dict(color='black', width=4),
            marker=dict(color='black', size=3),
            name='Pit edge',
            legendgroup='pit_edge',
            showlegend=True,
        ))

    # Plumb transfer point: surface-to-cave tie point
    if plumb is not None:
        fig.add_trace(go.Scatter3d(
            x=plumb['east'], y=plumb['north'], z=plumb['elev'],
            mode='markers',
            marker=dict(color='magenta', size=6, symbol='diamond'),
            name='Plumb line location',
            legendgroup='plumb',
            showlegend=True,
        ))

    # LiDAR cave cloud: clipped to the GPR-driven box (does NOT expand the
    # extent -- the scene ranges stay locked to the GPR data).
    if lidar is not None:
        le, ln, lz = lidar['east'], lidar['north'], lidar['elev']
        msk = ((le >= x_range[0]) & (le <= x_range[1]) &
               (ln >= y_range[0]) & (ln <= y_range[1]) &
               (lz >= z_range[0]) & (lz <= z_range[1]))
        print('  lidar: {} of {} points within box'.format(int(msk.sum()), len(le)))
        fig.add_trace(go.Scatter3d(
            x=le[msk], y=ln[msk], z=lz[msk],
            mode='markers',
            marker=dict(color="#4D2209", size=2, opacity=0.8),
            name='LiDAR cave',
            legendgroup='lidar',
            showlegend=True,
        ))

    surf_idx = list(range(n_surfs))

    # Gain slider steps: swap the precomputed surfacecolor arrays for all surfaces
    gain_steps = [
        dict(label='{:.1f}'.format(g), method='restyle',
             args=[{'surfacecolor': panel_surf(g)}, surf_idx])
        for g in gain_presets
    ]

    # Clip slider steps: restyle the colour range (computed at the default gain)
    clip_presets = [90, 95, 98, 99, 99.5]
    clip_steps = []
    for cp in clip_presets:
        vmax_cp = float(np.percentile(np.abs(all_amp), cp))
        clip_steps.append(dict(
            label='{}%'.format(int(cp) if cp == int(cp) else cp),
            method='restyle',
            args=[{'cmin': [-vmax_cp] * n_surfs,
                   'cmax': [ vmax_cp] * n_surfs}, surf_idx],
        ))

    fig.update_layout(
        title=dict(text='GPR profiles -- draped on GNSS surface',
                   x=0.5, xanchor='center', y=0.98, yanchor='top'),
        scene=dict(
            xaxis=dict(title='Easting (m, EPSG:4083)',  range=x_range),
            yaxis=dict(title='Northing (m, EPSG:4083)', range=y_range),
            zaxis=dict(title='Elevation (m asl)',        range=z_range),
            aspectmode='manual',
            aspectratio=aspect,
        ),
        sliders=[
            dict(active=gain_presets.index(default_gain),
                 currentvalue=dict(prefix='Gain exp: ', font=dict(size=13)),
                 pad=dict(t=20, b=10), x=0.0, xanchor='left', len=0.42,
                 y=-0.06, yanchor='top', steps=gain_steps),
            dict(active=clip_presets.index(99) if 99 in clip_presets else 0,
                 currentvalue=dict(prefix='Clip pct: ', font=dict(size=13)),
                 pad=dict(t=20, b=10), x=0.55, xanchor='left', len=0.42,
                 y=-0.06, yanchor='top', steps=clip_steps),
        ],
        legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.7)'),
        margin=dict(l=30, r=80, t=60, b=120),
        height=750,
        scene_camera=dict(
            eye=dict(x=1.4, y=1.4, z=0.6),
        ),
    )
    return fig


def main():
    parser = argparse.ArgumentParser(
        description='3D plot of GPR profiles draped on the GNSS surface.'
    )
    parser.add_argument('--velocity', type=float, default=None,
                        help='Override wave velocity in m/ns (default: per-profile params)')
    parser.add_argument('--gain', type=float, default=0.0,
                        help='Initial active gain preset (snapped to the nearest button)')
    parser.add_argument('--clip', type=float, default=99.0,
                        help='Amplitude clip percentile for initial colour scale (default: 99)')
    parser.add_argument('--vexag', type=float, default=1.0,
                        help='Vertical exaggeration factor (default: 1.0 = true 1:1:1 scale)')
    parser.add_argument('--no-equalize', dest='equalize', action='store_false',
                        help='Disable per-profile brightness equalisation (show raw shared scale)')
    parser.add_argument('--no-edge', dest='edge', action='store_false',
                        help='Do not draw the surveyed pit edge')
    parser.add_argument('--no-plumb', dest='plumb', action='store_false',
                        help='Do not draw the plumb transfer point')
    parser.add_argument('--no-lidar', dest='lidar', action='store_false',
                        help='Do not draw the LiDAR cave cloud')
    parser.set_defaults(equalize=True, edge=True, plumb=True, lidar=True)
    parser.add_argument('--out', type=str, default=None,
                        help='Output HTML path (default: auto)')
    args = parser.parse_args()

    for path in (GNSS_FP, GNSS_LINES):
        if not path.exists():
            sys.exit('GNSS CSV not found: ' + str(path.resolve()))

    gnss = {
        'fp':    load_gnss_fp(GNSS_FP),
        'lines': load_gnss_lines(GNSS_LINES),
    }
    print('Loaded {} petal GNSS points, {} line GNSS points'.format(
        len(gnss['fp']), len(gnss['lines'])))

    curtains = []
    for prof in PROFILES:
        npz_path = PROC_DIR / (prof['key'] + '_processed.npz')
        if not npz_path.exists():
            print('  [skip] {} -- processed NPZ not found'.format(prof['key']))
            continue
        east_fn, north_fn, elev_fn = build_track_interps(
            gnss[prof['source']], prof['gnss_line'], prof['metre'])
        velocity = args.velocity if args.velocity else load_velocity(prof['key'])
        c = drape_curtain(prof, east_fn, north_fn, elev_fn, velocity)
        curtains.append(c)
        print('  {} -- {} traces, surface {:.1f} m, base {:.1f} m asl'.format(
            prof['key'], c['n_traces'], c['z_top'], c['z_bot']))

    if not curtains:
        sys.exit('No FlowerPetal processed NPZ files found in {}'.format(PROC_DIR))

    # Snap the requested initial gain to the nearest available preset button
    default_gain = min(GAIN_PRESETS, key=lambda g: abs(g - args.gain))

    edge = load_edge(GNSS_FP) if args.edge else None
    if edge is not None:
        print('  pit edge -- {} points'.format(len(edge['east'])))
    plumb = load_plumb(GNSS_FP) if args.plumb else None
    if plumb is not None:
        print('  plumb line location -- {} point(s)'.format(len(plumb['east'])))
    lidar = load_lidar(LIDAR_XYZ) if args.lidar else None
    if lidar is not None:
        print('  lidar cloud -- {} points loaded'.format(len(lidar['east'])))
    elif args.lidar:
        print('  [skip] lidar -- XYZ not found at {}'.format(LIDAR_XYZ))

    fig = make_figure(curtains, args.clip, GAIN_PRESETS, default_gain,
                      vexag=args.vexag, edge=edge, plumb=plumb, lidar=lidar,
                      equalize=args.equalize)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUT_DIR / 'flowerpetal_3d.html'
    fig.write_html(str(out_path))
    print('Saved: {}  (gain buttons {}, active {})'.format(
        out_path.resolve(), GAIN_PRESETS, default_gain))


if __name__ == '__main__':
    main()

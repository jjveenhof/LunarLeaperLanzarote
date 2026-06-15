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

Inputs (no topo step required):
    Data/GPR/Processed/{stem}_processed.npz   (un-shifted processed amplitudes)
    Data/GPR/Processed/{stem}_params.json     (velocity)
    Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv  (petal track + elevation)
    Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv         (line track + elevation)

Usage:
    python plot_flowerpetal_3d.py
    python plot_flowerpetal_3d.py --velocity 0.11
    python plot_flowerpetal_3d.py --gain 4.0
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

# ---- PATHS -------------------------------------------------------------------
HERE       = Path(__file__).parent
PROC_DIR   = HERE / '../../Data/GPR/Processed'
GNSS_FP    = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv'
GNSS_LINES = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv'
OUT_DIR    = HERE / '../../Results/GPR/FlowerPetals3D'

# Back-antenna to rig midpoint offsets (metres), matching topo_correction.py.
OFFSET_50MHZ  = 1.10    # 2.2 m rig
OFFSET_100MHZ = 0.425   # 0.85 m rig

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


def drape_curtain(prof, east_fn, north_fn, elev_fn, velocity, gain_exp=0.0):
    """
    Load a processed radargram and drape it on the real surface.

    Each trace is positioned at its true GNSS elevation, with depth hanging
    straight down: Z[k, i] = elev[i] - depth[k].  This placement is the topo
    correction -- no datum, no static shift, no crop.

    gain_exp applies a gdp-style linear gain (travel_time ** exponent) indexed
    from sample 0 (the surface), matching the processing notebook.  0 = no gain.
    """
    npz_path = PROC_DIR / (prof['key'] + '_processed.npz')
    with np.load(str(npz_path)) as f:
        data      = f['data'].astype(np.float64)        # (n_samp, n_tr)
        dist_axis = f['dist_axis'].astype(np.float64)   # (n_tr,)
        time_axis = f['time_axis'].astype(np.float64)   # (n_samp,)

    # Optional gain, indexed from sample 0 -- identical to the notebook's gain.
    if gain_exp > 0:
        dt_ns  = float(time_axis[1] - time_axis[0])     # ns per sample
        sfreq  = 1000.0 / dt_ns                          # MHz (samples per us)
        idx    = np.arange(data.shape[0]) + 1
        data   = data * ((idx / sfreq) ** gain_exp)[:, np.newaxis]

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
        'amp': data,
        'name': prof['key'], 'label': prof['label'],
        'colours': prof['colours'], 'loop': prof['loop'],
        'split_offset_m': prof.get('split_offset_m', 0.0),
        'dtrace': dtrace,
        'east': east, 'north': north, 'elev': elev,
        'z_top': float(elev.max()),
        'z_bot': float(Z.min()),
        'n_traces': n_tr,
    }


def split_panels(c):
    """
    Turn a curtain into one or two display panels.

    A loop (FlowerPetal) is split at its apex (the trace farthest from the
    start) into 'out' and 'back' limbs, each with its own colour and legend
    toggle.  The apex trace is shared by both limbs so there is no seam.
    A straight line is returned as a single panel.
    """
    def panel(sl, colour, label, legend_id):
        return {
            'X': c['X'][:, sl], 'Y': c['Y'][:, sl], 'Z': c['Z'][:, sl],
            'amp': c['amp'][:, sl],
            'east': c['east'][sl], 'north': c['north'][sl], 'elev': c['elev'][sl],
            'colour': colour, 'label': label, 'legend_id': legend_id,
        }

    if not c['loop']:
        return [panel(slice(None), c['colours'][0], c['label'], c['name'])]

    east, north = c['east'], c['north']
    d2   = (east - east[0]) ** 2 + (north - north[0]) ** 2
    apex = int(np.argmax(d2))
    # Optional nudge of the split point along the track (metres -> traces)
    apex += int(round(c['split_offset_m'] / c['dtrace']))
    apex  = max(1, min(apex, len(east) - 2))
    out_sl, back_sl = slice(0, apex + 1), slice(apex, None)

    if c['X'][:, out_sl].shape[1] < 2 or c['X'][:, back_sl].shape[1] < 2:
        return [panel(slice(None), c['colours'][0], c['label'], c['name'])]

    return [
        panel(out_sl,  c['colours'][0], c['label'] + ' out',
              c['name'] + '_out'),
        panel(back_sl, c['colours'][1], c['label'] + ' back',
              c['name'] + '_back'),
    ]


def make_figure(curtains, clip_pct, vexag=1.0, edge=None, plumb=None):
    # Shared amplitude array for colour scaling
    all_amp = np.concatenate([c['amp'].ravel() for c in curtains])
    vmax = float(np.percentile(np.abs(all_amp), clip_pct))

    # Split loops into limbs; straight lines stay whole
    panels = []
    for c in curtains:
        panels.extend(split_panels(c))

    # Data extents (include the edge so the rim stays in view)
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
    z_bot    = min(z_bots)
    z_top    = max(z_tops)
    dz       = max(z_top - z_bot, 1.0)

    # Padded fixed ranges -- toggling traces will NOT rescale the scene
    x_pad = max(dx * 0.05, 1.0)
    y_pad = max(dy * 0.05, 1.0)
    z_pad = max(dz * 0.05, 0.5)
    x_range = [float(all_east.min())  - x_pad, float(all_east.max())  + x_pad]
    y_range = [float(all_north.min()) - y_pad, float(all_north.max()) + y_pad]
    z_range = [z_bot - z_pad, z_top + z_pad]

    # True 1:1:1 scale: aspect ratio proportional to the displayed ranges, so a
    # metre of Easting, Northing and Elevation all render the same length.
    # vexag multiplies only the vertical (1.0 = no exaggeration).
    xs = x_range[1] - x_range[0]
    ys = y_range[1] - y_range[0]
    zs = z_range[1] - z_range[0]
    amax = max(xs, ys, zs)
    aspect = dict(x=xs / amax, y=ys / amax, z=(zs / amax) * vexag)

    fig = go.Figure()

    n_surfs = len(panels)
    for i, p in enumerate(panels):
        show_cb = (i == 0)
        fig.add_trace(go.Surface(
            x=p['X'], y=p['Y'], z=p['Z'],
            surfacecolor=p['amp'],
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
            name='Plumb point',
            legendgroup='plumb',
            showlegend=True,
        ))

    # Clip preset buttons (updates cmin/cmax on all surface traces)
    surf_idx     = list(range(n_surfs))
    clip_presets = [90, 95, 98, 99, 99.5]
    clip_buttons = []
    for cp in clip_presets:
        vmax_cp = float(np.percentile(np.abs(all_amp), cp))
        clip_buttons.append(dict(
            label='{}%'.format(int(cp) if cp == int(cp) else cp),
            method='restyle',
            args=[{'cmin': [-vmax_cp] * n_surfs,
                   'cmax': [ vmax_cp] * n_surfs}, surf_idx],
        ))

    fig.update_layout(
        title='GPR profiles -- draped on GNSS surface',
        scene=dict(
            xaxis=dict(title='Easting (m, EPSG:4083)',  range=x_range),
            yaxis=dict(title='Northing (m, EPSG:4083)', range=y_range),
            zaxis=dict(title='Elevation (m asl)',        range=z_range),
            aspectmode='manual',
            aspectratio=aspect,
        ),
        updatemenus=[dict(
            type='buttons',
            direction='left',
            buttons=clip_buttons,
            x=0.0, xanchor='left',
            y=1.07, yanchor='top',
            showactive=True,
            bgcolor='white',
            bordercolor='lightgray',
        )],
        annotations=[dict(
            text='Clip:', showarrow=False,
            x=0.0, xref='paper', xanchor='right',
            y=1.07, yref='paper', yanchor='top',
            font=dict(size=12),
        )],
        legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.7)'),
        margin=dict(l=0, r=80, t=60, b=0),
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
                        help='Linear gain exponent, indexed from surface (default: 0 = off)')
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
    parser.set_defaults(equalize=True, edge=True, plumb=True)
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
        c = drape_curtain(prof, east_fn, north_fn, elev_fn,
                          velocity, gain_exp=args.gain)
        # Per-profile brightness equalisation: scale to a common 99th-percentile
        # so different max-time crops / frequencies render at comparable
        # brightness on the shared colour scale (the 50 MHz set is already
        # RMS-equal, so this mainly lifts the shorter 100 MHz record).
        if args.equalize:
            scale = float(np.percentile(np.abs(c['amp']), 99)) or 1.0
            c['amp'] = c['amp'] / scale
        curtains.append(c)
        print('  {} -- {} traces, surface {:.1f} m, base {:.1f} m asl'.format(
            prof['key'], c['n_traces'], c['z_top'], c['z_bot']))

    if not curtains:
        sys.exit('No processed NPZ files found in {}'.format(PROC_DIR))

    edge = load_edge(GNSS_FP) if args.edge else None
    if edge is not None:
        print('  pit edge -- {} points'.format(len(edge['east'])))
    plumb = load_plumb(GNSS_FP) if args.plumb else None
    if plumb is not None:
        print('  plumb point -- {} point(s)'.format(len(plumb['east'])))

    fig = make_figure(curtains, args.clip, vexag=args.vexag, edge=edge, plumb=plumb)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUT_DIR / 'flowerpetal_3d.html'
    fig.write_html(str(out_path))
    print('Saved: {}'.format(out_path.resolve()))


if __name__ == '__main__':
    main()

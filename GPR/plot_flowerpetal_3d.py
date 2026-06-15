"""
plot_flowerpetal_3d.py
3D Plotly visualisation of all FlowerPetal GPR profiles along their actual
GPS trajectories.

Each petal is rendered as a coloured amplitude curtain draped on the real
surface: x,y follow the GPS track, and each trace is positioned at its true
GNSS elevation with depth hanging straight down (Z = elev - depth).  This
elevation positioning IS the topographic correction -- it is mathematically
equivalent to the static datum shift in topo_correction.py, but done by
placement instead of array-shifting, so it needs no datum, no zero-fill, and
no cropping, and it preserves the real surface undulation.

Inputs (no topo step required):
    Data/GPR/Processed/{stem}_processed.npz   (un-shifted processed amplitudes)
    Data/GPR/Processed/{stem}_params.json     (velocity)
    Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv  (track + elevation)

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
HERE     = Path(__file__).parent
PROC_DIR = HERE / '../../Data/GPR/Processed'
GNSS_FP  = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv'
OUT_DIR  = HERE / '../../Results/GPR/FlowerPetals3D'

# Back-antenna to rig midpoint offset for 50 MHz rig (metres).
# Matches the value used in topo_correction.py.
OFFSET_50MHZ = 1.10

FP_PROFILES = [
    ('FlowerPetal1_50MHz', 'FP1', 'crimson'),
    ('FlowerPetal2_50MHz', 'FP2', 'royalblue'),
    ('FlowerPetal3_50MHz', 'FP3', 'forestgreen'),
]
# ------------------------------------------------------------------------------


def load_gnss_fp(csv_path):
    df = pd.read_csv(csv_path)
    return df[df['Line'].isin(['FP1', 'FP2', 'FP3'])].copy()


def build_track_interps(gnss_df, line_key):
    """Return (east_fn, north_fn, elev_fn): metre_pos -> UTM / elevation."""
    sub = gnss_df[gnss_df['Line'] == line_key].copy()
    sub['metre_pos'] = sub['FieldName'].str.extract(r'(\d+)$', expand=False).astype(float)
    sub = sub.sort_values('metre_pos')
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


def drape_curtain(profile_key, east_fn, north_fn, elev_fn, velocity, gain_exp=0.0):
    """
    Load processed radargram and drape it on the real surface.

    Each trace is positioned at its true GNSS elevation, with depth hanging
    straight down: Z[k, i] = elev[i] - depth[k].  This placement is the topo
    correction -- no datum, no static shift, no crop.

    gain_exp applies a gdp-style linear gain (travel_time ** exponent) indexed
    from sample 0 (the surface), matching the processing notebook.  0 = no gain.

    Returns dict: X, Y, Z, amp (all shape n_samp x n_tr), name, east, north,
                  elev, z_top (surface min/max), z_bot.
    """
    npz_path = PROC_DIR / (profile_key + '_processed.npz')
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

    # Map dist_axis to GNSS metre coordinate (back antenna + midpoint offset)
    gnss_m = dist_axis + OFFSET_50MHZ
    east   = east_fn(gnss_m)
    north  = north_fn(gnss_m)
    elev   = elev_fn(gnss_m)

    # Depth below the surface (first sample sits exactly on the surface)
    depth = (time_axis - time_axis[0]) * velocity / 2.0   # (n_samp,)

    n_samp, n_tr = data.shape
    X = np.tile(east[np.newaxis, :],  (n_samp, 1))
    Y = np.tile(north[np.newaxis, :], (n_samp, 1))
    Z = elev[np.newaxis, :] - depth[:, np.newaxis]        # (n_samp, n_tr)

    return {
        'X': X, 'Y': Y, 'Z': Z,
        'amp': data,
        'name': profile_key,
        'east': east, 'north': north, 'elev': elev,
        'z_top': float(elev.max()),
        'z_bot': float(Z.min()),
        'n_traces': n_tr,
    }


def split_limbs(c):
    """
    Split a petal-loop curtain into its two limbs at the apex (the trace
    farthest from the start), so each limb can be toggled independently.

    Returns a list of two panel dicts, each carrying sliced X/Y/Z/amp/east/
    north/elev plus a legend id, label and line dash.
    """
    east, north = c['east'], c['north']
    d2   = (east - east[0]) ** 2 + (north - north[0]) ** 2
    apex = int(np.argmax(d2))
    # Overlap the apex trace in both limbs so there is no seam in the surface.
    parts = [('out', slice(0, apex + 1), 'solid'),
             ('back', slice(apex, None), 'dash')]

    panels = []
    for label, sl, dash in parts:
        if c['X'][:, sl].shape[1] < 2:
            continue   # degenerate limb (apex at an endpoint) -- keep as one
        panels.append({
            'X': c['X'][:, sl], 'Y': c['Y'][:, sl], 'Z': c['Z'][:, sl],
            'amp': c['amp'][:, sl],
            'east': east[sl], 'north': north[sl], 'elev': c['elev'][sl],
            'colour': c['colour'],
            'legend_id': '{}_{}'.format(c['name'], label),
            'label': '{} {}'.format(c['short'], label),
            'dash': dash,
        })
    if not panels:   # fell through (single-trace edge case): emit whole curtain
        panels.append({
            'X': c['X'], 'Y': c['Y'], 'Z': c['Z'], 'amp': c['amp'],
            'east': east, 'north': north, 'elev': c['elev'],
            'colour': c['colour'], 'legend_id': c['name'],
            'label': c['short'], 'dash': 'solid',
        })
    return panels


def make_figure(curtains, clip_pct):
    # Shared amplitude array for colour scaling
    all_amp = np.concatenate([c['amp'].ravel() for c in curtains])
    vmax = float(np.percentile(np.abs(all_amp), clip_pct))

    # Split every petal loop into its two limbs (independent legend toggles)
    panels = []
    for c in curtains:
        panels.extend(split_limbs(c))

    # Data extents for aspect ratio and locked axis ranges
    all_east  = np.concatenate([c['east']  for c in curtains])
    all_north = np.concatenate([c['north'] for c in curtains])
    dx = float(all_east.max()  - all_east.min())
    dy = float(all_north.max() - all_north.min())
    xy_range = max(dx, dy, 1.0)
    z_bot    = min(c['z_bot'] for c in curtains)
    z_top    = max(c['z_top'] for c in curtains)
    dz       = max(z_top - z_bot, 1.0)
    z_ratio  = round(dz / xy_range, 2)

    # Padded fixed ranges -- toggling traces will NOT rescale the scene
    x_pad = max(dx * 0.05, 1.0)
    y_pad = max(dy * 0.05, 1.0)
    z_pad = max(dz * 0.05, 0.5)
    x_range = [float(all_east.min())  - x_pad, float(all_east.max())  + x_pad]
    y_range = [float(all_north.min()) - y_pad, float(all_north.max()) + y_pad]
    z_range = [z_bot - z_pad, z_top + z_pad]

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

    # Track lines: one per limb, drawn along the true surface elevation
    for p in panels:
        fig.add_trace(go.Scatter3d(
            x=p['east'], y=p['north'], z=p['elev'],
            mode='lines',
            line=dict(color=p['colour'], width=4, dash=p['dash']),
            name=p['label'],
            legendgroup=p['legend_id'],
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
        title='FlowerPetal GPR profiles -- draped on GNSS surface',
        scene=dict(
            xaxis=dict(title='Easting (m, EPSG:4083)',  range=x_range),
            yaxis=dict(title='Northing (m, EPSG:4083)', range=y_range),
            zaxis=dict(title='Elevation (m asl)',        range=z_range),
            aspectmode='manual',
            aspectratio=dict(x=1.0, y=1.0, z=z_ratio),
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
        description='3D plot of FlowerPetal GPR profiles draped on the GNSS surface.'
    )
    parser.add_argument('--velocity', type=float, default=None,
                        help='Override wave velocity in m/ns (default: per-profile params)')
    parser.add_argument('--gain', type=float, default=0.0,
                        help='Linear gain exponent, indexed from surface (default: 0 = off)')
    parser.add_argument('--clip', type=float, default=99.0,
                        help='Amplitude clip percentile for initial colour scale (default: 99)')
    parser.add_argument('--out', type=str, default=None,
                        help='Output HTML path (default: auto)')
    args = parser.parse_args()

    if not GNSS_FP.exists():
        sys.exit('GNSS CSV not found: ' + str(GNSS_FP.resolve()))

    gnss_df = load_gnss_fp(GNSS_FP)
    print('Loaded {} FlowerPetal GNSS points'.format(len(gnss_df)))

    curtains = []
    for profile_key, line_key, colour in FP_PROFILES:
        npz_path = PROC_DIR / (profile_key + '_processed.npz')
        if not npz_path.exists():
            print('  [skip] {} -- processed NPZ not found'.format(profile_key))
            continue
        east_fn, north_fn, elev_fn = build_track_interps(gnss_df, line_key)
        velocity = args.velocity if args.velocity else load_velocity(profile_key)
        c = drape_curtain(profile_key, east_fn, north_fn, elev_fn,
                          velocity, gain_exp=args.gain)
        c['colour'] = colour
        c['short']  = line_key
        curtains.append(c)
        print('  {} -- {} traces, surface {:.1f} m, base {:.1f} m asl'.format(
            profile_key, c['n_traces'], c['z_top'], c['z_bot']))

    if not curtains:
        sys.exit('No FlowerPetal processed NPZ files found in {}'.format(PROC_DIR))

    fig = make_figure(curtains, args.clip)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUT_DIR / 'flowerpetal_3d.html'
    fig.write_html(str(out_path))
    print('Saved: {}'.format(out_path.resolve()))


if __name__ == '__main__':
    main()

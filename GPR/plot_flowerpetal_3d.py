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

Gain and clip are interactive sliders in the HTML.  Gain is display-only and
rebuilt in the browser from the raw amplitude (embedded ONCE, as each surface's
initial surfacecolor) -- the saved NPZs stay un-gained; clip restyles the colour
range.  Doing the gain in JS keeps the HTML small: one amplitude copy instead of
one per gain preset (was ~67 MB with the presets baked in).

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
from profile_geometry import reconcile_geometry

# ---- PATHS -------------------------------------------------------------------
HERE       = Path(__file__).parent
PROC_DIR   = HERE / '../../Data/GPR/Processed'
GNSS_FP    = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv'
GNSS_LINES = HERE / '../../Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv'
OUT_DIR    = HERE / '../../Results/GPR/FlowerPetals3D'
LIDAR_XYZ  = HERE / '../../LiDAR La Corona/Reregistered clouds/PF_junction_subsampled.xyz'

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
    """Read velocity (m/ns) from the saved params, falling back to V_DEFAULT."""
    params_path = PROC_DIR / (profile_key + '_params.json')
    if params_path.exists():
        with open(str(params_path), encoding='utf-8') as f:
            return float(json.load(f).get('velocity', V_DEFAULT))
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


def make_figure(curtains, clip_pct, gain_presets, default_gain,
                vexag=1.0, edge=None, plumb=None, lidar=None, equalize=True):
    # Geometry panels (split loops into limbs; straight lines stay whole)
    panels = []
    for i, c in enumerate(curtains):
        panels.extend(split_panels(c, i))
    n_surfs = len(panels)

    # The gained, equalised surfacecolor is rebuilt in the BROWSER (see
    # write_html) from the raw amplitude embedded once per panel.  The browser
    # computes  colour = raw * (sample/sfreq)^gain / eqfac, exactly replicating
    # gdp's linear gain + the per-curtain 99th-percentile equalisation here.
    #
    # Raw is pre-scaled per curtain by kfac (its 99th percentile) so the embedded
    # numbers are ~order 1 (smaller JSON); kfac is folded back into eqfac so the
    # final colour is identical:  (raw/kfac) * w / (eqfac/kfac) = raw * w / eqfac.
    kfac = [float(np.percentile(np.abs(c['amp']), 99)) or 1.0 for c in curtains]

    eqfac = []   # eqfac[curtain_idx][gain_idx], already divided by kfac
    for ci, c in enumerate(curtains):
        row = []
        for g in gain_presets:
            gained = display_gain(c['amp'], c['sfreq'], g)
            fac = (float(np.percentile(np.abs(gained), 99)) or 1.0) if equalize else 1.0
            row.append(fac / kfac[ci])
        eqfac.append(row)

    # Raw per-panel amplitude (pre-scaled), embedded once for the JS rebuild.
    panels_raw = [(curtains[p['curtain_idx']]['amp'][:, p['sl']]
                   / kfac[p['curtain_idx']]) for p in panels]
    raw_vmax = 1.0   # transient colour range before JS runs (pre-scaled ~order 1)

    def panel_surf(g):
        """Equalised surfacecolor per panel at gain g -- the SAME result the JS
        rebuild produces, used here only to derive the clip thresholds."""
        gi = gain_presets.index(g)
        out = []
        for p in panels:
            ci = p['curtain_idx']
            fac = eqfac[ci][gi] * kfac[ci]            # original 99th-pct factor
            gained = display_gain(curtains[ci]['amp'], curtains[ci]['sfreq'], g) / fac
            out.append(gained[:, p['sl']])
        return out

    # Equalised amplitudes at the default gain -> source for the clip presets.
    surf0   = panel_surf(default_gain)
    all_amp = np.concatenate([a.ravel() for a in surf0])

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
            # surfacecolor is injected by JS on load (kept out of the figure so
            # the raw amplitude is embedded only once, in the JS state).
            colorscale='RdBu_r',
            cmin=-raw_vmax, cmax=raw_vmax,
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

    # Clip presets: colour-range thresholds from the default-gain equalised data.
    # Equalisation pins every gain's 99th percentile to ~1, so one threshold set
    # works across gains -- the browser just restyles cmin/cmax.
    clip_presets = [90, 95, 98, 99, 99.5]
    clip_vmax = [float(np.percentile(np.abs(all_amp), cp)) for cp in clip_presets]
    clip_default_idx = min(range(len(clip_presets)),
                           key=lambda i: abs(clip_presets[i] - clip_pct))

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
        legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.7)'),
        margin=dict(l=30, r=80, t=60, b=30),
        height=780,
        scene_camera=dict(
            eye=dict(x=1.4, y=1.4, z=0.6),
        ),
    )

    # State the browser needs to rebuild gained colour live (see write_html).
    # 'raw' is the pre-scaled amplitude per panel (one copy of the data).
    state = {
        'surf_idx': surf_idx,
        'curtain_of_surf': [p['curtain_idx'] for p in panels],
        'sfreq': [float(c['sfreq']) for c in curtains],
        'gains': [float(g) for g in gain_presets],
        'eqfac': [[float(v) for v in row] for row in eqfac],
        'default_gain_idx': gain_presets.index(default_gain),
        'clips': [float(c) for c in clip_presets],
        'clip_vmax': [float(v) for v in clip_vmax],
        'default_clip_idx': clip_default_idx,
        'raw': [np.round(a, 5).tolist() for a in panels_raw],
    }
    return fig, state


def write_html(fig, state, out_path):
    """Write a self-contained (offline) HTML: the Plotly figure plus left-side
    gain/clip sliders whose handlers rebuild the gained, equalised surfacecolor
    in the browser from the raw amplitude embedded once in each surface."""
    fig_html = fig.to_html(include_plotlyjs='inline', full_html=False,
                           div_id='gpr3d_fig')

    page = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>FlowerPetals 3D</title>
  <style>
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; }}
    .wrap {{ display: grid; grid-template-columns: 230px 1fr; gap: 12px; padding: 10px; }}
    .controls {{ border: 1px solid #d0d0d0; border-radius: 8px; padding: 12px;
                 height: fit-content; position: sticky; top: 10px; }}
    .ctrl {{ margin-bottom: 16px; }}
    .ctrl label {{ display: block; font-weight: 600; margin-bottom: 4px; }}
    .ctrl input[type=range] {{ width: 100%; }}
    .value {{ font-size: 13px; color: #222; margin-top: 3px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="controls">
      <div class="ctrl">
        <label>Gain exponent</label>
        <input id="gain_slider" type="range" min="0" max="{gmax}" step="1" value="{g0}" />
        <div id="gain_value" class="value"></div>
      </div>
      <div class="ctrl">
        <label>Clip percentile</label>
        <input id="clip_slider" type="range" min="0" max="{cmax}" step="1" value="{c0}" />
        <div id="clip_value" class="value"></div>
      </div>
    </div>
    <div>{fig_html}</div>
  </div>
  <script>
    const S = {state_json};
    const gd = document.getElementById('gpr3d_fig');
    const gainSlider = document.getElementById('gain_slider');
    const clipSlider = document.getElementById('clip_slider');
    const RAW = S.raw;   // pre-scaled amplitude per panel (the single data copy)

    function applyAll() {{
      const gi = parseInt(gainSlider.value, 10);
      const ci = parseInt(clipSlider.value, 10);
      const g  = S.gains[gi];
      const colors = [];
      for (let s = 0; s < S.surf_idx.length; s++) {{
        const c  = S.curtain_of_surf[s];
        const sf = S.sfreq[c];
        const eq = S.eqfac[c][gi];
        const raw = RAW[s];
        const out = new Array(raw.length);
        for (let k = 0; k < raw.length; k++) {{
          const w = (g > 0) ? Math.pow((k + 1) / sf, g) : 1.0;
          const scale = w / eq;
          const row = raw[k];
          const orow = new Array(row.length);
          for (let j = 0; j < row.length; j++) orow[j] = row[j] * scale;
          out[k] = orow;
        }}
        colors.push(out);
      }}
      const vm = S.clip_vmax[ci];
      const n  = S.surf_idx.length;
      Plotly.restyle(gd, {{
        surfacecolor: colors,
        cmin: Array(n).fill(-vm),
        cmax: Array(n).fill(vm)
      }}, S.surf_idx);
      document.getElementById('gain_value').textContent = g.toFixed(1);
      document.getElementById('clip_value').textContent = S.clips[ci].toFixed(1) + '%';
    }}

    gainSlider.addEventListener('input', applyAll);
    clipSlider.addEventListener('input', applyAll);

    // Wait until Plotly has built the plot, then inject the initial colours.
    (function init() {{
      if (gd && gd.data && gd.data.length) {{ applyAll(); }}
      else {{ setTimeout(init, 50); }}
    }})();
  </script>
</body>
</html>
""".format(
        gmax=len(state['gains']) - 1,
        cmax=len(state['clips']) - 1,
        g0=state['default_gain_idx'],
        c0=state['default_clip_idx'],
        fig_html=fig_html,
        state_json=json.dumps(state, separators=(',', ':')),
    )
    Path(out_path).write_text(page, encoding='utf-8')


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

    fig, state = make_figure(curtains, args.clip, GAIN_PRESETS, default_gain,
                             vexag=args.vexag, edge=edge, plumb=plumb, lidar=lidar,
                             equalize=args.equalize)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUT_DIR / 'flowerpetal_3d.html'
    write_html(fig, state, out_path)
    print('Saved: {}  (gain presets {}, active {})'.format(
        out_path.resolve(), GAIN_PRESETS, default_gain))


if __name__ == '__main__':
    main()

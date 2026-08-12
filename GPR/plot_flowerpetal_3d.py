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

ALSO A LIBRARY (imported as `fp` by other GPR scripts -- change these with care):
    geometry/IO : petal_track, build_track_interps, reconcile_geometry (re-export),
                  load_gnss_fp, load_gnss_lines, load_edge, load_plumb, load_lidar,
                  load_velocity
    scene       : make_figure, write_html   (reused by plot_petal_migration_3d for
                  the migrated scene + gain/clip sliders)
    constants   : PROFILES, PROC_DIR, GNSS_FP, GNSS_LINES, GAIN_PRESETS, LIDAR_XYZ, OUT_DIR
  Importers: plot_petal_migration_3d, plot_petal_migration_map, plot_petal_map,
             plot_lidar_cave_overlay, compare_intersections.
"""

import sys
import json
import argparse
import numpy as np
from pathlib import Path
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent))
from gpr_processing import display_gain
# Data layer split out to flowerpetal_io (F12); re-imported here so the five
# importer scripts keep resolving both `fp.NAME` and `from plot_flowerpetal_3d
# import ...`. reconcile_geometry is re-exported too (was re-exported before).
from profile_geometry import reconcile_geometry
from flowerpetal_io import (
    HERE, PROC_DIR, GNSS_FP, GNSS_LINES, OUT_DIR, LIDAR_XYZ,
    GAIN_PRESETS, LIDAR_SUBSAMPLE, PROFILES,
    V_DEFAULT, OFFSET_50MHZ, OFFSET_100MHZ, SECTION_START_100MHZ,
    load_gnss_fp, load_edge, load_plumb, load_gnss_lines, load_lidar,
    build_track_interps, load_velocity, petal_track, drape_curtain, split_panels,
)


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


def write_html(fig, state, out_path, title='Flower petals 3D'):
    """Write a self-contained (offline) HTML: the Plotly figure plus left-side
    gain/clip sliders whose handlers rebuild the gained, equalised surfacecolor
    in the browser from the raw amplitude embedded once in each surface.
    `title` sets the browser tab name so the unmigrated/migrated plots differ."""
    fig_html = fig.to_html(include_plotlyjs='inline', full_html=False,
                           div_id='gpr3d_fig')

    page = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{page_title}</title>
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
        page_title=title,
    )
    Path(out_path).write_text(page, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(
        description='3D plot of GPR profiles draped on the GNSS surface.'
    )
    parser.add_argument('--velocity', type=float, default=None,
                        help='Override wave velocity in m/ns (default: per-profile params)')
    parser.add_argument('--gain', type=float, default=3.0,
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
    out_path = Path(args.out) if args.out else OUT_DIR / 'flowerpetal_unmigrated_3d.html'
    write_html(fig, state, out_path, title='Flower petals 3D (unmigrated)')
    print('Saved: {}  (gain presets {}, active {})'.format(
        out_path.resolve(), GAIN_PRESETS, default_gain))


if __name__ == '__main__':
    main()

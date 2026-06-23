"""
migrate_velocity_scan.py
Constant-velocity Stolt migration scan for picking the GPR velocity from the data.

Migrates a profile over a range of trial velocities with the 2-D Stolt migration
supplied by Dr. Cedric Schmelzbach (see stolt_migration.py), and writes an interactive Plotly
HTML with a VELOCITY SLIDER: cycle the slider and pick the velocity that best
collapses diffractions / sharpens reflectors.  This is the data-driven,
lunar-analog-legitimate way to estimate velocity -- no LiDAR used; validate the
chosen velocity against the LiDAR ceiling depth afterwards (blind).

Input: Data/GPR/Topo/{line}_topo.npz  -- the topo-corrected (static datum shift
to ref_elev), un-gained, polarity-baked section.  Topo correction places every
trace at its hyperbolic position relative to a flat datum, which is exactly the
flat-surface geometry Stolt assumes; the per-trace zero-pad at the trace tops
(from the static shift) is handled by the dead-trace blanking + live-sample
taper, mirroring Dr. Cedric Schmelzbach's notebook.

Migration is run ON UN-GAINED data.  A display-only gain (--gain, default 0 =
off) may be applied for viewing -- the gdp 'linear' travel-time gain, identical
to GPRProcessing.ipynb and plot_flowerpetal_3d.py so the gain means the same
thing everywhere.

Usage:
    python migrate_velocity_scan.py
    python migrate_velocity_scan.py --line Line3_50MHz --vmin 0.08 --vmax 0.16 --dv 0.005
    python migrate_velocity_scan.py --gain 1.0 --clip 1.2
"""

import sys
import argparse
import json
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.signal import fftconvolve
from scipy.signal.windows import hann as _hann_win

sys.path.insert(0, str(Path(__file__).parent))
from stolt_migration import stolt_migration_2d
from gpr_processing import display_gain

HERE     = Path(__file__).parent
TOPO_DIR = HERE / '../../Data/GPR/Topo'
OUT_DIR  = HERE / '../../Results/GPR/Migration'

# Stolt parameters (match Cedric's notebook defaults)
PAD_T_FACTOR = 2.0    # one-sided time padding multiplier
PAD_X_TRACES = 40     # one-sided spatial padding [traces]
TAPER_W      = 5      # raised-cosine spatial edge taper [traces]
TAPER_T_FRAC = 0.10   # raised-cosine time edge taper fraction
# Live-sample (data-driven) taper at zero<->live boundaries (Hann half-widths)
LIVE_TAPER_X = 5      # [traces]
LIVE_TAPER_T = 25     # [samples]


def live_sample_taper(section):
    """Smooth Hann taper wherever live signal abuts the zero-filled (shifted)
    regions, suppressing FFT leakage from sharp amplitude edges.  Returns the
    tapered section and the boolean dead-trace mask (all-zero columns)."""
    trace_is_dead = ~np.any(section != 0, axis=0)
    mask_live = (section != 0).astype(np.float64)

    def _hann1d(hw):
        if hw <= 0:
            return np.array([1.0])
        return _hann_win(2 * int(hw) + 1)

    k_t = _hann1d(LIVE_TAPER_T)
    k_x = _hann1d(LIVE_TAPER_X)
    kernel = k_t[:, None] * k_x[None, :]
    kernel /= kernel.sum()
    taper = np.clip(fftconvolve(mask_live, kernel, mode='same'), 0.0, 1.0)
    return section * taper, trace_is_dead


def tgain_weights(t):
    """Per-sample weight basis for the gdp 'linear' display gain:
    travel_time = (k+1)/sfreq, sfreq = 1000/dt MHz, so travel_time = (k+1)*dt/1000.
    The browser raises this vector to the gain exponent (matches display_gain /
    the notebook / the 3D plot)."""
    dt = float(t[1] - t[0])
    sfreq = 1000.0 / dt
    return (np.arange(len(t)) + 1) / sfreq


def norm99(a):
    s = float(np.percentile(np.abs(a), 99))
    return a / s if s > 0 else a


def main():
    ap = argparse.ArgumentParser(description='Constant-velocity Stolt migration scan.')
    ap.add_argument('--line', default='Line3_50MHz', help='profile stem to migrate')
    ap.add_argument('--vmin', type=float, default=0.08, help='min velocity m/ns')
    ap.add_argument('--vmax', type=float, default=0.16, help='max velocity m/ns')
    ap.add_argument('--dv',   type=float, default=0.005, help='velocity step m/ns')
    ap.add_argument('--gain', type=float, default=0.0,
                    help='display-only gdp linear gain exponent (0 = off, ungained)')
    ap.add_argument('--clip', type=float, default=99.0,
                    help='initial percentile clip (0..100), applied to current view')
    ap.add_argument('--no-live-taper', action='store_true',
                    help='skip the data-driven live-sample taper')
    ap.add_argument('--gain-values', type=str, default='0.0,1.0,2.0,2.5,3.0,3.5,4.0',
                    help='comma-separated display gain exponents for slider')
    ap.add_argument('--clip-values', type=str, default='90,95,98,99,99.5',
                    help='comma-separated percentile clips for slider (e.g. 90,95,99)')
    ap.add_argument('--out', type=str, default=None, help='output HTML path')
    args = ap.parse_args()

    npz_path = TOPO_DIR / (args.line + '_topo.npz')
    if not npz_path.exists():
        sys.exit('Not found: ' + str(npz_path.resolve()))
    with np.load(str(npz_path)) as f:
        data       = f['data'].astype(np.float64)
        x          = f['dist_axis'].astype(np.float64)
        t          = f['time_axis'].astype(np.float64)
        ref_elev   = float(f['ref_elev'])
        elevations = f['elevations'].astype(np.float64)
    dt = float(t[1] - t[0])
    dx = float(x[1] - x[0])
    nt, nx = data.shape
    print('{}: {} samples x {} traces, dx={:.3f} m, dt={:.3f} ns'.format(
        args.line, nt, nx, dx, dt))

    # data-driven taper + dead-trace mask (topo shift leaves zero tops/edges)
    if args.no_live_taper:
        section, dead = data, ~np.any(data != 0, axis=0)
    else:
        section, dead = live_sample_taper(data)
    n_dead = int(dead.sum())
    print('Dead (all-zero) traces: {} / {}'.format(n_dead, nx))

    pad_x_mult   = (nx + PAD_X_TRACES) / nx
    taper_frac_x = TAPER_W / nx

    vels = np.round(np.arange(args.vmin, args.vmax + 1e-9, args.dv), 4)
    print('Stolt-migrating {} velocities {:.3f}..{:.3f} m/ns ...'.format(
        len(vels), vels[0], vels[-1]))

    frames, depth_axes = [], []
    for v in vels:
        mig = stolt_migration_2d(
            section, dt=dt, dx=dx, velocity=float(v),
            dz=0.5 * v * dt, nz=nt,
            exploding_reflector=True, apply_jacobian=True,
            pad_t=PAD_T_FACTOR, pad_x=pad_x_mult,
            taper_t=TAPER_T_FRAC, taper_x=taper_frac_x,
            depth_padding=2.0)
        if n_dead > 0:
            mig[:, dead] = 0.0
        depth = t * (0.5 * v)               # TWT -> depth below datum [m]
        frames.append(mig)
        depth_axes.append(depth)
        print('  v = {:.3f} m/ns  ->  max depth {:.2f} m  done'.format(v, depth[-1]))

    gain_vals = [float(s.strip()) for s in args.gain_values.split(',') if s.strip()]
    clip_vals = [float(s.strip()) for s in args.clip_values.split(',') if s.strip()]
    if len(gain_vals) == 0:
        gain_vals = [0.0]
    if len(clip_vals) == 0:
        clip_vals = [float(args.clip)]

    i0 = len(vels) // 2
    g0 = int(np.argmin(np.abs(np.asarray(gain_vals, dtype=float) - float(args.gain))))
    c0 = int(np.argmin(np.abs(np.asarray(clip_vals, dtype=float) - float(args.clip))))

    # Lightweight payload: precompute only velocity stacks; gain+clip are computed live in JS.
    section_norm = norm99(section).astype(np.float32)
    mig_norm_by_v = [norm99(fr).astype(np.float32) for fr in frames]

    depth0 = depth_axes[i0]
    sfreq  = 1000.0 / dt
    tgain  = tgain_weights(t)                      # (k+1)/sfreq, gdp-linear basis
    z_top0 = display_gain(section_norm, sfreq, gain_vals[g0])
    z_bot0 = display_gain(mig_norm_by_v[i0], sfreq, gain_vals[g0])

    # Python-side init clip threshold for first render.
    abs_vals0 = np.concatenate([np.abs(z_top0).ravel(), np.abs(z_bot0).ravel()])
    cthr0 = float(np.percentile(abs_vals0, clip_vals[c0])) if abs_vals0.size > 0 else 1.0
    if cthr0 <= 0:
        cthr0 = 1.0

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
        subplot_titles=('Unmigrated (Topo-corrected input)', 'Stolt migrated')
    )
    fig.add_trace(
        go.Heatmap(
            z=z_top0, x=x, y=depth0, colorscale='RdBu_r',
            zmin=-cthr0, zmax=cthr0,
            colorbar=dict(title='amp', thickness=12, y=0.79, len=0.38, x=1.05, xanchor='left'),
            hovertemplate='x %{x:.1f} m<br>z %{y:.2f} m<extra></extra>',
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Heatmap(
            z=z_bot0, x=x, y=depth0, colorscale='RdBu_r',
            zmin=-cthr0, zmax=cthr0,
            colorbar=dict(title='amp', thickness=12, y=0.21, len=0.38, x=1.05, xanchor='left'),
            hovertemplate='x %{x:.1f} m<br>z %{y:.2f} m<extra></extra>',
        ),
        row=2, col=1
    )

    elev_range0 = [ref_elev - float(depth0[-1]), ref_elev - float(depth0[0])]
    surf_line   = dict(color='black', width=1.4)
    surf_hover  = 'x %{x:.1f} m<br>elev %{y:.1f} m<extra>surface</extra>'
    fig.add_trace(go.Scatter(
        x=x, y=elevations, mode='lines', name='surface',
        line=surf_line, xaxis='x', yaxis='y3',
        showlegend=False, hovertemplate=surf_hover,
    ))
    fig.add_trace(go.Scatter(
        x=x, y=elevations, mode='lines', name='surface',
        line=surf_line, xaxis='x2', yaxis='y4',
        showlegend=False, hovertemplate=surf_hover,
    ))

    fig.update_layout(
        title='{} -- Velocity scan with unmigrated reference'.format(args.line),
        xaxis=dict(title=''),
        xaxis2=dict(title='distance (m)'),
        yaxis=dict(
            title='Depth below highest point (m)', autorange='reversed',
            range=[float(depth0[-1]), float(depth0[0])]
        ),
        yaxis2=dict(
            title='Depth below highest point (m)', autorange='reversed',
            range=[float(depth0[-1]), float(depth0[0])]
        ),
        yaxis3=dict(
            title='Elevation (m)', overlaying='y', side='right', anchor='x',
            range=elev_range0, showgrid=False,
        ),
        yaxis4=dict(
            title='Elevation (m)', overlaying='y2', side='right', anchor='x2',
            range=elev_range0, showgrid=False,
        ),
        margin=dict(l=70, r=150, t=90, b=70), height=920,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else OUT_DIR / (args.line + '_stolt_velocity_scan.html')
    fig_html = fig.to_html(include_plotlyjs='inline', full_html=False, div_id='vel_scan_fig')

    js_state = {
        'vels': [float(v) for v in vels],
        'gains': [float(g) for g in gain_vals],
        'clip_pcts': [float(c) for c in clip_vals],
        'depth_axes': [d.tolist() for d in depth_axes],
        'tgain': [float(w) for w in tgain],
        'ref_elev': float(ref_elev),
        'section_norm': np.round(section_norm, 6).tolist(),
        'mig_norm_by_v': [np.round(m, 6).tolist() for m in mig_norm_by_v],
    }

    html = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>{title}</title>
  <style>
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; }}
    .wrap {{ display: grid; grid-template-columns: 260px 1fr; gap: 12px; padding: 10px; }}
    .controls {{ border: 1px solid #d0d0d0; border-radius: 8px; padding: 10px; }}
    .ctrl {{ margin-bottom: 14px; }}
    .ctrl label {{ display: block; font-weight: 600; margin-bottom: 4px; }}
    .ctrl input[type=range] {{ width: 100%; }}
    .value {{ font-size: 13px; color: #222; margin-top: 3px; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"controls\">
      <div class=\"ctrl\">
        <label>Velocity</label>
        <input id=\"vel_slider\" type=\"range\" min=\"0\" max=\"{vmax}\" step=\"1\" value=\"{v0}\" />
        <div id=\"vel_value\" class=\"value\"></div>
      </div>
      <div class=\"ctrl\">
        <label>Gain</label>
        <input id=\"gain_slider\" type=\"range\" min=\"0\" max=\"{gmax}\" step=\"1\" value=\"{g0}\" />
        <div id=\"gain_value\" class=\"value\"></div>
      </div>
      <div class=\"ctrl\">
        <label>Clip Percentile</label>
        <input id=\"clip_slider\" type=\"range\" min=\"0\" max=\"{cmax}\" step=\"1\" value=\"{c0}\" />
        <div id=\"clip_value\" class=\"value\"></div>
      </div>
    </div>
    <div>{fig_html}</div>
  </div>
  <script>
    const S = {state_json};
    const gd = document.getElementById('vel_scan_fig');

    function gain2D(a2d, tgain, g) {{
      // gdp 'linear' display gain: weight_k = travel_time_k ** g (same as the
      // notebook + 3D plot).  g <= 0 -> unchanged.
      if (!(g > 0)) return a2d;
      const out = new Array(a2d.length);
      for (let i = 0; i < a2d.length; i++) {{
        const w = Math.pow(tgain[i], g);
        const row = a2d[i];
        const outRow = new Array(row.length);
        for (let j = 0; j < row.length; j++) outRow[j] = row[j] * w;
        out[i] = outRow;
      }}
      return out;
    }}

    function percentileAbsFromTwo(a2d, b2d, pct) {{
      const vals = [];
      for (let i = 0; i < a2d.length; i++) {{
        const ra = a2d[i];
        const rb = b2d[i];
        for (let j = 0; j < ra.length; j++) {{
          vals.push(Math.abs(ra[j]));
          vals.push(Math.abs(rb[j]));
        }}
      }}
      vals.sort((x, y) => x - y);
      if (vals.length === 0) return 1.0;
      const p = Math.min(100, Math.max(0, pct));
      const k = Math.floor((p / 100.0) * (vals.length - 1));
      const v = vals[k];
      return (v > 0) ? v : 1.0;
    }}

    function update() {{
      const vi = parseInt(document.getElementById('vel_slider').value, 10);
      const gi = parseInt(document.getElementById('gain_slider').value, 10);
      const ci = parseInt(document.getElementById('clip_slider').value, 10);

      const depth = S.depth_axes[vi];
      const gain = S.gains[gi];
      const clipPct = S.clip_pcts[ci];

      const zTop = gain2D(S.section_norm, S.tgain, gain);
      const zBot = gain2D(S.mig_norm_by_v[vi], S.tgain, gain);
      const clip = percentileAbsFromTwo(zTop, zBot, clipPct);

      Plotly.restyle(gd, {{ z: [zTop], y: [depth], zmin: [-clip], zmax: [clip] }}, [0]);
      Plotly.restyle(gd, {{ z: [zBot], y: [depth], zmin: [-clip], zmax: [clip] }}, [1]);
      const dBot = depth[depth.length - 1];
      const dTop = depth[0];
      Plotly.relayout(gd, {{
        'yaxis.range':  [dBot, dTop],
        'yaxis2.range': [dBot, dTop],
        'yaxis3.range': [S.ref_elev - dBot, S.ref_elev - dTop],
        'yaxis4.range': [S.ref_elev - dBot, S.ref_elev - dTop],
      }});

      document.getElementById('vel_value').textContent = S.vels[vi].toFixed(3) + ' m/ns';
      document.getElementById('gain_value').textContent = gain.toFixed(1);
      document.getElementById('clip_value').textContent = clipPct.toFixed(1) + '%';
    }}

    document.getElementById('vel_slider').addEventListener('input', update);
    document.getElementById('gain_slider').addEventListener('input', update);
    document.getElementById('clip_slider').addEventListener('input', update);
    update();
  </script>
</body>
</html>
""".format(
        title='{} velocity scan'.format(args.line),
        vmax=len(vels) - 1,
        gmax=len(gain_vals) - 1,
        cmax=len(clip_vals) - 1,
        v0=i0,
        g0=g0,
        c0=c0,
        fig_html=fig_html,
        state_json=json.dumps(js_state, separators=(',', ':')),
    )
    out.write_text(html, encoding='utf-8')
    print('Saved: {}'.format(out.resolve()))
    print('Use left-side sliders: velocity, gain, and live percentile clip.')


if __name__ == '__main__':
    main()

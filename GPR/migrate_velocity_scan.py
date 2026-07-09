"""
migrate_velocity_scan.py
Constant-velocity Stolt migration scan for picking the GPR velocity from the data.

Migrates a profile over a range of trial velocities with the 2-D Stolt migration
supplied by Dr. Cedric Schmelzbach (see stolt_migration.py), and writes an interactive Plotly
HTML with a VELOCITY SLIDER: cycle the slider and pick the velocity that best
collapses diffractions / sharpens reflectors.  This is the data-driven,
lunar-analog-legitimate way to estimate velocity -- no LiDAR used; validate the
chosen velocity against the LiDAR ceiling depth afterwards (blind).

Input: Data/GPR/Processed/{line}_processed.npz (pre-topo, un-gained, polarity- and
flip-baked) plus the elevation track (elevations, ref_elev) from the matching
Topo NPZ.  The static topo correction (datum shift to ref_elev) is recomputed at
EACH trial velocity, then migrated -- so both the topo shift and the migration use
the same velocity and stay self-consistent as the slider moves (the surface stays
pinned under the surface line instead of drifting at off-nominal velocities).
Topo correction places every trace at its hyperbolic position relative to a flat
datum, which is exactly the flat-surface geometry Stolt assumes; the per-trace
zero-pad at the trace tops (from the static shift) is handled by the dead-trace
blanking + live-sample taper, mirroring Dr. Cedric Schmelzbach's notebook.

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
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.signal import fftconvolve
from scipy.signal.windows import hann as _hann_win

sys.path.insert(0, str(Path(__file__).parent))
from stolt_migration import stolt_migration_2d
from gpr_processing import display_gain
from topo_correction import apply_topo_correction

HERE          = Path(__file__).parent
PROC_DIR      = HERE / '../../Data/GPR/Processed'
TOPO_DIR      = HERE / '../../Data/GPR/Topo'
OUT_DIR       = HERE / '../../Results/GPR/Migration'
MIGRATED_DIR  = HERE / '../../Results/GPR/Migrated'

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
    ap.add_argument('--pick-velocity', type=float, default=None, metavar='V',
                    help='migrate at single velocity V (m/ns) and save _migrated.npz; skips scan HTML')
    ap.add_argument('--no-live-taper', action='store_true',
                    help='skip the data-driven live-sample taper')
    ap.add_argument('--gain-values', type=str, default='0.0,1.0,2.0,2.5,3.0,3.5,4.0',
                    help='comma-separated display gain exponents for slider')
    ap.add_argument('--clip-values', type=str, default='90,95,98,99,99.5',
                    help='comma-separated percentile clips for slider (e.g. 90,95,99)')
    ap.add_argument('--out', type=str, default=None, help='output HTML path')
    args = ap.parse_args()

    # Load PRE-topo (processed) data + the velocity-independent elevation track.
    # Topo is recomputed at each trial velocity (below) so the section stays
    # consistent with its depth axis -- the surface no longer drifts under the
    # data as the velocity slider moves.
    proc_path = PROC_DIR / (args.line + '_processed.npz')
    topo_path = TOPO_DIR / (args.line + '_topo.npz')
    if not proc_path.exists():
        sys.exit('Not found: ' + str(proc_path.resolve()))
    if not topo_path.exists():
        sys.exit('Not found: ' + str(topo_path.resolve()))
    with np.load(str(proc_path)) as f:
        data0 = f['data'].astype(np.float64)
        x     = f['dist_axis'].astype(np.float64)
        t     = f['time_axis'].astype(np.float64)
    with np.load(str(topo_path)) as f:
        ref_elev   = float(f['ref_elev'])
        elevations = f['elevations'].astype(np.float64)
    dt = float(t[1] - t[0])
    dx = float(x[1] - x[0])
    nt, nx = data0.shape
    print('{}: {} samples x {} traces, dx={:.3f} m, dt={:.3f} ns'.format(
        args.line, nt, nx, dx, dt))

    pad_x_mult   = (nx + PAD_X_TRACES) / nx
    taper_frac_x = TAPER_W / nx

    def build_section(v):
        """Topo-correct the processed data at velocity v, then live-sample taper.
        Recomputing the static shift per v pins the surface to depth
        (ref_elev - elev) regardless of v, so it stays under the surface line."""
        corrected, _shifts, _re = apply_topo_correction(data0, t, elevations, v)
        if args.no_live_taper:
            return corrected, ~np.any(corrected != 0, axis=0)
        return live_sample_taper(corrected)

    # --- single-velocity NPZ + PNG save (--pick-velocity) ---
    if args.pick_velocity is not None:
        v = float(args.pick_velocity)
        print('Single migration at v = {:.4f} m/ns ...'.format(v))
        section, dead = build_section(v)
        mig = stolt_migration_2d(
            section, dt=dt, dx=dx, velocity=v,
            dz=0.5 * v * dt, nz=nt,
            exploding_reflector=True, apply_jacobian=True,
            pad_t=PAD_T_FACTOR, pad_x=pad_x_mult,
            taper_t=TAPER_T_FRAC, taper_x=taper_frac_x,
            depth_padding=2.0)
        if dead.any():
            mig[:, dead] = 0.0
        depth = t * (0.5 * v)

        # --- save NPZ ---
        MIGR_DATA_DIR = HERE / '../../Data/GPR/Migration'
        MIGR_DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_npz = MIGR_DATA_DIR / (args.line + '_migrated.npz')
        np.savez(str(out_npz),
                 data=mig.astype(np.float32),
                 dist_axis=x,
                 depth_axis=depth,
                 ref_elev=np.float64(ref_elev),
                 elevations=elevations,
                 velocity=np.float64(v))
        print('Saved NPZ: {}'.format(out_npz.resolve()))

        # --- static PNG ---
        gain_exp = args.gain
        plot_data = mig.copy()
        if gain_exp > 0:
            dz = float(depth[1] - depth[0])
            sfreq_eq = 1000.0 * v / (2.0 * dz)   # equivalent MHz for depth gain
            plot_data = display_gain(plot_data, sfreq_eq, gain_exp)
        clip = float(np.percentile(np.abs(plot_data), args.clip))
        if clip <= 0:
            clip = 1.0

        fig, axes = plt.subplots(2, 1, figsize=(14, 6),
                                 gridspec_kw={'height_ratios': [1, 4], 'hspace': 0.06})
        axes[0].plot(x, elevations, color='0.3', linewidth=1.0)
        axes[0].set_ylabel('Elev. (m)', fontsize=9)
        axes[0].set_xlim(float(x[0]), float(x[-1]))
        axes[0].tick_params(labelbottom=False)

        axes[1].imshow(plot_data, aspect='auto', cmap='seismic',
                       vmin=-clip, vmax=clip,
                       extent=[float(x[0]), float(x[-1]),
                               float(depth[-1]), float(depth[0])],
                       interpolation='nearest')
        axes[1].set_ylabel('Depth (m)', fontsize=9)
        axes[1].set_xlabel('Distance (m)', fontsize=9)

        gain_str = '  |  gain {:.1f}'.format(gain_exp) if gain_exp > 0 else ''
        axes[0].set_title(
            '{} -- Stolt migrated  |  v = {:.4f} m/ns{}'.format(args.line, v, gain_str),
            fontsize=10, loc='left')

        axes[1].text(0.01, 0.99, 'N', transform=axes[1].transAxes,
                     ha='left', va='top', fontsize=11, fontweight='bold', color='black')
        axes[1].text(0.99, 0.99, 'S', transform=axes[1].transAxes,
                     ha='right', va='top', fontsize=11, fontweight='bold', color='black')

        MIGRATED_DIR.mkdir(parents=True, exist_ok=True)
        out_png = MIGRATED_DIR / (args.line + '_migrated.png')
        plt.savefig(str(out_png), dpi=180, bbox_inches='tight')
        plt.close(fig)
        print('Saved PNG: {}'.format(out_png.resolve()))

        # --- before/after comparison (stacked: input on top, migrated below) ---
        # `section` is the topo-corrected migration input; `mig` its migration.
        # Same depth axis, same gain, per-panel clip -> only migration differs.
        # Conventions match the other figures: TWT on the right of the (time-domain)
        # before panel, absolute elevation on the right of the migrated after panel,
        # and the surface topography drawn inside both (air overburden shaded).
        before = display_gain(section, 1000.0 / dt, gain_exp) if gain_exp > 0 else section
        after  = display_gain(mig,     1000.0 / dt, gain_exp) if gain_exp > 0 else mig
        clip_b = float(np.percentile(np.abs(before), args.clip)) or 1.0
        clip_a = float(np.percentile(np.abs(after),  args.clip)) or 1.0
        ext_ba = [float(x[0]), float(x[-1]), float(depth[-1]), float(depth[0])]
        ba_depth_max = min(25.0, float(depth[-1]))   # nothing of interest below ~25 m
        surf_depth   = ref_elev - elevations         # surface depth below datum (per trace)

        fig2, ax2 = plt.subplots(2, 1, figsize=(14, 9), sharex=True,
                                 gridspec_kw={'hspace': 0.14})
        ax2[0].imshow(before, aspect='auto', cmap='seismic', vmin=-clip_b, vmax=clip_b,
                      extent=ext_ba, interpolation='nearest')
        ax2[0].set_title('{} -- before migration (topo-corrected input)'.format(args.line),
                         fontsize=10, loc='left')
        ax2[0].set_ylabel('Depth (m)', fontsize=9)
        ax2[1].imshow(after, aspect='auto', cmap='seismic', vmin=-clip_a, vmax=clip_a,
                      extent=ext_ba, interpolation='nearest')
        ax2[1].set_title('after Stolt migration  |  v = {:.3f} m/ns{}'.format(v, gain_str),
                         fontsize=10, loc='left')
        ax2[1].set_ylabel('Depth (m)', fontsize=9)
        ax2[1].set_xlabel('Distance (m)', fontsize=9)

        for _a in ax2:
            _a.fill_between(x, 0.0, surf_depth, color='0.85', zorder=2, linewidth=0)
            _a.plot(x, surf_depth, color='k', linewidth=1.1, zorder=3)
            _a.set_ylim(ba_depth_max, 0.0)
            _a.text(0.01, 0.99, 'N', transform=_a.transAxes, ha='left', va='top',
                    fontsize=11, fontweight='bold', color='black')
            _a.text(0.99, 0.99, 'S', transform=_a.transAxes, ha='right', va='top',
                    fontsize=11, fontweight='bold', color='black')

        # right-hand axes: TWT (ns) on the before panel, elevation (m asl) on the after
        _tax0 = ax2[0].twinx()
        _tax0.set_ylim(2.0 * ba_depth_max / v, 0.0)
        _tax0.set_ylabel('TWT (ns)', fontsize=9)
        _tax1 = ax2[1].twinx()
        _tax1.set_ylim(ref_elev - ba_depth_max, ref_elev)
        _tax1.set_ylabel('Elevation (m asl)', fontsize=9)

        out_ba = MIGRATED_DIR / (args.line + '_before_after.png')
        fig2.savefig(str(out_ba), dpi=180, bbox_inches='tight')
        plt.close(fig2)
        print('Saved before/after: {}'.format(out_ba.resolve()))
        return

    vels = np.round(np.arange(args.vmin, args.vmax + 1e-9, args.dv), 4)
    print('Stolt-migrating {} velocities {:.3f}..{:.3f} m/ns ...'.format(
        len(vels), vels[0], vels[-1]))

    top_frames, frames, depth_axes = [], [], []
    for v in vels:
        section, dead = build_section(v)     # topo-corrected at THIS velocity
        mig = stolt_migration_2d(
            section, dt=dt, dx=dx, velocity=float(v),
            dz=0.5 * v * dt, nz=nt,
            exploding_reflector=True, apply_jacobian=True,
            pad_t=PAD_T_FACTOR, pad_x=pad_x_mult,
            taper_t=TAPER_T_FRAC, taper_x=taper_frac_x,
            depth_padding=2.0)
        if dead.any():
            mig[:, dead] = 0.0
        depth = t * (0.5 * v)               # TWT -> depth below datum [m]
        top_frames.append(section)
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

    # Payload: the MIGRATED panel is a per-velocity stack. The top (unmigrated,
    # topo-corrected) panel is rebuilt in JS from a SINGLE pre-topo array by rolling
    # each trace by the static shift at the current velocity. This keeps the file
    # small enough to afford 6-decimal precision -- so gain at depth stays smooth
    # (storing 16 top copies forced 3 decimals, which the depth gain amplified into
    # blocky quantisation).
    pre_topo_norm = norm99(data0).astype(np.float32)
    mig_norm_by_v = [norm99(fr).astype(np.float32) for fr in frames]
    top0_norm     = norm99(top_frames[i0]).astype(np.float32)   # initial render only

    depth0 = depth_axes[i0]
    sfreq  = 1000.0 / dt
    tgain  = tgain_weights(t)                      # (k+1)/sfreq, gdp-linear basis
    z_top0 = display_gain(top0_norm, sfreq, gain_vals[g0])
    z_bot0 = display_gain(mig_norm_by_v[i0], sfreq, gain_vals[g0])

    # Python-side init clip threshold for first render.
    abs_vals0 = np.concatenate([np.abs(z_top0).ravel(), np.abs(z_bot0).ravel()])
    cthr0 = float(np.percentile(abs_vals0, clip_vals[c0])) if abs_vals0.size > 0 else 1.0
    if cthr0 <= 0:
        cthr0 = 1.0

    # depth-to-surface customdata: depth_below_datum - (ref_elev - elev(x))
    elev_corr = ref_elev - elevations           # static shift per trace, shape (nx,)
    dts0 = (depth0[:, None] - elev_corr[None, :]).tolist()   # (nt, nx)
    hover_tmpl = 'x %{x:.1f} m<br>depth to surface: %{customdata:.2f} m<extra></extra>'

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
        subplot_titles=('Unmigrated (Topo-corrected input)', 'Stolt migrated')
    )
    fig.add_trace(
        go.Heatmap(
            z=z_top0, x=x, y=depth0, colorscale='RdBu_r',
            zmin=-cthr0, zmax=cthr0,
            customdata=dts0,
            hovertemplate=hover_tmpl,
            colorbar=dict(title='amp', thickness=12, y=0.79, len=0.38, x=1.05, xanchor='left'),
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Heatmap(
            z=z_bot0, x=x, y=depth0, colorscale='RdBu_r',
            zmin=-cthr0, zmax=cthr0,
            customdata=dts0,
            hovertemplate=hover_tmpl,
            colorbar=dict(title='amp', thickness=12, y=0.21, len=0.38, x=1.05, xanchor='left'),
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

    # N/S endpoint annotations -- convention: North on left, South on right
    for _xval, _text, _xanchor in [
        (float(x[0]),  '<b>N</b>', 'left'),
        (float(x[-1]), '<b>S</b>', 'right'),
    ]:
        for _yref in ('y domain', 'y2 domain'):
            fig.add_annotation(
                x=_xval, xref='x', y=1.0, yref=_yref,
                text=_text, showarrow=False,
                xanchor=_xanchor, yanchor='bottom',
                font=dict(size=14, color='black'),
            )

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
        'elev_corr': elev_corr.tolist(),   # ref_elev - elev(x), one value per trace
        'dt': float(dt),
        # One pre-topo array (top panel rebuilt per-v in JS by rolling) + the
        # migrated stack, at 6 decimals so depth gain stays smooth.
        'pre_topo': np.round(pre_topo_norm, 6).tolist(),
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

    // depth-to-surface: depth_below_datum - elev_corr[trace]
    // elev_corr[i] = ref_elev - elev(x_i), precomputed in Python (static).
    function depthToSurf(depth) {{
      const nc = S.elev_corr.length;
      return depth.map(d => {{
        const row = new Array(nc);
        for (let i = 0; i < nc; i++) row[i] = d - S.elev_corr[i];
        return row;
      }});
    }}

    // Rebuild the topo-corrected (unmigrated) top panel at velocity v by rolling
    // each trace of the single stored pre-topo array down by its static shift
    // sh = round(2*elev_corr/v/dt) -- exactly what apply_topo_correction does in
    // Python, but done per-slider so the surface stays pinned across velocities.
    function buildTop(v) {{
      const P = S.pre_topo, ec = S.elev_corr, dt = S.dt;
      const nt = P.length, nx = P[0].length;
      const out = new Array(nt);
      for (let r = 0; r < nt; r++) out[r] = new Array(nx).fill(0.0);
      for (let j = 0; j < nx; j++) {{
        const sh = Math.round(2.0 * ec[j] / v / dt);
        for (let r = 0; r < nt; r++) {{
          const src = r - sh;
          if (src >= 0 && src < nt) out[r][j] = P[src][j];
        }}
      }}
      return out;
    }}

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

      const zTop = gain2D(buildTop(S.vels[vi]), S.tgain, gain);
      const zBot = gain2D(S.mig_norm_by_v[vi], S.tgain, gain);
      const clip = percentileAbsFromTwo(zTop, zBot, clipPct);
      const dts  = depthToSurf(depth);

      Plotly.restyle(gd, {{ z: [zTop], y: [depth], zmin: [-clip], zmax: [clip], customdata: [dts] }}, [0]);
      Plotly.restyle(gd, {{ z: [zBot], y: [depth], zmin: [-clip], zmax: [clip], customdata: [dts] }}, [1]);
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

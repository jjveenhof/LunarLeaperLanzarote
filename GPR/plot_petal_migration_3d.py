"""
plot_petal_migration_3d.py
3D view of Stolt-migrated flower-petal SEGMENTS alongside the migrated Line 3,
draped in the same scene as the unmigrated 3D plot (cave, pit rim, plumb).

Full 3-D migration is out of scope; instead each petal loop is cut into the
reasonably STRAIGHT sub-segments picked from plot_petal_map.py (SEGMENTS below,
distance-along-track in metres), and each straight segment is run through the
existing 2-D Stolt code (migrate_velocity_scan machinery: static topo correction
at the profile velocity -> live-sample taper -> Stolt migration). The migrated
segments are then draped as flat-datum curtains (migration references a flat
surface, so the curtain top sits at the segment's datum = its highest surface
point; relief within a short straight segment is small).

Line 3 is included from its already-migrated NPZ (Data/GPR/Migration/
Line3_50MHz_migrated.npz). All the furniture (LiDAR cave, pit edge, plumb) and
the interactive gain/clip sliders are reused verbatim from plot_flowerpetal_3d.py
via make_figure/write_html -- this script only swaps the draped curtains for
migrated ones.

Usage:
    python plot_petal_migration_3d.py
    python plot_petal_migration_3d.py --gain 3.0 --clip 99
Output:
    Results/GPR/FlowerPetals3D/flowerpetal_migrated_3d.html
"""

import sys
import argparse
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plot_flowerpetal_3d as fp
from topo_correction import apply_topo_correction
from stolt_migration import stolt_migration_2d
from migrate_velocity_scan import (
    live_sample_taper, PAD_T_FACTOR, PAD_X_TRACES, TAPER_W, TAPER_T_FRAC)

HERE      = Path(__file__).parent
MIGR_DIR  = HERE / '../../Data/GPR/Migration'
OUT_DIR   = fp.OUT_DIR

# Straight sub-segments per petal, distance-along-track (m); None = to the end.
# Picked from Results/GPR/Migration/petal_map.png. Tune here and rerun.
SEGMENTS = {
    'FlowerPetal1_50MHz': [(0, 28), (40, 52), (57, None)],
    'FlowerPetal2_50MHz': [(0, 30), (50, None)],   # 50-70 + 70-end merged into one
    'FlowerPetal3_50MHz': [(0, 25), (32, 48), (49, None)],
}

# One colour per segment (index-matched to SEGMENTS lists).
SEG_COLOURS = {
    'FlowerPetal1_50MHz': ['crimson', 'darkorange', 'magenta'],
    'FlowerPetal2_50MHz': ['royalblue', 'teal', 'navy'],
    'FlowerPetal3_50MHz': ['limegreen', 'olive', 'darkgreen'],
}

# Line 3 migrated sections drawn in the same scene (from their saved _migrated.npz).
# (key, colour, label) -- both frequencies, matching the unmigrated 3D plot which
# also shows L3 at 50 and 100 MHz.
L3_LINES = [
    ('Line3_50MHz',  'purple',    'L3 50MHz migrated'),
    ('Line3_100MHz', 'goldenrod', 'L3 100MHz migrated'),
]


def _petal_prof(key):
    return next(p for p in fp.PROFILES if p['key'] == key)


def _track(prof):
    """(dist_axis, time_axis, data, east, north, elev, dist_along) for a petal,
    geometry reconciled to the (flip-baked) data columns exactly as drape_curtain."""
    with np.load(str(fp.PROC_DIR / (prof['key'] + '_processed.npz'))) as f:
        data      = f['data'].astype(np.float64)
        dist_axis = f['dist_axis'].astype(np.float64)
        time_axis = f['time_axis'].astype(np.float64)
    gnss_df = fp.load_gnss_fp(fp.GNSS_FP)
    east_fn, north_fn, elev_fn = fp.build_track_interps(
        gnss_df, prof['gnss_line'], prof['metre'])
    gnss_m = dist_axis + prof['offset']
    east, north, elev = fp.reconcile_geometry(
        prof['key'], east_fn(gnss_m), north_fn(gnss_m), elev_fn(gnss_m))
    seg = np.hypot(np.diff(east), np.diff(north))
    dist_along = np.concatenate([[0.0], np.cumsum(seg)])
    return dist_axis, time_axis, data, east, north, elev, dist_along


def _curtain(name, label, colour, east_s, north_s, elev_s, amp, depth, ref_elev, sfreq):
    """Assemble the drape_curtain-shaped dict make_figure expects, for a migrated
    section. The migrated section is referenced to a flat datum (ref_elev), so a
    sample at row k sits at absolute elevation ref_elev - depth[k]. To make the
    curtain hug the real topography (instead of a flat top at the datum), the grid
    ABOVE each trace's own surface -- the dead-datum triangle from the static shift
    -- is blanked with NaN Z, which Plotly renders as a gap. Display-only: amp and
    the migration are untouched, and the live reflectors keep their true elevation."""
    n_samp = amp.shape[0]
    nx = amp.shape[1]
    X = np.tile(east_s[np.newaxis, :],  (n_samp, 1))
    Y = np.tile(north_s[np.newaxis, :], (n_samp, 1))
    Z = np.tile((ref_elev - depth)[:, np.newaxis], (1, nx)).astype(np.float64)
    # blank grid above each trace's true surface: depth[k] < (ref_elev - elev_i)
    above = depth[:, np.newaxis] < (ref_elev - np.asarray(elev_s))[np.newaxis, :]
    Z[above] = np.nan
    dtrace = float(np.hypot(east_s[1] - east_s[0], north_s[1] - north_s[0])) \
        if nx > 1 else 1.0
    return {
        'X': X, 'Y': Y, 'Z': Z,
        'amp': amp, 'sfreq': sfreq,
        'name': name, 'label': label,
        'colours': (colour,), 'loop': False, 'split_offset_m': 0.0,
        'dtrace': dtrace,
        'east': east_s, 'north': north_s, 'elev': elev_s,
        'z_top': float(ref_elev),
        'z_bot': float(np.nanmin(Z)),
        'n_traces': nx,
    }


def migrate_segment(prof, start_m, end_m, velocity, colour, label):
    """Cut a straight sub-segment, topo-correct + Stolt-migrate it, return a
    migrated curtain (flat-datum drape)."""
    dist_axis, time_axis, data, east, north, elev, dist_along = _track(prof)
    end = float(dist_along[-1]) if end_m is None else float(end_m)
    idx = np.where((dist_along >= float(start_m)) & (dist_along <= end))[0]
    if idx.size < 3:
        print('  [skip] {}: <3 traces in {}-{} m'.format(prof['key'], start_m, end_m))
        return None
    sl = slice(int(idx[0]), int(idx[-1]) + 1)
    data_s, east_s, north_s, elev_s = data[:, sl], east[sl], north[sl], elev[sl]

    corrected, _shifts, ref_elev = apply_topo_correction(
        data_s, time_axis, elev_s, velocity)
    section, dead = live_sample_taper(corrected)

    dt = float(time_axis[1] - time_axis[0])
    dx = float(dist_axis[1] - dist_axis[0])
    nt, nx = data_s.shape
    mig = stolt_migration_2d(
        section, dt=dt, dx=dx, velocity=velocity,
        dz=0.5 * velocity * dt, nz=nt,
        exploding_reflector=True, apply_jacobian=True,
        pad_t=PAD_T_FACTOR, pad_x=(nx + PAD_X_TRACES) / nx,
        taper_t=TAPER_T_FRAC, taper_x=TAPER_W / nx,
        depth_padding=2.0)
    if dead.any():
        mig[:, dead] = 0.0
    depth = time_axis * (0.5 * velocity)     # below datum (ref_elev)
    sfreq = 1000.0 / dt
    print('  {}: {}-{} m -> {} traces migrated'.format(
        prof['key'], start_m, '' if end_m is None else end_m, nx))
    return _curtain(prof['key'] + '_{}'.format(int(start_m)), label, colour,
                    east_s, north_s, elev_s, mig, depth, ref_elev, sfreq)


def l3_curtain(key, colour, label):
    """Migrated Line 3 (one frequency) from its saved NPZ, draped flat-datum."""
    with np.load(str(MIGR_DIR / (key + '_migrated.npz'))) as f:
        data      = f['data'].astype(np.float64)
        dist_axis = f['dist_axis'].astype(np.float64)
        depth     = f['depth_axis'].astype(np.float64)
        ref_elev  = float(f['ref_elev'])
        velocity  = float(f['velocity'])
    prof = _petal_prof(key)
    gnss_df = fp.load_gnss_lines(fp.GNSS_LINES)
    east_fn, north_fn, elev_fn = fp.build_track_interps(
        gnss_df, prof['gnss_line'], prof['metre'])
    gnss_m = dist_axis + prof['offset']
    east, north, elev = fp.reconcile_geometry(
        key, east_fn(gnss_m), north_fn(gnss_m), elev_fn(gnss_m))
    dz = float(depth[1] - depth[0])
    sfreq = 1000.0 * velocity / (2.0 * dz)   # depth-domain equivalent for the gain
    print('  {}: migrated NPZ, {} traces, v={:.3f}'.format(key, data.shape[1], velocity))
    return _curtain(key + '_migrated', label, colour,
                    east, north, elev, data, depth, ref_elev, sfreq)


def main():
    ap = argparse.ArgumentParser(description='3D migrated petal segments + L3.')
    ap.add_argument('--gain', type=float, default=3.0,
                    help='initial gain preset (snapped to nearest button)')
    ap.add_argument('--clip', type=float, default=99.0, help='initial clip percentile')
    ap.add_argument('--vexag', type=float, default=1.0, help='vertical exaggeration')
    ap.add_argument('--no-edge',  dest='edge',  action='store_false')
    ap.add_argument('--no-plumb', dest='plumb', action='store_false')
    ap.add_argument('--no-lidar', dest='lidar', action='store_false')
    ap.set_defaults(edge=True, plumb=True, lidar=True)
    ap.add_argument('--out', type=str, default=None)
    args = ap.parse_args()

    curtains = []
    for key, segs in SEGMENTS.items():
        prof = _petal_prof(key)
        velocity = fp.load_velocity(key)
        colours = SEG_COLOURS[key]
        for j, (s, e) in enumerate(segs):
            label = '{} {}-{} m'.format(prof['label'], s, '' if e is None else e)
            c = migrate_segment(prof, s, e, velocity,
                                colours[j % len(colours)], label)
            if c is not None:
                curtains.append(c)

    for key, colour, label in L3_LINES:
        curtains.append(l3_curtain(key, colour, label))

    default_gain = min(fp.GAIN_PRESETS, key=lambda g: abs(g - args.gain))
    edge  = fp.load_edge(fp.GNSS_FP)  if args.edge  else None
    plumb = fp.load_plumb(fp.GNSS_FP) if args.plumb else None
    lidar = fp.load_lidar(fp.LIDAR_XYZ) if args.lidar else None

    fig, state = fp.make_figure(curtains, args.clip, fp.GAIN_PRESETS, default_gain,
                                vexag=args.vexag, edge=edge, plumb=plumb, lidar=lidar,
                                equalize=True)
    fig.update_layout(title=dict(
        text='Migrated GPR segments (flower petals + Line 3) draped on GNSS surface',
        x=0.5, xanchor='center', y=0.98, yanchor='top'))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUT_DIR / 'flowerpetal_migrated_3d.html'
    fp.write_html(fig, state, out_path, title='Flower petals 3D (migrated)')
    print('Saved: {}'.format(out_path.resolve()))


if __name__ == '__main__':
    main()

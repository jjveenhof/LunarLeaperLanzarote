"""
plot_lidar_cave_overlay.py
THESIS figure: the LF (50 MHz) Stolt-migrated sections of L3 and L5 with the LiDAR
cave outline overlaid (section + outline only -- no GPR picks). Two stacked panels
(L3 top, L5 bottom), each with a primary Depth (m) axis and a secondary Elevation
(m asl) axis, matching the final migrated-profile figures.

Co-registration: the LiDAR outline CSVs store absolute
REGCAN95 (EPSG:4083) coords; the legacy `x` column is IGNORED. Instead each outline
vertex's (easting, northing) is projected onto the GPR section's own along-profile
axis by least-squares regression of the section's (E,N) onto its dist_axis -- exactly
what plot_model_terrain.gravity_profile() does for the gravity plots. Vertically the
outline drops in as depth = ref_elev - z. Grav and GPR lines are assumed colocated.

The section's (E,N) per trace come from the GNSS line track (same machinery as
plot_flowerpetal_3d), reconciled for flip_x so they align column-for-column with the
migrated data; a startup assert checks them against the migrated NPZ's stored
elevations so a flip/alignment slip is caught rather than silently mis-registering.

LiDAR outlines: Data/LiDAR/lidar_line{3,5}.csv (cols x,z,easting,northing; x ignored).
These are *.csv, which Code/.gitignore excludes -- untracked, local only.

Usage:
    python plot_lidar_cave_overlay.py
Output:
    Results/GPR/Migration/lidar_cave_overlay.png  (+ title-free thesis PDF)
"""

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plot_flowerpetal_3d as fp
from plot_dual_freq import load_npz, load_param, load_clip, CMAP
from gpr_processing import display_gain
from gpr_constants import OFFSET_50MHZ
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure

HERE     = Path(__file__).parent
MIGR_DIR = HERE / '../../Data/GPR/Migration'
LIDAR_DIR = HERE / '../../Data/LiDAR'
OUT_DIR  = HERE / '../../Results/GPR/Migrated'   # alongside the other migrated section figures

# Per line: GNSS line id + offset (dist_axis -> GNSS metre). flip is handled by
# fp.reconcile_geometry keyed on the profile, so it isn't repeated here.
LINES = {
    3: dict(gnss_line=3, offset=OFFSET_50MHZ, label='L3'),
    5: dict(gnss_line=5, offset=OFFSET_50MHZ, label='L5'),
}

OUTLINE_COLOUR = '#9400D3'   # violet -- matches LIDAR_COLOR in the grav terrain plots
OUTLINE_LW     = 1.8         # LiDAR outline line width
FIG_W          = 6.1         # inches (thesis linewidth; see plot_utils FIGURE-SIZING RULE)
ASPECT         = 0.8         # metres y : metres x drawn equal; 1.0 = true scale,
                             # <1 = flatter (a bit less than 1:1), >1 = vertical exaggeration
OUTLINE_DEPTH_MARGIN = 2.0   # extend the panel this far below the deepest outline point (m)


def project_to_track(te, tn, td, pe, pn):
    """Project points (pe,pn) onto the ACTUAL GNSS track polyline (te,tn) whose
    per-vertex along-track distance is td. For each point, find the nearest point
    on any track segment and return (along-track distance, perpendicular offset).

    This uses the full dense RTK track rather than a straight-line least-squares
    idealisation of it -- the most faithful registration the ground truth allows.
    The perpendicular offset is the real lateral separation of the LiDAR slice from
    the GPR line, which no projection can remove (it is geometry, not error)."""
    ax, ay = te[:-1], tn[:-1]
    dx, dy = te[1:] - ax, tn[1:] - ay
    seg2 = dx * dx + dy * dy
    seg2[seg2 == 0] = 1e-12
    out_d = np.empty(len(pe))
    out_perp = np.empty(len(pe))
    for k in range(len(pe)):
        t = np.clip(((pe[k] - ax) * dx + (pn[k] - ay) * dy) / seg2, 0.0, 1.0)
        fx, fy = ax + t * dx, ay + t * dy
        d2 = (pe[k] - fx) ** 2 + (pn[k] - fy) ** 2
        j = int(np.argmin(d2))
        out_d[k] = td[j] + t[j] * (td[j + 1] - td[j])
        out_perp[k] = float(np.sqrt(d2[j]))
    return out_d, out_perp


def prepare(n):
    """Load one line's migrated section + projected LiDAR outline."""
    cfg = LINES[n]
    key = 'Line{}_50MHz'.format(n)
    line = 'Line{}'.format(n)

    npz_path = MIGR_DIR / (key + '_migrated.npz')
    if not npz_path.exists():
        sys.exit('Migrated NPZ not found: ' + str(npz_path))
    data, dist_axis, depth_axis, is_depth, vel, ref_elev, elevs = load_npz(npz_path)
    if not is_depth or ref_elev is None or elevs is None:
        sys.exit('{}: expected a migrated (depth) NPZ with ref_elev/elevations'.format(key))

    # --- section (E,N) per trace, reconciled to the (flipped) data columns ---
    gnss_df = fp.load_gnss_lines(fp.GNSS_LINES)
    east_fn, north_fn, elev_fn = fp.build_track_interps(gnss_df, cfg['gnss_line'],
                                                        'meter_col')
    gnss_m = dist_axis + cfg['offset']
    east, north, elev = fp.reconcile_geometry(
        key, east_fn(gnss_m), north_fn(gnss_m), elev_fn(gnss_m))
    # alignment guard: reconciled elevations must match the NPZ's stored ones,
    # else the (E,N) used for the projection don't line up with the plotted data.
    dmax = float(np.max(np.abs(elev - elevs)))
    if dmax > 1.0:
        sys.exit('{}: reconciled elevations disagree with NPZ by {:.2f} m -- '
                 'geometry/flip misalignment, aborting'.format(key, dmax))
    print('  {}: elevation alignment max diff {:.3f} m (ok)'.format(key, dmax))

    # --- project the outline onto the actual dense GNSS track (not a straight fit) ---
    lid_path = LIDAR_DIR / 'lidar_line{}.csv'.format(n)
    lid = np.genfromtxt(str(lid_path), delimiter=',', names=True)
    # Cross-folder schema contract (see Code/LiDAR/README.md): Grav/grav_utils.py
    # reads this same file. Assert the expected columns here so a wrong-column read
    # (e.g. a re-exported CSV with a header change) fails legibly instead of silently
    # mis-registering the outline.
    expected_cols = {'x', 'z', 'easting', 'northing'}
    actual_cols = set(lid.dtype.names or ())
    if actual_cols != expected_cols:
        sys.exit('{}: unexpected columns in {} -- got {}, expected {}'.format(
            key, lid_path, sorted(actual_cols), sorted(expected_cols)))
    lx, perp = project_to_track(np.asarray(east), np.asarray(north), dist_axis,
                                lid['easting'], lid['northing'])
    ly = ref_elev - lid['z']                     # depth below datum
    print('  {}: outline lateral offset from track: mean {:.2f} m, max {:.2f} m'
          .format(key, float(np.mean(perp)), float(np.max(perp))))
    # close the outline loop for a clean cross-section
    lx = np.append(lx, lx[0])
    ly = np.append(ly, ly[0])

    # --- display gain + clip from params (migrated stage), like plot_dual_freq ---
    gain = float(load_param(line, '50MHz', 'migration_gain', 0.0))
    clip_pct = load_clip(line, '50MHz')
    depth_max = load_param(line, '50MHz', 'depth_max')
    disp = data
    if gain > 0:
        dz = float(depth_axis[1] - depth_axis[0])
        sfreq_eq = 1000.0 * vel / (2.0 * dz)     # depth-domain equiv of 1000/dt
        disp = display_gain(data, sfreq_eq, gain)
    clip = float(np.percentile(np.abs(disp), clip_pct))
    # depth extent: the params cap, but always deep enough to show the whole outline
    # (L5's cave floor falls below the section's default cap).
    zmax = float(depth_axis[-1])
    if depth_max:
        zmax = min(float(depth_max), zmax)
    zmax = max(zmax, float(np.nanmax(ly)) + OUTLINE_DEPTH_MARGIN)

    return dict(line=line, label=cfg['label'], disp=disp, dist_axis=dist_axis,
                depth_axis=depth_axis, ref_elev=ref_elev, elevs=elevs,
                clip=clip, gain=gain, clip_pct=clip_pct, zmax=zmax, vel=vel,
                lx=lx, ly=ly)


def render(ax, P):
    xs = P['dist_axis']
    ax.imshow(P['disp'], aspect='auto', cmap=CMAP,
              vmin=-P['clip'], vmax=P['clip'],
              extent=[float(xs[0]), float(xs[-1]),
                      float(P['depth_axis'][-1]), float(P['depth_axis'][0])],
              interpolation='nearest')
    ax.set_xlim(float(xs[0]), float(xs[-1]))
    ax.set_ylim(P['zmax'], 0.0)
    ax.set_aspect(ASPECT, adjustable='box')   # metres y : metres x (see ASPECT)

    # surface topography + air overburden shading (depth = ref_elev - elev)
    surf_depth = P['ref_elev'] - P['elevs']
    ax.fill_between(xs, 0.0, surf_depth, color='0.85', zorder=2, linewidth=0)
    ax.plot(xs, surf_depth, color='k', linewidth=1.1, zorder=3)

    # LiDAR cave outline
    ax.plot(P['lx'], P['ly'], color=OUTLINE_COLOUR, lw=OUTLINE_LW, zorder=4,
            label='LiDAR cave outline')

    # secondary elevation axis (m asl) = ref_elev - depth. secondary_yaxis (a
    # transform of the depth axis) instead of twinx, so it stays synced and does
    # not conflict with the fixed data aspect.
    refe = P['ref_elev']
    sax = ax.secondary_yaxis('right', functions=(lambda d: refe - d,
                                                 lambda e: refe - e))
    sax.set_ylabel('Elevation (m asl)', fontsize=9)

    ax.set_ylabel('Depth (m)', fontsize=9)
    ax.set_title('{} -- 50 MHz | gain {:.1f} | clip {:.1f}%'.format(
        P['label'], P['gain'], P['clip_pct']), fontsize=9, loc='left')


def main():
    P3 = prepare(3)
    P5 = prepare(5)

    # Each equal-aspect panel's box height (inches) = ASPECT * depth/width * panel
    # width. Size the FIGURE height to the sum of those (+ chrome) so the panels
    # aren't short boxes floating in a too-tall figure.
    panel_w = FIG_W - 1.4          # usable width after the L/R y-axis labels (approx)
    def _panel_h(P):
        xr = float(P['dist_axis'][-1] - P['dist_axis'][0])
        return ASPECT * P['zmax'] / xr * panel_w
    ph3, ph5 = _panel_h(P3), _panel_h(P5)
    fig_h = ph3 + ph5 + 1.3        # + titles / xlabel / inter-panel gap
    fig = plt.figure(figsize=(FIG_W, fig_h))
    gs = gridspec.GridSpec(2, 1, figure=fig,
                           height_ratios=[ph3, ph5], hspace=0.30)
    ax3 = fig.add_subplot(gs[0, 0])
    ax5 = fig.add_subplot(gs[1, 0])
    render(ax3, P3)
    render(ax5, P5)
    ax5.set_xlabel('Distance (m)', fontsize=9)
    ax3.legend(fontsize=7, loc='lower right', frameon=False)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'lidar_cave_overlay.png'
    fig.savefig(str(out), dpi=200, bbox_inches='tight')
    thesis_path, _ = save_figure(fig, out.stem, 'GPR', vector=True, dpi=300,
                                 titles='auto')
    plt.close(fig)
    print('Saved: {}'.format(out))
    print('thesis -> {}'.format(thesis_path))


if __name__ == '__main__':
    main()

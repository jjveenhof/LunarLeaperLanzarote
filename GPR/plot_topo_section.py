"""
plot_topo_section.py
QC-figure half of the topo correction (compute/plot split). topo_correction.py
keeps the numeric core (elevation interp, static shift, the `_topo.npz` writer);
this module holds ONLY the single-panel topographic radargram PNG it emits.

Nothing here writes an NPZ, so it cannot move a thesis number -- the split is purely
compute-vs-plot for digestibility. topo_correction imports `save_topo_figure` and the
`CLIP_FALLBACK` constant back from here.
"""

from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import sys
sys.path.insert(0, str(Path(__file__).parent))
from gpr_processing import display_gain             # display-only gain for the QC PNG

CLIP_FALLBACK = 99.5   # QC-PNG clip percentile if the params JSON has no clip_percentile


def save_topo_figure(out_path, profile_key, dist_axis, time_axis,
                     corrected, elevations, v, ref_elev, gain_exp=0.0, flip_x=False,
                     annotate_ns=True, clip_pct=CLIP_FALLBACK):
    """Single-panel topographic section: the radargram is drawn on an absolute
    elevation axis (m asl) so the surface relief sits inside the plot. The data is
    referenced to a flat datum (= max elevation) by the static shift, so the real
    surface dips below the datum -- that gap is the air overburden and is shaded."""
    fig, ax = plt.subplots(figsize=(14, 6))

    # Display-only gain (saved NPZ stays un-gained); uses the recorded view gain
    disp = corrected
    gain_note = ''
    if gain_exp and gain_exp > 0:
        sfreq = 1000.0 / float(time_axis[1] - time_axis[0])   # MHz
        disp = display_gain(corrected, sfreq, gain_exp)
        gain_note = ' | view gain {:.1f}'.format(gain_exp)

    # Map the time axis to absolute elevation: elev = ref_elev - TWT * v / 2.
    # Row 0 (time 0) is the datum (highest surface point); deeper rows are lower.
    t_max      = float(time_axis[-1])
    elev_bot   = ref_elev - t_max * v / 2.0

    clip_val = np.percentile(np.abs(disp), clip_pct)
    im = ax.imshow(disp, aspect='auto', cmap='seismic',
                   vmin=-clip_val, vmax=clip_val,
                   extent=[dist_axis[0], dist_axis[-1], elev_bot, ref_elev])

    # surface topography drawn inside the section; shade the air above it
    ax.fill_between(dist_axis, elevations, ref_elev,
                    color='0.85', zorder=3, linewidth=0)
    ax.plot(dist_axis, elevations, color='k', linewidth=1.3, zorder=4)

    ax.set_xlim(dist_axis[0], dist_axis[-1])
    ax.set_ylim(elev_bot, ref_elev)
    ax.set_xlabel('Distance (m)')
    ax.set_ylabel('Elevation (m asl)')
    # pretty label: "Line3_50MHz" -> "Line3 -- 50 MHz" (avoids the raw underscore,
    # which renders as a raised mark in Computer Modern)
    _p = profile_key.split('_')
    pretty = '{} -- {}'.format(_p[0], _p[1].replace('MHz', ' MHz')) \
        if len(_p) == 2 else profile_key
    ax.set_title('{} | v = {:.3f} m/ns{} | clip {:.1f}%'.format(
        pretty, v, gain_note, clip_pct))

    # N/S endpoint labels inside the section at top corners. Only meaningful for
    # the straight lines -- the flower petals curve through many azimuths (acquired
    # clockwise), so N/S is dropped there (orientation is read from the 3D plan view).
    if annotate_ns:
        ax.text(0.01, 0.03, 'N', transform=ax.transAxes, ha='left', va='bottom',
                fontsize=11, fontweight='bold', color='black')
        ax.text(0.99, 0.03, 'S', transform=ax.transAxes, ha='right', va='bottom',
                fontsize=11, fontweight='bold', color='black')

    # right-hand axis: depth below datum (m) = ref_elev - elevation = TWT * v / 2
    tax = ax.twinx()
    tax.set_ylim(t_max * v / 2.0, 0.0)   # 0 at datum, increasing downward
    tax.set_ylabel('Depth below datum (m)')

    plt.tight_layout()
    plt.savefig(str(out_path), dpi=150)
    plt.close(fig)

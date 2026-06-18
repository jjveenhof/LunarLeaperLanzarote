"""
compare_intersections.py
Polarity / consistency check between Line 3 and the FlowerPetals.

Where Line 3 crosses each 50 MHz petal, the same patch of ground is sampled
twice, so a shared reflector should look the same.  A clean sign reversal at the
crossing points to a polarity *convention* difference (wiring / instrument /
processing), not geology -- in which case flipping one dataset's sign is valid.

For each crossing this plots, side by side:
  - a small map of the two tracks with the crossing marked,
  - the nearest trace from each line, normalised and overlaid, so you can read
    the polarity of the strong shallow events directly.

Track geometry (offsets, metre mapping) is imported from plot_flowerpetal_3d so
it stays identical to the 3D view.  Both profiles are time-zero corrected in
processing, so their time axes are directly comparable.

Usage:
    python compare_intersections.py
    python compare_intersections.py --line Line3_50MHz --tmax 200
"""

import sys
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.spatial.distance import cdist

sys.path.insert(0, str(Path(__file__).parent))
import plot_flowerpetal_3d as p3d
from plot_flowerpetal_3d import (PROFILES, PROC_DIR, GNSS_FP, GNSS_LINES,
                                 load_gnss_fp, load_gnss_lines, build_track_interps)

OUT_DIR = Path(__file__).parent / '../../Results/GPR/PolarityCheck'

# Which profiles to compare: one straight line vs the petals (all 50 MHz)
DEFAULT_LINE = 'Line3_50MHz'
PETALS       = ['FlowerPetal1_50MHz', 'FlowerPetal2_50MHz', 'FlowerPetal3_50MHz']

AVG_HALFWIN = 2     # average +/- this many traces at the crossing to cut noise


def get_profile(key, gnss):
    """Return per-trace track (E, N), the radargram, time axis, and colour."""
    prof = next(p for p in PROFILES if p['key'] == key)
    east_fn, north_fn, _ = build_track_interps(
        gnss[prof['source']], prof['gnss_line'], prof['metre'])
    with np.load(str(PROC_DIR / (key + '_processed.npz'))) as f:
        data = f['data'].astype(np.float64)
        dist = f['dist_axis'].astype(np.float64)
        time = f['time_axis'].astype(np.float64)
    gnss_m = dist + prof['offset']
    return {
        'key': key, 'label': prof['label'], 'colour': prof['colours'][0],
        'E': east_fn(gnss_m), 'N': north_fn(gnss_m),
        'data': data, 'time': time,
    }


def nearest_crossing(a, b):
    """Closest approach between two tracks: returns (idx_a, idx_b, dist_m)."""
    D = cdist(np.c_[a['E'], a['N']], np.c_[b['E'], b['N']])
    ia, ib = np.unravel_index(np.argmin(D), D.shape)
    return int(ia), int(ib), float(D[ia, ib])


def avg_trace(data, idx, w=AVG_HALFWIN):
    lo = max(0, idx - w)
    hi = min(data.shape[1], idx + w + 1)
    return data[:, lo:hi].mean(axis=1)


def norm(tr):
    m = float(np.max(np.abs(tr)))
    return tr / m if m > 0 else tr


def main():
    ap = argparse.ArgumentParser(description='Polarity check at Line/petal crossings.')
    ap.add_argument('--line', default=DEFAULT_LINE, help='straight line profile key')
    ap.add_argument('--tmax', type=float, default=None,
                    help='max two-way time to show in ns (default: full)')
    args = ap.parse_args()

    gnss = {'fp': load_gnss_fp(GNSS_FP), 'lines': load_gnss_lines(GNSS_LINES)}
    line = get_profile(args.line, gnss)
    petals = [get_profile(k, gnss) for k in PETALS
              if (PROC_DIR / (k + '_processed.npz')).exists()]
    if not petals:
        sys.exit('No petal processed NPZs found.')

    nrow = len(petals)
    fig, axes = plt.subplots(nrow, 2, figsize=(11, 3.6 * nrow),
                             gridspec_kw={'width_ratios': [1.0, 1.3]})
    axes = np.atleast_2d(axes)

    print('Crossings with {} ({}):'.format(line['key'], line['label']))
    for r, pet in enumerate(petals):
        il, ip, dist = nearest_crossing(line, pet)
        cx, cy = line['E'][il], line['N'][il]
        flag = '' if dist < 2.0 else '   [!] far -- may not be a true crossing'
        print('  {:<18} dist {:.2f} m  (line trace {}, petal trace {}){}'.format(
            pet['label'], dist, il, ip, flag))

        # --- map ---
        axm = axes[r, 0]
        axm.plot(line['E'], line['N'], '-', color='0.6', lw=1.2, label=line['label'])
        axm.plot(pet['E'], pet['N'], '-', color=pet['colour'], lw=1.2, label=pet['label'])
        axm.plot(cx, cy, 'kx', ms=9, mew=2, label='crossing')
        axm.set_aspect('equal', 'datalim')
        axm.set_title('{} x {}   ({:.2f} m apart)'.format(
            line['label'], pet['label'], dist), fontsize=9)
        axm.set_xlabel('Easting (m)'); axm.set_ylabel('Northing (m)')
        axm.legend(fontsize=7, loc='best')
        axm.ticklabel_format(useOffset=False, style='plain')
        axm.tick_params(labelsize=7)

        # --- overlaid traces ---
        axt = axes[r, 1]
        tl = norm(avg_trace(line['data'], il))
        tp = norm(avg_trace(pet['data'], ip))
        tmax = args.tmax if args.tmax else max(line['time'][-1], pet['time'][-1])

        # objective polarity: cross-correlate over the shown window (petal
        # resampled onto the line time grid).  The peak SIGN is the polarity
        # (negative => reversed); the peak LAG absorbs residual time-zero shift.
        dt = float(line['time'][1] - line['time'][0])
        mask = line['time'] <= tmax
        a = tl[mask] - tl[mask].mean()
        b = np.interp(line['time'][mask], pet['time'], tp)
        b = b - b.mean()
        cc = np.correlate(a, b, 'full') / (np.sqrt((a**2).sum() * (b**2).sum()) + 1e-12)
        lags = np.arange(-len(a) + 1, len(b)) * dt
        win = np.abs(lags) <= 25.0          # only near-zero lags
        k = np.where(win)[0][np.argmax(np.abs(cc[win]))]
        cc_peak, cc_lag = float(cc[k]), float(lags[k])
        verdict = ('REVERSED' if cc_peak < -0.3 else
                   'same' if cc_peak > 0.3 else 'unclear')

        axt.plot(tl, line['time'], color='k', lw=1.3, label=line['label'])
        axt.plot(tp, pet['time'], color=pet['colour'], lw=1.3, label=pet['label'])
        axt.axvline(0, color='0.8', lw=0.8)
        axt.set_ylim(tmax, 0)
        axt.set_xlim(-1.1, 1.1)
        axt.set_xlabel('normalised amplitude'); axt.set_ylabel('two-way time (ns)')
        axt.set_title('xcorr {:+.2f} at {:+.0f} ns  ->  {}'.format(
            cc_peak, cc_lag, verdict), fontsize=9)
        axt.legend(fontsize=8, loc='lower right')
        axt.grid(True, alpha=0.3)
        print('    {} xcorr peak {:+.2f} at lag {:+.0f} ns -> {}'.format(
            pet['label'], cc_peak, cc_lag, verdict))

    fig.suptitle('Line 3 vs FlowerPetals -- polarity check at crossings', fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'intersection_traces.png'
    fig.savefig(str(out), dpi=160)
    plt.close(fig)
    print('Saved: {}'.format(out.resolve()))


if __name__ == '__main__':
    main()

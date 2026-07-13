"""
compare_intersections.py
Polarity / consistency check between Line 3 and the FlowerPetals.

Where Line 3 crosses each 50 MHz petal, the same patch of ground is sampled
twice, so a shared reflector should look the same.  A clean sign reversal at the
crossing points to a polarity *convention* difference (wiring / instrument /
processing), not geology -- in which case flipping one dataset's sign is valid.

The petals are loops, so Line 3 generally crosses each one TWICE (in and out);
all crossings are found via segment intersection, not just the closest approach.

For each crossing this plots, in three panels:
  - a map of the two tracks with the crossing marked,
  - the nearest trace from each line, display-gained and normalised, overlaid,
  - the normalised cross-correlation of the two traces, computed on the
    UN-GAINED traces (so the strong shallow events that set the convention
    dominate): the peak SIGN is the polarity (negative = reversed) and the peak
    LAG absorbs any residual time-zero shift.

Track geometry (offsets, metre mapping) is imported from plot_flowerpetal_3d so
it stays identical to the 3D view.  Gain is display-only (matches the rest of
the pipeline); the saved NPZs are untouched.

Usage:
    python compare_intersections.py
    python compare_intersections.py --gain 2.5
    python compare_intersections.py --line Line3_50MHz --tmax 250
"""

import sys
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.signal import hilbert

sys.path.insert(0, str(Path(__file__).parent))
from plot_flowerpetal_3d import (PROFILES, PROC_DIR, GNSS_FP, GNSS_LINES,
                                 load_gnss_fp, load_gnss_lines, build_track_interps)
from profile_geometry import reconcile_geometry
from gpr_processing import display_gain

OUT_DIR = Path(__file__).parent / '../../Results/GPR/PolarityCheck'

# Which profiles to compare: one straight line vs the petals (all 50 MHz)
DEFAULT_LINE = 'Line3_50MHz'
PETALS       = ['FlowerPetal1_50MHz', 'FlowerPetal2_50MHz', 'FlowerPetal3_50MHz']

AVG_HALFWIN = 2      # average +/- this many traces at the crossing to cut noise
LAG_WIN_NS  = 25.0   # only search for the xcorr peak within this lag (ns)


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
    east, north = reconcile_geometry(key, east_fn(gnss_m), north_fn(gnss_m))
    return {
        'key': key, 'label': prof['label'], 'colour': prof['colours'][0],
        'E': east, 'N': north,
        'data': data, 'time': time,
    }


def find_crossings(a, b, min_sep_m=0.5):
    """
    All geometric crossings of track a with track b, via segment intersection.
    Returns a list of dicts {il, ip, pt} (nearest trace on each, crossing point),
    de-duplicated so a single crossing split across adjacent segments counts once.
    """
    A = np.c_[a['E'], a['N']]
    B = np.c_[b['E'], b['N']]
    hits = []
    for i in range(len(A) - 1):
        p1, r = A[i], A[i + 1] - A[i]
        for j in range(len(B) - 1):
            p3, s = B[j], B[j + 1] - B[j]
            denom = r[0] * s[1] - r[1] * s[0]
            if abs(denom) < 1e-12:
                continue
            qp = p3 - p1
            t = (qp[0] * s[1] - qp[1] * s[0]) / denom
            u = (qp[0] * r[1] - qp[1] * r[0]) / denom
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                pt = p1 + t * r
                il = int(np.argmin(np.hypot(A[:, 0] - pt[0], A[:, 1] - pt[1])))
                ip = int(np.argmin(np.hypot(B[:, 0] - pt[0], B[:, 1] - pt[1])))
                hits.append({'il': il, 'ip': ip, 'pt': pt})

    # de-duplicate crossings that map to the same physical point
    out = []
    for h in hits:
        if any(np.hypot(*(h['pt'] - o['pt'])) < min_sep_m for o in out):
            continue
        out.append(h)
    return out


def avg_trace(data, idx, w=AVG_HALFWIN):
    lo = max(0, idx - w)
    hi = min(data.shape[1], idx + w + 1)
    return data[:, lo:hi].mean(axis=1)


def gain_trace(tr, time, exponent):
    """Display-only gdp linear gain on a single trace."""
    sfreq = 1000.0 / float(time[1] - time[0])
    return display_gain(tr[:, np.newaxis], sfreq, exponent)[:, 0]


def norm(tr):
    m = float(np.max(np.abs(tr)))
    return tr / m if m > 0 else tr


def main():
    ap = argparse.ArgumentParser(description='Polarity check at Line/petal crossings.')
    ap.add_argument('--line', default=DEFAULT_LINE, help='straight line profile key')
    ap.add_argument('--gain', type=float, default=3.0,
                    help='display gain exponent applied to the traces (default: 3.0)')
    ap.add_argument('--tmax', type=float, default=None,
                    help='max two-way time to show in ns (default: full)')
    args = ap.parse_args()

    gnss = {'fp': load_gnss_fp(GNSS_FP), 'lines': load_gnss_lines(GNSS_LINES)}
    line = get_profile(args.line, gnss)
    petals = [get_profile(k, gnss) for k in PETALS
              if (PROC_DIR / (k + '_processed.npz')).exists()]
    if not petals:
        sys.exit('No petal processed NPZs found.')

    # collect every crossing of the line with every petal
    crossings = []
    for pet in petals:
        cl = find_crossings(line, pet)
        for n, c in enumerate(sorted(cl, key=lambda h: h['il']), 1):
            c['pet'] = pet
            c['name'] = '{} #{}'.format(pet['label'], n)
            crossings.append(c)
    if not crossings:
        sys.exit('No crossings found between {} and the petals.'.format(line['label']))

    nrow = len(crossings)
    fig, axes = plt.subplots(nrow, 3, figsize=(8.6, 1.95 * nrow),
                             gridspec_kw={'width_ratios': [1.0, 1.2, 1.0]})
    axes = np.atleast_2d(axes)

    print('Crossings with {} ({}), display gain {}:'.format(
        line['key'], line['label'], args.gain))
    for r, c in enumerate(crossings):
        pet, il, ip = c['pet'], c['il'], c['ip']
        cx, cy = line['E'][il], line['N'][il]
        dist = float(np.hypot(line['E'][il] - pet['E'][ip],
                              line['N'][il] - pet['N'][ip]))

        # display traces (gained) and metric traces (un-gained)
        tl = norm(gain_trace(avg_trace(line['data'], il), line['time'], args.gain))
        tp = norm(gain_trace(avg_trace(pet['data'],  ip), pet['time'],  args.gain))
        rl = norm(avg_trace(line['data'], il))
        rp = norm(avg_trace(pet['data'],  ip))
        tmax = args.tmax if args.tmax else max(line['time'][-1], pet['time'][-1])

        # cross-correlation on UN-GAINED traces (petal resampled onto line grid)
        dt = float(line['time'][1] - line['time'][0])
        mask = line['time'] <= tmax
        a = rl[mask] - rl[mask].mean()
        b = np.interp(line['time'][mask], pet['time'], rp)
        b = b - b.mean()
        cc = np.correlate(a, b, 'full') / (np.sqrt((a**2).sum() * (b**2).sum()) + 1e-12)
        lags = np.arange(-len(a) + 1, len(b)) * dt
        # The wavelet rings, so cc oscillates -- pick the lag where the cc
        # ENVELOPE peaks (true alignment, immune to cycle-skip), then read the
        # signed cc there for polarity.
        env = np.abs(hilbert(cc))
        win = np.abs(lags) <= LAG_WIN_NS
        k = np.where(win)[0][np.argmax(env[win])]
        cc_peak, cc_lag = float(cc[k]), float(lags[k])
        verdict = ('REVERSED' if cc_peak < -0.3 else
                   'same' if cc_peak > 0.3 else 'unclear')
        vcol = ('tab:red' if cc_peak < -0.3 else
                'tab:green' if cc_peak > 0.3 else 'gray')
        print('  {:<10} dist {:.2f} m   xcorr {:+.2f} @ {:+.0f} ns -> {}'.format(
            c['name'], dist, cc_peak, cc_lag, verdict))

        # --- map ---
        axm = axes[r, 0]
        axm.plot(line['E'], line['N'], '-', color='0.6', lw=1.2, label=line['label'])
        axm.plot(pet['E'], pet['N'], '-', color=pet['colour'], lw=1.2, label=pet['label'])
        axm.plot(cx, cy, 'kx', ms=5, mew=1.2, label='crossing')
        axm.set_aspect('equal', 'datalim')
        axm.set_title('{}   ({:.2f} m apart)'.format(c['name'], dist), fontsize=9)
        axm.set_xlabel('Easting (m)'); axm.set_ylabel('Northing (m)')
        axm.legend(fontsize=7, loc='best')
        axm.ticklabel_format(useOffset=False, style='plain')
        axm.tick_params(labelsize=7)

        # --- overlaid traces (time on x) ---
        axt = axes[r, 1]
        axt.plot(line['time'], tl, color='k', lw=1.2, label=line['label'])
        axt.plot(pet['time'], tp, color=pet['colour'], lw=1.2, label=pet['label'])
        axt.axhline(0, color='0.8', lw=0.8)
        axt.set_xlim(0, tmax)
        axt.set_ylim(-1.1, 1.1)
        axt.set_xlabel('two-way time (ns)')
        axt.set_ylabel('norm. amplitude')      # gain stated in the caption
        axt.set_title('overlaid traces', fontsize=9)
        axt.legend(fontsize=8, loc='upper right')
        axt.grid(True, alpha=0.3)

        # --- cross-correlation curve ---
        axc = axes[r, 2]
        axc.axvspan(-LAG_WIN_NS, LAG_WIN_NS, color='0.92')
        axc.plot(lags, cc, color=pet['colour'], lw=1.2)
        axc.plot(lags, env, color='0.5', lw=0.9, ls='--', label='envelope')
        axc.plot(lags, -env, color='0.5', lw=0.9, ls='--')
        axc.axhline(0, color='0.7', lw=0.8)
        axc.plot([cc_lag], [cc_peak], 'o', color=vcol, ms=4)
        axc.set_xlim(-50, 50)
        axc.set_ylim(-1.05, 1.05)
        axc.set_xlabel('lag (ns)')
        axc.set_ylabel('norm. cross-corr')
        axc.set_title('peak {:+.2f} @ {:+.0f} ns  ->  {}'.format(cc_peak, cc_lag, verdict),
                      fontsize=9, color=vcol)
        axc.grid(True, alpha=0.3)

    # share axes down the rows: the trace (col 1) and xcorr (col 2) columns have
    # identical x/y meaning per row, so only the bottom row needs the x label/ticks.
    # The map column (col 0) keeps its own ticks (each crossing spans a different
    # E/N range) but sheds the repeated axis-label words on non-bottom rows.
    for r in range(nrow):
        if r < nrow - 1:
            for col in range(3):
                axes[r, col].set_xlabel('')
            axes[r, 1].tick_params(labelbottom=False)
            axes[r, 2].tick_params(labelbottom=False)
        if r > 0:
            axes[r, 1].set_title('')      # generic "overlaid traces" only on top

    fig.suptitle('Line 3 vs FlowerPetals -- polarity check at all crossings', fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.98])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'intersection_traces.png'
    fig.savefig(str(out), dpi=160)
    import sys as _sys, pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
    from plot_utils import save_figure
    save_figure(fig, out.stem, "Appendices", vector=True)   # title-free thesis PDF
    plt.close(fig)
    print('Saved: {}'.format(out.resolve()))


if __name__ == '__main__':
    main()

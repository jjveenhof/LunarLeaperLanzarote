"""
check_polarity.py
First-break polarity convention check across every processed profile.

The direct air/ground wave at the top of every trace has a polarity fixed by
the acquisition convention (wiring, and any stitch-flip baked in).  Averaging
across traces stacks that direct wave coherently while reflectors (which move
with position) average out, so the mean trace gives a clean, per-profile
convention signature -- independent of frequency or survey geometry, so it
classifies ALL profiles, not just the ones that cross each other.

Each profile is scored by the SIGN of the dominant peak of its mean trace in an
early window (the direct wave).  Profiles are then classified against the
FlowerPetals as the reference convention; a flipped profile is one whose direct
wave is mirror-imaged relative to the petals.

Reads the processed NPZs (sign-preserving pipeline), so it reflects the current
state -- re-run after a stitch fix + reprocess to confirm everything lines up.

Usage:
    python check_polarity.py
    python check_polarity.py --tmeas 40 --tdisp 100
"""

import sys
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure
from pathlib import Path

HERE     = Path(__file__).parent
PROC_DIR = HERE / '../../Data/GPR/Processed'
OUT_DIR  = HERE / '../../Results/GPR/PolarityCheck'

# Profiles whose convention defines the reference ("+")
REF_KEYS = ['FlowerPetal1_50MHz', 'FlowerPetal2_50MHz', 'FlowerPetal3_50MHz']


def load_mean(npz_path):
    with np.load(str(npz_path)) as f:
        data = f['data'].astype(np.float64)
        time = f['time_axis'].astype(np.float64)
    return data.mean(axis=1), time


def dominant_sign(mean_trace, time, t_meas):
    """Sign (and time) of the dominant peak within the first t_meas ns."""
    win = time <= t_meas
    m, t = mean_trace[win], time[win]
    if not np.any(m):
        return 0, 0.0
    k = int(np.argmax(np.abs(m)))
    return int(np.sign(m[k])), float(t[k])


def norm(tr):
    a = float(np.max(np.abs(tr)))
    return tr / a if a > 0 else tr


def main():
    ap = argparse.ArgumentParser(description='First-break polarity convention check.')
    ap.add_argument('--tmeas', type=float, default=40.0,
                    help='window (ns) for the direct-wave dominant peak (default: 40)')
    ap.add_argument('--tdisp', type=float, default=100.0,
                    help='window (ns) shown in each panel (default: 100)')
    args = ap.parse_args()

    files = sorted(PROC_DIR.glob('*_processed.npz'))
    # skip experimental variants (e.g. the SVD-removal test) -- not part of the
    # final profile set, so they don't belong in the convention figure
    files = [f for f in files if '_svd' not in f.name]
    if not files:
        sys.exit('No processed NPZs found in {}'.format(PROC_DIR.resolve()))

    profs = []
    for fp in files:
        stem = fp.name.replace('_processed.npz', '')
        mean, time = load_mean(fp)
        sgn, t0 = dominant_sign(mean, time, args.tmeas)
        profs.append({'stem': stem, 'mean': mean, 'time': time, 'sign': sgn, 't0': t0})

    # reference convention = majority sign of the petals
    ref_signs = [p['sign'] for p in profs if p['stem'] in REF_KEYS]
    ref = int(np.sign(sum(ref_signs))) if ref_signs else 1
    if ref_signs and len(set(ref_signs)) > 1:
        print('[!] reference petals disagree on polarity -- inspect manually:', ref_signs)
    for p in profs:
        p['class'] = 'consistent' if p['sign'] == ref else 'FLIPPED'

    # --- report ---
    print('Reference convention (petals): dominant-peak sign {:+d}\n'.format(ref))
    print('{:<22} {:>5} {:>9} {:>12}'.format('profile', 'sign', 't_peak', 'vs petals'))
    for p in profs:
        print('{:<22} {:>+5d} {:>7.1f}ns {:>12}'.format(
            p['stem'], p['sign'], p['t0'], p['class']))
    flipped = [p['stem'] for p in profs if p['class'] == 'FLIPPED']
    print('\nFlipped relative to petals: {}'.format(flipped if flipped else 'none'))

    # --- figure: one mean-trace panel per profile ---
    n = len(profs)
    ncol = 3
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.45 * ncol, 1.48 * nrow),
                             sharex=True, sharey=True)
    axes = np.array(axes).reshape(nrow, ncol)

    def pretty(stem):
        # drop the underscore (cmr10 renders it as a raised dot) and space out "MHz"
        return stem.replace('_', ' ').replace('MHz', ' MHz')

    for idx, p in enumerate(profs):
        r, c = divmod(idx, ncol)
        ax = axes[r, c]
        flipped = p['class'] == 'FLIPPED'
        mark = 'tab:red' if flipped else 'tab:blue'   # pick marker; red flags a flip
        win = p['time'] <= args.tdisp
        ax.plot(p['time'][win], norm(p['mean'][win]), color='k', lw=1.2)
        ax.axhline(0, color='0.8', lw=0.7)
        ax.axvspan(0, args.tmeas, color='0.93')
        ax.axvline(p['t0'], color=mark, lw=1.3, ls='--')
        ax.set_ylim(-1.1, 1.1)
        # profile name only; sign/classification go in the console table + caption
        ax.set_title(pretty(p['stem']), fontsize=8,
                     color='tab:red' if flipped else 'black')
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)
        if c == 0:                          # shared axes: label the outer edges only
            ax.set_ylabel('norm. amplitude', fontsize=8)
        if idx + ncol >= n:                 # bottom-most filled panel in this column
            ax.set_xlabel('two-way time (ns)', fontsize=8)
            ax.tick_params(labelbottom=True)

    for idx in range(n, nrow * ncol):       # blank the unused cells
        r, c = divmod(idx, ncol)
        axes[r, c].axis('off')

    fig.suptitle('First-break polarity convention -- mean trace per profile '
                 '(grey = scoring window)', fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'convention_check.png'
    fig.savefig(str(out), dpi=160)
    save_figure(fig, out.stem, "Appendices", vector=True)   # title-free thesis PDF
    plt.close(fig)
    print('\nSaved: {}'.format(out.resolve()))


if __name__ == '__main__':
    main()

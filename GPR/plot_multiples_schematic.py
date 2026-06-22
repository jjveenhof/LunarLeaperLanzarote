"""
plot_multiples_schematic.py
Explanatory schematic of GPR reflection events over an air-filled lava tube:
the ceiling primary, the floor reflection, and the two multiples that can be
mistaken for deeper structure.

Left panel  : true geometry (rock / air cave / rock) with ray paths for each
              event, drawn at separate x positions for clarity.
Right panel : the synthetic zero-offset trace -- where each event lands in
              two-way time and in APPARENT depth (depth axis built with the rock
              velocity, the way the radargram is plotted).  This is what makes
              the floor reflection appear shallower than it really is and puts a
              ceiling multiple at ~2x the ceiling depth.

All geometry/velocity parameters are at the top -- edit to match a real crossing.

Usage:
    python plot_multiples_schematic.py
"""

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# ---- PARAMETERS (edit to taste) ----------------------------------------------
D_CEIL = 5    # rock thickness, surface to cave ceiling (m)
H_CAVE = 10    # true cave height, ceiling to floor (m)
V_ROCK = 0.125    # m/ns -- rock velocity (also the plotting velocity)
V_AIR  = 0.30    # m/ns -- air velocity (~speed of light)

HERE    = Path(__file__).parent
OUT_DIR = HERE / '../../Results/GPR/Multiples'
# ------------------------------------------------------------------------------

D_FLOOR = D_CEIL + H_CAVE          # true floor depth (m)

# Two-way travel times (ns)
t_ceil  = 2 * D_CEIL / V_ROCK                       # ceiling primary
t_floor = t_ceil + 2 * H_CAVE / V_AIR               # floor (extra leg in air)
t_mc    = 2 * t_ceil                                # ceiling surface-multiple
t_mv    = t_ceil + 2 * (2 * H_CAVE / V_AIR)         # first intra-cavity multiple

# Apparent depth as the radargram plots it (always uses the rock velocity)
def app_depth(t):
    return t * V_ROCK / 2.0

EVENTS = [
    # (label, t_ns, colour, polarity, real?)
    ('P  ceiling primary', t_ceil,  'tab:blue',  '+', True),
    ('F  floor reflection', t_floor, 'tab:green', '-', True),
    ('Mc ceiling multiple', t_mc,    'tab:red',   '',  False),
    ('Mv cavity multiple',  t_mv,    'tab:orange','',  False),
]


def draw_geometry(ax):
    xmax = 12.0
    z_bottom = D_FLOOR + 2.0

    # layers
    ax.axhspan(0, D_CEIL, color='#e8d8c0', zorder=0)              # rock above
    ax.axhspan(D_CEIL, D_FLOOR, color='white', zorder=0)         # air cave
    ax.axhspan(D_FLOOR, z_bottom, color='#e8d8c0', zorder=0)      # rock below
    ax.axhline(0,       color='#7a5c3a', lw=2.5)                 # surface
    ax.axhline(D_CEIL,  color='k', lw=1.5)
    ax.axhline(D_FLOOR, color='k', lw=1.5)

    ax.text(xmax - 0.2, D_CEIL / 2, 'rock', ha='right', va='center',
            fontsize=9, style='italic', color='#7a5c3a')
    ax.text(xmax - 0.2, (D_CEIL + D_FLOOR) / 2, 'air-filled cave', ha='right',
            va='center', fontsize=9, style='italic', color='gray')
    ax.text(0.2, 0 - 0.4, 'surface (antenna)', ha='left', va='bottom', fontsize=9)
    ax.text(0.2, D_CEIL - 0.2, 'ceiling', ha='left', va='bottom', fontsize=8)
    ax.text(0.2, D_FLOOR - 0.2, 'floor', ha='left', va='bottom', fontsize=8)

    def ray(xs, zs, colour):
        ax.plot(xs, zs, color=colour, lw=1.6, zorder=3)
        # arrowheads along segments
        for i in range(len(xs) - 1):
            ax.annotate('', xy=(xs[i+1], zs[i+1]),
                        xytext=(xs[i], zs[i]),
                        arrowprops=dict(arrowstyle='-|>', color=colour, lw=1.6))

    def bounce(x, z, colour, fill=True):
        ax.plot([x], [z], marker='o', ms=6, color=colour,
                mfc=colour if fill else 'white', mec=colour, zorder=4)

    s = 0.35  # half-offset between down/up legs for visibility

    # P : surface -> ceiling -> surface
    xc = 1.8
    ray([xc - s, xc, xc + s], [0, D_CEIL, 0], 'tab:blue')
    bounce(xc, D_CEIL, 'tab:blue')

    # F : surface -> (through ceiling) -> floor -> surface
    xc = 4.3
    ray([xc - s, xc, xc + s], [0, D_FLOOR, 0], 'tab:green')
    bounce(xc - s/2, D_CEIL, 'tab:green', fill=False)   # transmission through ceiling
    bounce(xc + s/2, D_CEIL, 'tab:green', fill=False)
    bounce(xc, D_FLOOR, 'tab:green')

    # Mc : surface -> ceiling -> surface -> ceiling -> surface
    xc = 7.2
    xs = [xc - 1.5*s, xc - 0.5*s, xc + 0.5*s, xc + 1.5*s, xc + 2.5*s]
    zs = [0, D_CEIL, 0, D_CEIL, 0]
    ray(xs, zs, 'tab:red')
    bounce(xc - 0.5*s, D_CEIL, 'tab:red')
    bounce(xc + 0.5*s, 0, 'tab:red')         # bounce off the underside of surface
    bounce(xc + 1.5*s, D_CEIL, 'tab:red')

    # Mv : surface -> ceiling -> floor -> ceiling -> floor -> ceiling -> surface
    xc = 10.2
    xs = [xc - 1.2*s, xc - 0.8*s, xc - 0.4*s, xc, xc + 0.4*s, xc + 0.8*s, xc + 1.2*s]
    zs = [0, D_CEIL, D_FLOOR, D_CEIL, D_FLOOR, D_CEIL, 0]
    ray(xs, zs, 'tab:orange')
    for xx, zz in zip(xs[1:-1], zs[1:-1]):
        bounce(xx, zz, 'tab:orange')

    ax.set_xlim(0, xmax)
    ax.set_ylim(z_bottom, -1.2)   # depth down, a little headroom for surface label
    ax.set_xlabel('horizontal position (schematic, m)')
    ax.set_ylabel('true depth below surface (m)')
    ax.set_title('Ray paths (true geometry)\nrock v = {:.2f}, air v = {:.2f} m/ns'.format(
        V_ROCK, V_AIR), fontsize=10)


def draw_trace(ax):
    # two-way time axis (down), with an apparent-depth twin
    t_max = t_mv * 1.15
    ax.set_ylim(t_max, 0)
    ax.set_xlim(-1.2, 1.2)
    ax.axvline(0, color='0.8', lw=0.8)

    for label, t, colour, pol, real in EVENTS:
        # a little wiggle to suggest a wavelet, sign from polarity
        amp = 0.8
        if pol == '-':
            amp = -amp
        tt = np.linspace(t - 6, t + 6, 100)
        wig = amp * np.exp(-((tt - t) / 2.5) ** 2) * np.cos((tt - t) / 2.0)
        ax.plot(wig, tt, color=colour, lw=1.8)
        ax.axhline(t, color=colour, lw=0.8, ls=':', alpha=0.7)

    ax.set_xticks([])
    ax.set_ylabel('two-way time (ns)')
    ax.set_title('Synthetic trace\n(apparent depth uses rock v)', fontsize=10)

    # apparent-depth axis on the right
    ax2 = ax.twinx()
    ax2.set_ylim(app_depth(t_max), 0)
    ax2.set_ylabel('apparent depth (m)  [= t x {:.2f} / 2]'.format(V_ROCK))


def main():
    fig, (axL, axR) = plt.subplots(
        1, 2, figsize=(13, 7), gridspec_kw={'width_ratios': [2.0, 1.0]})
    draw_geometry(axL)
    draw_trace(axR)

    note = ('Floor true depth {:.1f} m, but it plots at ~{:.1f} m -- the air gap is '
            'crossed at {:.2f} m/ns yet depth-converted with rock {:.2f} m/ns, so the '
            'floor is pulled up to ~{:.0f}% of the cave height below the ceiling. '
            'Mc sits at ~2x the ceiling depth; both multiples are artifacts, not geology.'
            ).format(D_FLOOR, app_depth(t_floor), V_AIR, V_ROCK,
                     100 * V_ROCK / V_AIR)
    fig.text(0.5, 0.02, note, ha='center', va='bottom', fontsize=8.5, wrap=True)

    fig.suptitle('GPR events over an air-filled lava tube: primaries and multiples',
                 fontsize=12)
    fig.tight_layout(rect=[0, 0.06, 1, 0.96])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'multiples_schematic.png'
    fig.savefig(str(out), dpi=170)
    plt.close(fig)
    print('Saved: {}'.format(out.resolve()))
    print('Events (two-way ns | apparent m):')
    for label, t, _, _, _ in EVENTS:
        print('  {:<22} {:6.1f} ns   {:5.2f} m'.format(label, t, app_depth(t)))


if __name__ == '__main__':
    main()

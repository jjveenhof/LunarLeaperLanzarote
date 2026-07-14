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

Third panel : the dimensionless companion -- a lookup chart of where every
              arrival lands as a function of the cave-height-to-overburden
              ratio H/D.  Times are normalised by the ceiling two-way time
              t_rock = 2D/v_rock, so the ceiling sits at 1 and the whole
              pattern collapses onto one parameter -- the velocity ratio sets
              the slopes, nothing else.  Use it to read off, for a given H/D,
              whether the floor arrives before or after the first ceiling
              multiple.

All three panels are combined into a single figure (one thesis-ready output);
titles are dropped (captioned in LaTeX instead) and v_rock/v_air/k should be
stated in that caption.

Usage:
    python plot_multiples_schematic.py
"""

import sys
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# Import BEFORE any plotting: sets the thesis (Computer Modern) font via rcParams
# on import, so both the local browse PNG and the thesis PDF match -- a call-site
# import here (after the panels are drawn) left the browse PNG in default fonts.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure

# ---- PARAMETERS (edit to taste) ----------------------------------------------
D_CEIL = 5    # rock thickness, surface to cave ceiling (m)
H_CAVE = 10    # true cave height, ceiling to floor (m)
V_ROCK = 0.125    # m/ns -- rock velocity (also the plotting velocity)
V_AIR  = 0.30    # m/ns -- air velocity (~speed of light)

# Colourblind-friendly palette (Okabe-Ito) for the event families
C_CEIL  = '#0072B2'   # blue            -- ceiling primary
C_FLOOR = '#009E73'   # bluish green    -- floor reflection
C_MULT  = '#D55E00'   # vermillion      -- ceiling / overburden multiples
C_CAV   = '#CC79A7'   # reddish purple  -- cavity reverberations

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
    ('P  ceiling primary', t_ceil,  C_CEIL,  '+', True),
    ('F  floor reflection', t_floor, C_FLOOR, '-', True),
    ('Mc ceiling multiple', t_mc,    C_MULT,  '+', False),
    ('Mv cavity multiple',  t_mv,    C_CAV,   '-', False),
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

    # placed in the gap between the F and Mc ray families -- the only clear
    # stretch wide enough that the label text doesn't cross any ray
    x_label = 5.6
    ax.text(x_label, D_CEIL / 2, 'rock', ha='center', va='center',
            fontsize=8, style='italic', color='#7a5c3a')
    ax.text(x_label+1, (D_CEIL + D_FLOOR) / 2, 'air-filled tube', ha='center',
            va='center', fontsize=8, style='italic', color='gray')
    ax.text(0.2, 0 - 0.55, 'surface', ha='left', va='bottom', fontsize=7)
    ax.text(0.2, D_CEIL - 0.35, 'ceiling', ha='left', va='bottom', fontsize=7)
    ax.text(0.2, D_FLOOR - 0.35, 'floor', ha='left', va='bottom', fontsize=7)

    def ray(xs, zs, colour):
        ax.plot(xs, zs, color=colour, lw=1.0, zorder=3)
        # arrowhead centred on each segment's midpoint (not its endpoint) --
        # a short stub spanning 42-58% of the segment, same direction as travel
        for i in range(len(xs) - 1):
            x0, z0, x1, z1 = xs[i], zs[i], xs[i+1], zs[i+1]
            xt, zt = x0 + 0.42 * (x1 - x0), z0 + 0.42 * (z1 - z0)
            xh, zh = x0 + 0.58 * (x1 - x0), z0 + 0.58 * (z1 - z0)
            ax.annotate('', xy=(xh, zh), xytext=(xt, zt),
                        arrowprops=dict(arrowstyle='-|>', color=colour, lw=1.0))

    def bounce(x, z, colour, fill=True):
        ax.plot([x], [z], marker='o', ms=6, color=colour,
                mfc=colour if fill else 'white', mec=colour, zorder=4)

    def x_at_depth(x0, z0, x1, z1, zc):
        """x where the segment (x0,z0)->(x1,z1) crosses depth zc."""
        return x0 + (x1 - x0) * (zc - z0) / (z1 - z0)

    s = 0.35  # half-offset between down/up legs for visibility

    # P : surface -> ceiling -> surface
    xc = 1.8
    ray([xc - s, xc, xc + s], [0, D_CEIL, 0], C_CEIL)
    bounce(xc, D_CEIL, C_CEIL)

    # F : surface -> (through ceiling) -> floor -> surface
    xc = 4.3
    xL, xR = xc - s, xc + s
    ray([xL, xc, xR], [0, D_FLOOR, 0], C_FLOOR)
    # transmission dots: where each leg actually crosses the ceiling depth
    bounce(x_at_depth(xL, 0, xc, D_FLOOR, D_CEIL), D_CEIL, C_FLOOR, fill=False)
    bounce(x_at_depth(xc, D_FLOOR, xR, 0, D_CEIL), D_CEIL, C_FLOOR, fill=False)
    bounce(xc, D_FLOOR, C_FLOOR)

    # Mc : surface -> ceiling -> surface -> ceiling -> surface
    xc = 7.2
    xs = [xc - 1.5*s, xc - 0.5*s, xc + 0.5*s, xc + 1.5*s, xc + 2.5*s]
    zs = [0, D_CEIL, 0, D_CEIL, 0]
    ray(xs, zs, C_MULT)
    bounce(xc - 0.5*s, D_CEIL, C_MULT)
    bounce(xc + 0.5*s, 0, C_MULT)         # bounce off the underside of surface
    bounce(xc + 1.5*s, D_CEIL, C_MULT)

    # Mv : surface -> (through ceiling) -> floor -> ceiling -> floor -> (through
    #      ceiling) -> surface. Only 3 of the 5 marked points are true
    # reflections (floor, then ceiling hit from the AIR side, then floor); the
    # first/last "ceiling" points are transmissions (crossing into/out of the
    # cave, direction unchanged) -- drawn open, like F's transmission dots.
    xc = 10.2
    xs = [xc - 1.2*s, xc - 0.8*s, xc - 0.4*s, xc, xc + 0.4*s, xc + 0.8*s, xc + 1.2*s]
    zs = [0, D_CEIL, D_FLOOR, D_CEIL, D_FLOOR, D_CEIL, 0]
    ray(xs, zs, C_CAV)
    fills = [False, True, True, True, False]   # transmit, reflect x3, transmit
    for (xx, zz), f in zip(zip(xs[1:-1], zs[1:-1]), fills):
        bounce(xx, zz, C_CAV, fill=f)

    # D / H dimension arrows, in the clear margin right of the Mv ray family
    # (text sits to the LEFT of its arrow)
    x_dim = 11.5
    ax.text(x_dim - 0.2, D_CEIL / 2, '$D$', ha='right', va='center', fontsize=8)
    ax.annotate('', xy=(x_dim, D_CEIL), xytext=(x_dim, 0),
               arrowprops=dict(arrowstyle='<->', color='k', lw=0.9))
    ax.text(x_dim - 0.2, (D_CEIL + D_FLOOR) / 2, '$H$', ha='right', va='center', fontsize=8)
    ax.annotate('', xy=(x_dim, D_FLOOR), xytext=(x_dim, D_CEIL),
               arrowprops=dict(arrowstyle='<->', color='k', lw=0.9))

    ax.set_xlim(0, xmax)
    ax.set_ylim(z_bottom, -1.7)   # depth down, a little headroom for surface label
    ax.set_xlabel('Position (m)')
    ax.set_ylabel('Depth (m)')
    ax.set_title('a)', loc='left', fontsize=10)


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
        ax.plot(wig, tt, color=colour, lw=1.2)
        ax.axhline(t, color=colour, lw=0.8, ls=':', alpha=0.7)

    ax.set_xticks([])
    ax.set_ylabel('TWT (ns)')
    ax.set_title('b)', loc='left', fontsize=10)

    # apparent-depth axis on the right
    ax2 = ax.twinx()
    ax2.set_ylim(app_depth(t_max), 0)
    ax2.set_ylabel('Apparent depth (m)')


def draw_chart(ax, hd_max=10.0, n_rock=2, n_cav=2):
    """Dimensionless arrival chart: normalised two-way time (t / t_ceil) versus
    the cave-height-to-overburden ratio H/D.  Only the velocity ratio matters."""
    k = V_AIR / V_ROCK                     # floor slope is 1/k; crossover at H/D = k
    hd = np.linspace(0, hd_max, 400)

    # Ceiling family (positive polarity): horizontal lines y = n
    ax.plot([0, hd_max], [1, 1], color=C_CEIL, lw=1.4, label='Ceiling primary')
    for n in range(2, n_rock + 1):
        ax.plot([0, hd_max], [n, n], color=C_MULT, lw=0.9,
                label='Overburden multiple' if n == 2 else None)

    # Floor family (negative polarity): y = 1 + n*(H/D)/k
    ax.plot(hd, 1 + hd / k, color=C_FLOOR, lw=1.4, label='Floor reflection')
    for n in range(2, n_cav + 1):
        ax.plot(hd, 1 + n * hd / k, color=C_CAV, lw=0.9,
                label='Tube multiple' if n == 2 else None)

    # marker for the floor / first-ceiling-multiple crossover region (fixed at
    # x=2 rather than the exact H/D=k value -- a clean reference line, no label).
    # x=2 is also exactly H_CAVE/D_CEIL for the geometry used in panels (a)/(b),
    # so this line doubles as "here is that specific example on the general chart".
    ax.axvline(2.0, color='0.5', lw=1.0, ls=':')
    ax.text(1.95, 3.45, 'slice shown in (b)', rotation=90, fontsize=6,
           color='0.5', ha='right', va='center')

    y_max = 4.0
    ax.set_xlim(0, hd_max)
    ax.set_ylim(y_max, 0)                   # time increases downward, ceiling near top
    ax.set_xlabel(r'$H/D$')
    ax.set_ylabel(r'$t\,/\,t_\mathrm{ceil}$')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=6, loc='lower right', framealpha=0.9, handlelength=1.4,
             labelspacing=0.3, borderpad=0.4)

    # floor reflection meets the first overburden multiple at (H/D, t/t_ceil) =
    # (k, 2) = (2.4, 2) -- opposite polarities (F is '-', the overburden
    # multiple is '+') arriving simultaneously, so they cancel: destructive
    # interference, not just a crossing.
    ax.annotate('destructive\ninterference', xy=(k, 2.0), xytext=(4.6, 0.45),
               fontsize=6, color='0.3', ha='left', va='center',
               arrowprops=dict(arrowstyle='->', color='0.3', lw=0.8))

    ax.set_title('c)', loc='left', fontsize=10)

    # right-hand twin: apparent-depth-over-overburden. d_app/D = t/t_ceil exactly
    # (d_app = t*v_rock/2, t_ceil = 2D/v_rock -- D and v_rock cancel), so this is
    # the same y-value under a second, dimensioned-adjacent label -- same axis
    # convention as panel (b)'s Apparent depth twin.
    ax_r = ax.twinx()
    ax_r.set_ylim(ax.get_ylim())
    ax_r.set_ylabel(r'$d_\mathrm{app}/D$')


def make_combined():
    # figsize width vs thesis \linewidth (6.1 in, see plot_utils sizing rule): a bit
    # wider than native so 3 dense panels + labels don't collide (rule exception for
    # dense multi-panel figures -- same tradeoff as the appendix polarity/intersection
    # figures). constrained_layout (not tight_layout) handles the twinx panel cleanly.
    fig, (axL, axM, axR) = plt.subplots(
        1, 3, figsize=(8.0, 3.3),
        gridspec_kw={'width_ratios': [1.55, 0.85, 1.15]},
        constrained_layout=True)
    draw_geometry(axL)
    draw_trace(axM)
    draw_chart(axR)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / 'gpr_arrivals_schematic.png'
    fig.savefig(str(out), dpi=170)
    save_figure(fig, out.stem, "GPR", vector=True)   # title-free thesis PDF
    plt.close(fig)
    print('Saved: {}'.format(out.resolve()))
    print('Events (two-way ns | apparent m):')
    for label, t, _, _, _ in EVENTS:
        print('  {:<22} {:6.1f} ns   {:5.2f} m'.format(label, t, app_depth(t)))


def main():
    ap = argparse.ArgumentParser(description='Combined GPR arrivals schematic '
                                              '(geometry + trace + arrival chart).')
    ap.parse_args()
    make_combined()


if __name__ == '__main__':
    main()

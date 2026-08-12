"""
Sensitivity sweeps for the tube inversion (was Figure 2 of invert_tube.run_mode).
Two APPENDIX plates, each a 1x3 multi-panel over the three cases (L3 circle, L3
ellipse, L5 circle):
  picks    -- recovered AREA vs a WIDE sweep of the ceiling (and, for the ellipse,
              floor) pick, so a gross mispick shows as curvature. Overlays the nominal
              pick +/- sigma_pick and the 1 SE total area band.
  velocity -- recovered AREA vs assumed migration velocity, AIR-GAP-consistent: the
              ceiling depth scales prop v_rock while the void height (v_air, ~exact) is
              held, so the tube shifts in depth and keeps its height. Overlays the
              nominal v +/- sigma_v and the 1 SE band.
All panels of BOTH plates share ONE area y-scale, so slopes are directly comparable
(the whole point of the appendix: it shows the recovered area is near-LINEAR in each
input over the plausible range, justifying the first-order error propagation -- and
that the velocity slope is much flatter than the pick slope).

Unlike the misfit/terrain figures this one RUNS the engine (the sweeps aren't covered
by any stored artifact), so it builds an explicit InvCfg per line from the preset + CLI
and calls invert_tube directly. Kept flexible for the planned sensitivity analyses.

Run:  python plot_sensitivity.py
"""

import argparse
import numpy as np
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))   # Code/ for plot_utils
from plot_utils import save_figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches
from matplotlib.legend_handler import HandlerTuple

import invert_tube as it
import run_inversion as drv          # reuse slope_se_of (no side effects on import)

CASES = [(3, "circle"), (3, "ellipse"), (5, "circle")]   # fixed appendix cases
C_CEIL, C_FLOOR, C_VEL, C_BAND = "#0099FF", "#00CC80", "#8000FF", "#FF5C00"

# Bottom figure-legend placement (both plates). GAP between the panels and the legend:
#   raise LEGEND_RESERVE  -> panels move UP        -> bigger gap (panels a touch shorter)
#   lower LEGEND_Y        -> legend moves DOWN     -> bigger gap (until it clips the edge)
# do the opposite of either to tighten the gap.
LEGEND_RESERVE = 0.05    # fraction of figure height reserved below the panels
LEGEND_Y = 0.01          # legend anchor height (figure fraction); HIGHER = legend up

SWEEP_MS = 2             # sweep marker size (points); bigger = bigger dots
SWEEP_LW = 1           # sweep line width (points); bigger = thicker line


def cfg_for(line, args):
    """InvCfg for a line from its preset + CLI overrides (mirrors run_inversion)."""
    over = dict(sigma_pick=args.sigma_pick)
    if args.velocity is not None:
        over["velocity"] = args.velocity
    if args.velocity_sigma is not None:
        over["velocity_sigma"] = args.velocity_sigma
    return it.cfg_for(line, slope_se=drv.slope_se_of(line), **over)


def _setup(line, mode):
    sx, d, se = it.load_line(line)
    sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
    x0s = it.x0_grid(sx, d)
    return sx, d, se, sizes, x0s


def _nominal(line, mode, ceiling, floor, cfg):
    sx, d, se, sizes, x0s = _setup(line, mode)
    res = it.invert(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg)
    u = it.size_area_se(mode, sx, d, se, res, ceiling, floor, sizes, cfg)
    return u["area"], u["area_se_tot"]


def pick_curves(line, mode, ceiling, floor, cfg, sweep, step=1.0):
    """Recovered AREA vs swept ceiling (and floor, ellipse). Returns a data dict."""
    sx, d, se, sizes, x0s = _setup(line, mode)
    ceilings = np.arange(max(ceiling - sweep, it.MIN_CEILING), ceiling + sweep + 1e-6, step)
    area_c = []
    for c in ceilings:
        fu = floor if mode == "circle" else max(floor, c + 1)
        s = it.invert(mode, sx, d, se, c, fu, sizes, x0s, cfg)["size"]
        area_c.append(it.area_of(mode, s, c, fu))
    out = dict(line=line, mode=mode, ceiling=ceiling, floor=floor,
               sigma_pick=cfg.sigma_pick, ceilings=ceilings, area_c=np.array(area_c))
    if mode == "ellipse":
        floors = np.arange(floor - sweep, floor + sweep + 1e-6, step)
        area_f = []
        for f in floors:
            ff = max(f, ceiling + 1)
            s = it.invert(mode, sx, d, se, ceiling, ff, sizes, x0s, cfg)["size"]
            area_f.append(it.area_of(mode, s, ceiling, ff))
        out.update(floors=floors, area_f=np.array(area_f))
    out["area0"], out["area_se"] = _nominal(line, mode, ceiling, floor, cfg)
    return out


def velocity_curve(line, mode, ceiling, floor, cfg, vlo=0.08, vhi=0.16, npts=17):
    """Recovered AREA vs assumed migration velocity (air-gap-consistent mapping)."""
    sx, d, se, sizes, x0s = _setup(line, mode)
    vref, void = cfg.velocity, floor - ceiling      # void height v_air-fixed, held
    vs = np.linspace(vlo, vhi, npts)
    area_v = []
    for v in vs:
        c = ceiling * (v / vref)
        f = c + void
        s = it.invert(mode, sx, d, se, c, f, sizes, x0s, cfg)["size"]
        area_v.append(it.area_of(mode, s, c, f))
    out = dict(line=line, mode=mode, vs=vs, area_v=np.array(area_v),
               vref=vref, vsig=cfg.velocity_sigma)
    out["area0"], out["area_se"] = _nominal(line, mode, ceiling, floor, cfg)
    return out


def _common_ylim(datasets, pad=0.05):
    """One area y-range spanning every curve of every dataset, so slopes compare."""
    vals = []
    for dd in datasets:
        for k in ("area_c", "area_f", "area_v"):
            if k in dd:
                vals.append(dd[k])
        vals.append(np.array([dd["area0"] - dd["area_se"], dd["area0"] + dd["area_se"]]))
    lo, hi = min(v.min() for v in vals), max(v.max() for v in vals)
    m = pad * (hi - lo)
    return lo - m, hi + m


def draw_band(ax, area0, area_se):
    """Nominal area +/- total 1 SE (per panel); labelled once in the figure legend."""
    ax.axhspan(area0 - area_se, area0 + area_se, color=C_BAND, alpha=0.15, zorder=0)
    ax.axhline(area0, color=C_BAND, lw=1.0, zorder=1)


def _band_handle():
    return (Line2D([], [], color=C_BAND, lw=1.0),
            mpatches.Patch(color=C_BAND, alpha=0.15))


def _marker_band(color):
    """Legend proxy for a dashed nominal line + its shaded +/-1 sigma strip."""
    return (Line2D([], [], color=color, ls="--", lw=0.9),
            mpatches.Patch(color=color, alpha=0.12))


def _figure_legend(fig, handles, labels, ncol):
    fig.legend(handles, labels, loc="lower center", ncol=ncol, fontsize=8,
               frameon=True, handletextpad=0.5, columnspacing=1.3,
               handler_map={tuple: HandlerTuple(ndivide=None)},
               bbox_to_anchor=(0.5, LEGEND_Y))


def pick_plate(data, ylim, out):
    fig, axes = plt.subplots(1, 3, figsize=(6.1, 2.3))
    for i, (ax, dd) in enumerate(zip(axes, data)):
        ax.plot(dd["ceilings"], dd["area_c"], "o-", color=C_CEIL, ms=SWEEP_MS, lw=SWEEP_LW)
        ax.axvspan(dd["ceiling"] - dd["sigma_pick"], dd["ceiling"] + dd["sigma_pick"],
                   color=C_CEIL, alpha=0.12, zorder=0)
        ax.axvline(dd["ceiling"], color=C_CEIL, ls="--", lw=0.9)
        if "area_f" in dd:
            ax.plot(dd["floors"], dd["area_f"], "s-", color=C_FLOOR, ms=SWEEP_MS, lw=SWEEP_LW)
            ax.axvspan(dd["floor"] - dd["sigma_pick"], dd["floor"] + dd["sigma_pick"],
                       color=C_FLOOR, alpha=0.12, zorder=0)
            ax.axvline(dd["floor"], color=C_FLOOR, ls="--", lw=0.9)
        draw_band(ax, dd["area0"], dd["area_se"])
        ax.set_ylim(*ylim)
        # ellipse sweeps BOTH picks; circle only the ceiling.
        ax.set_xlabel(r"GPR pick depth $c$ or $f$ (m)" if dd["mode"] == "ellipse"
                      else r"GPR pick depth $c$ (m)")
        ax.set_title(f"L{dd['line']} {dd['mode']}", fontsize=10, fontweight="bold")
        ax.grid(True, alpha=0.25, ls="--")
        if i > 0:
            ax.tick_params(labelleft=False)      # y-scale shared -> drop repeat labels
    axes[0].set_ylabel(r"recovered area $A$ (m$^2$)")
    handles = [Line2D([], [], color=C_CEIL, marker="o", ms=SWEEP_MS, lw=SWEEP_LW),
               Line2D([], [], color=C_FLOOR, marker="s", ms=SWEEP_MS, lw=SWEEP_LW),
               _marker_band(C_CEIL), _marker_band(C_FLOOR), _band_handle()]
    labels = ["ceiling sweep", "floor sweep", r"ceiling pick $\pm$ SE",
              r"floor pick $\pm$ SE", r"best model $\pm$ SE"]
    fig.tight_layout(rect=[0, LEGEND_RESERVE, 1, 1])            # leave room for the figure legend
    _figure_legend(fig, handles, labels, ncol=5)
    fig.savefig(out, dpi=140)
    save_figure(fig, out.stem, "Inversion", vector=True)   # title-free vector -> thesis
    plt.close(fig)
    print(f"  saved -> {out.relative_to(it.BASE)}")


def velocity_plate(data, ylim, out):
    fig, axes = plt.subplots(1, 3, figsize=(6.1, 2.3), sharex=True)
    for i, (ax, dd) in enumerate(zip(axes, data)):
        ax.plot(dd["vs"], dd["area_v"], "o-", color=C_VEL, ms=SWEEP_MS, lw=SWEEP_LW)
        ax.axvspan(dd["vref"] - dd["vsig"], dd["vref"] + dd["vsig"], color=C_VEL,
                   alpha=0.12, zorder=0)
        ax.axvline(dd["vref"], color=C_VEL, ls="--", lw=0.9)
        draw_band(ax, dd["area0"], dd["area_se"])
        ax.set_ylim(*ylim)
        ax.set_xlabel("migration velocity $v$ (m/ns)")
        ax.set_title(f"L{dd['line']} {dd['mode']}", fontsize=10, fontweight="bold")
        ax.grid(True, alpha=0.25, ls="--")
        if i > 0:
            ax.tick_params(labelleft=False)      # y-scale shared -> drop repeat labels
    axes[0].set_ylabel(r"recovered area $A$ (m$^2$)")
    vlab = rf"$v = {data[0]['vref']:g} \pm {data[0]['vsig']:g}$ m/ns"
    handles = [Line2D([], [], color=C_VEL, marker="o", ms=SWEEP_MS, lw=SWEEP_LW),
               _marker_band(C_VEL), _band_handle()]
    labels = ["velocity sweep", vlab, r"best model $\pm$ SE"]
    fig.tight_layout(rect=[0, LEGEND_RESERVE, 1, 1])
    _figure_legend(fig, handles, labels, ncol=3)
    fig.savefig(out, dpi=140)
    save_figure(fig, out.stem, "Inversion", vector=True)   # title-free vector -> thesis
    plt.close(fig)
    print(f"  saved -> {out.relative_to(it.BASE)}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sweep", type=float, default=it.SWEEP, help="+/- pick range (m)")
    p.add_argument("--sigma-pick", type=float, default=1.25, help="GPR pick 1-sigma (m)")
    p.add_argument("--velocity", type=float, default=None, help="override velocity (m/ns)")
    p.add_argument("--velocity-sigma", type=float, default=None,
                   help="override velocity 1-sigma (m/ns)")
    return p.parse_args()


def main():
    args = parse_args()
    print("Computing pick + velocity sweeps for", ", ".join(f"L{l} {m}" for l, m in CASES))
    picks, vels = [], []
    for line, mode in CASES:
        pre = it.LINE_PRESETS[line]
        ceiling = pre["ceiling"]
        floor = pre["floor"] or it.FLOOR_FALLBACK
        cfg = cfg_for(line, args)
        picks.append(pick_curves(line, mode, ceiling, floor, cfg, args.sweep))
        vels.append(velocity_curve(line, mode, ceiling, floor, cfg))
    ylim = _common_ylim(picks + vels)        # one scale across BOTH plates
    print(f"  common area y-range: {ylim[0]:.0f} - {ylim[1]:.0f} m^2")
    pick_plate(picks, ylim, it.FIG / "sensitivity_picks.png")
    velocity_plate(vels, ylim, it.FIG / "sensitivity_velocity.png")


if __name__ == "__main__":
    main()

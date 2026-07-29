"""
One-at-a-time GPR-pick sensitivity sweep for the tube inversion (was Figure 2 of
invert_tube.run_mode). For each mode it re-inverts over a WIDE range of the ceiling
(and, for the ellipse, the floor) pick, so a gross mispick is visible as curvature,
and overlays the nominal pick +/- sigma_pick and the combined 1 SE size band.

Unlike the misfit/terrain figures this one RUNS the engine (it sweeps the picks, which
no stored artifact covers), so it builds an explicit InvCfg from the line preset + CLI
and calls invert_tube directly. Kept deliberately flexible: the planned sensitivity
analyses (LiDAR-pick robustness, free-depth search, density) can adapt this driver.

Run:  python plot_sensitivity.py --line 3 [--modes circle ellipse] [--sweep 6]
      python plot_sensitivity.py --line 5
"""

import argparse
import numpy as np
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))   # Code/ for plot_utils
from plot_utils import save_figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import invert_tube as it
import run_inversion as drv          # reuse slope_se_of (no side effects on import)


def build_cfg(line, args):
    """InvCfg for a line from its preset + CLI overrides (mirrors run_inversion)."""
    pre = it.LINE_PRESETS[line]
    return it.InvCfg(
        velocity=args.velocity if args.velocity is not None else pre["velocity"],
        velocity_sigma=(args.velocity_sigma if args.velocity_sigma is not None
                        else pre["velocity_sigma"]),
        sigma_pick=args.sigma_pick, slope_se=drv.slope_se_of(line),
        truncate=None if args.truncate.lower() in ("inf", "none") else float(args.truncate))


def sweep_mode(line, mode, ceiling, floor, cfg, sweep):
    """Draw + save the pick-sensitivity figure for one (line, mode)."""
    sx, d, se = it.load_line(line)
    sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
    size_lbl = "radius r (m)" if mode == "circle" else "half-width a (m)"
    xmin = sx[np.argmin(d)]
    x0s = np.arange(xmin - 20, xmin + 20, 0.5)
    tag = "" if cfg.truncate is None else f"_trunc{int(cfg.truncate)}"
    ttl = "" if cfg.truncate is None else f"  [tube truncated at {cfg.truncate:.0f} m]"

    res = it.invert(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg)
    u = it.size_area_se(mode, sx, d, se, res, ceiling, floor, sizes, cfg)
    size0, se_tot = u["size"], u["se_tot"]

    fig, ax = plt.subplots(figsize=(7, 5))
    ceilings = np.arange(max(ceiling - sweep, it.MIN_CEILING),
                         ceiling + sweep + 0.01, 1.0)
    best_vs_ceil = [it.invert(mode, sx, d, se, c,
                              floor if mode == "circle" else max(floor, c + 1),
                              sizes, x0s, cfg)["size"] for c in ceilings]
    ax.plot(ceilings, best_vs_ceil, "o-", color="#0099FF", label="vs ceiling")
    if mode == "ellipse":
        floors = np.arange(floor - sweep, floor + sweep + 0.01, 1.0)
        best_vs_floor = [it.invert(mode, sx, d, se, ceiling, max(f, ceiling + 1),
                                   sizes, x0s, cfg)["size"] for f in floors]
        ax.plot(floors, best_vs_floor, "s-", color="#00CC80", label="vs floor")
    # nominal picks with +/- sigma_pick margin (blue = ceiling, green = floor)
    ax.axvspan(ceiling - cfg.sigma_pick, ceiling + cfg.sigma_pick, color="#0099FF",
               alpha=0.12, zorder=0)
    ax.axvline(ceiling, color="#0099FF", ls="--", lw=0.9,
               label=r"ceiling pick $\pm1\sigma$")
    if mode == "ellipse":
        ax.axvspan(floor - cfg.sigma_pick, floor + cfg.sigma_pick, color="#00CC80",
                   alpha=0.12, zorder=0)
        ax.axvline(floor, color="#00CC80", ls="--", lw=0.9,
                   label=r"floor pick $\pm1\sigma$")
    # horizontal band = combined 1 SE (data + picks + velocity + detrend), x0 fixed
    # at the best-fit lateral position for the analytic pick/velocity propagation.
    ax.axhspan(size0 - se_tot, size0 + se_tot, color="#FF5C00", alpha=0.15,
               label=rf"{size0:.1f} $\pm$ {se_tot:.1f} m (1 SE total)")
    ax.axhline(size0, color="#FF5C00", lw=1.0)
    ax.set_xlabel("GPR pick depth (m)")
    ax.set_ylabel(f"recovered {size_lbl}")
    ax.set_title(f"Line {line} {mode} -- pick sensitivity "
                 f"(at best cave-centre position)" + ttl)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25, ls="--")
    fig.tight_layout()
    out = it.FIG / f"sensitivity_line{line}_{mode}{tag}.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"  saved -> {out.relative_to(it.BASE)}  "
          f"({size_lbl.split()[0]} = {size0:.2f} +/- {se_tot:.2f} m)")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--line", type=int, default=3, choices=sorted(it.LINE_PRESETS))
    p.add_argument("--modes", nargs="+", choices=["circle", "ellipse"], default=None)
    p.add_argument("--ceiling", type=float, help="override ceiling pick (m)")
    p.add_argument("--floor", type=float, help="override floor pick (m, ellipse)")
    p.add_argument("--truncate", default="inf", help="pit distance (m) or 'inf'")
    p.add_argument("--sweep", type=float, default=it.SWEEP,
                   help="+/- pick range swept (m)")
    p.add_argument("--sigma-pick", type=float, default=1.25, help="GPR pick 1-sigma (m)")
    p.add_argument("--velocity", type=float, default=None, help="override velocity (m/ns)")
    p.add_argument("--velocity-sigma", type=float, default=None,
                   help="override velocity 1-sigma (m/ns)")
    return p.parse_args()


def main():
    args = parse_args()
    pre = it.LINE_PRESETS[args.line]
    ceiling = args.ceiling if args.ceiling is not None else pre["ceiling"]
    floor = args.floor if args.floor is not None else (pre["floor"] or 16.0)
    modes = tuple(args.modes) if args.modes else pre["modes"]
    if "ellipse" in modes and pre["floor"] is None and args.floor is None:
        raise SystemExit(f"Line {args.line} has no floor pick; pass --floor or "
                         f"drop ellipse (--modes circle).")
    cfg = build_cfg(args.line, args)
    print(f"Line {args.line} pick sweep (+/- {args.sweep:.0f} m):")
    for mode in modes:
        sweep_mode(args.line, mode, ceiling, floor, cfg, args.sweep)


if __name__ == "__main__":
    main()

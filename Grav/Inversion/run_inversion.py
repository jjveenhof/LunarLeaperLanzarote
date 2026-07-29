"""Driver for the GPR-constrained tube inversion (gravity-for-volume).

This is the ONLY script that RUNS the inversion. For each (line, mode, truncation)
it computes the best fit, the chi2 misfit surface, the analytic uncertainty budget,
and the 300-sample posterior ensemble, then PERSISTS them as artifacts
(Results/Grav/Inversion/artifacts/inv_line{L}_{mode}[_trunc{T}].npz) via inversion_io.
The plot scripts (plot_misfit_row, plot_model_terrain, plot_misfit, plot_sensitivity)
load those artifacts and never re-run the grid search or the Monte Carlo.

Engine: invert_tube.py (pure functions + InvCfg). Persistence: inversion_io.py.

Run:  python run_inversion.py                     # all preset lines/modes, untruncated
      python run_inversion.py --line 3 --truncate inf 10 15
      python run_inversion.py --line 5 --sigma-pick 1.0
"""
import argparse
import numpy as np
import invert_tube as it
import inversion_io as io

ENS_N = 300          # posterior ensemble size (matches the reported MC SEs)
SEED = 0             # base RNG seed; per-mode derived as [SEED, 0(circle)/1(ellipse)]


def slope_se_of(line):
    """Regional-trend slope 1-sigma for a line (0 if the trend-params file is absent)."""
    if not it.TREND.exists():
        print("  (no trend-params file; detrend uncertainty omitted)")
        return 0.0
    tp = np.genfromtxt(it.TREND, delimiter=",", names=True)
    row = tp[tp["Line"] == line]
    return float(row["slope_se"][0]) if len(row) else 0.0


def run_one(line, mode, ceiling, floor, cfg, seed=SEED, ens_n=ENS_N):
    """Compute + persist one (line, mode, truncation) case; return (res, u, baseline)."""
    sx, d, se = it.load_line(line)
    sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
    xmin = sx[np.argmin(d)]
    x0s = np.arange(xmin - 20, xmin + 20, 0.5)

    res = it.invert(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg)
    u = it.size_area_se(mode, sx, d, se, res, ceiling, floor, sizes, cfg)
    baseline = it.fit_offset(
        it.forward(mode, res["size"], res["x0"], ceiling, floor, sx, cfg),
        d, 1.0 / se ** 2)[0]
    rng = np.random.default_rng([seed, 0 if mode == "circle" else 1])
    ens = np.array(it.sample_ensemble(mode, sx, d, se, ceiling, floor, ens_n, rng, cfg))

    path = io.save_artifact(io.artifact_path(line, mode, cfg.truncate),
                            line=line, mode=mode, cfg=cfg, ceiling=ceiling, floor=floor,
                            sizes=sizes, x0s=x0s, res=res, u=u, baseline=baseline,
                            ensemble=ens, ens_seed=seed)

    lbl = "r" if mode == "circle" else "a"
    tag = "" if cfg.truncate is None else f" [trunc {cfg.truncate:.0f} m]"
    print(f"  [{mode}{tag}] {lbl}={res['size']:.2f} m (data 1sigma "
          f"{res['size_lo']:.2f}-{res['size_hi']:.2f}), x0={res['x0']:.1f} m, "
          f"area={u['area']:.0f} m^2, chi2_nu={res['chi2red']:.2f}")
    print(f"       size SE={u['se_tot']:.2f} m | area SE={u['area_se_tot']:.0f} m^2 "
          f"(data {u['area_se_data']:.0f} | picks {u['area_se_pick']:.0f} | "
          f"vel {u['area_se_vel']:.0f} | det {u['area_se_det']:.0f})")
    print(f"       -> {path.relative_to(it.BASE)}")
    return res, u, baseline


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--line", type=int, choices=sorted(it.LINE_PRESETS),
                   help="restrict to one line (default: all preset lines)")
    p.add_argument("--ceiling", type=float, help="override ceiling pick (m)")
    p.add_argument("--floor", type=float, help="override floor pick (m, ellipse)")
    p.add_argument("--modes", nargs="+", choices=["circle", "ellipse"],
                   help="override which shapes to fit")
    p.add_argument("--truncate", nargs="+", default=["inf"],
                   help="one or more pit distances in m; 'inf' = infinite 2D tube")
    p.add_argument("--sigma-pick", type=float, default=1.25,
                   help="GPR pick 1-sigma (m); default lambda/2 at 50 MHz")
    p.add_argument("--velocity", type=float, default=None,
                   help="override GPR migration velocity (m/ns; default is per-line)")
    p.add_argument("--velocity-sigma", type=float, default=None,
                   help="override velocity 1-sigma (m/ns)")
    p.add_argument("--seed", type=int, default=SEED, help="base RNG seed for the ensemble")
    p.add_argument("--ensemble", type=int, default=ENS_N, help="posterior ensemble size")
    return p.parse_args()


def main():
    args = parse_args()
    lines = [args.line] if args.line is not None else sorted(it.LINE_PRESETS)
    truncs = [None if t.lower() in ("inf", "none") else float(t) for t in args.truncate]

    for line in lines:
        pre = it.LINE_PRESETS[line]
        ceiling = args.ceiling if args.ceiling is not None else pre["ceiling"]
        floor = args.floor if args.floor is not None else (pre["floor"] or 16.0)
        modes = tuple(args.modes) if args.modes else pre["modes"]
        if "ellipse" in modes and pre["floor"] is None and args.floor is None:
            raise SystemExit(f"Line {line} has no floor pick; pass --floor or "
                             f"drop ellipse (--modes circle).")
        velocity = args.velocity if args.velocity is not None else pre["velocity"]
        velocity_sigma = (args.velocity_sigma if args.velocity_sigma is not None
                          else pre["velocity_sigma"])
        slope_se = slope_se_of(line)

        sx, d, se = it.load_line(line)
        print(f"Line {line}: {len(sx)} stations, residual min {d.min()*1000:.0f} uGal "
              f"(ceiling {ceiling:.1f} m"
              + (f", floor {floor:.1f} m" if "ellipse" in modes else "") + ")")
        for truncate in truncs:
            cfg = it.InvCfg(velocity=velocity, velocity_sigma=velocity_sigma,
                            sigma_pick=args.sigma_pick, slope_se=slope_se,
                            truncate=truncate)
            for mode in modes:
                run_one(line, mode, ceiling, floor, cfg,
                        seed=args.seed, ens_n=args.ensemble)


if __name__ == "__main__":
    main()

"""
Density chain-sweep for the tube inversion -- the last independent systematic.

Density is the ONLY inversion input that is CHAIN-COUPLED: the same host-rock density
sets (a) the Bouguer slab correction, (b) the terrain correction (linear in rho, so the
colleague's file is rescaled by rho/1.875), and hence the CBA and its regional de-trend,
AND (c) the void density contrast the inversion divides by. So it cannot be swept in the
forward model alone -- every rho re-runs the WHOLE pipeline:

    apply_corrections.py rho  ->  integrate_corrections.py rho  ->  detrend_regional.py rho
                                                                 ->  invert at density=rho

Naively one expects A ~ 1/rho (fixed anomaly / density contrast). The measured response
is still an INVERSE law, but a displaced one -- an offset hyperbola

    A(rho) = a/rho + b        (fits all cases to R2 >= 0.997)

where a/rho is the void-contrast scaling and the offset b is the rho-dependence of the
corrections that survives the de-trend (see fit_hyperbola for the derivation). b = 0 is
exactly pure 1/rho. Measured: L5 has b = -1 m^2, i.e. pure 1/rho to within 1%, while L3
has b = -161 (circle) / -75 (ellipse) m^2 -- the same inverse law shifted down, which
reads as a steeper fall without being a different functional form. The two lines differ
because their topography sits differently relative to the cave anomaly, so different
amounts of the rho-scaled corrections survive the de-trend. Quantifying b is the point
of running the real chain instead of assuming 1/rho.

DELIVERABLE (question turned around): rather than assume a density range and report an
area bracket, sweep a WIDE range and report the density TOLERANCE -- how far rho may
depart from nominal before the induced area change exceeds the reported 1 SE. That is
directly actionable advice ("density must be known to +/- X g/cm3 to not dominate the
error budget") for a mission that has to decide how much effort to spend constraining it.

Monte Carlo is deliberately NOT run per rho: the sweep needs the best-fit area response,
not a re-derived ensemble. The 1 SE reference comes from the nominal (rho_0) run.
Detrend plotting is suppressed (--no-plots): those figure names do not encode rho and
would otherwise clobber the canonical rho=1.875 figures and their thesis PDFs.

Writes the sweep table to Results/Grav/Inversion/density_sweep.csv and the plate to
density_sweep.png (+ title-free thesis vector). Canonical inversion artifacts are NOT
touched -- this calls the engine directly, like plot_sensitivity.py.

Run:  python sweep_density.py                       # 1.4 - 2.8, step 0.1
      python sweep_density.py --lo 1.5 --hi 2.5 --step 0.05
      python sweep_density.py --no-chain            # reuse existing per-rho CSVs
"""

import argparse
import subprocess
import sys
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

GRAV = _pl.Path(__file__).resolve().parents[1]        # Code/Grav (pipeline scripts)
CASES = [(3, "circle"), (3, "ellipse"), (5, "circle")]
RHO_NOM = 1.875                                       # nominal chain density (g/cm3)
C_SWEEP, C_BAND, C_NOM = "#C1272D", "#FF5C00", "#0099FF"
SWEEP_MS, SWEEP_LW = 2, 1
LEGEND_RESERVE, LEGEND_Y = 0.05, 0.01   # 5 legend entries in one row (ncol=5)


def run_chain(rho):
    """Re-run the gravity pipeline at one rho (plots suppressed). Returns True on OK."""
    steps = [("apply_corrections.py", [f"{rho}"]),
             ("integrate_corrections.py", [f"{rho}"]),
             ("detrend_regional.py", [f"{rho}", "--no-plots"])]
    for script, args in steps:
        r = subprocess.run([sys.executable, script] + args, cwd=GRAV,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  !! {script} failed at rho={rho}:\n{r.stderr[-800:]}")
            return False
    return True


def invert_at(rho):
    """Best-fit area per case using the chain outputs for this rho."""
    tp = np.genfromtxt(it.trend_file(rho), delimiter=",", names=True)
    out = {}
    for line, mode in CASES:
        ceiling, floor, _ = it.geometry_of(line)
        row = tp[tp["Line"] == line]
        slope_se = float(row["slope_se"][0]) if len(row) else 0.0
        cfg = it.cfg_for(line, slope_se=slope_se,
                         density=rho * 1000.0)          # g/cm3 -> kg/m3
        sx, d, se = it.load_line(line, rho)
        sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
        x0s = it.x0_grid(sx, d)
        res = it.invert(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg)
        out[(line, mode)] = dict(area=it.area_of(mode, res["size"], ceiling, floor),
                                 size=res["size"], x0=res["x0"],
                                 chi2red=res["chi2red"])
    return out


def nominal_se():
    """Total 1 SE on area at the nominal density -- the tolerance reference.

    This MUST be the SE the thesis actually reports in tab:inversion-results, which is
    the MONTE CARLO one: the standard deviation of the posterior ensemble areas stored
    in the canonical artifact (run_inversion.py). The analytic `area_se_tot` budget is
    close but not identical (37.0/24.8/34.3 vs 41.2/24.5/35.6 m^2), and quoting a
    tolerance against an SE the reader cannot find in the results table is a trap.
    Falls back to the analytic budget only if the artifact is missing.
    """
    import inversion_io as io
    tp = np.genfromtxt(it.trend_file(RHO_NOM), delimiter=",", names=True)
    out = {}
    for line, mode in CASES:
        try:
            a = io.load_artifact(line, mode)
            ens = a["ensemble"]
            areas = np.array([it.area_of(mode, s, c, f) for (s, _x, c, f) in ens])
            out[(line, mode)] = (float(a["area"]), float(areas.std(ddof=1)))
            continue
        except (FileNotFoundError, KeyError):
            print(f"  (no artifact for L{line} {mode}; falling back to analytic SE)")
        ceiling, floor, _ = it.geometry_of(line)
        row = tp[tp["Line"] == line]
        slope_se = float(row["slope_se"][0]) if len(row) else 0.0
        cfg = it.cfg_for(line, slope_se=slope_se, density=RHO_NOM * 1000.0)
        sx, d, se = it.load_line(line, RHO_NOM)
        sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
        x0s = it.x0_grid(sx, d)
        res = it.invert(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg)
        u = it.size_area_se(mode, sx, d, se, res, ceiling, floor, sizes, cfg)
        out[(line, mode)] = (u["area"], u["area_se_tot"])
    return out


def fit_hyperbola(rhos, areas):
    """Least-squares fit of A(rho) = a/rho + b, the physical form of the response.

    The inversion must reproduce the observed anomaly, whose amplitude goes as the
    density contrast times the area, ~ rho*A. That amplitude is itself rho-dependent,
    because the Bouguer slab and terrain corrections scale with rho and the linear
    de-trend does not remove all of it:  amplitude(rho) = D0 + rho*D1. Setting
    rho*A ~ D0 + rho*D1 gives

        A(rho) = (D0/k)/rho + (D1/k)  ==  a/rho + b

    so `a` is the void-contrast term and `b` is the correction feedback that survives
    the de-trend. b = 0 is exactly the pure 1/rho response; b < 0 makes the curve fall
    faster than 1/rho without changing the functional form. Returns (a, b, R2).
    """
    rhos = np.asarray(rhos, float); areas = np.asarray(areas, float)
    M = np.column_stack([1.0 / rhos, np.ones_like(rhos)])
    (a, b), *_ = np.linalg.lstsq(M, areas, rcond=None)
    ss_res = np.sum((areas - M @ [a, b]) ** 2)
    ss_tot = np.sum((areas - areas.mean()) ** 2)
    return a, b, 1.0 - ss_res / ss_tot


def tolerance(b0, b1, area0, se):
    """Rho interval over which the FITTED response stays within the 1 SE band.

    Crossing the fitted hyperbola, not the swept points. The recovered areas are
    quantised by the size search grid (a 0.1 m size step is ~2-5 m^2 of area, i.e. the
    same order as the fit residual), so interpolating between raw sweep points inherits
    that jitter and also depends on the rho step; the fit averages it out and gives a
    closed form. Solving  b0/rho + b1 = area0 -/+ se  for rho:

        rho_lo = b0 / (area0 + se - b1)      (larger area -> lower rho)
        rho_hi = b0 / (area0 - se - b1)

    area0 and se are the REPORTED best-fit area and its MC SE (tab:inversion-results),
    so the band is anchored to the published result rather than to the fit's own value
    at rho_0. Returns (lo, hi); a bound is None if the denominator is non-positive,
    i.e. the curve never leaves the band on that side.
    """
    lo_den, hi_den = area0 + se - b1, area0 - se - b1
    return (b0 / lo_den if lo_den > 0 else None,
            b0 / hi_den if hi_den > 0 else None)


def _common_ylim(rhos, table, ref, pad=0.05):
    """One area y-range spanning every curve AND every SE band, so the three panels
    share a scale -- required, since the tick labels are hidden on panels 2-3 and
    differing scales would then be silently invisible."""
    vals = []
    for c in CASES:
        vals += [table[r][c]["area"] for r in rhos]
        area0, se = ref[c]
        vals += [area0 - se, area0 + se]
    lo, hi = min(vals), max(vals)
    m = pad * (hi - lo)
    return lo - m, hi + m


def plate(rhos, table, ref, tols, fits, out):
    fig, axes = plt.subplots(1, 3, figsize=(6.1, 2.3), sharex=True)
    ylim = _common_ylim(rhos, table, ref)
    for i, ((line, mode), ax) in enumerate(zip(CASES, axes)):
        area0, se = ref[(line, mode)]
        a = [table[r][(line, mode)]["area"] for r in rhos]
        ax.axhspan(area0 - se, area0 + se, color=C_BAND, alpha=0.15, zorder=0)
        ax.axhline(area0, color=C_BAND, lw=1.0, zorder=1)
        ax.axvline(RHO_NOM, color=C_NOM, ls="--", lw=0.9, zorder=1)
        # Fitted A = a/rho + b (smooth), with the swept values as markers on top: the
        # response IS an inverse law, just displaced by the feedback offset b. (A pure
        # 1/rho reference curve was dropped once the offset form was established -- b
        # itself reports the departure, so drawing the b=0 case only added clutter.)
        ah, bh, _ = fits[(line, mode)]
        rr = np.linspace(min(rhos), max(rhos), 200)
        # DASHED: this is a fitted model, not measured points. In the pick/velocity
        # plates a solid line through markers IS the swept data, so keep the two
        # visually distinct across the figure family.
        ax.plot(rr, ah / rr + bh, ls="--", color=C_SWEEP, lw=SWEEP_LW, zorder=3)
        ax.plot(rhos, a, "o", color=C_SWEEP, ms=SWEEP_MS, zorder=4)
        lo, hi = tols[(line, mode)]
        for v in (lo, hi):                              # tolerance crossings
            if v is not None:
                ax.axvline(v, color="0.35", ls=":", lw=1.0, zorder=2)
        ax.set_ylim(*ylim)                       # shared scale -> slopes comparable
        ax.set_xlabel(r"density $\rho$ (g cm$^{-3}$)")
        ax.set_title(f"L{line} {mode}", fontsize=10, fontweight="bold")
        ax.grid(True, alpha=0.25, ls="--")
        if i > 0:
            ax.tick_params(labelleft=False)
    axes[0].set_ylabel(r"recovered area $A$ (m$^2$)")
    handles = [Line2D([], [], color=C_SWEEP, marker="o", ms=SWEEP_MS, ls="none"),
               Line2D([], [], color=C_SWEEP, ls="--", lw=SWEEP_LW),
               Line2D([], [], color=C_NOM, ls="--", lw=0.9),
               (Line2D([], [], color=C_BAND, lw=1.0),
                mpatches.Patch(color=C_BAND, alpha=0.15)),
               Line2D([], [], color="0.35", ls=":", lw=1.0)]
    labels = ["density sweep", r"fit $a/\rho + b$", rf"$\rho = {RHO_NOM}$",
              r"best model $\pm$ SE", "1 SE crossing"]
    fig.tight_layout(rect=[0, LEGEND_RESERVE, 1, 1])
    fig.legend(handles, labels, loc="lower center", ncol=5, fontsize=8, frameon=True,
               handletextpad=0.5, columnspacing=1.3,
               handler_map={tuple: HandlerTuple(ndivide=None)},
               bbox_to_anchor=(0.5, LEGEND_Y))
    fig.savefig(out, dpi=140)
    save_figure(fig, out.stem, "Inversion", vector=True)
    plt.close(fig)
    print(f"  saved -> {out.relative_to(it.BASE)}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lo", type=float, default=1.4, help="lowest density (g/cm3)")
    p.add_argument("--hi", type=float, default=2.8, help="highest density (g/cm3)")
    p.add_argument("--step", type=float, default=0.1, help="density step (g/cm3)")
    p.add_argument("--no-chain", action="store_true",
                   help="skip the pipeline re-run; reuse existing per-rho CSVs")
    args = p.parse_args()

    rhos = list(np.round(np.arange(args.lo, args.hi + 1e-9, args.step), 4))
    if not any(abs(r - RHO_NOM) < 1e-9 for r in rhos):
        rhos.append(RHO_NOM); rhos.sort()              # nominal must be on the grid

    print(f"Density chain-sweep: {len(rhos)} values, {rhos[0]} to {rhos[-1]} g/cm3")
    table = {}
    for r in rhos:
        if not args.no_chain and not run_chain(r):
            continue
        table[r] = invert_at(r)
        s = "  ".join(f"L{l}{m[0]} {table[r][(l, m)]['area']:6.1f}" for l, m in CASES)
        print(f"  rho={r:<6.3f} {s}")

    rhos = [r for r in rhos if r in table]
    ref = nominal_se()
    fits = {c: fit_hyperbola(rhos, [table[r][c]["area"] for r in rhos]) for c in CASES}
    # Tolerance from the FITTED curve (see tolerance()), so it needs the fit first.
    tols = {c: tolerance(fits[c][0], fits[c][1], *ref[c]) for c in CASES}

    print("\n=== response model  A(rho) = a/rho + b  (b = 0 is pure 1/rho) ===")
    for line, mode in CASES:
        a, b, r2 = fits[(line, mode)]
        area0, _ = ref[(line, mode)]
        contrast = a / RHO_NOM                       # the 1/rho term at nominal
        print(f"  L{line} {mode:7s}: a={a:6.1f}  b={b:7.1f} m^2  R2={r2:.4f} | "
              f"at rho_0: contrast {contrast:5.1f}, feedback {b:6.1f} "
              f"({100*abs(b)/contrast:4.1f}% of contrast)")

    print("\n=== density tolerance (|dA| within 1 SE of the nominal area) ===")
    for line, mode in CASES:
        area0, se = ref[(line, mode)]
        lo, hi = tols[(line, mode)]
        f = lambda v: "beyond swept range" if v is None else f"{v:.3f}"
        half = min(RHO_NOM - lo if lo else np.inf, hi - RHO_NOM if hi else np.inf)
        ht = "n/a" if not np.isfinite(half) else f"+/-{half:.3f}"
        print(f"  L{line} {mode:7s}: A0={area0:5.1f} +/- {se:4.1f} m^2 | "
              f"rho in [{f(lo)}, {f(hi)}] | tightest {ht} g/cm3")

    csv = it.FIG / "density_sweep.csv"
    with open(csv, "w") as fh:
        fh.write("rho," + ",".join(f"area_L{l}_{m}" for l, m in CASES) + "\n")
        for r in rhos:
            fh.write(f"{r}," + ",".join(f"{table[r][c]['area']:.3f}" for c in CASES) + "\n")
    print(f"\n  saved -> {csv.relative_to(it.BASE)}")
    plate(rhos, table, ref, tols, fits, it.FIG / "density_sweep.png")


if __name__ == "__main__":
    main()

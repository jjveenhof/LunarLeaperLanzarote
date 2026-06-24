"""
La Corona tube inversion (Line 3) from the detrended CBA residual.

GPR-constrained, gravity-for-volume design:
  - mode "circle":  fix the GPR ceiling depth, fit radius R and centre offset x0.
                    R reads as a MEAN cave radius. Circle top stays at the ceiling.
  - mode "ellipse": fix GPR ceiling + floor (vertical extent), fit half-width a
                    and x0.

Forward model: forward_polygon.polygon_gz (fast analytic 2D Talwani). Density is
FIXED at 1875 kg/m^3 -- changing it would change the Bouguer correction and hence
the CBA data + SEs, so a density sweep is a chain-level exercise (re-run the
pipeline per rho), not a forward-only knob; deliberately out of scope here.

Inversion = dense GRID SEARCH (cheap with the analytic forward), which yields the
whole chi-square surface -> best fit AND its data-driven uncertainty (Delta chi2).

Sensitivity to the GPR picks, two complementary layers:
  - one-at-a-time SWEEP over a wide pick range (covers gross mispicks),
  - MONTE-CARLO with Gaussian pick noise (resolution-level uncertainty),
    folding the pick uncertainty into the recovered size.

Run in any env (no pyGIMLi needed):
    C:/Users/jj_ve/miniconda3/envs/GPR_plotting_LL/python.exe invert_tube.py
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.optimize import minimize_scalar
from forward_polygon import polygon_gz, ellipse_vertices, RHO_HOST

BASE = Path(__file__).resolve().parents[3]
DET = BASE / "Data/Gravimetry/Processed/bouguer_anomaly_decay_rho1p875_detrended.csv"
FIG = BASE / "Results/Grav/Inversion"
FIG.mkdir(parents=True, exist_ok=True)

# ---- configuration (edit here) ----------------------------------------------
LINE = 3
DENSITY = RHO_HOST              # 1875 kg/m^3, fixed (see module docstring)
CEILING0, FLOOR0 = 5.0, 16.0   # nominal Line 3 GPR picks (m)
MIN_CEILING = 1.0              # m, shallowest physical void top (rock cover above)
SIGMA_PICK = 1.0               # m, ~50 MHz vertical resolution (100 MHz ~0.5)
SWEEP = 6.0                    # m, +/- range for the wide one-at-a-time sweep
N_MC = 3000                    # Monte-Carlo draws
NVERT = 144                    # polygon vertices (>0.1% accurate, fast)

# Tube length: None = infinite 2D tube (default). Set to a distance (m) to
# truncate the tube on one side (e.g. a collapse pit ~10-15 m from Line 3),
# which scales the signal down -> refit returns a larger cross-section.
TRUNCATE_D = None

# Grids capped at structurally plausible sizes (no 35 m-radius caves on Earth),
# so the fine 0.1 m step gives smooth sweeps / MC histograms for free.
RADIUS_GRID = np.arange(1.0, 20.0, 0.1)    # circle radius (m)
WIDTH_GRID = np.arange(1.0, 30.0, 0.1)     # ellipse half-width (m)


def load_line(line=LINE):
    d = np.genfromtxt(DET, delimiter=",", names=True)
    m = d["Line"] == line
    x, resid, se = d["dist"][m], d["CBA_detrended"][m], d["SE"][m]
    o = np.argsort(x)
    return x[o], resid[o], se[o]


def shape_params(mode, size, ceiling, floor):
    """(a, b, depth): semi-axes (horizontal, vertical) and centre depth."""
    if mode == "circle":
        R = size
        return R, R, ceiling + R                # circle top pinned at the ceiling
    b = (floor - ceiling) / 2.0                 # vertical semi-axis fixed by GPR
    return size, b, ceiling + b                 # size = half-width


def area_of(mode, size, ceiling, floor):
    """Cross-sectional area (m^2) = volume per unit tube length."""
    a, b, _ = shape_params(mode, size, ceiling, floor)
    return np.pi * a * b


def forward(mode, size, x0, ceiling, floor, sx):
    a, b, depth = shape_params(mode, size, ceiling, floor)
    g = polygon_gz(sx, ellipse_vertices(a, b, x0, depth, n=NVERT), -DENSITY)
    if TRUNCATE_D is None:                       # infinite 2D tube
        return g
    # One-sided finite tube (ends at d on the pit side): scale by the truncation
    # factor at the centroid depth. Fast approximation of the exact per-cell
    # forward_polygon.tube_gz (error << the truncation correction itself).
    F = 0.5 * (1.0 + TRUNCATE_D / np.hypot(depth, TRUNCATE_D))
    return F * g


def chi2_surface(mode, sx, d, se, ceiling, floor, sizes, x0s):
    # x0-shift trick: forward(x0) == forward(0) evaluated at (sensors - x0).
    # Compute one dense forward per size, then interpolate for every x0.
    xq = np.arange(sx.min() - x0s.max() - 2, sx.max() - x0s.min() + 2, 0.5)
    chi2 = np.empty((len(sizes), len(x0s)))
    for i, s in enumerate(sizes):
        g0 = forward(mode, s, 0.0, ceiling, floor, xq)
        for j, x0 in enumerate(x0s):
            g = np.interp(sx - x0, xq, g0)
            chi2[i, j] = np.sum(((g - d) / se) ** 2)
    return chi2


def invert(mode, sx, d, se, ceiling, floor, sizes, x0s):
    chi2 = chi2_surface(mode, sx, d, se, ceiling, floor, sizes, x0s)
    i, j = np.unravel_index(np.argmin(chi2), chi2.shape)
    chi2min = float(chi2.min())
    dof = len(d) - 2
    chi2red = chi2min / dof
    # When the model under-fits (chi2red >> 1) the formal errors are too tight;
    # rescale them so reduced chi2 = 1 -> 1-sigma threshold becomes chi2red.
    thresh = max(1.0, chi2red)
    prof = chi2.min(axis=1)                              # profile over x0
    mask = (prof - prof.min()) <= thresh
    return dict(chi2=chi2, size=sizes[i], x0=x0s[j], chi2min=chi2min, dof=dof,
                chi2red=chi2red, size_lo=sizes[mask].min(), size_hi=sizes[mask].max())


def best_size_only(mode, sx, d, se, ceiling, floor, sizes, x0):
    """Continuous 1D size fit at fixed x0 (fast inner loop for MC).

    chi2(size) is smooth and unimodal, so a bounded minimiser finds the best
    size in ~15 forwards instead of scanning the whole grid.
    """
    def chi(s):
        g = forward(mode, s, x0, ceiling, floor, sx)
        return np.sum(((g - d) / se) ** 2)
    r = minimize_scalar(chi, bounds=(sizes[0], sizes[-1]), method="bounded",
                        options={"xatol": 0.05})
    return r.x


# ============================== run one mode =================================
def run_mode(mode, sx, d, se):
    sizes = RADIUS_GRID if mode == "circle" else WIDTH_GRID
    size_lbl = "radius R (m)" if mode == "circle" else "half-width a (m)"
    tag = "" if TRUNCATE_D is None else f"_trunc{int(TRUNCATE_D)}"
    ttl = "" if TRUNCATE_D is None else f"  [tube truncated at {TRUNCATE_D:.0f} m]"
    xmin = sx[np.argmin(d)]
    x0s = np.arange(xmin - 20, xmin + 20, 0.5)

    res = invert(mode, sx, d, se, CEILING0, FLOOR0, sizes, x0s)
    chi2red = res["chi2red"]
    print(f"\n[{mode}{tag}] best {size_lbl.split()[0]}={res['size']:.2f} m "
          f"(data 1sigma, rescaled: {res['size_lo']:.2f}-{res['size_hi']:.2f}), "
          f"x0={res['x0']:.1f} m, chi2_red={chi2red:.1f}")

    # ---- Figure 1: chi2 surface + best-fit overlay --------------------------
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))
    chi2 = res["chi2"]
    lev = max(1.0, chi2red)                            # rescale confidence levels
    im = a1.pcolormesh(x0s, sizes, chi2 - chi2.min(), cmap="viridis_r",
                       vmax=30 * lev, shading="auto")
    a1.contour(x0s, sizes, chi2 - chi2.min(), levels=[2.30 * lev, 6.17 * lev],
               colors="w", linewidths=1.0)            # joint 68%, 95% (rescaled)
    a1.plot(res["x0"], res["size"], "r*", markersize=14)
    a1.set_xlabel("tube centre x0 (m)")
    a1.set_ylabel(size_lbl)
    a1.set_title(rf"$\chi^2-\chi^2_{{min}}$ surface (white = 68%, 95%)")
    fig.colorbar(im, ax=a1, label=r"$\Delta\chi^2$")

    g_best = forward(mode, res["size"], res["x0"], CEILING0, FLOOR0, sx)
    a2.errorbar(sx, d, yerr=se, fmt="o", color="#FF5C00", capsize=3,
                markersize=5, label="detrended residual")
    a2.plot(sx, g_best, "-", color="k", lw=2,
            label=f"best fit ({size_lbl.split()[0]}={res['size']:.1f} m)")
    a2.axhline(0, color="0.6", lw=0.8)
    a2.set_xlabel("distance along profile (m)")
    a2.set_ylabel("g (mGal)")
    a2.set_title(rf"Line {LINE} {mode} fit ($\chi^2_\nu$={chi2red:.1f})")
    a2.legend(fontsize=8)
    a2.grid(True, alpha=0.25, ls="--")
    fig.suptitle(f"Line {LINE} inversion -- {mode} (ceiling {CEILING0:.0f} m"
                 + (f", floor {FLOOR0:.0f} m" if mode == "ellipse" else "") + ")" + ttl,
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / f"invert_line{LINE}_{mode}{tag}.png", dpi=140)
    print(f"      saved -> Results/Grav/Inversion/invert_line{LINE}_{mode}{tag}.png")

    # ---- Figure 2: sensitivity to the GPR picks -----------------------------
    fig, (b1, b2) = plt.subplots(1, 2, figsize=(13, 5))

    # (a) wide one-at-a-time sweep (kept physical: ceiling >= MIN_CEILING)
    ceilings = np.arange(max(CEILING0 - SWEEP, MIN_CEILING),
                         CEILING0 + SWEEP + 0.01, 1.0)
    best_vs_ceil = [invert(mode, sx, d, se, c,
                           FLOOR0 if mode == "circle" else max(FLOOR0, c + 1),
                           sizes, x0s)["size"] for c in ceilings]
    b1.plot(ceilings, best_vs_ceil, "o-", color="#0099FF", label="vs ceiling")
    if mode == "ellipse":
        floors = np.arange(FLOOR0 - SWEEP, FLOOR0 + SWEEP + 0.01, 1.0)
        best_vs_floor = [invert(mode, sx, d, se, CEILING0, max(f, CEILING0 + 1),
                                sizes, x0s)["size"] for f in floors]
        b1.plot(floors, best_vs_floor, "s-", color="#00CC80", label="vs floor")
    b1.axvline(CEILING0, color="0.6", ls="--", lw=0.8)
    b1.set_xlabel("GPR pick depth (m)")
    b1.set_ylabel(f"recovered {size_lbl}")
    b1.set_title("One-at-a-time sweep (covers mispicks)")
    b1.legend(fontsize=8)
    b1.grid(True, alpha=0.25, ls="--")

    # (b) Monte-Carlo over pick noise (x0 fixed at the data best for speed)
    rng = np.random.default_rng(0)
    mc = np.empty(N_MC)
    mc_area = np.empty(N_MC)
    for k in range(N_MC):
        c = max(rng.normal(CEILING0, SIGMA_PICK), MIN_CEILING)
        f = rng.normal(FLOOR0, SIGMA_PICK)
        if mode == "ellipse" and f <= c + 1:
            f = c + 1
        s = best_size_only(mode, sx, d, se, c, f, sizes, res["x0"])
        mc[k] = s
        mc_area[k] = area_of(mode, s, c, f)              # per-draw geometry
    p16, p50, p84 = np.percentile(mc, [16, 50, 84])
    se_pick = float(np.std(mc))                           # pick-propagated 1 SE
    area_best = area_of(mode, res["size"], CEILING0, FLOOR0)  # volume per metre
    area_se = float(np.std(mc_area))

    step = sizes[1] - sizes[0]                            # align bins to the grid
    bins = np.arange(mc.min() - step / 2, mc.max() + step, step)
    b2.hist(mc, bins=bins, color="#FF5C00", alpha=0.8)
    for p, ls in [(p16, ":"), (p50, "-"), (p84, ":")]:
        b2.axvline(p, color="k", ls=ls)
    b2.set_xlabel(f"recovered {size_lbl}")
    b2.set_ylabel("count")
    b2.set_title(f"MC over picks (sigma={SIGMA_PICK:.1f} m): "
                 f"{p50:.2f} +/- {se_pick:.2f} m (1 SE)")
    fig.suptitle(f"Line {LINE} {mode} -- sensitivity to GPR picks" + ttl,
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / f"sensitivity_line{LINE}_{mode}{tag}.png", dpi=140)
    print(f"      saved -> Results/Grav/Inversion/sensitivity_line{LINE}_{mode}{tag}.png")
    print(f"      MC {size_lbl.split()[0]} = {p50:.2f} +/- {se_pick:.2f} m "
          f"(1 SE, picks only); 68% [{p16:.2f}, {p84:.2f}]")
    print(f"      area = {area_best:.0f} +/- {area_se:.0f} m^2 "
          f"(= volume per metre of tube)")


def main():
    sx, d, se = load_line()
    print(f"Line {LINE}: {len(sx)} stations, residual min {d.min()*1000:.0f} uGal")
    for mode in ("circle", "ellipse"):
        run_mode(mode, sx, d, se)


if __name__ == "__main__":
    main()

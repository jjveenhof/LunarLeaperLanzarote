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

Inversion = dense GRID SEARCH (cheap with the analytic forward) over (size, x0),
with a DC offset fitted analytically at every grid point: gravity here is
relative (arbitrary datum), so the model's far-field level is a free nuisance
parameter (the weighted-mean residual). The search yields the whole chi-square
surface -> best fit AND its data-driven uncertainty (Delta chi2); dof = n - 3.

Sensitivity to the GPR picks:
  - one-at-a-time SWEEP over a wide pick range (covers gross mispicks),
  - ANALYTIC linear propagation of the pick 1-sigma into size and area, via
    central-difference partials at the best x0 (SE^2 = sum (d size/d pick)^2
    sigma^2). The recovered size is a smooth function of the pick(s), so the
    local slope is all we need -- no sampling. For the ellipse this captures the
    inverse-linear slope (da/db = -K/b^2); the half-width is then mildly
    right-skewed, so the reported SE is a first-order summary.
  - VELOCITY uncertainty: the picks are time picks, so a fractional migration-
    velocity error scales every depth jointly (ceiling+floor together) -- a
    systematic, common-mode term, propagated separately.
  - DETREND uncertainty: the regional slope removed before inverting has its own
    1-sigma (from detrend_regional.py); perturbing the residual by that tilt and
    refitting gives its contribution.
All contributions (data grid-search interval + picks + velocity + detrend) are
combined in quadrature into one reported SE; truncation is kept separate as a
systematic bracket (compare the inf-vs-truncated runs).

Run in any env; configure from the command line, e.g.:
    python invert_tube.py                              # Line 3 preset, infinite
    python invert_tube.py --line 5                     # Line 5 preset (circle)
    python invert_tube.py --line 3 --truncate inf 10 15   # 3 truncation runs
    python invert_tube.py --ceiling 6 --floor 17       # override picks
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
TREND = BASE / "Data/Gravimetry/Processed/detrend_trend_params_rho1p875.csv"
FIG = BASE / "Results/Grav/Inversion"
FIG.mkdir(parents=True, exist_ok=True)

# ---- per-line presets: GPR picks + which shapes are fittable ----------------
# Override any of these from the command line (see parse_args / module docstring).
LINE_PRESETS = {
    # GPR-derived geometry + migration velocity per line (2026-07-01). Depths in m
    # below surface (floors air-gap corrected). Velocity feeds the velocity-
    # uncertainty channel and DIFFERS per line (L3 0.125, L5 0.11 m/ns).
    # L3 re-pick: ceiling 3.5, floor 14.3 (from apparent 8.0). Supersedes 4.0/14.6.
    3: dict(ceiling=3.5, floor=14.3, modes=("circle", "ellipse"),
            velocity=0.125, velocity_sigma=0.010),
    # L5: no floor reflector -> circle-only. velocity_sigma assumed (GPR gave none).
    5: dict(ceiling=10.5, floor=None, modes=("circle",),
            velocity=0.11, velocity_sigma=0.010),
}

# ---- fixed constants --------------------------------------------------------
LINE_COLORS = {2: "#0099FF", 3: "#FF5C00", 5: "#00CC80"}   # QGIS map palette
DENSITY = RHO_HOST             # 1875 kg/m^3, fixed (chain-coupled; see docstring)
MIN_CEILING = 1.0             # m, shallowest physical void top (rock cover above)
SWEEP = 6.0                   # m, +/- range for the wide one-at-a-time sweep
NVERT = 144                  # polygon vertices (>0.1% accurate, fast)
# Grids capped at structurally plausible sizes (no 35 m-radius caves on Earth),
# so the fine 0.1 m step gives smooth sweeps / MC histograms for free.
RADIUS_GRID = np.arange(1.0, 20.0, 0.1)    # circle radius (m)
WIDTH_GRID = np.arange(1.0, 30.0, 0.1)     # ellipse half-width (m)

# ---- runtime config (set by parse_args in main; defaults = Line 3 preset) ---
LINE = 3
CEILING0, FLOOR0 = 3.5, 14.3
MODES = ("circle", "ellipse")
SIGMA_PICK = 1.0             # m, ~50 MHz vertical resolution (100 MHz ~0.5)
# GPR migration velocity: picks are time picks, so velocity scales ALL depths
# jointly (a systematic, common-mode term -- distinct from the per-pick noise).
# Per line, from LINE_PRESETS (set in main); defaults below are Line 3's.
VELOCITY = 0.125             # m/ns
VELOCITY_SIGMA = 0.010       # m/ns 1-sigma
SLOPE_SE = 0.0               # mGal/m, regional-trend slope 1-sigma (set in main)
TRUNCATE_D = None            # set per-run from the --truncate list (None = inf 2D)


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


def fit_offset(g, d, w):
    """Best DC level c and resulting chi2 (relative gravity -> arbitrary datum).

    The model ->0 far from the tube, but the data flanks sit at an arbitrary
    constant level, so c is a free nuisance parameter solved analytically (the
    weighted mean residual) at every trial geometry. Costs one dof (n-3).
    """
    c = np.sum(w * (d - g)) / np.sum(w)
    return c, np.sum(w * (d - g - c) ** 2)


def chi2_surface(mode, sx, d, se, ceiling, floor, sizes, x0s):
    # x0-shift trick: forward(x0) == forward(0) evaluated at (sensors - x0).
    # Compute one dense forward per size, then interpolate for every x0.
    w = 1.0 / se ** 2
    xq = np.arange(sx.min() - x0s.max() - 2, sx.max() - x0s.min() + 2, 0.5)
    chi2 = np.empty((len(sizes), len(x0s)))
    for i, s in enumerate(sizes):
        g0 = forward(mode, s, 0.0, ceiling, floor, xq)
        for j, x0 in enumerate(x0s):
            g = np.interp(sx - x0, xq, g0)
            chi2[i, j] = fit_offset(g, d, w)[1]
    return chi2


def invert(mode, sx, d, se, ceiling, floor, sizes, x0s):
    chi2 = chi2_surface(mode, sx, d, se, ceiling, floor, sizes, x0s)
    i, j = np.unravel_index(np.argmin(chi2), chi2.shape)
    chi2min = float(chi2.min())
    dof = len(d) - 3                                     # size, x0, DC offset
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
    w = 1.0 / se ** 2
    def chi(s):
        g = forward(mode, s, x0, ceiling, floor, sx)
        return fit_offset(g, d, w)[1]
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
    c_best = fit_offset(forward(mode, res["size"], res["x0"], CEILING0, FLOOR0, sx),
                        d, 1.0 / se ** 2)[0]
    print(f"\n[{mode}{tag}] best {size_lbl.split()[0]}={res['size']:.2f} m "
          f"(data 1sigma, rescaled: {res['size_lo']:.2f}-{res['size_hi']:.2f}), "
          f"x0={res['x0']:.1f} m, baseline={c_best*1000:.0f} uGal, chi2_red={chi2red:.1f}")

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

    # Evaluate the (smooth analytic) forward on a dense grid for display -- the fit
    # itself only needs it at the stations, but plotting there gives a jagged curve.
    xd = np.linspace(sx.min(), sx.max(), 400)
    g_dense = forward(mode, res["size"], res["x0"], CEILING0, FLOOR0, xd) + c_best
    a2.errorbar(sx, d, yerr=se, fmt="o", color=LINE_COLORS.get(LINE, "#FF5C00"),
                capsize=3, markersize=5, label="detrended residual")
    a2.plot(xd, g_dense, "-", color="k", lw=2,
            label=f"best fit ({size_lbl.split()[0]}={res['size']:.1f} m)")
    a2.axhline(c_best, color="0.6", lw=0.8, ls=":",
               label=f"fitted baseline ({c_best*1000:.0f} uGal)")
    a2.set_xlabel("distance along profile (m)")
    a2.set_ylabel("g (mGal)")
    a2.set_title(rf"Line {LINE} {mode} fit ($\chi^2_\nu$={chi2red:.1f})")
    a2.legend(fontsize=8)
    a2.grid(True, alpha=0.25, ls="--")
    # Plot N->S (N on the left) to match the GPR sections; dist stays S->N.
    a1.invert_xaxis()
    a2.invert_xaxis()
    a2.text(0.006, 0.97, "N", transform=a2.transAxes, ha="left", va="top",
            fontweight="bold", fontsize=11, color="0.3")
    a2.text(0.994, 0.97, "S", transform=a2.transAxes, ha="right", va="top",
            fontweight="bold", fontsize=11, color="0.3")
    fig.suptitle(f"Line {LINE} inversion -- {mode} (ceiling {CEILING0:.1f} m"
                 + (f", floor {FLOOR0:.1f} m" if mode == "ellipse" else "") + ")" + ttl,
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / f"invert_line{LINE}_{mode}{tag}.png", dpi=140)
    print(f"      saved -> Results/Grav/Inversion/invert_line{LINE}_{mode}{tag}.png")

    # ---- pick uncertainty: analytic linear propagation ----------------------
    # The recovered size is a smooth function of the GPR pick(s) and we know the
    # local slope, so we propagate it directly (no sampling). Central-difference
    # partials at the best x0 capture the inverse-linear ellipse slope
    # (da/db = -K/b^2) automatically. Picks assumed independent:
    #   SE^2 = (d size/d ceiling)^2 sigma^2 + (d size/d floor)^2 sigma^2
    # The ellipse half-width is mildly right-skewed (a ~ 1/b); this SE is the
    # first-order (Gaussian) summary, which is all we report.
    h = 0.5

    def fit(c, f):
        s = best_size_only(mode, sx, d, se, c, f, sizes, res["x0"])
        return s, area_of(mode, s, c, f)

    size0 = res["size"]
    area_best = area_of(mode, size0, CEILING0, FLOOR0)
    sp, ap = fit(CEILING0 + h, FLOOR0)
    sm, am = fit(max(CEILING0 - h, MIN_CEILING), FLOOR0)
    ds_dc, da_dc = (sp - sm) / (2 * h), (ap - am) / (2 * h)
    ds_df = da_df = 0.0
    if mode == "ellipse":
        sp, ap = fit(CEILING0, FLOOR0 + h)
        sm, am = fit(CEILING0, max(FLOOR0 - h, CEILING0 + 1))
        ds_df, da_df = (sp - sm) / (2 * h), (ap - am) / (2 * h)
    se_pick = np.hypot(ds_dc, ds_df) * SIGMA_PICK
    area_se = np.hypot(da_dc, da_df) * SIGMA_PICK

    # ---- velocity uncertainty: a SYSTEMATIC common-mode depth scaling --------
    # The picks are time picks; a fractional velocity error scales every depth by
    # the same factor, so ceiling AND floor move together (correlated, unlike the
    # independent pick noise above). Step = 1-sigma fraction, so SE = half-spread.
    dv = VELOCITY_SIGMA / VELOCITY
    sp, ap = fit(CEILING0 * (1 + dv), FLOOR0 * (1 + dv))
    sm, am = fit(max(CEILING0 * (1 - dv), MIN_CEILING), FLOOR0 * (1 - dv))
    se_vel = abs(sp - sm) / 2.0
    area_se_vel = abs(ap - am) / 2.0

    # ---- detrend uncertainty: the regional slope was removed before inverting,
    # so its 1-sigma tilts the residual we fit. Perturb the data by +/- the
    # slope SE (anchor cancels: the DC offset is floated) and refit. ----------
    tilt = SLOPE_SE * (sx - sx.mean())

    def fit_data(dd):
        s = best_size_only(mode, sx, dd, se, CEILING0, FLOOR0, sizes, res["x0"])
        return s, area_of(mode, s, CEILING0, FLOOR0)

    sp, ap = fit_data(d + tilt)
    sm, am = fit_data(d - tilt)
    se_det = abs(sp - sm) / 2.0
    area_se_det = abs(ap - am) / 2.0

    # ---- data (measurement) term: the chi2-rescaled grid-search half-interval.
    se_data = (res["size_hi"] - res["size_lo"]) / 2.0
    area_se_data = abs(area_of(mode, res["size_hi"], CEILING0, FLOOR0)
                       - area_of(mode, res["size_lo"], CEILING0, FLOOR0)) / 2.0

    # ---- combine all 1-sigma contributions in quadrature (truncation is a
    # separate systematic bracket: see the inf-vs-truncated runs, not here). ---
    quad = lambda *v: float(np.sqrt(np.sum(np.square(v))))
    se_tot = quad(se_data, se_pick, se_vel, se_det)
    area_se_tot = quad(area_se_data, area_se, area_se_vel, area_se_det)

    # ---- Figure 2: one-at-a-time sweep (covers gross mispicks) ---------------
    fig, b1 = plt.subplots(figsize=(7, 5))
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
    # nominal picks with +/- SIGMA_PICK margin (blue = ceiling, green = floor)
    b1.axvspan(CEILING0 - SIGMA_PICK, CEILING0 + SIGMA_PICK, color="#0099FF",
               alpha=0.12, zorder=0)
    b1.axvline(CEILING0, color="#0099FF", ls="--", lw=0.9,
               label=r"ceiling pick $\pm1\sigma$")
    if mode == "ellipse":
        b1.axvspan(FLOOR0 - SIGMA_PICK, FLOOR0 + SIGMA_PICK, color="#00CC80",
                   alpha=0.12, zorder=0)
        b1.axvline(FLOOR0, color="#00CC80", ls="--", lw=0.9,
                   label=r"floor pick $\pm1\sigma$")
    # horizontal band = combined 1 SE (data + picks + velocity + detrend); x0 fixed
    # at the best-fit lateral position for the analytic pick/velocity propagation.
    b1.axhspan(size0 - se_tot, size0 + se_tot, color="#FF5C00", alpha=0.15,
               label=rf"{size0:.1f} $\pm$ {se_tot:.1f} m (1 SE total)")
    b1.axhline(size0, color="#FF5C00", lw=1.0)
    b1.set_xlabel("GPR pick depth (m)")
    b1.set_ylabel(f"recovered {size_lbl}")
    b1.set_title(f"Line {LINE} {mode} -- pick sensitivity (at best cave-centre position)" + ttl)
    b1.legend(fontsize=8)
    b1.grid(True, alpha=0.25, ls="--")
    fig.tight_layout()
    fig.savefig(FIG / f"sensitivity_line{LINE}_{mode}{tag}.png", dpi=140)
    print(f"      saved -> Results/Grav/Inversion/sensitivity_line{LINE}_{mode}{tag}.png")
    skew = "  (half-width mildly right-skewed; SE first-order)" \
        if mode == "ellipse" else ""
    print(f"      {size_lbl.split()[0]} = {size0:.2f} +/- {se_tot:.2f} m (1 SE total)"
          f"{skew}")
    print(f"         contributions (m): data {se_data:.2f} | picks {se_pick:.2f} | "
          f"velocity {se_vel:.2f} | detrend {se_det:.2f}")
    print(f"      area = {area_best:.0f} +/- {area_se_tot:.0f} m^2 (1 SE total, "
          f"= volume per metre)")
    print(f"         contributions (m^2): data {area_se_data:.0f} | picks {area_se:.0f}"
          f" | velocity {area_se_vel:.0f} | detrend {area_se_det:.0f}")


def parse_args():
    import argparse
    p = argparse.ArgumentParser(
        description="La Corona tube inversion (GPR-constrained, gravity-for-volume).")
    p.add_argument("--line", type=int, default=3, choices=sorted(LINE_PRESETS),
                   help="profile line (loads its GPR-pick preset)")
    p.add_argument("--ceiling", type=float, help="override ceiling pick (m)")
    p.add_argument("--floor", type=float, help="override floor pick (m, ellipse)")
    p.add_argument("--modes", nargs="+", choices=["circle", "ellipse"],
                   help="override which shapes to fit")
    p.add_argument("--truncate", nargs="+", default=["inf"],
                   help="one or more pit distances in m; 'inf' = infinite 2D tube "
                        "(e.g. --truncate inf 10 15)")
    p.add_argument("--sigma-pick", type=float, default=1.0,
                   help="GPR pick 1-sigma (m)")
    p.add_argument("--velocity", type=float, default=None,
                   help="override GPR migration velocity (m/ns; default is per-line)")
    p.add_argument("--velocity-sigma", type=float, default=None,
                   help="override velocity 1-sigma (m/ns)")
    return p.parse_args()


def main():
    global LINE, CEILING0, FLOOR0, MODES, SIGMA_PICK, VELOCITY, VELOCITY_SIGMA
    global SLOPE_SE, TRUNCATE_D
    args = parse_args()
    pre = LINE_PRESETS[args.line]
    LINE = args.line
    CEILING0 = args.ceiling if args.ceiling is not None else pre["ceiling"]
    FLOOR0 = args.floor if args.floor is not None else (pre["floor"] or 16.0)
    MODES = tuple(args.modes) if args.modes else pre["modes"]
    SIGMA_PICK = args.sigma_pick
    VELOCITY = args.velocity if args.velocity is not None else pre["velocity"]
    VELOCITY_SIGMA = (args.velocity_sigma if args.velocity_sigma is not None
                      else pre["velocity_sigma"])

    # Regional-trend slope 1-sigma for this line (its tilt was removed before the
    # inversion, so its uncertainty propagates into the residual we fit).
    if TREND.exists():
        tp = np.genfromtxt(TREND, delimiter=",", names=True)
        row = tp[tp["Line"] == LINE]
        SLOPE_SE = float(row["slope_se"][0]) if len(row) else 0.0
    else:
        print(f"  (no trend-params file; detrend uncertainty omitted)")
        SLOPE_SE = 0.0
    truncs = [None if t.lower() in ("inf", "none") else float(t)
              for t in args.truncate]

    if "ellipse" in MODES and pre["floor"] is None and args.floor is None:
        raise SystemExit(f"Line {LINE} has no floor pick; pass --floor or drop "
                         f"ellipse (--modes circle).")

    sx, d, se = load_line(LINE)
    print(f"Line {LINE}: {len(sx)} stations, residual min {d.min()*1000:.0f} uGal "
          f"(ceiling {CEILING0:.1f} m"
          + (f", floor {FLOOR0:.1f} m" if "ellipse" in MODES else "") + ")")
    for TRUNCATE_D in truncs:
        for mode in MODES:
            run_mode(mode, sx, d, se)


if __name__ == "__main__":
    main()

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

This module is the pure NUMERICAL ENGINE: forward model, grid search, uncertainty
budget and posterior sampler, all as side-effect-free functions taking an explicit
InvCfg. It runs NOTHING on import and has no __main__. The driver run_inversion.py
computes + persists artifacts; the plot_*.py scripts read them (or, for the pick
sweep, call the engine here with their own cfg). It does not import matplotlib.
"""

import numpy as np
import sys as _sys
from dataclasses import dataclass
from pathlib import Path
from scipy.optimize import minimize_scalar
from forward_polygon import polygon_gz, ellipse_vertices, RHO_HOST
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/Grav for grav_utils
from grav_utils import rho_str, RHO_DEFAULT   # one definition of the rho->filename map

BASE = Path(__file__).resolve().parents[3]
PROC = BASE / "Data/Gravimetry/Processed"
FIG = BASE / "Results/Grav/Inversion"
FIG.mkdir(parents=True, exist_ok=True)


def det_file(rho=RHO_DEFAULT):
    """Detrended-CBA residual for a chain density rho (g/cm3) -- the inversion input."""
    return PROC / f"bouguer_anomaly_decay_rho{rho_str(rho)}_detrended.csv"


def trend_file(rho=RHO_DEFAULT):
    """Regional-trend parameters (incl. slope_se) for a chain density rho (g/cm3)."""
    return PROC / f"detrend_trend_params_rho{rho_str(rho)}.csv"


# Canonical rho = 1.875 paths, kept as module constants for the default chain.
DET = det_file()
TREND = trend_file()

# ---- per-line presets: GPR picks + which shapes are fittable ----------------
# The driver (run_inversion.py) reads these and its CLI overrides into an InvCfg.
LINE_PRESETS = {
    # GPR-derived geometry + migration velocity per line (2026-07-16). Depths in m
    # below surface (floors air-gap corrected). Velocity feeds the velocity-
    # uncertainty channel; BOTH lines now migrated at 0.125 m/ns (L5 remigrated
    # from 0.11 -- diffraction collapse admits 0.10-0.13, single value settled).
    # velocity_sigma raised 0.010 -> 0.015 m/ns (2026-07-29): more honest 1-sigma
    # spanning the diffraction-collapse range; makes velocity a co-leading channel
    # on L5 / L3-ellipse rather than understating it. Best fits unchanged.
    # Picks live in Data/GPR/Migration/tube_picks.csv (ceiling + apparent floor);
    # floor here = air-gap corrected: ceiling + (floor_app - ceiling)*0.3/v_rock.
    # L3 refined pick: ceiling 3.8, floor 14.6 (apparent 8.3). Supersedes 3.5/14.3.
    3: dict(ceiling=3.8, floor=14.6, modes=("circle", "ellipse"),
            velocity=0.125, velocity_sigma=0.015),
    # L5: no floor reflector -> circle-only. Ceiling re-picked on the v=0.125
    # remigration: 8.6 (was 10.5 at v=0.11). velocity_sigma assumed (GPR gave none).
    5: dict(ceiling=8.6, floor=None, modes=("circle",),
            velocity=0.125, velocity_sigma=0.015),
}

# ---- fixed constants --------------------------------------------------------
LINE_COLORS = {2: "#0099FF", 3: "#FF5C00", 5: "#00CC80"}   # QGIS map palette
DENSITY = RHO_HOST             # kg/m^3, canonical chain density (= InvCfg.density
                               # default). Swept runs pass their own via InvCfg.
MIN_CEILING = 1.0             # m, shallowest physical void top (rock cover above)
SWEEP = 6.0                   # m, +/- range for the wide one-at-a-time sweep
NVERT = 144                  # polygon vertices (>0.1% accurate, fast)
# Grids capped at structurally plausible sizes (no 35 m-radius caves on Earth),
# so the fine 0.1 m step gives smooth sweeps / MC histograms for free.
RADIUS_GRID = np.arange(1.0, 20.0, 0.1)    # circle radius (m)
WIDTH_GRID = np.arange(1.0, 30.0, 0.1)     # ellipse half-width (m)


@dataclass(frozen=True)
class InvCfg:
    """Per-run inversion configuration. Threaded explicitly through every engine
    function so callers (driver, plots, diagnostics) never mutate global state --
    there IS no global state to mutate. ceiling/floor stay per-call arguments (the
    sensitivity sweeps vary them at fixed cfg). Built by run_inversion.py from
    LINE_PRESETS + CLI, stored in each artifact, rebuilt by inversion_io.cfg_of."""
    velocity: float = 0.125          # m/ns, GPR migration velocity
    velocity_sigma: float = 0.015    # m/ns, velocity 1-sigma
    sigma_pick: float = 1.25         # m, GPR pick 1-sigma (lambda/2 at 50 MHz)
    slope_se: float = 0.0            # mGal/m, regional-trend slope 1-sigma
    truncate: float = None           # pit distance (m); None = infinite 2D tube
    # Host-rock density in kg/m^3 (NOT g/cm3 -- 1875.0, not 1.875) for the void
    # contrast. CHAIN-COUPLED: the same rock density sets the Bouguer slab + terrain
    # correction upstream, so a density sweep must re-run the pipeline at the matching
    # rho and read that chain's detrended residual (see det_file/trend_file), never
    # vary this alone.
    density: float = RHO_HOST


def load_line(line, rho=RHO_DEFAULT):
    """Detrended residual for one line at chain density rho (g/cm3)."""
    d = np.genfromtxt(det_file(rho), delimiter=",", names=True)
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


def forward(mode, size, x0, ceiling, floor, sx, cfg):
    a, b, depth = shape_params(mode, size, ceiling, floor)
    g = polygon_gz(sx, ellipse_vertices(a, b, x0, depth, n=NVERT), -cfg.density)
    if cfg.truncate is None:                     # infinite 2D tube
        return g
    # One-sided finite tube (ends at d on the pit side): scale by the truncation
    # factor at the centroid depth. Fast approximation of the exact per-cell
    # forward_polygon.tube_gz (error << the truncation correction itself).
    F = 0.5 * (1.0 + cfg.truncate / np.hypot(depth, cfg.truncate))
    return F * g


def fit_offset(g, d, w):
    """Best DC level c and resulting chi2 (relative gravity -> arbitrary datum).

    The model ->0 far from the tube, but the data flanks sit at an arbitrary
    constant level, so c is a free nuisance parameter solved analytically (the
    weighted mean residual) at every trial geometry. Costs one dof (n-3).
    """
    c = np.sum(w * (d - g)) / np.sum(w)
    return c, np.sum(w * (d - g - c) ** 2)


def chi2_surface(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg):
    # x0-shift trick: forward(x0) == forward(0) evaluated at (sensors - x0).
    # Compute one dense forward per size, then interpolate for every x0.
    w = 1.0 / se ** 2
    xq = np.arange(sx.min() - x0s.max() - 2, sx.max() - x0s.min() + 2, 0.5)
    chi2 = np.empty((len(sizes), len(x0s)))
    for i, s in enumerate(sizes):
        g0 = forward(mode, s, 0.0, ceiling, floor, xq, cfg)
        for j, x0 in enumerate(x0s):
            g = np.interp(sx - x0, xq, g0)
            chi2[i, j] = fit_offset(g, d, w)[1]
    return chi2


def invert(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg):
    chi2 = chi2_surface(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg)
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


def best_size_only(mode, sx, d, se, ceiling, floor, sizes, x0, cfg):
    """Continuous 1D size fit at fixed x0 (fast inner loop for MC).

    chi2(size) is smooth and unimodal, so a bounded minimiser finds the best
    size in ~15 forwards instead of scanning the whole grid.
    """
    w = 1.0 / se ** 2
    def chi(s):
        g = forward(mode, s, x0, ceiling, floor, sx, cfg)
        return fit_offset(g, d, w)[1]
    r = minimize_scalar(chi, bounds=(sizes[0], sizes[-1]), method="bounded",
                        options={"xatol": 0.05})
    return r.x


def size_area_se(mode, sx, d, se, res, ceiling, floor, sizes, cfg=None):
    """Combined 1-sigma on recovered size AND area, from the four RANDOM channels
    (data + picks + velocity + detrend) added in quadrature. Truncation is a
    separate systematic bracket, NOT included here. Uses cfg.sigma_pick,
    cfg.velocity, cfg.velocity_sigma, cfg.slope_se. Returns a dict of components +
    totals so both the driver and the terrain-model plot share one budget definition.
    """
    h = 0.5

    def fit(c, f):
        s = best_size_only(mode, sx, d, se, c, f, sizes, res["x0"], cfg)
        return s, area_of(mode, s, c, f)

    size0 = res["size"]
    area_best = area_of(mode, size0, ceiling, floor)

    # picks: independent ceiling/floor noise (central-difference partials).
    sp, ap = fit(ceiling + h, floor)
    sm, am = fit(max(ceiling - h, MIN_CEILING), floor)
    ds_dc, da_dc = (sp - sm) / (2 * h), (ap - am) / (2 * h)
    ds_df = da_df = 0.0
    if mode == "ellipse":
        sp, ap = fit(ceiling, floor + h)
        sm, am = fit(ceiling, max(floor - h, ceiling + 1))
        ds_df, da_df = (sp - sm) / (2 * h), (ap - am) / (2 * h)
    se_pick = np.hypot(ds_dc, ds_df) * cfg.sigma_pick
    area_se_pick = np.hypot(da_dc, da_df) * cfg.sigma_pick

    # velocity: a SYSTEMATIC common-mode DEPTH SHIFT of the whole tube. Picks are time
    # picks, so a fractional migration-velocity error scales the OVERBURDEN depth
    # (ceiling prop v_rock). The air-gap-corrected void height is set by v_air (a
    # constant, ~exact), so the cave height is INVARIANT to v_rock and the floor shifts
    # by the SAME absolute amount as the ceiling -- the tube slides in depth, keeping
    # its height. Shift = ceiling * dv (NOT floor * dv: scaling each pick by its own
    # depth would wrongly let the ellipse height breathe). For circle mode the floor is
    # unused, so this reduces to the ceiling scaling as before (circles unchanged).
    dv = cfg.velocity_sigma / cfg.velocity
    shift = ceiling * dv
    sp, ap = fit(ceiling + shift, floor + shift)
    sm, am = fit(max(ceiling - shift, MIN_CEILING), floor - shift)
    se_vel = abs(sp - sm) / 2.0
    area_se_vel = abs(ap - am) / 2.0

    # detrend: the removed regional slope's 1-sigma tilts the residual we fit.
    tilt = cfg.slope_se * (sx - sx.mean())

    def fit_data(dd):
        s = best_size_only(mode, sx, dd, se, ceiling, floor, sizes, res["x0"], cfg)
        return s, area_of(mode, s, ceiling, floor)

    sp, ap = fit_data(d + tilt)
    sm, am = fit_data(d - tilt)
    se_det = abs(sp - sm) / 2.0
    area_se_det = abs(ap - am) / 2.0

    # data: the chi2-rescaled grid-search half-interval.
    se_data = (res["size_hi"] - res["size_lo"]) / 2.0
    area_se_data = abs(area_of(mode, res["size_hi"], ceiling, floor)
                       - area_of(mode, res["size_lo"], ceiling, floor)) / 2.0

    quad = lambda *v: float(np.sqrt(np.sum(np.square(v))))
    return dict(
        size=size0, area=area_best,
        se_data=se_data, se_pick=se_pick, se_vel=se_vel, se_det=se_det,
        se_tot=quad(se_data, se_pick, se_vel, se_det),
        area_se_data=area_se_data, area_se_pick=area_se_pick,
        area_se_vel=area_se_vel, area_se_det=area_se_det,
        area_se_tot=quad(area_se_data, area_se_pick, area_se_vel, area_se_det),
    )


def sample_ensemble(mode, sx, d, se, ceil0, floor0, n, rng, cfg):
    """Hierarchical posterior sample of tube geometry over the SAME four channels
    size_area_se propagates (picks, velocity common-mode, detrend tilt, data noise)
    -- sampled instead of propagated, for the terrain-plot ensemble/envelope. Each
    draw perturbs the GPR picks (independent noise), the migration velocity (common-
    mode depth SHIFT of the whole tube by the overburden amount, cave height preserved
    -- see size_area_se for the air-gap rationale), the regional-trend slope (a tilt
    on the residual) and the station data (measurement noise), then refits (size, x0)
    on a coarse grid with the DC baseline floated inside invert(). Returns
    [(size, x0, ceiling, floor), ...]. Uses cfg.sigma_pick, cfg.velocity,
    cfg.velocity_sigma, cfg.slope_se (+ the MIN_CEILING constant) -- so it stays in
    lock-step with the analytic budget in size_area_se (one channel definition, both).

    The data-noise draw is inflated by sqrt(max(1, chi2_nu)) -- the SAME chi2-
    rescaling the analytic data channel uses (invert()'s size interval) -- so the
    ensemble spread (envelope, x0 SE, MC area SD) reflects the model under-fit and
    matches the reported analytic SE. Only the DATA channel is rescaled; the pick/
    velocity/detrend sigmas are external and stay as-is.
    """
    sizes = (np.arange(1.0, 20.0, 0.25) if mode == "circle"
             else np.arange(1.0, 30.0, 0.25))          # coarser than the fit grid
    xmin = sx[np.argmin(d)]
    x0s = np.arange(xmin - 20, xmin + 20, 0.5)
    dv_sig = cfg.velocity_sigma / cfg.velocity
    xm = sx - sx.mean()
    # Nominal fit -> chi2_nu, to rescale the data noise for the under-fit (as analytic).
    inflate = np.sqrt(max(1.0, invert(mode, sx, d, se, ceil0, floor0,
                                      sizes, x0s, cfg)["chi2red"]))
    out = []
    for _ in range(n):
        # velocity: common-mode depth SHIFT (overburden-driven, cave height preserved)
        vshift = ceil0 * rng.normal(0, dv_sig)
        c = ceil0 + rng.normal(0, cfg.sigma_pick) + vshift
        f = floor0 + (rng.normal(0, cfg.sigma_pick) if mode == "ellipse" else 0.0) + vshift
        c = max(c, MIN_CEILING)
        if mode == "ellipse":
            f = max(f, c + 1.0)
        dd = d + rng.normal(0, cfg.slope_se) * xm + rng.normal(0.0, se * inflate)
        res = invert(mode, sx, dd, se, c, f, sizes, x0s, cfg)
        out.append((res["size"], res["x0"], c, f))
    return out

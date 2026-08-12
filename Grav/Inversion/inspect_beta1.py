"""
Where does the offset beta1 in A(rho) = beta0/rho + beta1 come from?

The density sweep (sweep_density.py) measures A(rho) and fits an offset hyperbola.
Pure theory (App. "integrated gravity anomaly") says the integrated anomaly fixes the
mass deficit rho*A, hence A = const/rho exactly, i.e. beta1 = 0. Measured: L5 sits at
beta1 = -1 m^2 (pure 1/rho), but L3 at -161 (circle) / -75 (ellipse). This script asks
WHY, by decomposing the response instead of hypothesising about it.

rho enters in exactly TWO places:
  (1) the CHAIN -- Bouguer slab + terrain correction scale with rho, so the detrended
      CBA that the inversion fits is itself a function of rho;
  (2) the CONTRAST -- the inversion divides the required mass deficit by Delta rho.
Only (2) is in the textbook argument. So the tests below switch them on and off
independently. Every test reuses the per-rho chain outputs already on disk (written by
sweep_density.py), so nothing is re-derived and no pipeline is re-run.

TEST A -- decomposition. Three variants of the same sweep:
    full     : data at rho,      contrast at rho     (= the canonical sweep)
    frozen-d : data at rho_nom,  contrast at rho     (chain feedback OFF)
    frozen-c : data at rho,      contrast at rho_nom (contrast scaling OFF)
  beta1 of `frozen-d` is whatever the inversion itself produces without any chain
  feedback -- i.e. how far the fitted GEOMETRY has to move off the pure mass-deficit
  argument because the anomaly SHAPE, not just its amplitude, must fit. Whatever
  beta1 is left over in `full` is the chain.

TEST B -- is it DEPTH? The two lines differ in modelled ceiling depth (L3 3.8 m,
  L5 8.6 m), the obvious explanation for their different beta1. So force BOTH lines to
  the SAME ceiling and re-run the sweep at each. If depth is the cause, beta1 must
  converge when the depths match. Circle model on both lines, so the models are
  comparable (an ellipse has a second pick and is a different model).

TEST C -- what does the chain actually do to the data? For every station, fit the
  detrended CBA against rho and report the slope (uGal per g/cm3). No inversion is
  involved, so this is the raw input to any mechanism.

TEST D -- is it SIZE? TEST B cannot answer that: forcing the ceiling moves size and
  depth together. So impose an ellipse of height h on a FIXED centroid depth instead --
  the tube grows symmetrically about a fixed centre, changing area at constant depth --
  and use the SAME imposed geometry on both lines, matching depth and size across them
  at once. NB B holds the ceiling fixed while the centroid moves and D holds the
  centroid fixed while the ceiling moves, so neither is a perfect depth control alone;
  read them together.

Run:  python inspect_beta1.py            # all four tests
      python inspect_beta1.py --test B
"""

import argparse
import numpy as np
import invert_tube as it

RHO_NOM = 1.875
# The per-rho chain outputs that sweep_density.py left on disk.
RHOS = [1.4, 1.5, 1.6, 1.7, 1.8, 1.875, 1.9, 2.0, 2.1, 2.2,
        2.3, 2.4, 2.5, 2.6, 2.7, 2.8]
CEIL_GRID = [3.0, 5.0, 7.0, 9.0, 11.0, 13.0]     # forced ceilings for TEST B
CASES = [(3, "circle"), (3, "ellipse"), (5, "circle")]
# TEST D: ellipse of imposed height centred on a fixed centroid depth -> size varies at
# CONSTANT depth. Centroid = L3's nominal one, (3.8 + 14.6)/2; 10.8 m is L3's true
# height. Heights are capped so the ceiling stays above MIN_CEILING.
CENTROID = 9.2
HEIGHT_GRID = [4.0, 6.0, 8.0, 10.8, 13.0, 16.0]


def cfg_at(line, rho_contrast, rho_trend):
    """InvCfg with the void contrast set by rho_contrast; detrend slope SE read from
    the chain run at rho_trend (it is a property of that chain output)."""
    tp = np.genfromtxt(it.trend_file(rho_trend), delimiter=",", names=True)
    row = tp[tp["Line"] == line]
    return it.cfg_for(line,
                      slope_se=float(row["slope_se"][0]) if len(row) else 0.0,
                      density=rho_contrast * 1000.0)


def area_at(line, mode, rho_data, rho_contrast, ceiling=None):
    """Best-fit area for one (line, mode) with the data and the contrast density set
    INDEPENDENTLY, and optionally an overridden ceiling."""
    pre = it.LINE_PRESETS[line]
    if ceiling is None:
        ceiling, floor, _ = it.geometry_of(line)
    else:
        # Hold the GPR cave HEIGHT and slide the tube to the forced ceiling, so the
        # ellipse stays the same shape; the circle ignores floor anyway.
        h = (pre["floor"] - pre["ceiling"]) if pre["floor"] else 0.0
        floor = ceiling + h
    cfg = cfg_at(line, rho_contrast, rho_data)
    sx, d, se = it.load_line(line, rho_data)
    sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
    x0s = it.x0_grid(sx, d)
    res = it.invert(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg)
    return it.area_of(mode, res["size"], ceiling, floor)


def area_at_cf(line, mode, rho_data, rho_contrast, ceiling, floor):
    """area_at() with BOTH picks imposed explicitly (TEST D needs to set the ceiling
    and the floor independently, not slide a fixed-height tube)."""
    cfg = cfg_at(line, rho_contrast, rho_data)
    sx, d, se = it.load_line(line, rho_data)
    sizes = it.RADIUS_GRID if mode == "circle" else it.WIDTH_GRID
    x0s = it.x0_grid(sx, d)
    res = it.invert(mode, sx, d, se, ceiling, floor, sizes, x0s, cfg)
    return it.area_of(mode, res["size"], ceiling, floor)


def fit(rhos, areas):
    """A = beta0/rho + beta1; returns (beta0, beta1, R2)."""
    rhos, areas = np.asarray(rhos, float), np.asarray(areas, float)
    M = np.column_stack([1.0 / rhos, np.ones_like(rhos)])
    (b0, b1), *_ = np.linalg.lstsq(M, areas, rcond=None)
    ss_res = np.sum((areas - M @ [b0, b1]) ** 2)
    ss_tot = np.sum((areas - areas.mean()) ** 2)
    return b0, b1, 1.0 - ss_res / ss_tot


def test_A():
    print("\n=== TEST A: which of the two rho entry points makes beta1 ? ===")
    print("  full     = data(rho)     + contrast(rho)      [canonical sweep]")
    print("  frozen-d = data(rho_nom) + contrast(rho)      [chain feedback OFF]")
    print("  frozen-c = data(rho)     + contrast(rho_nom)  [contrast scaling OFF]\n")
    print(f"  {'case':<12}{'variant':<10}{'beta0':>8}{'beta1':>9}{'R2':>8}")
    for line, mode in CASES:
        for name, rd, rc in (("full", None, None),
                             ("frozen-d", RHO_NOM, None),
                             ("frozen-c", None, RHO_NOM)):
            areas = [area_at(line, mode, rd or r, rc or r) for r in RHOS]
            b0, b1, r2 = fit(RHOS, areas)
            print(f"  L{line} {mode:<9}{name:<10}{b0:8.0f}{b1:9.0f}{r2:8.4f}")
        print()


def test_B():
    print("\n=== TEST B: force both lines to the SAME ceiling (circle model) ===")
    print("  If depth causes the L3/L5 split, beta1 must converge at matched depth.\n")
    print(f"  {'ceiling':>8}", end="")
    for line in (3, 5):
        L = "L" + str(line)
        print(f"{L + ' A(rho0)':>12}{L + ' beta0':>11}{L + ' beta1':>11}", end="")
    print(f"{'ratio b1':>10}")
    for c in CEIL_GRID:
        print(f"  {c:8.1f}", end="")
        b1s = {}
        for line in (3, 5):
            areas = [area_at(line, "circle", r, r, ceiling=c) for r in RHOS]
            b0, b1, _ = fit(RHOS, areas)
            b1s[line] = b1
            a0 = areas[RHOS.index(RHO_NOM)]          # recovered area at nominal rho
            print(f"{a0:12.0f}{b0:11.0f}{b1:11.0f}", end="")
        rat = b1s[3] / b1s[5] if abs(b1s[5]) > 1e-9 else np.inf
        print(f"{rat:10.1f}")
    # SIZE control: forcing the ceiling also moves the recovered area, so the table
    # above contains pairs of (line, ceiling) with MATCHED area at different lines.
    # Reading beta1 across such a pair asks "is it size?" the same way a matched
    # ceiling asks "is it depth?".
    print("\n  Read a matched-AREA pair across the two lines to control for size.")


def test_D():
    """Size at FIXED depth. Forcing the ceiling (TEST B) moves size and depth together,
    so it cannot separate them. An ellipse of imposed height h centred on a FIXED
    centroid depth does: the tube grows symmetrically about a fixed centre, so the
    recovered area changes while the depth does not. The same imposed geometry is used
    on both lines, so this matches depth AND size across them simultaneously -- the
    strictest form of the "is it size?" question. (For L5 the imposed ellipse is a
    controlled test geometry, not a claim about its true shape -- L5 has no floor pick.)
    """
    print("\n=== TEST D: size at FIXED depth (ellipse, common centroid) ===")
    print(f"  Centroid held at {CENTROID:.1f} m on BOTH lines; height h imposed,")
    print("  half-width fitted. Depth is constant down each column.\n")
    print(f"  {'height':>7}", end="")
    for line in (3, 5):
        L = "L" + str(line)
        print(f"{L + ' A(rho0)':>12}{L + ' beta1':>11}{L + ' b1/A':>11}", end="")
    print()
    for h in HEIGHT_GRID:
        c, f = CENTROID - h / 2.0, CENTROID + h / 2.0
        print(f"  {h:7.1f}", end="")
        for line in (3, 5):
            areas = [area_at_cf(line, "ellipse", r, r, c, f) for r in RHOS]
            _b0, b1, _ = fit(RHOS, areas)
            a0 = areas[RHOS.index(RHO_NOM)]
            print(f"{a0:12.0f}{b1:11.0f}{b1 / a0:11.2f}", end="")
        print()
    print("\n  Same row = same depth AND same imposed height on both lines.")


def test_C():
    print("\n=== TEST C: how the detrended CBA itself moves with rho ===")
    print("  Per-station linear fit of detrended CBA vs rho (uGal per g/cm3).")
    print("  No inversion involved -- this is the chain's raw effect on the data.\n")
    for line in (3, 5):
        sx0, d0, _ = it.load_line(line, RHO_NOM)
        D = np.array([it.load_line(line, r)[1] for r in RHOS])    # (n_rho, n_stn)
        slope = np.polyfit(RHOS, D, 1)[0] * 1000.0                # mGal -> uGal
        icave = int(np.argmin(d0))
        # flanks = the outer quarter of the profile on each side
        n = len(sx0)
        flank = np.r_[np.arange(0, n // 4), np.arange(3 * n // 4, n)]
        print(f"  Line {line}:  cave station (x={sx0[icave]:6.1f} m) "
              f"d(CBA)/drho = {slope[icave]:+7.1f} uGal per g/cm3")
        print(f"            flank mean                  "
              f"d(CBA)/drho = {np.mean(slope[flank]):+7.1f}")
        print(f"            cave MINUS flank            "
              f"                {slope[icave] - np.mean(slope[flank]):+7.1f}"
              "   <- what the inversion sees as extra anomaly\n")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--test", default="ABCD", help="which tests to run, e.g. 'B' or 'AC'")
    a = p.parse_args()
    if "D" in a.test:
        test_D()
    if "A" in a.test:
        test_A()
    if "B" in a.test:
        test_B()
    if "C" in a.test:
        test_C()


if __name__ == "__main__":
    main()

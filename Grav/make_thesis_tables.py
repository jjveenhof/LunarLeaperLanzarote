"""
Reproduce the two correction-budget tables in the thesis from the pipeline CSVs.

    python make_thesis_tables.py            # print both tables + the LaTeX bodies
    python make_thesis_tables.py --check    # compare against the values in the thesis

Covers:
  tab:corr_budget  (main.tex) -- magnitude range and uncertainty of each CBA term
  tab:tc_perline   (main.tex) -- along-profile variation of the terrain correction
  tab:se-budget    (main.tex) -- per-channel area-uncertainty budget for the inversion
                                 (needs the inversion artifacts; skipped if absent)

Why this exists
---------------
Both tables were typed straight into main.tex with nothing tying them to the pipeline.
A figure with no producing script is obvious when it goes stale; a TABLE is not -- wrong
numbers look exactly like right ones. This script closes that gap: it recomputes every
cell from the same CSVs the thesis chain produces, and `--check` asserts they still match
what the thesis claims.

It does NOT write into main.tex. The tables are hand-formatted (phantom spacing, mixed
math), and the thesis is frozen -- so this prints, and the author compares. `--check`
exits non-zero if any cell has drifted.

Inputs (from run_pipeline.py):
  bouguer_anomaly_decay_rho{X}.csv          SBA chain: Grav_lsq, SE_lsq, FAC, LAT, BC, SE_elev
  bouguer_anomaly_decay_rho{X}_with_TC.csv  adds dTC (terrain correction, base-relative)

All values are mGal, relative to the per-line per-day base station (g_base = 0).
"""

import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd

from grav_utils import PROC_DIR, RHO_DEFAULT, rho_str, sba_file

# The values currently in main.tex, for --check. Keyed so a mismatch names the cell.
# If a number here legitimately changes, the THESIS is what needs updating -- and per
# that is something to investigate and explain, not to quietly edit away.
THESIS_CORR_BUDGET = {
    "obs_min": -0.49, "obs_max": +0.50, "obs_se_med": 0.015, "obs_se_max": 0.058,
    "elev_min": -0.41, "elev_max": +0.59, "elev_se_med": 0.003, "elev_se_max": 0.006,
    "lat_min": -0.09, "lat_max": 0.0,
    "tc_min": +0.08, "tc_max": +0.22,
}
THESIS_TC_PERLINE = {
    2: (0.089, 0.002, 0.008, 0.014),
    3: (0.099, 0.016, 0.050, 0.020),
    4: (0.112, 0.040, 0.135, 0.014),
    5: (0.090, 0.003, 0.013, 0.029),
}
# tab:se-budget: (data, picks, velocity, detrend, quad-sum, MC) in m^2, rounded as printed.
THESIS_SE_BUDGET = {
    (3, "circle"):  (19, 28, 10, 12, 37, 41),
    (3, "ellipse"): (15, 16,  7,  9, 25, 24),
    (5, "circle"):  (23, 18, 15,  9, 34, 36),
}


def load(rho=RHO_DEFAULT):
    sba = pd.read_csv(sba_file(rho))
    tc_path = PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str(rho)}_with_TC.csv"
    tc = pd.read_csv(tc_path)
    # The colleague's raw corrections. `Terrain_correction` here is the ABSOLUTE terrain
    # correction; the `dTC` column in the with_TC file is the BASE-RELATIVE one
    # (dTC = TC - TC_base). The thesis tables quote the ABSOLUTE values (mean ~0.09-0.11),
    # so read them from here -- dTC has the same std and span but a mean near zero.
    coll = pd.read_csv(PROC_DIR / "LL_gravity_corrections.csv")
    return sba, tc, coll


def corr_budget(sba, tc, coll):
    """Magnitude range + uncertainty for each term of the CBA."""
    # Elevation term = free-air + Bouguer slab, applied together (both driven by dh).
    elev = sba["FAC"] + sba["BC"]
    rows = [
        ("Observed anomaly, g_k", sba["Grav_lsq"], sba["SE_lsq"]),
        ("Elevation (free-air + Bouguer)", elev, sba["SE_elev"]),
        ("Latitude correction", sba["LAT"], None),
        ("Terrain correction", coll["Terrain_correction"], None),
    ]
    out = []
    for name, val, se in rows:
        v = val.dropna()
        se_med = se_max = None
        if se is not None:
            s = se.dropna()
            se_med, se_max = float(s.median()), float(s.max())
        out.append((name, float(v.min()), float(v.max()), se_med, se_max))
    return out


def tc_perline(tc, coll):
    """Along-profile variation of the terrain correction, per line.

    Mean/std/span: the colleague's ABSOLUTE Terrain_correction over ALL stations.
    Station SE:    the MEDIAN SE_lsq over NON-BASE stations -- see STATION_SE_NOTE.

    The two columns deliberately use different station sets. The base station's SE_lsq is
    EXACTLY 0 by datum definition, so including it in a "typical station SE" would drag
    every line toward a structural zero; its terrain correction, by contrast, is an
    ordinary value like any other station's."""
    out = []
    for line, g in coll.groupby("Line"):
        d = g["Terrain_correction"].dropna()
        sub = tc[(tc["Line"] == line) & (tc["loc_id"] != 0)]      # drop the datum station
        se = sub["SE_lsq"].dropna()
        out.append((int(line), float(d.mean()), float(d.std(ddof=1)),
                    float(d.max() - d.min()), float(se.median())))
    return out


def se_budget():
    """Per-channel area-uncertainty budget for each inversion case (tab:se-budget).

    Returns {(line, mode): (data, picks, vel, det, quad_sum, mc)} in m^2, or None if the
    inversion artifacts are not on disk. The first five come from `size_area_se`'s
    first-order propagation, stored in the artifact by run_inversion.py; the MC column is
    the SD of the artifact's posterior ensemble areas -- the SAME quantity reported in
    tab:inversion-results and drawn by plot_area_summary.py.

    This table was briefly listed in REPRODUCE.md as hand-written. It is not: every cell
    is calculated, and all 18 reproduce exactly."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / "Inversion"))
    try:
        import invert_tube as it
        import inversion_io as io
    except ImportError:
        return None
    out = {}
    for (line, mode) in THESIS_SE_BUDGET:
        try:
            d = io.load_artifact(line, mode)
        except FileNotFoundError:
            continue
        areas = np.array([it.area_of(mode, s, c, f) for (s, _x, c, f) in d["ensemble"]])
        out[(line, mode)] = (d["area_se_data"], d["area_se_pick"], d["area_se_vel"],
                             d["area_se_det"], d["area_se_tot"], float(areas.std(ddof=1)))
    return out or None


# PROVENANCE of the "Station SE" column -- resolved 2026-08-12 (was a rule-3 escalation).
# It is the MEDIAN SE_lsq over NON-BASE stations, rounded half-up to 3 dp:
#     raw  L2 0.013808   L3 0.020285   L4 0.013541   L5 0.028816
#     ->      0.014         0.020         0.014         0.029      = the thesis row exactly.
# The thesis values are CORRECT. My original escalation was wrong, for two reasons:
#   1. I averaged over ALL stations including the base, whose SE_lsq is EXACTLY 0 by datum
#      definition. That structural zero pulled every line down, which is why my numbers
#      were uniformly too small (0.012 / 0.015 / 0.012 / 0.026) rather than wrong in a
#      random direction -- the uniform-offset signature I mistook for a stale pipeline.
#   2. L4 sits on a rounding boundary. 0.013541 rounds half-up to 0.014; the 2026-08-01
#      TAU_MIN fix moved it to 0.013447 -> 0.013. So L4 alone is genuinely pipeline-state
#      dependent, by 0.0001 mGal. Verified by rebuilding the 2026-06-11 state (ed6f723).
# NB numpy/Python round half to EVEN, so use round_half_up() when comparing to the thesis.
STATION_SE_NOTE = True


def round_half_up(x, nd=3):
    """Round as a person or a spreadsheet would. Banker's rounding turns L4's 0.013541
    into 0.013 at 3 dp, where the thesis (correctly) shows 0.014."""
    q = Decimal("1").scaleb(-nd)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def report(rho=RHO_DEFAULT):
    sba, tc, coll = load(rho)
    budget = corr_budget(sba, tc, coll)
    perline = tc_perline(tc, coll)

    print(f"rho = {rho} g/cm3   ({len(sba)} stations)\n")
    print("tab:corr_budget -- magnitude and uncertainty of the gravity corrections")
    print(f"  {'Term':<34s} {'Magnitude (mGal)':>22s}   Uncertainty (mGal)")
    for name, lo, hi, se_med, se_max in budget:
        mag = f"{lo:+.2f} to {hi:+.2f}"
        unc = "--" if se_med is None else f"median {se_med:.3f}  max {se_max:.3f}"
        print(f"  {name:<34s} {mag:>22s}   {unc}")

    print("\ntab:tc_perline -- along-profile variation of the terrain correction")
    print(f"  {'Line':<6s}{'Mean':>8s}{'Std':>8s}{'Span':>8s}{'Station SE':>12s}")
    for line, mean, std, span, se in perline:
        print(f"  {line:<6d}{mean:8.3f}{std:8.3f}{span:8.3f}{se:12.3f}")

    print("\n-- LaTeX body, tab:tc_perline --")
    for line, mean, std, span, se in perline:
        print(f"    {line} & {mean:.3f} & {std:.3f} & {span:.3f} & {se:.3f} \\\\")

    seb = se_budget()
    print("\ntab:se-budget -- per-channel area-uncertainty budget (m^2)")
    if seb is None:
        print("  (no inversion artifacts on disk -- run Inversion/run_inversion.py)")
    else:
        print(f"  {'Line':<5}{'Shape':<9}{'data':>6}{'picks':>7}{'vel':>6}"
              f"{'det':>6}{'quad':>7}{'MC':>6}")
        for (line, mode), v in sorted(seb.items()):
            print(f"  {line:<5}{mode:<9}" + "".join(f"{x:6.0f}" if i != 1 else f"{x:7.0f}"
                                                    for i, x in enumerate(v[:4]))
                  + f"{v[4]:7.0f}{v[5]:6.0f}")

    return budget, perline


def check(rho=RHO_DEFAULT):
    """Compare every cell against the values in main.tex. Returns a list of mismatches."""
    sba, tc, coll = load(rho)
    budget = dict()
    for name, lo, hi, se_med, se_max in corr_budget(sba, tc, coll):
        key = {"Observed anomaly, g_k": "obs",
               "Elevation (free-air + Bouguer)": "elev",
               "Latitude correction": "lat",
               "Terrain correction": "tc"}[name]
        budget[f"{key}_min"], budget[f"{key}_max"] = lo, hi
        if se_med is not None:
            budget[f"{key}_se_med"], budget[f"{key}_se_max"] = se_med, se_max

    bad = []
    # Thesis quotes these to 2 dp (magnitudes) / 3 dp (SEs); compare at that precision.
    for k, want in THESIS_CORR_BUDGET.items():
        got = budget.get(k)
        dp = 3 if "_se_" in k else 2
        if got is None or round(got, dp) != round(want, dp):
            bad.append(f"tab:corr_budget {k}: thesis {want}, computed "
                       f"{'MISSING' if got is None else round(got, dp)}")

    for line, mean, std, span, se in tc_perline(tc, coll):
        want = THESIS_TC_PERLINE.get(line)
        if want is None:
            bad.append(f"tab:tc_perline L{line}: present in data, absent from the thesis")
            continue
        for label, g, w in zip(("mean", "std", "span", "SE"),
                               (mean, std, span, se), want):
            if round_half_up(g) != round_half_up(w):
                bad.append(f"tab:tc_perline L{line} {label}: thesis {w}, "
                           f"computed {round_half_up(g)} (raw {g:.6f})")

    seb = se_budget()
    if seb is None:
        print("  (tab:se-budget not checked -- no inversion artifacts on disk)")
    else:
        cols = ("data", "picks", "velocity", "detrend", "quad-sum", "MC")
        for key, want in THESIS_SE_BUDGET.items():
            got = seb.get(key)
            if got is None:
                bad.append(f"tab:se-budget {key}: no artifact")
                continue
            for label, g, w in zip(cols, got, want):
                if round(g) != w:
                    bad.append(f"tab:se-budget L{key[0]} {key[1]} {label}: "
                               f"thesis {w}, computed {round(g)}")
    return bad


if __name__ == "__main__":
    rho = RHO_DEFAULT
    report(rho)
    if "--check" in sys.argv:
        bad = check(rho)
        print("\n" + "-" * 60)
        if bad:
            print(f"MISMATCH -- {len(bad)} cell(s) differ from main.tex:")
            for b in bad:
                print(f"  {b}")
            print("\nThe thesis is frozen: do NOT edit either side to make these agree.")
            print("Find out WHY before changing anything.")
            sys.exit(1)
        print("OK -- every cell matches the values in main.tex.")

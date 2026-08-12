"""
Reproduce the two correction-budget tables in the thesis from the pipeline CSVs.

    python make_thesis_tables.py            # print both tables + the LaTeX bodies
    python make_thesis_tables.py --check    # compare against the values in the thesis

Covers:
  tab:corr_budget  (main.tex) -- magnitude range and uncertainty of each CBA term
  tab:tc_perline   (main.tex) -- along-profile variation of the terrain correction

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

import numpy as np
import pandas as pd

from grav_utils import PROC_DIR, RHO_DEFAULT, rho_str, sba_file

# The values currently in main.tex, for --check. Keyed so a mismatch names the cell.
# If a number here legitimately changes, the THESIS is what needs updating -- and per
# REFACTOR.md rule 3 that is an escalation, not a quiet edit.
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

    Mean/std/span come from the colleague's ABSOLUTE Terrain_correction. The last
    column ("Station SE") is the measurement SE it is compared against -- see
    STATION_SE_NOTE: the thesis value for this column does NOT reproduce from any
    statistic of SE_lsq / SE_SBA, and is reported here as median SE_lsq alongside the
    thesis figure rather than silently reconciled."""
    out = []
    for line, g in coll.groupby("Line"):
        d = g["Terrain_correction"].dropna()
        se = tc[tc["Line"] == line]["SE_lsq"].dropna()
        out.append((int(line), float(d.mean()), float(d.std(ddof=1)),
                    float(d.max() - d.min()), float(se.median())))
    return out


# The "Station SE" column of tab:tc_perline (0.014 / 0.020 / 0.014 / 0.029) could not be
# reproduced from the pipeline: no statistic (mean / median / max / RMS, over all stations
# or only those with a TC) of SE_lsq, SE_SBA or SE_elev yields it. Closest is mean SE_lsq
# over TC-bearing stations (0.015 / 0.018 / 0.011 / 0.028). Flagged to the author under
# REFACTOR.md rule 3 -- NOT reconciled here, in either direction.
STATION_SE_NOTE = True


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
            if round(g, 3) != round(w, 3):
                bad.append(f"tab:tc_perline L{line} {label}: thesis {w}, "
                           f"computed {round(g, 3)}")
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
            print("Escalate to the root QandA.md (REFACTOR.md rule 3).")
            sys.exit(1)
        print("OK -- every cell matches the values in main.tex.")

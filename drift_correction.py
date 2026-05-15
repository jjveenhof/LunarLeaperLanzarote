"""
Apply linear loop drift correction to the station-mean gravity values.

Input
-----
  Data/Gravimetry/station_means.csv

Output
------
  Data/Gravimetry/drift_corrected.csv

Method
------
  Within each Line, stations are sorted by time. Consecutive base station pairs
  bracket a loop. For each loop with at least one non-base station between the
  pair, drift is modelled as linear:

    drift_rate    = (g_end − g_start) / (t_end − t_start)
    g_corr(t)     = g_raw(t) − drift_rate × (t − t_start)

  Each loop is corrected independently. Corrected values are expressed relative
  to that loop's own start base station — no cross-loop chaining is applied.

  Uncertainty propagation:
    SE_drift_rate    = sqrt(SE_start² + SE_end²) / (t_end − t_start)
    SE_correction(t) = SE_drift_rate × (t − t_start)
    SE_corr(t)       = sqrt(SE_wmean(t)² + SE_correction(t)²)

Consistency check
-----------------
  Base stations: all per line — after correction all should read the same value
    (they are at the same physical location). Residual spread = drift model error.
  Non-base co-located pairs: same line, within TIE_DISTANCE_M metres.
"""

import numpy as np
import pandas as pd
from pathlib import Path

BASE       = Path(__file__).resolve().parents[1]
MEANS_FILE = BASE / "Data/Gravimetry/station_means.csv"
OUT_FILE   = BASE / "Data/Gravimetry/drift_corrected.csv"

TIE_DISTANCE_M = 3.0


# ── Drift correction ──────────────────────────────────────────────────────────

def correct_line(group):
    group = group.sort_values("datetime").reset_index(drop=True)
    group["Grav_corr"]         = np.nan
    group["SE_corr"]           = np.nan
    group["drift_rate_mGal_h"] = np.nan
    group["loop_id"]           = pd.NA

    base_idx = group.index[group["StationType"] == "base"].tolist()
    if len(base_idx) < 2:
        return group, []

    loop_id  = 0
    loop_log = []

    for i_pair in range(len(base_idx) - 1):
        i_start = base_idx[i_pair]
        i_end   = base_idx[i_pair + 1]
        inner   = [k for k in range(i_start + 1, i_end)
                   if group.loc[k, "StationType"] != "base"]
        if not inner:
            continue

        loop_id += 1
        base_s = group.loc[i_start]
        base_e = group.loc[i_end]

        t_start       = base_s["datetime"]
        dt_min        = (base_e["datetime"] - t_start).total_seconds() / 60
        drift_rate    = (base_e["Grav_wmean"] - base_s["Grav_wmean"]) / dt_min
        SE_drift_rate = np.sqrt(base_s["SE_wmean"]**2 + base_e["SE_wmean"]**2) / dt_min

        for idx in [i_start] + inner + [i_end]:
            t_elapsed  = (group.loc[idx, "datetime"] - t_start).total_seconds() / 60
            correction = drift_rate * t_elapsed
            SE_corr    = np.sqrt(group.loc[idx, "SE_wmean"]**2
                                 + (SE_drift_rate * t_elapsed)**2)
            group.loc[idx, "Grav_corr"]         = group.loc[idx, "Grav_wmean"] - correction
            group.loc[idx, "SE_corr"]           = SE_corr
            group.loc[idx, "drift_rate_mGal_h"] = drift_rate * 60
            group.loc[idx, "loop_id"]           = loop_id

        loop_log.append({
            "loop_id":      loop_id,
            "base_start":   f"L{int(base_s['Line'])}S{int(base_s['Station'])}",
            "base_end":     f"L{int(base_e['Line'])}S{int(base_e['Station'])}",
            "t_start":      base_s["Time_first"],
            "t_end":        base_e["Time_first"],
            "drift_mGal_h": drift_rate * 60,
            "n_stations":   len(inner),
        })

    return group, loop_log


# ── Consistency check ─────────────────────────────────────────────────────────

def consistency_check(df):
    print("\nConsistency check:")

    print("\n  Base stations (all per line — same physical location, spread = drift model error):")
    for line, lg in df.groupby("Line"):
        bases = lg[(lg["StationType"] == "base") & lg["Grav_corr"].notna()]
        if len(bases) < 2:
            continue
        spread = (bases["Grav_corr"].max() - bases["Grav_corr"].min()) * 1000
        rms    = bases["Grav_corr"].std() * 1000
        print(f"    Line {line}: {len(bases)} base stations — "
              f"spread = {spread:.1f} µGal,  RMS = {rms:.1f} µGal")

    print(f"\n  Co-located non-base pairs (same line, within {TIE_DISTANCE_M} m):")
    any_pairs = False
    for line, lg in df.groupby("Line"):
        non_base = lg[(lg["StationType"] != "base")
                      & lg["Grav_corr"].notna()
                      & lg["Easting"].notna()].reset_index(drop=True)
        if len(non_base) < 2:
            continue
        coords = non_base[["Easting", "Northing"]].values
        for i in range(len(non_base)):
            for j in range(i + 1, len(non_base)):
                dist = np.sqrt((coords[i, 0] - coords[j, 0])**2
                               + (coords[i, 1] - coords[j, 1])**2)
                if dist > TIE_DISTANCE_M:
                    continue
                any_pairs = True
                ri, rj      = non_base.iloc[i], non_base.iloc[j]
                disc        = (ri["Grav_corr"] - rj["Grav_corr"]) * 1000
                combined_se = np.sqrt(ri["SE_corr"]**2 + rj["SE_corr"]**2) * 1000
                print(f"    Line {line}  "
                      f"S{int(ri['Station'])} ({ri['StationType']}) vs "
                      f"S{int(rj['Station'])} ({rj['StationType']}): "
                      f"Δg = {disc:+.1f} µGal  "
                      f"(combined SE = {combined_se:.1f} µGal,  dist = {dist:.2f} m)")
    if not any_pairs:
        print("    No co-located pairs found.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Reading {MEANS_FILE.name} …")
    df = pd.read_csv(MEANS_FILE, dtype={"Time_first": str, "Date": str})
    df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time_first"],
                                    format="%Y/%m/%d %H:%M:%S")
    print(f"  {len(df)} stations across Lines {sorted(df['Line'].unique())}")

    all_results, all_loops = [], []

    for line, group in df.groupby("Line"):
        corrected, loop_log = correct_line(group.copy())
        all_results.append(corrected)
        for entry in loop_log:
            entry["Line"] = line
        all_loops.extend(loop_log)
        n_corr = corrected["Grav_corr"].notna().sum()
        print(f"  Line {line}: {len(loop_log)} loop(s), {n_corr}/{len(group)} stations corrected")

    result = (pd.concat(all_results)
                .sort_values(["Line", "Station"])
                .reset_index(drop=True)
                .drop(columns=["datetime"]))

    print("\nLoop summary:")
    for e in all_loops:
        print(f"  Line {e['Line']} loop {e['loop_id']:2d}: "
              f"{e['base_start']} ({e['t_start']}) → {e['base_end']} ({e['t_end']})  |  "
              f"drift = {e['drift_mGal_h']:+.4f} mGal/h  |  {e['n_stations']} stations")

    consistency_check(result)

    cols = [
        "Line", "Station",
        "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
        "Grav_wmean", "Grav_corr", "SE_wmean", "SE_corr",
        "drift_rate_mGal_h", "loop_id", "n_readings",
        "Date", "Time_first", "Time_last",
        "StationType", "Notes",
    ]
    result[cols].to_csv(OUT_FILE, index=False, float_format="%.6f")
    print(f"\nSaved → {OUT_FILE.name}")


if __name__ == "__main__":
    main()

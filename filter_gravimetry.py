"""
Filter the combined gravimetry dataset and write a clean CSV for drift correction.

Input
-----
  Data/Gravimetry/combined_gravimetry.csv   raw combined dataset (from combine_gravimetry.py)
  Data/Gravimetry/exclusions.csv            manual exclusion list

Output
------
  Data/Gravimetry/filtered_gravimetry.csv

Filters applied in order
------------------------
  1. Exclusion list — applied first, before any automatic filter.
       - Paste a full row from combined_gravimetry.csv → drops that one reading (Time matched).
       - Add only Line + Station (leave Time blank or use *) → drops the whole station.
     Extra columns are ignored, so pasting full rows from the raw CSV works directly.
  2. Warmup drop    — first N_WARMUP readings per station dropped (instrument settling).
  3. SD threshold   — readings with SD > SD_MAX dropped.
  4. Tilt threshold — readings where |TiltX| > TILT_MAX or |TiltY| > TILT_MAX dropped.
  5. Rej threshold  — readings with Rej > REJ_MAX dropped.
     Note: Rej does not appear in the SE formula (SD already reflects accepted samples only),
     but high Rej is still a useful proxy for an unstable setup or noisy environment.

Per-station overrides
---------------------
  KEEP_ALL   — stations that skip the warmup and all automatic filters entirely.
               The exclusion list still applies.
  OVERRIDES  — per-station parameter overrides, e.g. a relaxed tilt threshold.
               Unspecified parameters fall back to the global defaults.
"""

import csv
import numpy as np
import pandas as pd
from pathlib import Path

BASE      = Path(__file__).resolve().parents[1]
RAW_FILE  = BASE / "Data/Gravimetry/combined_gravimetry.csv"
FILT_FILE = BASE / "Data/Gravimetry/filtered_gravimetry.csv"
EXCL_FILE = BASE / "Data/Gravimetry/exclusions.csv"

# ── Global filtering parameters ───────────────────────────────────────────────
N_WARMUP  = 5     # readings to drop at the start of each station (instrument settling)
SD_MAX    = 0.15  # mGal  — drop readings with SD above this
TILT_MAX  = 20    # arcsec — drop readings where |TiltX| or |TiltY| exceeds this
REJ_MAX   = 10   # counts — drop readings with more than this many rejected 6 Hz samples

# ── Per-station overrides ─────────────────────────────────────────────────────
# Stations listed here skip the warmup drop and ALL automatic filters.
# The exclusion list is still applied.
KEEP_ALL = {
    (2, 16),
    (4, 10),
}

# Override individual filter parameters for specific stations.
# Any key not listed falls back to the global default above.
OVERRIDES = {
    (3, 29): {"tilt_max": 35},  # ground was unstable — relax tilt threshold
}


# ── Exclusion list ────────────────────────────────────────────────────────────

def load_exclusions():
    if not EXCL_FILE.exists():
        # Header matches combined_gravimetry.csv so full rows can be pasted directly.
        # For station-level exclusions just write Line,Station with the rest empty.
        combined_cols = pd.read_csv(RAW_FILE, nrows=0).columns.tolist()
        pd.DataFrame(columns=combined_cols).to_csv(EXCL_FILE, index=False)
        print(f"  Created empty exclusion list → {EXCL_FILE.name}")
        return pd.DataFrame(columns=["Line", "Station", "Time"])

    # Use csv.reader so rows with extra pasted columns are handled without error.
    # Only the first three columns (Line, Station, Time) are extracted.
    rows = []
    with open(EXCL_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        if not {"Line", "Station"}.issubset(header):
            raise ValueError(
                f"{EXCL_FILE.name} must have at least Line and Station columns, "
                f"got {header}"
            )
        li  = header.index("Line")
        si  = header.index("Station")
        ti  = header.index("Time") if "Time" in header else None
        for row in reader:
            if not row:
                continue
            time_val = row[ti].strip() if (ti is not None and ti < len(row)) else ""
            time_val = None if time_val in ("", "*", "nan") else time_val
            rows.append({
                "Line":    int(row[li]),
                "Station": int(row[si]),
                "Time":    time_val,
            })

    return pd.DataFrame(rows, columns=["Line", "Station", "Time"])


def _apply_exclusions(df, exclusions):
    if exclusions.empty:
        return df

    station_excl = exclusions[exclusions["Time"].isna()]
    reading_excl = exclusions[exclusions["Time"].notna()]

    if not station_excl.empty:
        all_stations   = set(zip(df["Line"], df["Station"]))
        excl_stations  = set(zip(station_excl["Line"], station_excl["Station"]))
        unmatched = excl_stations - all_stations
        if unmatched:
            for ls in sorted(unmatched):
                print(f"  WARNING: exclusion entry L{ls[0]}S{ls[1]} (no Time) "
                      f"matched no station in the dataset")
        df = df[~df.apply(lambda r: (r["Line"], r["Station"]) in excl_stations, axis=1)]

    if not reading_excl.empty:
        all_readings  = set(zip(df["Line"], df["Station"], df["Time"]))
        excl_readings = set(zip(reading_excl["Line"], reading_excl["Station"], reading_excl["Time"]))
        unmatched = excl_readings - all_readings
        if unmatched:
            for ls in sorted(unmatched):
                print(f"  WARNING: exclusion entry L{ls[0]}S{ls[1]} Time={ls[2]} "
                      f"matched no reading in the dataset")
        df = df[~df.apply(lambda r: (r["Line"], r["Station"], r["Time"]) in excl_readings, axis=1)]

    return df


# ── Main filter pipeline ──────────────────────────────────────────────────────

def apply_filters(df, exclusions):
    n_start = len(df)
    report  = []

    # 1. Exclusion list — always first so warmup counts are based on remaining readings
    n_before = len(df)
    df = _apply_exclusions(df, exclusions)
    report.append(("Exclusion list", n_before - len(df)))

    # Split off KEEP_ALL stations — they skip every automatic filter from here on
    station_key  = list(zip(df["Line"], df["Station"]))
    keep_all_mask = pd.Series([k in KEEP_ALL for k in station_key], index=df.index)
    df_keep = df[keep_all_mask]
    df      = df[~keep_all_mask]

    # 2. Warmup drop — first N_WARMUP readings per station (sorted by Time)
    n_before   = len(df)
    warmup_idx = (
        df.sort_values("Time")
          .groupby(["Line", "Station"])
          .head(N_WARMUP)
          .index
    )
    df = df.drop(index=warmup_idx)
    report.append(("Warmup drop", n_before - len(df)))

    # Helper: get per-station parameter, falling back to global default
    def param(line, station, key, default):
        return OVERRIDES.get((line, station), {}).get(key, default)

    # 3. SD threshold
    n_before = len(df)
    sd_thresh = df.apply(lambda r: param(r["Line"], r["Station"], "sd_max", SD_MAX), axis=1)
    df = df[df["SD"] <= sd_thresh]
    report.append((f"SD > {SD_MAX} mGal", n_before - len(df)))

    # 4. Tilt threshold (per-station override supported)
    n_before   = len(df)
    tilt_thresh = df.apply(lambda r: param(r["Line"], r["Station"], "tilt_max", TILT_MAX), axis=1)
    df = df[(df["TiltX"].abs() <= tilt_thresh) & (df["TiltY"].abs() <= tilt_thresh)]
    report.append((f"|Tilt| > {TILT_MAX} arcsec", n_before - len(df)))

    # 5. Rej threshold
    n_before  = len(df)
    rej_thresh = df.apply(lambda r: param(r["Line"], r["Station"], "rej_max", REJ_MAX), axis=1)
    df = df[df["Rej"] <= rej_thresh]
    report.append((f"Rej > {REJ_MAX} samples", n_before - len(df)))

    # Recombine keep-all stations with the filtered set
    df = pd.concat([df_keep, df]).sort_values(["Line", "Station", "Time"]).reset_index(drop=True)

    print(f"\n  Filter summary (started with {n_start} readings):")
    print(f"    {'KEEP_ALL stations (skipped auto-filters)':<38} {len(KEEP_ALL)} station(s): "
          f"{sorted(KEEP_ALL)}")
    for label, n_dropped in report:
        print(f"    {label:<38} dropped {n_dropped:4d}")
    print(f"    {'Total remaining':<38} {len(df):4d}")

    return df


def main():
    print(f"Reading {RAW_FILE.name} …")
    df = pd.read_csv(RAW_FILE, dtype={"Time": str, "Date": str})
    print(f"  {len(df)} readings across {df.groupby(['Line', 'Station']).ngroups} stations")

    print("Loading exclusion list …")
    exclusions = load_exclusions()
    print(f"  {len(exclusions)} manual exclusions")

    print("\nApplying filters …")
    filtered = apply_filters(df, exclusions)

    filtered.to_csv(FILT_FILE, index=False, float_format="%.6f")
    print(f"\nSaved → {FILT_FILE.name}")

    n_stations  = filtered.groupby(["Line", "Station"]).ngroups
    n_no_gnss   = filtered.groupby(["Line", "Station"])["Easting"].first().isna().sum()
    type_counts = filtered.groupby(["Line", "Station"])["StationType"].first().value_counts()
    n_nan_se    = filtered["SE_i"].isna().sum()
    print(f"\nFiltered dataset:")
    print(f"  Stations retained     : {n_stations}")
    print(f"  Without GNSS position : {n_no_gnss}")
    print(f"  Station types:\n{type_counts.to_string()}")
    print(f"  Readings with SE_i = NaN (Dur*6 - Rej ≤ 0): {n_nan_se}")


if __name__ == "__main__":
    main()

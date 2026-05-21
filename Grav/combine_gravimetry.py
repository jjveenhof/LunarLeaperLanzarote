"""
Combine CG-5 gravimetry data, GNSS positions, and field notes into one CSV.

Inputs
------
  Data/Gravimetry/Field data/*.txt              CG-5 ASCII dumps
  Data/GNSS/01.05.26/LunLeapLanzGrav.txt        cumulative GNSS positions
  Data/Gravimetry/Notes/GravNotes*.txt           per-day field notes

Output
------
  Data/Gravimetry/combined_gravimetry.csv        all readings, unfiltered

Structure
---------
  One row per CG-5 reading (not per station), so individual measurements can
  be inspected and selectively excluded before further processing.
  GNSS positions and field notes are joined by (Line, Station) and repeated
  for every reading at that station.

  SE_i = SD_i / sqrt(Dur_i)  â€” per-reading instrument SE (CG-5 manual formula ERR = SD/sqrt(Dur)).
  Rej is already reflected in SD (instrument computes SD from accepted samples only).
  To compute the weighted station mean later:
    w_i = 1/SE_i^2,  g_w = sum(w_i * Grav_i) / sum(w_i),  SE_station = 1/sqrt(sum(w_i))

Notes
-----
  - Lines 0 and 1 are excluded (calibration / test data).
  - When a station has multiple GNSS measurements the last one is kept.
  - Readings where Dur*6 - Rej <= 0 get SE_i = NaN (exclude from weighting).
"""

import re
import numpy as np
import pandas as pd
from pathlib import Path

BASE      = Path(__file__).resolve().parents[2]
CG5_DIR   = BASE / "Data/Gravimetry/Field data"
NOTES_DIR = BASE / "Data/Gravimetry/Notes"
GNSS_FILE = BASE / "Data/GNSS/01.05.26/LunLeapLanzGrav.txt"
OUT_FILE  = BASE / "Data/Gravimetry/combined_gravimetry.csv"


# â”€â”€ CG-5 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def load_cg5():
    # The CG-5 accumulates all measurements in each dump, so only the most
    # recently modified file is needed â€” it contains the complete dataset.
    latest = max(CG5_DIR.glob("*.txt"), key=lambda f: f.stat().st_mtime)
    print(f"  Using CG-5 file: {latest.name}")

    rows = []
    with open(latest, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("/") or line.startswith("Line"):
                continue
            parts = line.split()
            if len(parts) < 15:
                continue
            try:
                rows.append({
                    "Line":    float(parts[0]),
                    "Station": float(parts[1]),
                    "Grav":    float(parts[3]),
                    "SD":      float(parts[4]),
                    "TiltX":   float(parts[5]),
                    "TiltY":   float(parts[6]),
                    "Temp":    float(parts[7]),
                    "Tide":    float(parts[8]),
                    "Dur":     float(parts[9]),
                    "Rej":     float(parts[10]),
                    "Time":    parts[11],
                    "Date":    parts[14],
                })
            except ValueError:
                continue

    df = pd.DataFrame(rows)
    df = df[df["Line"] >= 2].copy()

    # Per-reading SE: ERR = SD / sqrt(Dur), per CG-5 manual.
    # Dur is in seconds. Rej is already reflected in SD (the instrument computes SD
    # from accepted samples only), so no explicit Rej correction is needed here.
    df["SE_i"] = np.where(df["Dur"] > 0, df["SD"] / np.sqrt(df["Dur"]), np.nan)

    return df.reset_index(drop=True)


# â”€â”€ GNSS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_GNSS_PAT = re.compile(r"^GRAVL(\d+)S(\d+)$")


def load_gnss():
    rows = []
    with open(GNSS_FILE, encoding="utf-8", errors="replace") as f:
        for raw in f:
            parts = raw.strip().split("\t")
            # expected: Name  Easting  Northing  Elevation  <empty>  HorizErr  VertErr  DateTime
            if len(parts) < 7:
                continue
            m = _GNSS_PAT.match(parts[0])
            if not m:
                continue
            try:
                rows.append({
                    "Line":      float(m.group(1)),
                    "Station":   float(m.group(2)),
                    "Easting":   float(parts[1]),
                    "Northing":  float(parts[2]),
                    "Elevation": float(parts[3]),
                    "HorizErr":  float(parts[5]),
                    "VertErr":   float(parts[6]),
                })
            except ValueError:
                continue
    df = pd.DataFrame(rows)
    # Keep last measurement per station (user instruction)
    return df.groupby(["Line", "Station"]).last().reset_index()


# â”€â”€ Field notes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_LINE_HDR   = re.compile(r"line\s+(\d+)\s+grav", re.IGNORECASE)
_STATION_RE = re.compile(r"^\s*(\d+)[.:]\s+(.+)$")

# Ordered by priority: first match wins.
# Tie, end, and start stations all serve the same role in drift correction
# (loop closure reference points), so they share the "tie" label.
# BASE regex uses STA[TI]+ON to tolerate common transposition typos (e.g. BASESTAION).
_TYPE_RULES = [
    ("base", re.compile(r"BASE\s*STA[TI]+ON|BASE\s*AGAIN|^base\b", re.IGNORECASE)),
    ("tie",  re.compile(r"T[EI]+[EI]\s*[/&]?\s*(END\s*)?STA[TI]+ON|TIESTA[TI]+ON|END\s*STA[TI]+ON|ENDSTA[TI]+ON|START\s*POINT", re.IGNORECASE)),
]


def _classify(text):
    # Station type labels always appear before the first period (e.g. "TIE STATION. ...").
    # Restrict matching to that prefix to avoid false positives from incidental mentions
    # like "only the base station follows" later in the note text.
    title = text.split(".")[0].strip() or text
    for label, pat in _TYPE_RULES:
        if pat.search(title):
            return label
    return "regular"


def _parse_notes_file(filepath):
    records = []
    current_line = None
    with open(filepath, encoding="utf-8", errors="replace") as f:
        for raw in f:
            row = raw.rstrip()
            m = _LINE_HDR.search(row)
            if m:
                current_line = float(m.group(1))
                continue
            if current_line is None:
                continue
            m = _STATION_RE.match(row)
            if m:
                text = m.group(2).strip()
                records.append({
                    "Line":        current_line,
                    "Station":     float(m.group(1)),
                    "StationType": _classify(text),
                    "Notes":       text,
                })
    return records


def load_notes():
    records = []
    for f in sorted(NOTES_DIR.glob("GravNotes*.txt")):
        records.extend(_parse_notes_file(f))
    if not records:
        return pd.DataFrame(columns=["Line", "Station", "StationType", "Notes"])
    return pd.DataFrame(records)


# â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main():
    print("Loading CG-5 data â€¦")
    cg5 = load_cg5()
    n_stations = cg5.groupby(["Line", "Station"]).ngroups
    print(f"  {len(cg5)} readings across {n_stations} stations (Lines â‰¥ 2)")

    print("Loading GNSS positions â€¦")
    gnss = load_gnss()
    print(f"  {len(gnss)} positions")

    print("Loading field notes â€¦")
    notes = load_notes()
    print(f"  {len(notes)} annotated stations")

    combined = (
        cg5
        .merge(gnss,  on=["Line", "Station"], how="left")
        .merge(notes, on=["Line", "Station"], how="left")
    )
    combined["StationType"] = combined["StationType"].fillna("regular")
    combined["Line"]    = combined["Line"].astype(int)
    combined["Station"] = combined["Station"].astype(int)
    combined["Dur"]     = combined["Dur"].astype(int)
    combined["Rej"]     = combined["Rej"].astype(int)
    combined = combined.sort_values(["Line", "Station", "Time"]).reset_index(drop=True)

    cols = [
        "Line", "Station",
        "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
        "Grav", "SD", "SE_i",
        "TiltX", "TiltY", "Temp", "Tide", "Dur", "Rej",
        "Time", "Date",
        "StationType", "Notes",
    ]
    combined[cols].to_csv(OUT_FILE, index=False, float_format="%.6f")

    print(f"\nSaved â†’ {OUT_FILE.name}")
    n_no_gnss  = combined.groupby(["Line", "Station"])["Easting"].first().isna().sum()
    n_no_notes = combined.groupby(["Line", "Station"])["Notes"].first().isna().sum()
    type_counts = combined.groupby(["Line", "Station"])["StationType"].first().value_counts()
    print(f"\nCoverage (per station):")
    print(f"  Without GNSS position : {n_no_gnss}")
    print(f"  Without field notes   : {n_no_notes}")
    print(f"  Station types:\n{type_counts.to_string()}")


if __name__ == "__main__":
    main()


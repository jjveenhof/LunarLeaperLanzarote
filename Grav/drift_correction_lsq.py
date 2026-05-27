"""
Least-squares network adjustment for gravimetry drift correction.

Model (supervisor's notes):
    u_i = g_k(i)  +  d_j(i) * (t_i - t0_j)  +  s_j(i)  +  n_i

Unknowns  m = [g_1,...,g_{K-1},  d_1,...,d_J,  s_1,...,s_J]
    g_k : gravity anomaly at location k rel. to base  (K-1 unknowns, g_base=0 datum)
    d_j : linear drift rate for loop j                (J unknowns, mGal/min)
    s_j : static offset for loop j                    (J unknowns, all loops free)

Weighted solution:
    m* = (G^T P^{-1} G)^{-1} G^T P^{-1} u
    C_m = sigma_0^2 * (G^T P^{-1} G)^{-1}
    sigma_0^2 = r^T P^{-1} r / (N - K - 2J + 1)

Physical location grouping:
    - All base stations on a line share one location (the datum).
    - Tie / regular stations within TIE_DISTANCE_M of each other share one location.

Input
-----
    Data/Gravimetry/station_means_{name}.csv

Output
------
    Data/Gravimetry/lsq_corrected_{name}.csv

Usage
-----
    python drift_correction_lsq.py drop5      # specific config
    python drift_correction_lsq.py            # defaults to decay
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.spatial.distance import cdist

BASE       = Path(__file__).resolve().parents[2]
DATA_DIR   = BASE / "Data/Gravimetry"
PROC_DIR   = BASE / "Data/Gravimetry/Processed"
TIE_DIST_M = 3.0     # metres, co-location threshold for tie stations


# -- Loop assignment ------------------------------------------------------------

def assign_loops(group):
    """
    Sort stations by time, identify loops (consecutive base-station pairs with
    inner stations between them), and assign loop_id and t0_min per station.
    Transition base pairs (nothing between them) are skipped.
    """
    group = group.sort_values("datetime").reset_index(drop=True)
    group["t_line_min"] = (
        (group["datetime"] - group["datetime"].iloc[0])
        .dt.total_seconds() / 60
    )
    group["loop_id"] = pd.NA
    group["t0_min"]  = np.nan

    base_idx      = group.index[group["StationType"] == "base"].tolist()
    loop_id       = 0
    extra_rows    = []    # duplicate rows for shared base stations
    prev_end_info = None  # (i_end, loop_id, t0) of the last valid loop

    for i in range(len(base_idx) - 1):
        i_start = base_idx[i]
        i_end   = base_idx[i + 1]
        inner   = [k for k in range(i_start + 1, i_end)
                   if group.loc[k, "StationType"] != "base"]
        if not inner:
            continue

        loop_id += 1
        t0 = group.loc[i_start, "t_line_min"]

        # Shared base: i_start is the same station as the previous loop's i_end.
        # It was already assigned to the previous loop, but now gets overwritten
        # to this loop. Add an extra row so it also closes the previous loop.
        if prev_end_info is not None and prev_end_info[0] == i_start:
            extra = group.loc[i_start].copy()
            extra["loop_id"] = prev_end_info[1]   # earlier loop
            extra["t0_min"]  = prev_end_info[2]   # earlier loop's t0
            extra_rows.append(extra)

        for idx in [i_start] + inner + [i_end]:
            group.loc[idx, "loop_id"] = loop_id
            group.loc[idx, "t0_min"]  = t0

        prev_end_info = (i_end, loop_id, t0)

    if extra_rows:
        group = pd.concat([group, pd.DataFrame(extra_rows)],
                          ignore_index=True)

    return group


# -- Location clustering --------------------------------------------------------

def assign_locations(group):
    """
    Assign a physical location index (loc_id):
      loc_id = 0  -> all base stations (shared; this is the datum)
      loc_id > 0  -> unique physical location, clustered by 2D GNSS distance
    """
    group = group.copy()
    group["loc_id"] = -1

    group.loc[group["StationType"] == "base", "loc_id"] = 0

    non_base = group[group["StationType"] != "base"]
    has_gnss = non_base["Easting"].notna()
    next_id  = 1

    if has_gnss.any():
        gnss   = non_base[has_gnss]
        coords = gnss[["Easting", "Northing"]].values
        D      = cdist(coords, coords)

        # Union-Find connected components
        n      = len(gnss)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for i in range(n):
            for j in range(i + 1, n):
                if D[i, j] <= TIE_DIST_M:
                    union(i, j)

        comp_map = {}
        for i, idx in enumerate(gnss.index):
            c = find(i)
            if c not in comp_map:
                comp_map[c] = next_id
                next_id += 1
            group.loc[idx, "loc_id"] = comp_map[c]

    # Stations without GNSS get their own unique location
    for idx in non_base[~has_gnss].index:
        group.loc[idx, "loc_id"] = next_id
        next_id += 1

    return group


# -- LS system -----------------------------------------------------------------

def build_G(obs, loops, locs, loop_map, loc_map):
    """
    Build the design matrix G and return it together with row and column labels.

    Datum: g_base = 0 (loc_id=0 fixed, not an unknown).
    All other g_k are gravity anomalies relative to the base station.

    Columns: [g_loc1, ..., g_loc{K-1},  d_loop1, ..., d_loopJ,  s_loop1, ..., s_loopJ]
    Rows:    one per observation in obs (already reset_index'd).
    """
    J      = len(loops)
    locs_free = [l for l in locs if l != 0]   # base excluded from unknowns
    K_free = len(locs_free)
    loc_map_free = {l: i for i, l in enumerate(locs_free)}
    N      = len(obs)
    n_unk  = K_free + J + J               # same total as before: (K-1) + J + J = K+2J-1

    G = np.zeros((N, n_unk))

    for i, row in obs.iterrows():
        j  = loop_map[row["loop_id"]]
        dt = row["t_line_min"] - row["t0_min"]
        if row["loc_id"] != 0:             # base is fixed to 0, no g column
            k = loc_map_free[row["loc_id"]]
            G[i, k] = 1.0                  # g_k (anomaly)
        G[i, K_free + j]     = dt          # d_j  (mGal/min)
        G[i, K_free + J + j] = 1.0        # s_j  (all loops free)

    col_labels = (
        [f"g_loc{int(l)}" for l in locs_free] +
        [f"d_loop{l}" for l in loops] +
        [f"s_loop{l}" for l in loops]
    )
    row_labels = [
        f"S{int(r['Station'])} {r['StationType'][0].upper()} L{int(r['loop_id'])}"
        for _, r in obs.iterrows()
    ]

    return G, col_labels, row_labels


def solve_line(group):
    """
    Build and solve the weighted LS system for one line.
    Returns (result_df, loop_df, sigma_0) or (None, None, None) on failure.
    """
    obs = group[group["loop_id"].notna()].copy().reset_index(drop=True)
    if obs.empty:
        return None, None, None

    obs["loop_id"] = obs["loop_id"].astype(int)

    loops    = sorted(obs["loop_id"].unique())
    locs     = sorted(obs["loc_id"].unique())
    loop_map = {l: i for i, l in enumerate(loops)}
    loc_map  = {l: i for i, l in enumerate(locs)}

    J      = len(loops)
    locs_free = [l for l in locs if l != 0]
    K_free = len(locs_free)
    loc_map_free = {l: i for i, l in enumerate(locs_free)}
    N      = len(obs)
    n_unk  = K_free + J + J

    G, _, _ = build_G(obs, loops, locs, loop_map, loc_map)
    u_vec   = obs["Grav_est"].values
    sigma   = obs["SE_est"].values

    W     = np.diag(1.0 / sigma**2)
    GtW   = G.T @ W
    N_mat = GtW @ G
    rhs   = GtW @ u_vec

    try:
        cond = np.linalg.cond(N_mat)
        if cond > 1e12:
            print(f"    WARNING: poorly conditioned normal matrix (cond = {cond:.1e})")
        N_inv  = np.linalg.inv(N_mat)
        m_star = N_inv @ rhs
    except np.linalg.LinAlgError:
        print("    ERROR: singular normal matrix")
        return None, None, None

    residuals  = u_vec - G @ m_star
    dof        = N - n_unk
    sigma_0_sq = float((residuals @ W @ residuals) / dof) if dof > 0 else 1.0
    C_m        = sigma_0_sq * N_inv
    se_m       = np.sqrt(np.diag(C_m))

    g_vals = m_star[:K_free];          se_g  = se_m[:K_free]
    d_vals = m_star[K_free:K_free+J];  se_d  = se_m[K_free:K_free+J]
    s_vals = m_star[K_free+J:];        se_s  = se_m[K_free+J:]

    # Results per station; base station (loc_id=0) gets anomaly=0 by datum definition
    result_rows = []
    for i, row in obs.iterrows():
        loc_id = int(row["loc_id"])
        if loc_id == 0:
            g_lsq  = 0.0
            se_lsq = 0.0
        else:
            k      = loc_map_free[loc_id]
            g_lsq  = g_vals[k]
            se_lsq = se_g[k]
        result_rows.append({
            "Line":        int(row["Line"]),
            "Station":     int(row["Station"]),
            "Easting":     row["Easting"],
            "Northing":    row["Northing"],
            "Elevation":   row["Elevation"],
            "HorizErr":    row["HorizErr"],
            "VertErr":     row["VertErr"],
            "Grav_est":    row["Grav_est"],
            "SE_est":      row["SE_est"],
            "Grav_lsq":    g_lsq,
            "SE_lsq":      se_lsq,
            "loc_id":      loc_id,
            "loop_id":     int(row["loop_id"]),
            "residual":    residuals[i],
            "Date":        row["Date"],
            "Time_first":  row["Time_first"],
            "StationType": row["StationType"],
            "Notes":       row["Notes"],
        })

    # Loop parameters
    loop_rows = []
    for j, loop_id in enumerate(loops):
        loop_rows.append({
            "Line":               int(obs["Line"].iloc[0]),
            "loop_id":            loop_id,
            "drift_mGal_h":       d_vals[j] * 60,
            "SE_drift_mGal_h":    se_d[j] * 60,
            "offset_microGal":    s_vals[j] * 1000,
            "SE_offset_microGal": se_s[j] * 1000,
        })

    return pd.DataFrame(result_rows), pd.DataFrame(loop_rows), float(np.sqrt(sigma_0_sq))


# -- Main ----------------------------------------------------------------------

def main(config_name="decay"):
    in_file  = PROC_DIR / f"station_means_{config_name}.csv"
    out_file = PROC_DIR / f"lsq_corrected_{config_name}.csv"

    print(f"Config: {config_name}")
    print(f"Reading {in_file.name} ...")
    df = pd.read_csv(in_file, dtype={"Time_first": str, "Date": str})
    df["datetime"] = pd.to_datetime(
        df["Date"] + " " + df["Time_first"], format="%Y/%m/%d %H:%M:%S"
    )
    print(f"  {len(df)} stations across Lines {sorted(df['Line'].unique())}")

    all_results, all_loops = [], []

    for line, group in df.groupby("Line"):
        print(f"\nLine {line}:")
        group = assign_loops(group.copy())
        group = assign_locations(group)

        K    = int(group["loc_id"].nunique())
        J    = int(group["loop_id"].dropna().max()) if group["loop_id"].notna().any() else 0
        N    = int(group["loop_id"].notna().sum())
        over = N > K + 2 * J - 1
        print(f"  K={K} locations, J={J} loops, N={N} obs  "
              f"({'over-determined' if over else 'UNDER-DETERMINED'}, "
              f"need N > {K + 2*J - 1})")

        result_df, loop_df, sigma_0 = solve_line(group)
        if result_df is None:
            continue

        print(f"  sigma_0 = {sigma_0:.4f}  (dimensionless; 1 = model fits within SE_est)")
        print(f"  {'Loop':>4}  {'drift (mGal/h)':>16}  {'offset (microGal)':>14}")
        for _, lr in loop_df.iterrows():
            print(f"  {int(lr['loop_id']):>4}  {lr['drift_mGal_h']:>+16.4f}  "
                  f"{lr['offset_microGal']:>+14.3f}")

        all_results.append(result_df)
        all_loops.append(loop_df)

    if not all_results:
        print("No results.")
        return

    result = (pd.concat(all_results)
                .sort_values(["Line", "Station"])
                .reset_index(drop=True))
    result.to_csv(out_file, index=False, float_format="%.6f")
    print(f"\nSaved -> {out_file.name}")

    # Consistency check: residuals at co-located stations
    print("\nResiduals at co-located stations:")
    counts = (result.groupby(["Line", "loc_id"])
                    .size()
                    .reset_index(name="n")
                    .query("n > 1"))
    for _, row in counts.iterrows():
        grp = result[(result["Line"] == row["Line"]) &
                     (result["loc_id"] == row["loc_id"])]
        labels = ", ".join(
            f"S{r['Station']}({r['StationType'][0]})" for _, r in grp.iterrows()
        )
        res_microGal = grp["residual"].abs() * 1000
        print(f"  Line {int(row['Line'])} loc {int(row['loc_id'])}: "
              f"{labels}  |resid| = "
              f"{', '.join(f'{v:.2f}' for v in res_microGal)} microGal")


if __name__ == "__main__":
    config = sys.argv[1] if len(sys.argv) > 1 else "decay"
    main(config)


"""
Statistical inspection of the LSQ drift adjustment.

Produces two figures per Line:

  1. Statistics sheet
       - sigma_0 and degrees of freedom
       - SE_lsq per location (bar chart)
       - Normalised residuals histogram  r_i / SE_est_i
       - Correlation matrix of all unknowns (heatmap)

  2. Base-station timeline
       - Raw Grav_est vs absolute time, coloured by loop
       - LSQ estimate g_base +/- SE_lsq as horizontal band
       - Drift-corrected individual measurements (g_base + residual)
       - Vertical lines at loop boundaries

Usage
-----
    python inspect_lsq.py                             # default: drop5
    python inspect_lsq.py decay
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.colors as mcolors
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drift_correction_lsq import (
    assign_loops, assign_locations, build_G, PROC_DIR
)

BASE    = Path(__file__).resolve().parents[3]
SAVE_DIR = BASE / "Analysis/Grav"
LOOP_CMAP = plt.cm.tab10


# -- Re-run LS to get covariance -----------------------------------------------

def solve_with_cov(group):
    """Return solution + full covariance matrix + normalised residuals."""
    obs = group[group["loop_id"].notna()].copy().reset_index(drop=True)
    obs["loop_id"] = obs["loop_id"].astype(int)

    loops    = sorted(obs["loop_id"].unique())
    locs     = sorted(obs["loc_id"].unique())
    loop_map = {l: i for i, l in enumerate(loops)}
    loc_map  = {l: i for i, l in enumerate(locs)}

    J, K = len(loops), len(locs)
    G, col_labels, row_labels = build_G(obs, loops, locs, loop_map, loc_map)

    u_vec = obs["Grav_est"].values
    sigma = obs["SE_est"].values
    W     = np.diag(1.0 / sigma**2)
    GtW   = G.T @ W
    N_mat = GtW @ G
    rhs   = GtW @ u_vec

    try:
        N_inv  = np.linalg.inv(N_mat)
        m_star = N_inv @ rhs
    except np.linalg.LinAlgError:
        return None

    residuals    = u_vec - G @ m_star
    dof          = len(obs) - G.shape[1]
    sigma_0_sq   = float((residuals @ W @ residuals) / dof) if dof > 0 else 1.0
    C_m          = sigma_0_sq * N_inv
    norm_resid   = residuals / sigma          # r_i / SE_est_i

    # Correlation matrix
    se_m   = np.sqrt(np.diag(C_m))
    corr_m = C_m / np.outer(se_m, se_m)
    corr_m = np.clip(corr_m, -1, 1)

    return {
        "obs": obs, "G": G, "m_star": m_star,
        "C_m": C_m, "corr_m": corr_m,
        "residuals": residuals, "norm_resid": norm_resid,
        "sigma_0": float(np.sqrt(sigma_0_sq)), "dof": dof,
        "loops": loops, "locs": locs, "loop_map": loop_map, "loc_map": loc_map,
        "K": K, "J": J, "col_labels": col_labels, "row_labels": row_labels,
    }


# -- Figure 1: Statistics sheet ------------------------------------------------

def plot_stats(line_id, res, config_name):
    obs        = res["obs"]
    corr_m     = res["corr_m"]
    norm_resid = res["norm_resid"]
    K, J       = res["K"], res["J"]

    fig = plt.figure(figsize=(22, 5.5))
    fig.suptitle(f"LSQ statistics -- Line {line_id}  [{config_name}]   "
                 f"$\\sigma_0$ = {res['sigma_0']:.3f}  (dof = {res['dof']})",
                 fontsize=12, fontweight="bold")

    gs = fig.add_gridspec(1, 3, wspace=0.35, width_ratios=[1, 1, 1])
    ax_se   = fig.add_subplot(gs[0, 0])
    ax_hist = fig.add_subplot(gs[0, 1])
    ax_corr = fig.add_subplot(gs[0, 2])

    # -- SE_lsq per location ---------------------------------------------------
    se_g = np.sqrt(np.diag(res["C_m"]))[:K] * 1000   # microGal
    locs = res["locs"]
    # Annotate base and tie locations
    obs       = res["obs"]
    loc_sizes = obs.groupby("loc_id")["loc_id"].transform("count")
    tie_locs  = set(obs[loc_sizes > 1]["loc_id"].unique()) - {0}

    loc_labels = [
        f"loc{int(l)}" + (" (base)" if l == 0 else " (tie)" if l in tie_locs else "")
        for l in locs
    ]
    colors = ["dimgrey" if l == 0 else "steelblue" for l in locs]
    ax_se.bar(range(K), se_g, color=colors)
    ax_se.set_xticks(range(K))
    ax_se.set_xticklabels(loc_labels, rotation=45, ha="right", fontsize=7)
    ax_se.set_ylabel(r"SE$_\mathrm{lsq}$ ($\mu$Gal)")
    ax_se.set_title("Formal uncertainty per location")
    ax_se.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))

    # -- Normalised residuals -- co-located stations only -----------------------
    # Unique-location stations always have residual ~= 0 by construction (the LS
    # fits them exactly), so only co-located stations carry meaningful residuals.
    obs = res["obs"]
    loc_counts = obs.groupby("loc_id")["loc_id"].transform("count")
    coloc_mask = loc_counts > 1
    nr_coloc   = norm_resid[coloc_mask.values]
    nr_all     = norm_resid

    ax_hist.hist(nr_coloc, bins=12, color="steelblue", edgecolor="white",
                 alpha=0.8, density=True, label=f"Co-located (n={coloc_mask.sum()})")
    ax_hist.hist(nr_all,   bins=12, color="lightgrey", edgecolor="white",
                 alpha=0.4, density=True, label=f"All (n={len(nr_all)})")
    ax_hist.axvline(0, color="k", linewidth=0.8, linestyle="--")
    ax_hist.set_xlabel("r_i / SE_est_i")
    ax_hist.set_ylabel("Density")
    ax_hist.set_title("Normalised residuals\n(co-located stations = filled; all = grey)")
    ax_hist.legend(fontsize=7)

    # -- Correlation matrix ----------------------------------------------------
    n_unk = corr_m.shape[0]
    im = ax_corr.imshow(corr_m, cmap="RdBu_r", vmin=-1, vmax=1,
                        aspect="equal", interpolation="none")
    ax_corr.axvline(K - 0.5, color="k", linewidth=1.2)
    ax_corr.axvline(K + J - 0.5, color="k", linewidth=1.2)
    ax_corr.axhline(K - 0.5, color="k", linewidth=1.2)
    ax_corr.axhline(K + J - 0.5, color="k", linewidth=1.2)
    labels = res["col_labels"]
    ax_corr.set_xticks(range(n_unk))
    ax_corr.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    ax_corr.set_yticks(range(n_unk))
    ax_corr.set_yticklabels(labels, fontsize=7)
    ax_corr.set_title("Correlation matrix of all unknowns  "
                      "(g_k | d_j | s_j,  separated by black lines)")
    plt.colorbar(im, ax=ax_corr, fraction=0.015, label="Correlation")

    return fig


# -- Figure 2: Base-station timeline -------------------------------------------

def plot_base_timeline(line_id, res, lsq_df, config_name):
    obs      = res["obs"]
    loops    = res["loops"]
    loop_map = res["loop_map"]

    base_obs = obs[obs["StationType"] == "base"].copy()
    if base_obs.empty:
        return None

    g_base  = 0.0    # base station is the datum (g_base = 0 by definition)
    se_base = 0.0

    # Absolute time in hours from first measurement of the line
    t0  = obs["datetime"].min() if "datetime" in obs.columns else None
    if t0 is None:
        return None
    base_obs["t_h"] = (base_obs["datetime"] - t0).dt.total_seconds() / 3600

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle(f"Base station measurements -- Line {line_id}  [{config_name}]",
                 fontsize=12, fontweight="bold")

    # Loop boundary lines
    for loop_id in loops:
        loop_data = base_obs[base_obs["loop_id"] == loop_id]
        if loop_data.empty:
            continue
        t_start = loop_data["t_h"].min()
        ax.axvline(t_start, color="grey", linewidth=0.8,
                   linestyle="--", alpha=0.6)

    # Raw measurements coloured by loop
    for _, row in base_obs.iterrows():
        j     = loop_map.get(row["loop_id"], 0) if pd.notna(row["loop_id"]) else 0
        color = LOOP_CMAP(int(j) % 10)
        ax.errorbar(row["t_h"], row["Grav_est"], yerr=row["SE_est"],
                    fmt="o", color=color, markersize=6,
                    capsize=3, elinewidth=0.8, zorder=3)

    # LSQ estimate +/- SE as horizontal band
    ax.axhline(g_base, color="black", linewidth=1.5, label=f"g_base = {g_base:.4f} mGal")
    ax.axhspan(g_base - se_base, g_base + se_base,
               alpha=0.15, color="black", label=f"$\\pm$ SE$_{{lsq}}$ = {se_base*1000:.2f} $\\mu$Gal")

    # Drift-corrected measurements (g_base + residual)
    base_idx = [i for i, row in obs.iterrows() if row["StationType"] == "base"]
    for idx in base_idx:
        row   = obs.loc[idx]
        j     = loop_map.get(row["loop_id"], 0) if pd.notna(row["loop_id"]) else 0
        color = LOOP_CMAP(int(j) % 10)
        t_h   = (row["datetime"] - t0).total_seconds() / 3600
        g_c   = res["m_star"][0] + (res["residuals"][idx] if idx < len(res["residuals"]) else 0)
        ax.plot(t_h, g_c, "x", color=color,
                markersize=8, markeredgewidth=1.8, zorder=4)

    # Loop colour legend
    loop_patches = [
        plt.Line2D([0], [0], marker="o", color=LOOP_CMAP(loop_map[l] % 10),
                   linestyle="None", markersize=6, label=f"Loop {int(l)}")
        for l in loops
    ]
    symbol_patches = [
        plt.Line2D([0], [0], marker="o", color="grey", linestyle="None",
                   markersize=6, label="Raw Grav_est +/- SE_est"),
        plt.Line2D([0], [0], marker="x", color="grey", linestyle="None",
                   markersize=8, markeredgewidth=1.8, label="Drift-corrected"),
    ]
    ax.legend(handles=symbol_patches + loop_patches, fontsize=8, ncol=3)

    ax.set_xlabel("Time since first measurement (hours)")
    ax.set_ylabel("Gravity anomaly (mGal)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.4f"))
    ax.grid(True, alpha=0.25, linestyle="--")

    return fig


# -- Main ----------------------------------------------------------------------

def main(config_name=None):
    if config_name is None:
        config_name = sys.argv[1] if len(sys.argv) > 1 else "decay"

    in_file  = PROC_DIR / f"station_means_{config_name}.csv"
    lsq_file = PROC_DIR / f"lsq_corrected_{config_name}.csv"

    print(f"Config: {config_name}")
    df = pd.read_csv(in_file, dtype={"Time_first": str, "Date": str})
    df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time_first"],
                                    format="%Y/%m/%d %H:%M:%S")
    lsq_df = pd.read_csv(lsq_file)

    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    for line_id, group in df.groupby("Line"):
        print(f"\nLine {line_id}:")
        group = assign_loops(group.copy())
        group = assign_locations(group)
        group["datetime"] = group["datetime"]  # keep datetime

        res = solve_with_cov(group)
        if res is None:
            print("  LS failed, skipping.")
            continue

        print(f"  sigma0 = {res['sigma_0']:.4f}  (dof = {res['dof']})")

        # Figure 1: stats sheet
        fig1 = plot_stats(line_id, res, config_name)
        p1   = SAVE_DIR / f"lsq_stats_{config_name}_line{line_id}.png"
        fig1.savefig(p1, dpi=150, bbox_inches="tight")
        print(f"  Saved -> {p1.name}")

        # Figure 2: base station timeline (need datetime in obs)
        obs = res["obs"]
        obs["datetime"] = group.set_index(
            group.index[:len(obs)]
        )["datetime"].values[:len(obs)]
        # Simpler: re-attach datetime by matching station
        obs = obs.merge(
            group[["Station", "datetime"]].drop_duplicates("Station"),
            on="Station", how="left"
        )
        res["obs"] = obs

        fig2 = plot_base_timeline(line_id, res, lsq_df, config_name)
        if fig2 is not None:
            p2 = SAVE_DIR / f"lsq_base_{config_name}_line{line_id}.png"
            fig2.savefig(p2, dpi=150, bbox_inches="tight")
            print(f"  Saved -> {p2.name}")

    plt.show()


if __name__ == "__main__":
    main()


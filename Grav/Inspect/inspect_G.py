"""Visualise the G (design) matrix for each line using the exact build_G from drift_correction_lsq."""
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drift_correction_lsq import assign_loops, assign_locations, build_G

BASE = Path(__file__).resolve().parents[3]
df   = pd.read_csv(BASE / "Data/Gravimetry/Processed/station_means_drop5.csv",
                   dtype={"Time_first": str, "Date": str})
df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time_first"],
                                format="%Y/%m/%d %H:%M:%S")

for line_id, df_line in df.groupby("Line"):
    grp = assign_loops(df_line.copy())
    grp = assign_locations(grp)

    obs = grp[grp["loop_id"].notna()].copy().reset_index(drop=True)
    obs["loop_id"] = obs["loop_id"].astype(int)

    loops    = sorted(obs["loop_id"].unique())
    locs     = sorted(obs["loc_id"].unique())
    loop_map = {l: i for i, l in enumerate(loops)}
    loc_map  = {l: i for i, l in enumerate(locs)}

    G, col_labels, row_labels = build_G(obs, loops, locs, loop_map, loc_map)

    J, K, N, n_unk = len(loops), len(locs), len(obs), G.shape[1]

    fig, ax = plt.subplots(figsize=(max(10, n_unk * 0.6), max(8, N * 0.38)))

    vmax = max(abs(G).max(), 1.0)
    im   = ax.imshow(G, aspect="auto", cmap="RdBu_r",
                     vmin=-vmax, vmax=vmax, interpolation="none")

    for r in range(N):
        for c in range(n_unk):
            v = G[r, c]
            if abs(v) > 1e-10:
                ax.text(c, r, f"{v:.1f}", ha="center", va="center",
                        fontsize=6.5,
                        color="white" if abs(v) > 0.5 * vmax else "black")

    # Vertical separators between g / d / s blocks
    ax.axvline(K - 0.5,     color="k", linewidth=1.5)
    ax.axvline(K + J - 0.5, color="k", linewidth=1.5)

    ax.set_xticks(range(n_unk))
    ax.set_xticklabels(col_labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(N))
    ax.set_yticklabels(row_labels, fontsize=8)

    # Block labels above
    ax.text((K - 1) / 2,        -1.2, "g_k  (locations)", ha="center", fontsize=9, style="italic")
    ax.text(K + (J - 1) / 2,    -1.2, "d_j  (drift)",     ha="center", fontsize=9, style="italic")
    if J > 1:
        ax.text(K + J + (J - 2) / 2, -1.2, "s_j  (offset)", ha="center", fontsize=9, style="italic")

    plt.colorbar(im, ax=ax, fraction=0.02, label="Entry value")
    ax.set_title(
        f"Design matrix G  --  Line {line_id}   "
        f"(K={K} locs, J={J} loops, N={N} obs, dof={N - n_unk})",
        fontsize=11
    )
    plt.tight_layout()
    save_dir = BASE / "Analysis/Grav"
    save_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_dir / f"G_matrix_line{line_id}.png", dpi=150, bbox_inches="tight")
    print(f"Saved -> G_matrix_line{line_id}.png")

plt.show()


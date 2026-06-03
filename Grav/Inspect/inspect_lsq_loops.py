"""
Inspect LSQ drift and offset parameters per loop, one figure per line.

Two panels per line:
  Left  -- Drift rate (microGal/h) per loop, with heuristic limits at +/-60 microGal/h
  Right -- Loop offset relative to loop 1 (microGal), showing inter-loop jumps

Offsets are shown relative to loop 1 because in the anomaly formulation all
s_j absorb the absolute gravity level (~5400 mGal), making absolute values
uninformative. The relative offsets show instrumental jumps between loops.

Input
-----
    Data/Gravimetry/Processed/lsq_loops_{config}.csv

Usage
-----
    python inspect_lsq_loops.py          # default: decay
    python inspect_lsq_loops.py drop5
"""

import sys
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE     = Path(__file__).resolve().parents[3]
PROC_DIR = BASE / "Data/Gravimetry/Processed"
SAVE_DIR = BASE / "Results/Grav/LSQ/Stats"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

DRIFT_LIMIT = 60   # microGal/h -- heuristic upper bound on acceptable drift

config = sys.argv[1] if len(sys.argv) > 1 else "decay"
df = pd.read_csv(PROC_DIR / f"lsq_loops_{config}.csv")

for line_id, ldf in df.groupby("Line"):
    ldf     = ldf.sort_values("loop_id").reset_index(drop=True)
    loops   = ldf["loop_id"].tolist()
    n_loops = len(loops)
    x       = np.arange(n_loops)

    # Relative offsets: subtract loop 1; propagate SE in quadrature
    s0        = ldf["offset_microGal"].iloc[0]
    se_s0     = ldf["SE_offset_microGal"].iloc[0]
    s_rel     = ldf["offset_microGal"] - s0
    se_s_rel  = np.sqrt(ldf["SE_offset_microGal"]**2 + se_s0**2)
    se_s_rel.iloc[0] = 0.0   # loop 1 is the reference, no uncertainty

    # Drift in microGal/h
    d_uGal    = ldf["drift_mGal_h"] * 1000
    se_d_uGal = ldf["SE_drift_mGal_h"] * 1000

    fig, (ax_d, ax_s) = plt.subplots(1, 2, figsize=(10, 4))
    fig.suptitle(f"LSQ loop parameters -- Line {line_id}  [{config}]",
                 fontsize=11, fontweight="bold")

    # -- Drift rate ------------------------------------------------------------
    ax_d.bar(x, d_uGal, color="steelblue", zorder=3)
    ax_d.errorbar(x, d_uGal, yerr=se_d_uGal,
                  fmt="none", color="black", capsize=4, elinewidth=1.0, zorder=4)
    ax_d.axhline(0,            color="black", linewidth=0.8, linestyle="--", zorder=2)
    ax_d.axhline( DRIFT_LIMIT, color="red",   linewidth=1.0, linestyle="--",
                  alpha=0.7, zorder=2, label=f"+/-{DRIFT_LIMIT} $\\mu$Gal/h limit")
    ax_d.axhline(-DRIFT_LIMIT, color="red",   linewidth=1.0, linestyle="--",
                  alpha=0.7, zorder=2)
    ax_d.set_xticks(x)
    ax_d.set_xticklabels([f"Loop {int(l)}" for l in loops])
    ax_d.set_ylabel(r"Drift rate ($\mu$Gal/h)")
    ax_d.set_title("Drift rate per loop")
    ax_d.grid(True, alpha=0.25, linestyle="--", axis="y")
    ax_d.legend(fontsize=7)

    # -- Relative offset -------------------------------------------------------
    ax_s.bar(x, s_rel, color="steelblue", zorder=3)
    ax_s.errorbar(x, s_rel, yerr=se_s_rel,
                  fmt="none", color="black", capsize=4, elinewidth=1.0, zorder=4)
    ax_s.axhline(0, color="black", linewidth=0.8, linestyle="--", zorder=2)
    ax_s.set_xticks(x)
    ax_s.set_xticklabels([f"Loop {int(l)}" for l in loops])
    ax_s.set_ylabel(r"Offset relative to Loop 1 ($\mu$Gal)")
    ax_s.set_title("Loop offset  (relative to Loop 1)")
    ax_s.grid(True, alpha=0.25, linestyle="--", axis="y")

    plt.tight_layout()
    save_path = SAVE_DIR / f"lsq_loops_{config}_line{line_id}.png"
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Saved -> {save_path.name}")

plt.show()

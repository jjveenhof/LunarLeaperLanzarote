"""
Combined profile plot anchored at P4 (Line 4, loc_id=4).

Three profiles, all plotted left-to-right from P4 (distance = 0):
  NE arm  -- Line 4, loc_ids 4->5->6->7->8    perpendicular to the cave
  NW arm  -- Line 4, loc_ids 4->3->2->1,      along the cave to the NW
               with Line 3 loc_id 15 (P15) inserted between loc_ids 4 and 3
  L3 sub  -- Line 3, loc_ids 15->25           north, ~45 deg from cave

P15 (Line 3, loc_id=15) is the shared point: physically between P4 (~13.5 m)
and P3 (~8.6 m, actual GNSS distances). It is included both as a point on the
NW arm and as the anchor of the L3 subset.

Both lines share the same base station location, so their LSQ anomalies are
directly comparable with no datum correction required.

A sanity check prints the deviation of P15 from a distance-weighted linear
interpolation between P4 and P3 (Line 4 values).
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

BASE     = Path(__file__).resolve().parents[2]
PROC_DIR = BASE / "Data/Gravimetry/Processed"

# If a rho value is passed (e.g. --rho 2.5), use Bouguer file; otherwise use LSQ
rho_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--rho"), None)
if rho_arg is not None:
    rho     = float(rho_arg)
    rho_str = f"{rho:.1f}".replace(".", "p")
    IN_FILE  = PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str}.csv"
    G_COL    = "SBA"
    SE_COL   = "SE_CBA"
    YLABEL   = f"Simple Bouguer Anomaly (mGal)  [rho = {rho} g/cm3]"
    SAVE_DIR = BASE / "Results/Grav/Bouguer"
    FILESTEM = f"line4_combined_SBA_rho{rho_str}"
else:
    IN_FILE  = PROC_DIR / "lsq_corrected_decay.csv"
    G_COL    = "Grav_lsq"
    SE_COL   = "SE_lsq"
    YLABEL   = "Gravity anomaly (mGal)"
    SAVE_DIR = BASE / "Results/Grav/LSQ/Lines"
    FILESTEM = "line4_combined"

SAVE_DIR.mkdir(parents=True, exist_ok=True)

# -- Configuration (loc_ids) ---------------------------------------------------
L4_NE  = [4, 5, 6, 7, 8]    # Line 4 NE arm in order from P4
L4_NW  = [4, 3, 2, 1]       # Line 4 NW arm in order from P4 (P15 inserted below)
L3_P15 = 15                  # loc_id of P15 in Line 3
L3_SUB = list(range(15, 26)) # Line 3 subset loc_ids (P15 to end)

# -- Load data -----------------------------------------------------------------
df = pd.read_csv(IN_FILE, dtype={"Date": str})

def get_locs(line, loc_ids):
    """Return one row per loc_id (sorted by loc_ids order) for a given line."""
    sub = (df[(df["Line"] == line) & (df["loc_id"].isin(loc_ids))]
           .drop_duplicates("loc_id")
           .set_index("loc_id"))
    return sub.loc[[l for l in loc_ids if l in sub.index]]

l4_ne  = get_locs(4, L4_NE)
l4_nw  = get_locs(4, L4_NW)
l3_p15 = get_locs(3, [L3_P15])
l3_sub = get_locs(3, L3_SUB)

# -- Cumulative distance from P4 -----------------------------------------------
def cumulative_dist(coords):
    """Cumulative Euclidean distance along a sequence of (E, N) coords."""
    dists = [0.0]
    for i in range(1, len(coords)):
        d = np.hypot(coords[i, 0] - coords[i-1, 0],
                     coords[i, 1] - coords[i-1, 1])
        dists.append(dists[-1] + d)
    return np.array(dists)

p4_coords = l4_ne.loc[4, ["Easting", "Northing"]].values

# NE arm: P4 at 0
ne_coords = l4_ne[["Easting", "Northing"]].values
ne_dists  = cumulative_dist(ne_coords)

# NW arm: P4, then P15, then P3, P2, P1
# Insert P15 (Line 3) between P4 and P3
nw_seq_locs = [4]      # from Line 4
nw_seq_src  = ["l4"]
nw_seq_locs.append(L3_P15); nw_seq_src.append("l3")
for l in [3, 2, 1]:
    nw_seq_locs.append(l); nw_seq_src.append("l4")

nw_coords = np.array([
    (l3_p15 if src == "l3" else l4_nw).loc[loc, ["Easting", "Northing"]].values
    for loc, src in zip(nw_seq_locs, nw_seq_src)
])
nw_dists = cumulative_dist(nw_coords)

nw_g   = np.array([
    (l3_p15 if src == "l3" else l4_nw).loc[loc, G_COL]
    for loc, src in zip(nw_seq_locs, nw_seq_src)
])
nw_se  = np.array([
    (l3_p15 if src == "l3" else l4_nw).loc[loc, SE_COL]
    for loc, src in zip(nw_seq_locs, nw_seq_src)
])

# L3 subset: starts at P15, offset by P4->P15 distance
p15_dist = np.hypot(
    l3_p15.loc[L3_P15, "Easting"]  - p4_coords[0],
    l3_p15.loc[L3_P15, "Northing"] - p4_coords[1]
)
l3_coords = l3_sub[["Easting", "Northing"]].values
l3_dists  = p15_dist + cumulative_dist(l3_coords)

# -- Sanity check: P15 vs. linear interpolation between P4 and P3 --------------
g_p4  = l4_ne.loc[4,  G_COL]
g_p3  = l4_nw.loc[3,  G_COL]
g_p15 = l3_p15.loc[L3_P15, G_COL]

d_p4_p15 = np.hypot(l3_p15.loc[L3_P15,"Easting"]  - l4_ne.loc[4,"Easting"],
                    l3_p15.loc[L3_P15,"Northing"] - l4_ne.loc[4,"Northing"])
d_p3_p15 = np.hypot(l3_p15.loc[L3_P15,"Easting"]  - l4_nw.loc[3,"Easting"],
                    l3_p15.loc[L3_P15,"Northing"] - l4_nw.loc[3,"Northing"])
d_total  = d_p4_p15 + d_p3_p15
g_interp = g_p4 * (d_p3_p15 / d_total) + g_p3 * (d_p4_p15 / d_total)
delta    = g_p15 - g_interp
print(f"Sanity check at P15:")
print(f"  P4 g_lsq  = {g_p4:+.4f}  SE = {l4_ne.loc[4,'SE_lsq']*1000:.1f} uGal")
print(f"  P3 g_lsq  = {g_p3:+.4f}  SE = {l4_nw.loc[3,'SE_lsq']*1000:.1f} uGal")
print(f"  P15 g_lsq = {g_p15:+.4f}  SE = {l3_p15.loc[L3_P15,'SE_lsq']*1000:.1f} uGal")
print(f"  Interpolated at P15 position = {g_interp:+.4f} mGal")
print(f"  Residual (P15 - interpolated) = {delta*1000:+.1f} uGal")

# -- Plot ----------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(13, 5))

ax.errorbar(ne_dists, l4_ne[G_COL], yerr=l4_ne[SE_COL],
            fmt="o-", color="steelblue", capsize=3, linewidth=1.5, markersize=6,
            label="L4 NE arm  (perp. to cave)")

ax.errorbar(nw_dists, nw_g, yerr=nw_se,
            fmt="o-", color="darkorange", capsize=3, linewidth=1.5, markersize=6,
            label="L4 NW arm  (along cave)  -- P15 from L3 inserted")

ax.errorbar(l3_dists, l3_sub[G_COL], yerr=l3_sub[SE_COL],
            fmt="o-", color="seagreen", capsize=3, linewidth=1.5, markersize=6,
            label="L3 subset  (N, ~45 deg from cave)")

# Mark P4 and P15
ax.axvline(0,         color="k",    linewidth=0.9, linestyle="--", alpha=0.6)
ax.axvline(p15_dist,  color="grey", linewidth=0.9, linestyle=":",  alpha=0.7)

ymax = ax.get_ylim()[1]
ax.text(0,        ymax, "P4",  ha="center", va="bottom", fontsize=8, fontweight="bold")
ax.text(p15_dist, ymax, "P15", ha="center", va="bottom", fontsize=8, color="grey")

ax.set_xlabel("Distance from P4 (m)")
ax.set_ylabel(YLABEL)
ax.set_title("Cave signature comparison -- Lines 3 and 4", fontweight="bold", fontsize=12)
ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
ax.grid(True, alpha=0.25, linestyle="--")
ax.legend(fontsize=9)

plt.tight_layout()
save_path = SAVE_DIR / f"{FILESTEM}.png"
fig.savefig(save_path, dpi=150, bbox_inches="tight")
print(f"\nSaved -> {save_path.name}")
plt.show()

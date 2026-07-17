"""
Two candidate residual / diagnostic plots for the network-adjustment section.
Generate BOTH so the user can pick the more intuitive one for the thesis.

  Style A -- Closure residuals at co-located stations.
      For every physical location occupied more than once, plot the adjusted
      residual r_i of each occupation. A perfectly drift-corrected survey would
      give identical gravity at repeat visits, so scatter here = network
      closure. One panel per line.

  Style B -- All residuals vs station, with the +/- SE_est band.
      Signed r_i for every observation with its input SE as an error bar and a
      zero line. If the model is adequate the points scatter around zero within
      their errors; outliers (e.g. L5 S28) stick out. One panel per line.

Residuals are in mGal.

Usage:  python Inspect/inspect_lsq_residuals.py [config]   # default decay
Out:    Results/Grav/LSQ/lsq_residuals_closure_{config}.png
        Results/Grav/LSQ/lsq_residuals_perstation_{config}.png
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drift_correction_lsq import assign_loops, assign_locations, PROC_DIR
from inspect_lsq import solve_with_cov
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # Code/ for plot_utils
from plot_utils import save_figure

BASE     = Path(__file__).resolve().parents[3]
SAVE_DIR = BASE / "Results/Grav/LSQ"
LINES    = [2, 3, 4, 5]

# Author the hybrid figure at the width it occupies on the page so text renders at
# the thesis size (\includegraphics[width=\linewidth] scales the whole figure by
# L/W; thesis \linewidth = 6.1 in). LARGER W -> text shrinks on the page.
HYB_W_IN, HYB_H_IN = 6.1, 5.4
JITTER = 0.15   # half-width of horizontal spread for repeats within a group

# marker colour by station role (matches the other grav plots' intent)
ROLE_COLOR = {"base": "black", "tie": "darkorange", "regular": "steelblue"}


def _solve_line(df, line_id):
    group = df[df["Line"] == line_id].copy()
    group = assign_loops(group)
    group = assign_locations(group)
    return solve_with_cov(group)


def plot_closure(results, config):
    """Style A: residual of each occupation, grouped by co-located location."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), squeeze=False)
    for ax, line_id in zip(axes.flat, LINES):
        res = results.get(line_id)
        if res is None:
            ax.set_visible(False)
            continue
        obs = res["obs"].copy()
        obs["resid_mGal"] = res["residuals"]

        # keep only locations visited more than once (closure only exists there)
        sizes = obs.groupby("loc_id")["loc_id"].transform("count")
        rep   = obs[sizes > 1]

        xt, xl = [], []
        for x, (loc_id, grp) in enumerate(rep.groupby("loc_id")):
            for _, r in grp.iterrows():
                ax.plot(x, r["resid_mGal"] * 1.0, "o",
                        color=ROLE_COLOR.get(r["StationType"], "grey"),
                        markersize=6, zorder=3)
            # label the group by its station numbers
            stns = "/".join(f"S{int(s)}" for s in grp["Station"])
            xt.append(x)
            xl.append(f"P{int(loc_id)}\n{stns}")
        ax.axhline(0, color="k", linewidth=0.8, linestyle="--", zorder=1)
        ax.set_xticks(xt)
        ax.set_xticklabels(xl, fontsize=6, rotation=0)
        ax.set_title(f"Line {line_id}  "
                     f"($\\chi^2_\\nu$ = {res['chi2_red']:.2f})")
        ax.set_ylabel("Residual (mGal)")
        ax.grid(True, axis="y", alpha=0.25, linestyle="--")

    handles = [plt.Line2D([0], [0], marker="o", linestyle="None", color=c, label=k)
               for k, c in ROLE_COLOR.items()]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=True)
    fig.suptitle("Closure residuals at co-located stations", fontweight="bold")
    fig.tight_layout(rect=[0, 0.05, 1, 0.97])
    out = SAVE_DIR / f"lsq_residuals_closure_{config}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"saved -> {out.relative_to(BASE)}")


def plot_perstation(results, config):
    """Style B: every residual vs station with its +/- SE_est error bar."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), squeeze=False)
    for ax, line_id in zip(axes.flat, LINES):
        res = results.get(line_id)
        if res is None:
            ax.set_visible(False)
            continue
        obs = res["obs"].copy()
        obs = obs.sort_values("Station").reset_index(drop=True)
        r   = res["residuals"]
        # residuals array is aligned to res["obs"] order; re-map after sort
        r_sorted = res["obs"].assign(_r=res["residuals"]) \
                             .sort_values("Station")["_r"].values

        x = np.arange(len(obs))
        for xi, (_, row), ri in zip(x, obs.iterrows(), r_sorted):
            ax.errorbar(xi, ri * 1.0, yerr=row["SE_est"], fmt="o",
                        color=ROLE_COLOR.get(row["StationType"], "grey"),
                        markersize=4, capsize=2, elinewidth=0.7, zorder=3)
        ax.axhline(0, color="k", linewidth=0.8, linestyle="--", zorder=1)
        ax.set_xticks(x)
        ax.set_xticklabels([f"S{int(s)}" for s in obs["Station"]],
                           fontsize=5, rotation=90)
        ax.set_title(f"Line {line_id}  "
                     f"($\\chi^2_\\nu$ = {res['chi2_red']:.2f})")
        ax.set_ylabel("Residual (mGal)")
        ax.grid(True, axis="y", alpha=0.25, linestyle="--")

    handles = [plt.Line2D([0], [0], marker="o", linestyle="None", color=c, label=k)
               for k, c in ROLE_COLOR.items()]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=True)
    fig.suptitle("Adjustment residuals per station (bars = input SE)",
                 fontweight="bold")
    fig.tight_layout(rect=[0, 0.05, 1, 0.97])
    out = SAVE_DIR / f"lsq_residuals_perstation_{config}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"saved -> {out.relative_to(BASE)}")


def plot_hybrid(results, config):
    """Hybrid A+B: co-located groups (closure) WITH +/- SE_est error bars.
    Residuals in microGal; y-axis shared across panels for direct comparison."""
    # sharey=True -> one common y-scale so panels compare directly (L5's large
    # S28 residual sets the range; the quiet lines then read as genuinely flat).
    fig, axes = plt.subplots(2, 2, figsize=(HYB_W_IN, HYB_H_IN),
                             sharey=True, squeeze=False)
    for i, (ax, line_id) in enumerate(zip(axes.flat, LINES)):
        res = results.get(line_id)
        if res is None:
            ax.set_visible(False)
            continue
        obs = res["obs"].copy()
        obs["resid_uGal"] = res["residuals"] * 1000.0   # mGal -> microGal

        sizes = obs.groupby("loc_id")["loc_id"].transform("count")
        rep   = obs[sizes > 1]

        xt, xl = [], []
        for x, (loc_id, grp) in enumerate(rep.groupby("loc_id")):
            n = len(grp)
            offs = np.linspace(-JITTER, JITTER, n) if n > 1 else [0.0]
            for dx, (_, r) in zip(offs, grp.iterrows()):
                ax.errorbar(x + dx, r["resid_uGal"], yerr=r["SE_est"] * 1000.0,
                            fmt="o", color=ROLE_COLOR.get(r["StationType"], "grey"),
                            markersize=4, capsize=2, elinewidth=0.7, zorder=3)
            xt.append(x)
            # base (loc 0) is occupied many times -> its station list overruns the
            # neighbouring label; collapse it to "base". Small tie/regular groups
            # keep their station numbers.
            if loc_id == 0:
                xl.append("base")
            else:
                stns = "/".join(f"S{int(s)}" for s in grp["Station"])
                xl.append(f"P{int(loc_id)}\n{stns}")
        ax.axhline(0, color="k", linewidth=0.8, linestyle="--", zorder=1)
        ax.set_xticks(xt)
        ax.set_xticklabels(xl, fontsize=6, rotation=0)
        ax.set_title(f"Line {line_id}  ($\\chi^2_\\nu$ = {res['chi2_red']:.2f})")
        if i % 2 == 0:                       # y-label on the left column only
            ax.set_ylabel(r"Residual ($\mu$Gal)")
        ax.grid(True, axis="y", alpha=0.25, linestyle="--")

    handles = [plt.Line2D([0], [0], marker="o", linestyle="None", color=c, label=k)
               for k, c in ROLE_COLOR.items()]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=True)
    fig.suptitle("Residuals at co-located stations (bars = input SE)",
                 fontweight="bold")
    fig.tight_layout(rect=[0, 0.06, 1, 0.96])
    # thesis-width, title-free PDF + a titled browse PNG beside the results
    thesis_path, browse = save_figure(
        fig, f"lsq_residuals_hybrid_{config}", "Grav",
        vector=True, tight=False, browse_dir=SAVE_DIR)
    print(f"saved thesis -> {thesis_path}")
    print(f"saved browse -> {browse}")


def main(config="decay"):
    in_file = PROC_DIR / f"station_gravity_{config}.csv"
    df = pd.read_csv(in_file, dtype={"Time_first": str, "Time_mid": str, "Date": str})
    df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time_mid"],
                                    format="%Y/%m/%d %H:%M:%S")
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    for line_id in LINES:
        if (df["Line"] == line_id).any():
            results[line_id] = _solve_line(df, line_id)

    plot_closure(results, config)
    plot_perstation(results, config)
    plot_hybrid(results, config)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "decay")

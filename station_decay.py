"""
Fit an exponential decay to the CG-5 gravity readings at each station.

Model:  g(t) = g_inf + A * exp(-t / tau)

  g_inf  — asymptotic gravity value (what we want)
  A      — initial offset from the asymptote (settling amplitude)
  tau    — settling time constant (minutes)

Input
-----
  Data/Gravimetry/filtered_gravimetry_drop0.csv

Output
------
  Data/Gravimetry/station_decay.csv   one row per station with g_inf and fit quality

Visual
------
  One figure per Line, grid of subplots — one per station.
  Green fit  : A is statistically significant (real settling).
  Grey fit   : station already settled (A not significant, fit = flat mean).
  Red label  : fit did not converge.
"""

import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
from scipy.optimize import curve_fit

BASE       = Path(__file__).resolve().parents[1]
FILT_FILE  = BASE / "Data/Gravimetry/filtered_gravimetry_drop0.csv"
OUT_FILE   = BASE / "Data/Gravimetry/station_decay.csv"
MEANS_FILE = BASE / "Data/Gravimetry/station_means_decay.csv"   # pipeline-compatible

# A / SE_A must exceed this ratio to be considered "real settling"
SIGNIFICANCE_THRESHOLD = 0.8


# ── Model ─────────────────────────────────────────────────────────────────────

def decay_model(t, g_inf, A, tau):
    return g_inf + A * np.exp(-t / tau)


def fit_station(t_min, grav, se):
    """
    Fit exponential decay.  Returns (g_inf, se_g_inf, A, se_A, tau, converged).
    t_min : time in minutes from first reading
    grav  : gravity values (mGal)
    se    : per-reading SE (mGal), used as sigma for weighted fit
    """
    g0   = grav.iloc[-1]          # last reading as first guess for g_inf
    A0   = grav.iloc[0] - g0     # initial offset
    tau0 = max(t_min.max() / 3, 0.5)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            popt, pcov = curve_fit(
                decay_model, t_min, grav,
                p0=[g0, A0, tau0],
                sigma=se, absolute_sigma=True,
                bounds=([-np.inf, -np.inf, 0.01], [np.inf, np.inf, 60]),
                maxfev=5000,
            )
        perr = np.sqrt(np.diag(pcov))
        return popt[0], perr[0], popt[1], perr[1], popt[2], True
    except Exception:
        return g0, se.mean(), 0.0, np.nan, tau0, False


# ── Plot one line ──────────────────────────────────────────────────────────────

def plot_line(line_df, line_id, results):
    stations = sorted(line_df["Station"].unique())
    n = len(stations)
    ncols = 6
    nrows = int(np.ceil(n / ncols))

    fig, axes = plt.subplots(nrows, ncols,
                              figsize=(ncols * 2.8, nrows * 3.0),
                              squeeze=False)
    fig.suptitle(f"Line {line_id} — exponential decay fits", fontsize=12, y=1.0)

    for idx, station in enumerate(stations):
        ax  = axes[idx // ncols][idx % ncols]
        grp = line_df[line_df["Station"] == station].sort_values("Time").reset_index(drop=True)

        t_abs = pd.to_datetime(grp["Date"] + " " + grp["Time"],
                               format="%Y/%m/%d %H:%M:%S")
        t_min = (t_abs - t_abs.iloc[0]).dt.total_seconds() / 60

        grav = grp["Grav"]
        se   = grp["SE_i"].fillna(grp["SE_i"].mean())

        g_inf, se_g_inf, A, se_A, tau, converged = fit_station(t_min, grav, se)

        settled     = (not converged) or (abs(A) < SIGNIFICANCE_THRESHOLD * se_A)
        fit_color   = "grey" if settled else "tab:green"
        label_color = "red" if not converged else "black"

        # Data points
        ax.errorbar(t_min, grav, yerr=se,
                    fmt="o", color="steelblue", markersize=3,
                    capsize=2, linewidth=0.6, elinewidth=0.6, zorder=3,
                    label="readings")

        # Fitted curve
        t_dense = np.linspace(0, t_min.max(), 200)
        ax.plot(t_dense, decay_model(t_dense, g_inf, A, tau),
                color=fit_color, linewidth=1.2, zorder=2,
                label="decay fit" if not settled else "flat fit")

        # Weighted mean (always computed, shown as reference for settled stations)
        w_plot     = 1.0 / se**2
        g_wmean_p  = (w_plot * grav).sum() / w_plot.sum()

        # Asymptote: always show g_inf from fit as dashed line
        ax.axhline(g_inf, color=fit_color, linewidth=0.9,
                   linestyle="--", alpha=0.8, label="g∞ (fit)")
        # For settled stations also overlay the weighted mean
        if settled:
            ax.axhline(g_wmean_p, color="darkorange", linewidth=0.9,
                       linestyle=":", alpha=0.9, label="weighted mean")

        # Title and CSV use weighted mean for settled, g_inf for settling
        display_g = g_wmean_p if settled else g_inf
        status    = "settled" if settled else f"τ={tau:.1f}m"
        ax.set_title(f"S{station}\ng={display_g:.3f}, {status}",
                     fontsize=7, color=label_color, pad=3)
        ax.tick_params(labelsize=6)
        ax.yaxis.set_major_formatter(plt.matplotlib.ticker.FormatStrFormatter("%.3f"))
        # Only show x-label on bottom row to avoid crowding
        if idx // ncols == nrows - 1:
            ax.set_xlabel("min", fontsize=6)
        ax.margins(y=0.18)

    # Hide unused subplots
    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    # Figure-level legend — placed inside the figure at the bottom
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="steelblue", linestyle="None",
               markersize=4, label="Readings ± SE"),
        Line2D([0], [0], color="tab:green", linewidth=1.2,
               label="Decay fit (settling)"),
        Line2D([0], [0], color="tab:green", linewidth=0.9, linestyle="--",
               label="g∞ asymptote"),
        Line2D([0], [0], color="grey", linewidth=1.2,
               label="Flat fit (settled)"),
        Line2D([0], [0], color="grey", linewidth=0.9, linestyle="--",
               label="g∞ (settled)"),
        Line2D([0], [0], color="darkorange", linewidth=0.9, linestyle=":",
               label="Weighted mean (settled)"),
    ]
    plt.tight_layout(rect=[0, 0.06, 1, 0.97], h_pad=2.5, w_pad=1.0)
    fig.legend(handles=legend_elements, loc="lower center",
               ncol=6, fontsize=7, frameon=True,
               bbox_to_anchor=(0.5, 0.02), bbox_transform=fig.transFigure)
    return fig


# ── Main ──────────────────────────────────────────────────────────────────────

def main(plot=True):
    print(f"Reading {FILT_FILE.name} …")
    df = pd.read_csv(FILT_FILE, dtype={"Time": str, "Date": str})
    print(f"  {df.groupby(['Line','Station']).ngroups} stations")

    records = []
    for (line, station), grp in df.groupby(["Line", "Station"]):
        grp   = grp.sort_values("Time").reset_index(drop=True)
        t_abs = pd.to_datetime(grp["Date"] + " " + grp["Time"],
                               format="%Y/%m/%d %H:%M:%S")
        t_min = (t_abs - t_abs.iloc[0]).dt.total_seconds() / 60
        se    = grp["SE_i"].fillna(grp["SE_i"].mean())

        # Weighted mean — fallback for settled stations
        w         = 1.0 / se**2
        g_wmean   = (w * grp["Grav"]).sum() / w.sum()
        se_wmean  = 1.0 / np.sqrt(w.sum())

        g_inf, se_g_inf, A, se_A, tau, converged = fit_station(t_min, grp["Grav"], se)
        settled = (not converged) or (abs(A) < SIGNIFICANCE_THRESHOLD * se_A)

        # Best gravity estimate: g_inf from fit for settling stations,
        # weighted mean for settled ones (fit asymptote unreliable when A ≈ 0)
        best_g  = g_wmean  if settled else g_inf
        best_se = se_wmean if settled else se_g_inf

        records.append({
            "Line": line, "Station": station,
            "Easting":   grp["Easting"].iloc[0],
            "Northing":  grp["Northing"].iloc[0],
            "Elevation": grp["Elevation"].iloc[0],
            "HorizErr":  grp["HorizErr"].iloc[0],
            "VertErr":   grp["VertErr"].iloc[0],
            "g_inf":     best_g,
            "SE_g_inf":  best_se,
            "g_wmean":   g_wmean,
            "SE_wmean":  se_wmean,
            "A":         A,
            "SE_A":      se_A,
            "tau_min":   tau,
            "converged": converged,
            "settled":   settled,
            "n_readings": len(grp),
            "StationType": grp["StationType"].iloc[0],
            "Notes":     grp["Notes"].iloc[0],
        })

    results = pd.DataFrame(records)
    n_settling = (~results["settled"]).sum()
    n_settled  = results["settled"].sum()
    n_failed   = (~results["converged"]).sum()
    print(f"  Settling (A significant): {n_settling}")
    print(f"  Already settled:          {n_settled}")
    print(f"  Fit failed:               {n_failed}")

    results.to_csv(OUT_FILE, index=False, float_format="%.6f")
    print(f"Saved → {OUT_FILE.name}")

    # Pipeline-compatible version: rename g_inf/SE_g_inf to Grav_wmean/SE_wmean
    # so drift_correction.py can consume it directly.
    pipe_cols = {
        "g_inf":    "Grav_wmean",
        "SE_g_inf": "SE_wmean",
    }
    means_df = results.rename(columns=pipe_cols)[[
        "Line", "Station", "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
        "Grav_wmean", "SE_wmean", "n_readings",
        "StationType", "Notes",
    ]]
    # station_means.py also writes Date/Time_first/Time_last/Temp_mean;
    # carry them from the filtered readings
    meta = (df.sort_values("Time")
              .groupby(["Line", "Station"])
              .agg(Temp_mean=("Temp", "mean"),
                   Date=("Date", "first"),
                   Time_first=("Time", "first"),
                   Time_last=("Time", "last"))
              .reset_index())
    means_df = means_df.merge(meta, on=["Line", "Station"], how="left")
    means_df.to_csv(MEANS_FILE, index=False, float_format="%.6f")
    print(f"Saved → {MEANS_FILE.name}  (pipeline-compatible)")

    if plot:
        fig_dir = BASE / "Results/Grav/Decay fitting"
        fig_dir.mkdir(parents=True, exist_ok=True)
        for line_id in sorted(df["Line"].unique()):
            fig = plot_line(df[df["Line"] == line_id], line_id, results)
            save_path = fig_dir / f"decay_line{line_id}.png"
            fig.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"Saved → {save_path.name}")
        plt.show()


if __name__ == "__main__":
    main()

"""
Fit an exponential decay to the CG-5 gravity readings at each station.

Model:  g(t) = g_inf + A * exp(-t / tau)

  g_inf  -> asymptotic gravity value (what we want)
  A      -> initial offset from the asymptote (settling amplitude)
  tau    -> settling time constant (minutes)

Input
-----
  Data/Gravimetry/Processed/filtered_gravimetry_all.csv

Output
------
  Data/Gravimetry/Processed/decay_fits.csv          fit parameters (g_inf, A, tau, quality)
  Data/Gravimetry/Processed/station_gravity_decay.csv  g_inf per station, pipeline format

Visual
------
  One figure per Line, grid of subplots, one per station.
  Green fit  : A is statistically significant (real settling).
  Grey fit   : station already settled (A not significant, fit = flat mean).
  Red label  : fit did not converge.
"""

import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure
import matplotlib.gridspec as gridspec
from pathlib import Path
from scipy.optimize import curve_fit

BASE       = Path(__file__).resolve().parents[2]
PROC_DIR   = BASE / "Data/Gravimetry/Processed"
FILT_FILE  = PROC_DIR / "filtered_gravimetry_all.csv"
OUT_FILE   = PROC_DIR / "decay_fits.csv"
MEANS_FILE = PROC_DIR / "station_gravity_decay.csv"   # g_inf per station, pipeline format

# A / SE_A must exceed this ratio to be considered "real settling"
SIGNIFICANCE_THRESHOLD = 1.0
# tau below this value (minutes) is physically implausible -- treat as settled
TAU_MIN = 0.5


# -- Model ---------------------------------------------------------------------

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


# -- Plot one line --------------------------------------------------------------

# -- Appendix grid layout ------------------------------------------------------
# These figures used to be built 16.8 in wide (6 cols x 2.8 in) and then squeezed into
# \textwidth (~6.3 in) by LaTeX -- a ~2.6x shrink, which is why a 7 pt title landed on
# the page at ~2.7 pt and was unreadable. Building at the FINAL width instead makes one
# pt here one pt on the page. ROW_H_IN reproduces the OLD aspect ratio exactly
# (old = nrows*3.0 / 16.8), so the figure occupies the same space on the page as before
# and only the text changes size. Raise the FS_* values for bigger text; past a point
# the 3-line titles will start to collide and the grid needs fewer columns instead.
GRID_NCOLS = 6
FIG_W_IN = 6.5                              # the width LaTeX renders these at
ROW_H_IN = 0.98                             # height of ONE ROW OF AXES; LOWER = shorter
                                            # figure (L5 needs to leave room for its
                                            # caption on the page)
# Reserves for the suptitle and the figure legend, in INCHES rather than as a fraction
# of the figure. As a fraction the gap grew with the row count (7% was 0.33 in on L4 but
# 0.57 in on L3), so the tall figures wasted the most space and the legend drifted away
# from the panels. Absolute reserves keep the gap identical on every line.
TOP_RES_IN, LEG_RES_IN = 0.20, 0.32         # LOWER = tighter to the panels
FS_TITLE, FS_TICK, FS_AXLAB, FS_LEG, FS_SUP = 6, 5.5, 6, 5.5, 8
# Ink weight. SMALLER = lighter/thinner marks, which keeps 124 tiny panels from reading
# as a wall of blue. MS_DATA is the reading marker; LW_THIN the error bars; LW_FIT the
# fitted curve; LW_REF the dashed/dotted reference lines.
MS_DATA, CAPSIZE, LW_THIN, LW_FIT, LW_REF = 0.8, 1.2, 0.35, 0.5, 0.4
CAPTHICK = 0.25          # cap stroke weight; LOWER = shorter/flatter caps.
                         # CAPSIZE is the cap WIDTH -- raise it for wider caps.


def plot_line(line_df, line_id, results):
    stations = sorted(line_df["Station"].unique())
    n = len(stations)
    ncols = GRID_NCOLS
    nrows = int(np.ceil(n / ncols))

    fig_h = nrows * ROW_H_IN + TOP_RES_IN + LEG_RES_IN
    fig, axes = plt.subplots(nrows, ncols, figsize=(FIG_W_IN, fig_h), squeeze=False)
    fig.suptitle(f"Line {line_id}, exponential decay fits", fontsize=FS_SUP,
                 y=1.0 - 0.35 * TOP_RES_IN / fig_h)

    for idx, station in enumerate(stations):
        ax  = axes[idx // ncols][idx % ncols]
        grp = line_df[line_df["Station"] == station].sort_values("Time").reset_index(drop=True)

        t_abs = pd.to_datetime(grp["Date"] + " " + grp["Time"],
                               format="%Y/%m/%d %H:%M:%S")
        t_min = (t_abs - t_abs.iloc[0]).dt.total_seconds() / 60

        grav = grp["Grav"]
        se   = grp["SE_i"].fillna(grp["SE_i"].mean())

        g_inf, se_g_inf, A, se_A, tau, converged = fit_station(t_min, grav, se)

        settled     = (not converged) or (abs(A) < SIGNIFICANCE_THRESHOLD * se_A) or (tau < TAU_MIN)
        fit_color   = "grey" if settled else "tab:green"
        label_color = "red" if not converged else "black"

        # Weighted mean (always computed, shown as reference for settled stations).
        # Needed BEFORE plotting now: it sets the per-panel reference level.
        w_plot      = 1.0 / se**2
        g_wmean_p   = (w_plot * grav).sum() / w_plot.sum()
        se_wmean_p  = 1.0 / np.sqrt(w_plot.sum())

        # Reported value for this station: weighted mean if settled, else g_inf.
        display_g  = g_wmean_p  if settled else g_inf
        display_se = se_wmean_p if settled else se_g_inf

        # Plot RELATIVE to the reported value, in uGal. Absolute mGal tick labels were
        # 8 characters wide ("5468.164") and ate a third of every panel; offsets are 3.
        # Nothing is lost -- the absolute value is in the panel title. The reference is
        # the reported value, so the dashed/dotted line the station is judged against
        # always sits at 0.
        uG = lambda v: (v - display_g) * 1000.0

        # Data points
        ax.errorbar(t_min, uG(grav), yerr=se * 1000.0,
                    fmt="o", color="steelblue", markersize=MS_DATA,
                    capsize=CAPSIZE, capthick=CAPTHICK, linewidth=LW_THIN,
                    elinewidth=LW_THIN, zorder=3,
                    label="readings")

        # Fitted curve
        t_dense = np.linspace(0, t_min.max(), 200)
        ax.plot(t_dense, uG(decay_model(t_dense, g_inf, A, tau)),
                color=fit_color, linewidth=LW_FIT, zorder=2,
                label="decay fit" if not settled else "flat fit")

        # Asymptote line + uncertainty band
        ax.axhline(uG(g_inf), color=fit_color, linewidth=LW_REF,
                   linestyle="--", alpha=0.8, label="$g_\\infty$ (fit)")
        if not settled:
            # lw=0: axhspan's Polygon otherwise strokes its own edge in the same
            # colour AND alpha as the fill, so the boundary blends twice and reads as
            # a darker rim. Killing the edge makes the band evenly tinted.
            ax.axhspan(uG(g_inf - se_g_inf), uG(g_inf + se_g_inf),
                       color="tab:green", alpha=0.15, zorder=1, lw=0,
                       label="$g_\\infty$ uncertainty")
        if settled:
            # Settled: show weighted mean with its uncertainty band
            ax.axhline(uG(g_wmean_p), color="darkorange", linewidth=LW_REF,
                       linestyle=":", alpha=0.9, label="weighted mean")
            ax.axhspan(uG(g_wmean_p - se_wmean_p), uG(g_wmean_p + se_wmean_p),
                       color="darkorange", alpha=0.15, zorder=1, lw=0)

        status = "settled" if settled else f"$\\tau$={tau:.1f}m"
        ax.set_title(f"S{station}  {status}",
                     fontsize=FS_TITLE, color=label_color, pad=2)
        ax.tick_params(labelsize=FS_TICK, pad=1.5)
        # Only show axis labels on the outer edges to avoid crowding
        if idx // ncols == nrows - 1:
            ax.set_xlabel("min", fontsize=FS_AXLAB, labelpad=1)
        if idx % ncols == 0:
            ax.set_ylabel(r"$g-g_{\rm rep}$ ($\mu$Gal)", fontsize=FS_AXLAB, labelpad=1)
        ax.margins(y=0.18)

    # Hide unused subplots
    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    # Same y-axis span for all subplots, each centered on its own data
    visible_axes = [axes[i // ncols][i % ncols] for i in range(n)]
    span = max(ax.get_ylim()[1] - ax.get_ylim()[0] for ax in visible_axes)
    for ax in visible_axes:
        mid = sum(ax.get_ylim()) / 2
        ax.set_ylim(mid - span / 2, mid + span / 2)

    # Figure-level legend placed inside the figure at the bottom
    from matplotlib.lines import Line2D
    import matplotlib.patches as mpatches
    legend_elements = [
        Line2D([0], [0], marker="o", color="steelblue", linestyle="None",
               markersize=MS_DATA*1.6, label="Readings +/- SE"),
        Line2D([0], [0], color="tab:green", linewidth=LW_FIT,
               label="Decay fit (settling)"),
        Line2D([0], [0], color="tab:green", linewidth=LW_REF, linestyle="--",
               label="$g_\\infty$ (settling)"),
        mpatches.Patch(color="tab:green", alpha=0.25,
               label="+/- SE($g_\\infty$) (settling)"),
        Line2D([0], [0], color="grey", linewidth=LW_FIT,
               label="Flat fit (settled)"),
        Line2D([0], [0], color="grey", linewidth=LW_REF, linestyle="--",
               label="$g_\\infty$ (settled)"),
        Line2D([0], [0], color="darkorange", linewidth=LW_REF, linestyle=":",
               label="Weighted mean (settled)"),
        mpatches.Patch(color="darkorange", alpha=0.3,
               label="+/- SE(mean) (settled)"),
    ]
    plt.tight_layout(rect=[0, LEG_RES_IN / fig_h, 1, 1 - TOP_RES_IN / fig_h],
                     h_pad=0.15, w_pad=0.05)
    fig.legend(handles=legend_elements, loc="lower center",
               ncol=4, fontsize=FS_LEG, frameon=True,
               bbox_to_anchor=(0.5, 0.005), bbox_transform=fig.transFigure)
    return fig


# -- Main ----------------------------------------------------------------------

def main(plot=True):
    print(f"Reading {FILT_FILE.name} ...")
    df = pd.read_csv(FILT_FILE, dtype={"Time": str, "Date": str})
    print(f"  {df.groupby(['Line','Station']).ngroups} stations")

    records = []
    for (line, station), grp in df.groupby(["Line", "Station"]):
        grp   = grp.sort_values("Time").reset_index(drop=True)
        t_abs = pd.to_datetime(grp["Date"] + " " + grp["Time"],
                               format="%Y/%m/%d %H:%M:%S")
        t_min = (t_abs - t_abs.iloc[0]).dt.total_seconds() / 60
        se    = grp["SE_i"].fillna(grp["SE_i"].mean())

        # Weighted mean, fallback for settled stations
        w         = 1.0 / se**2
        g_wmean   = (w * grp["Grav"]).sum() / w.sum()
        se_wmean  = 1.0 / np.sqrt(w.sum())

        g_inf, se_g_inf, A, se_A, tau, converged = fit_station(t_min, grp["Grav"], se)
        settled = ((not converged) or (abs(A) < SIGNIFICANCE_THRESHOLD * se_A)
                   or (tau < TAU_MIN))     # match plot_line(): reject degenerate fits

        # Best gravity estimate: g_inf from fit for settling stations,
        # weighted mean for settled ones (fit asymptote unreliable when A ~= 0)
        best_g  = g_wmean  if settled else g_inf
        best_se = se_wmean if settled else se_g_inf

        records.append({
            "Line": line, "Station": station,
            "Date":      grp["Date"].iloc[0],
            "Time":      grp["Time"].iloc[0],
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
    print(f"Saved -> {OUT_FILE.name}")

    # Pipeline-compatible version: rename g_inf/SE_g_inf to Grav_est/SE_est
    # so drift_correction.py can consume it directly.
    pipe_cols = {
        "g_inf":    "Grav_est",
        "SE_g_inf": "SE_est",
    }
    means_df = (results
        .drop(columns=["SE_wmean", "g_wmean"])   # drop raw diagnostics; SE_g_inf becomes SE_est
        .rename(columns=pipe_cols)
        [["Line", "Station", "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
          "Grav_est", "SE_est", "n_readings", "StationType", "Notes"]]
    )
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

    # Compute midpoint time as the representative time of each measurement
    t_first = pd.to_datetime(means_df["Date"] + " " + means_df["Time_first"],
                             format="%Y/%m/%d %H:%M:%S")
    t_last  = pd.to_datetime(means_df["Date"] + " " + means_df["Time_last"],
                             format="%Y/%m/%d %H:%M:%S")
    means_df["Time_mid"] = (t_first + (t_last - t_first) / 2).dt.strftime("%H:%M:%S")

    means_df = means_df[[
        "Line", "Station", "Easting", "Northing", "Elevation", "HorizErr", "VertErr",
        "Grav_est", "SE_est", "n_readings", "Temp_mean",
        "Date", "Time_first", "Time_mid", "Time_last", "StationType", "Notes",
    ]]
    means_df.to_csv(MEANS_FILE, index=False, float_format="%.6f")
    print(f"Saved -> {MEANS_FILE.name}  (pipeline-compatible)")

    if plot:
        fig_dir = BASE / "Results/Grav/Decay fitting"
        fig_dir.mkdir(parents=True, exist_ok=True)
        for line_id in sorted(df["Line"].unique()):
            fig = plot_line(df[df["Line"] == line_id], line_id, results)
            save_path = fig_dir / f"decay_line{line_id}.png"
            fig.savefig(save_path, dpi=150, bbox_inches="tight")
            save_figure(fig, save_path.stem, "Appendices/Grav decay fits", vector=True)
            print(f"Saved -> {save_path.name}")
        plt.show()


if __name__ == "__main__":
    main()


"""
Per-line regional de-trend of the Complete Bouguer Anomaly (gravity only).

For each line a robust, uncertainty-weighted straight line is fit to CBA vs.
along-profile distance: Huber IRLS with measurement weights 1/SE^2 (precise
points count more) while the Huber step keeps the localised cave low -- often a
low-SE, high-leverage point -- from dragging the trend. The broad regional field
dominates the fit; the cave low falls out as a coherent residual, so NO cave
position from GPR/LiDAR is used (independent / ground-truth only -> no inverse crime).

Outputs per line:
  - regional gradient magnitude (mGal/km) and its map azimuth, for comparison
    with the island-scale regional gravity map (Camacho et al. 2001 etc.)
  - detrended residual = CBA - robust trend  (the cave anomaly to forward-model)

Line 4 (flower petals) is intentionally skipped: its bent geometry is not a
single profile and it is not intended for inversion.

Usage
-----
    python detrend_regional.py            # default rho = 1.875
    python detrend_regional.py 2.0        # other density (with_TC file)
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from pathlib import Path
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))   # Code/ for plot_utils
from plot_utils import save_figure

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grav_utils import BASE, PROC_DIR, RHO_DEFAULT, rho_str, along_profile_distance

LINES = [2, 3, 5]                                   # Line 4 skipped on purpose
LINE_COLORS = {2: "#0099FF", 3: "#FF5C00", 5: "#00CC80"}   # QGIS map palette

# Combined (multi-panel) figures are authored at the width they occupy on the page
# so text renders at the intended thesis size (\includegraphics[width=L] scales the
# whole figure by L/W; thesis \linewidth = 6.1 in). LARGER width -> text shrinks.
COMBINED_W_IN = 6.1        # thesis full-text width
COMBINED_PANEL_H_IN = 2.0  # per-line panel height (in); raise for taller panels

# Regional gradient read off the island-scale Bouguer map (Camacho et al. 2001):
# the direction in which gravity INCREASES and its magnitude. Each 1-D profile
# only senses the component of this vector along its own azimuth, so the script
# projects it onto each line for an apples-to-apples check against the fit.
MAP_GRAD_MAG = 1.5      # mGal/km  (map shows ~1-2)
MAP_GRAD_AZ  = 337.5    # deg from N, NNW

rho = float(sys.argv[1]) if len(sys.argv) > 1 else RHO_DEFAULT
INPUT = PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str(rho)}_with_TC.csv"
OUTCSV = PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str(rho)}_detrended.csv"
TRENDCSV = PROC_DIR / f"detrend_trend_params_rho{rho_str(rho)}.csv"
FIG_DIR = BASE / "Results/Grav/Detrend"
FIG_DIR.mkdir(parents=True, exist_ok=True)


def compass16(deg):
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) // 22.5) % 16]


def robust_wls(x, y, se, k=1.345, n_iter=50, tol=1e-12):
    """
    Robust, uncertainty-weighted straight-line fit (Huber IRLS).

    Weights combine measurement precision (1/SE^2) with a Huber factor that
    down-weights points whose residual is large relative to the overall scatter,
    so a precise-but-anomalous cave point cannot capture the trend.

    Returns slope, intercept, slope_se, chi2_red (all in the units of x, y).
    The slope SE is the weighted-covariance value scaled by the reduced chi-square,
    so it reflects the real scatter relative to the quoted SEs (chi2_red ~ 1 means
    the SEs explain the scatter; >> 1 means extra, unmodelled scatter).
    """
    se = np.where(np.isfinite(se) & (se > 0), se, np.nanmedian(se))
    se = np.maximum(se, 1e-9)
    X = np.column_stack([x, np.ones_like(x, dtype=float)])
    w_meas = 1.0 / se ** 2

    # Start from the purely measurement-weighted (non-robust) solution.
    W = w_meas.copy()
    beta = np.linalg.solve((X * W[:, None]).T @ X, (X * W[:, None]).T @ y)
    for _ in range(n_iter):
        r = y - X @ beta
        t = r / se                                  # residual in units of its SE
        s0 = 1.4826 * np.median(np.abs(t - np.median(t))) or 1.0
        a = np.abs(t / s0)                          # ~unit-scale standardised resid
        c = np.where(a <= k, 1.0, k / a)            # Huber weight
        W = c * w_meas
        beta_new = np.linalg.solve((X * W[:, None]).T @ X, (X * W[:, None]).T @ y)
        if np.max(np.abs(beta_new - beta)) < tol:
            beta = beta_new
            break
        beta = beta_new

    r = y - X @ beta
    cov = np.linalg.inv((X * W[:, None]).T @ X)
    dof = max(c.sum() - 2.0, 1.0)
    chi2_red = float(np.sum(W * r ** 2) / dof)
    cov *= chi2_red
    return float(beta[0]), float(beta[1]), float(np.sqrt(cov[0, 0])), chi2_red


def line_profile(df, line_id):
    """One row per loc_id with along-profile distance, sorted by distance."""
    d = df[(df["Line"] == line_id) & (df["StationType"] != "base")]
    g = (d.groupby("loc_id")
           .agg(Easting=("Easting", "mean"), Northing=("Northing", "mean"),
                CBA=("CBA", "mean"), SE=("SE_SBA", "mean"),
                StationType=("StationType", "first"))  # for tie-station markers
           .dropna(subset=["Easting", "Northing", "CBA"])
           .reset_index())
    g["Station"] = g["loc_id"]
    g = along_profile_distance(g).sort_values("dist").reset_index(drop=True)
    return g


TIE_MARKER = "v"   # tie stations drawn as down-triangles; regular stations as circles


def plot_points(ax, x, y, se, stype, color, ms=6, capsize=3, elinewidth=1.2,
                label=None):
    """Errorbar scatter splitting tie stations (triangles) from regular (circles)."""
    x, y, se, stype = (np.asarray(a) for a in (x, y, se, stype))
    is_tie = stype == "tie"
    # Regular points (carry the legend label); ties as marginally larger triangles.
    for mask, marker, size, lab in ((~is_tie, "o", ms, label),
                                    (is_tie, TIE_MARKER, ms + 1, None)):
        if mask.any():
            ax.errorbar(x[mask], y[mask], yerr=se[mask], fmt=marker, color=color,
                        capsize=capsize, markersize=size, elinewidth=elinewidth,
                        zorder=3, label=lab)


def main():
    print(f"Reading {INPUT.name} ...\n")
    df = pd.read_csv(INPUT, dtype={"Date": str})

    # Map regional gradient as an (E, N) vector in mGal/km.
    map_vec = MAP_GRAD_MAG * np.array([np.sin(np.radians(MAP_GRAD_AZ)),
                                       np.cos(np.radians(MAP_GRAD_AZ))])

    out_rows = []
    print(f"Map regional: {MAP_GRAD_MAG:.1f} mGal/km toward "
          f"{compass16(MAP_GRAD_AZ)} ({MAP_GRAD_AZ:.0f} deg)\n")
    print(f"{'Line':>4}  {'fit slope':>10}  {'95% CI':>20}  "
          f"{'map proj':>9}  {'agree?':>7}  {'chi2_red':>8}  resid range (uGal)")
    print("-" * 92)

    chi2_by_line = {}
    param_rows = []                                    # per-line trend params
    fit_panels = []                                    # ingredients for the combined fits figure
    for line_id in LINES:
        g = line_profile(df, line_id)
        x, y, se = g["dist"].values, g["CBA"].values, g["SE"].values

        # Robust, uncertainty-weighted straight-line fit (slope in mGal/m).
        slope, intercept, slope_se, chi2_red = robust_wls(x, y, se)
        trend = slope * x + intercept
        resid = y - trend
        chi2_by_line[line_id] = chi2_red
        # slope_se is in mGal/m; xm anchors the tilt for downstream propagation.
        param_rows.append((line_id, slope, slope_se, intercept, x.mean(), chi2_red))

        # Signed slope (mGal/km) with 95% CI from the weighted covariance.
        slope_km = slope * 1000
        lo_km, hi_km = (slope - 1.96 * slope_se) * 1000, (slope + 1.96 * slope_se) * 1000
        straddles = lo_km < 0 < hi_km   # direction undetermined if CI spans 0

        # Map direction of increasing 'dist' = from first to last station.
        p0 = g[["Easting", "Northing"]].iloc[0].values
        p1 = g[["Easting", "Northing"]].iloc[-1].values
        ddir = (p1 - p0) / np.hypot(*(p1 - p0))
        grad_vec = np.sign(slope) * ddir              # points uphill in gravity
        az = np.degrees(np.arctan2(grad_vec[0], grad_vec[1])) % 360

        # Slope the map gradient predicts along this profile's +dist direction.
        map_slope = float(map_vec @ ddir)             # mGal/km
        agree = "yes" if lo_km <= map_slope <= hi_km else "NO"

        print(f"{line_id:>4}  {slope_km:>+10.3f}  [{lo_km:+7.3f},{hi_km:+7.3f}]"
              f"  {map_slope:>+9.3f}  {agree:>7}  {chi2_red:>8.2f}  "
              f"[{resid.min()*1000:+.0f}, {resid.max()*1000:+.0f}]")

        g["trend"] = trend
        g["CBA_detrended"] = resid
        g["Line"] = line_id
        out_rows.append(g[["Line", "loc_id", "Easting", "Northing", "dist",
                           "CBA", "SE", "trend", "CBA_detrended", "StationType"]])

        # -- Plot: CBA + robust trend (top), detrended residual (bottom) -------
        color = LINE_COLORS[line_id]
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                                       gridspec_kw={"height_ratios": [2, 1]})

        stype = g["StationType"].values
        plot_points(ax1, x, y, g["SE"].values, stype, color,
                    label=r"CBA $\pm$ SE")
        ax1.plot(x, trend, "--", color="0.35", linewidth=1.6, zorder=2,
                 label="robust trend")
        # Slope-CI fan: rotate the trend about the profile mid-point by +/-1.96 SE.
        xm = x.mean()
        ym = slope * xm + intercept
        ax1.fill_between(x, ym + (lo_km / 1000.0) * (x - xm),
                         ym + (hi_km / 1000.0) * (x - xm),
                         color="0.35", alpha=0.15, zorder=1, label="95% CI")

        # Compact info box instead of a wordy legend.
        toward_txt = (r"$\approx$ flat" if straddles
                      else rf"toward {compass16(az)} (${az:.0f}^\circ$)")
        info = "\n".join([
            rf"slope $= {slope_km:+.2f}$ mGal/km, {toward_txt}",
            rf"95% CI $[{lo_km:+.2f},\ {hi_km:+.2f}]$",
            rf"$\chi^2_\nu = {chi2_red:.1f}$",
        ])
        ax1.text(0.015, 0.97, info, transform=ax1.transAxes, va="top", ha="left",
                 fontsize=9, bbox=dict(boxstyle="round", fc="white", ec="0.7",
                                       alpha=0.85))

        # Keep the fit ingredients for the combined "all fits" figure built below.
        fit_panels.append(dict(line_id=line_id, x=x, y=y, se=g["SE"].values,
                               stype=stype, trend=trend, xm=xm, ym=ym, lo_km=lo_km,
                               hi_km=hi_km, color=color, info=info))

        ax1.set_ylabel("CBA (mGal)")
        ax1.set_title(rf"Line {line_id} $-$ regional de-trend (robust weighted)",
                      fontweight="bold", fontsize=12)
        h, l = ax1.get_legend_handles_labels()
        h.append(Line2D([], [], marker=TIE_MARKER, color=color, linestyle="None",
                        markersize=7))
        l.append("tie station")
        ax1.legend(h, l, fontsize=8, loc="upper right", framealpha=0.85)
        ax1.grid(True, alpha=0.25, linestyle="--")
        ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
        # Headroom so the info box (top-left) and legend (top-right) clear the data.
        ylo, yhi = ax1.get_ylim()
        ax1.set_ylim(ylo, yhi + 0.42 * (yhi - ylo))

        ax2.axhline(0, color="0.35", linewidth=1.0)
        plot_points(ax2, x, resid, g["SE"].values, stype, color)
        ax2.set_xlabel("Distance along profile (m)")
        ax2.set_ylabel("Detrended CBA (mGal)")
        ax2.grid(True, alpha=0.25, linestyle="--")
        ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
        # Plot N->S (N on the left) to match the GPR sections; dist stays S->N.
        # dist increases N->S from 0 (grav_utils) -> N already on the left
        ax2.text(0.006, 0.96, "N", transform=ax2.transAxes, ha="left", va="top",
                 fontweight="bold", fontsize=11, color="0.3")
        ax2.text(0.994, 0.96, "S", transform=ax2.transAxes, ha="right", va="top",
                 fontweight="bold", fontsize=11, color="0.3")

        fig.tight_layout()
        save_path = FIG_DIR / f"detrend_line{line_id}.png"
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        save_figure(fig, save_path.stem, "Grav", vector=True)   # title-free thesis PDF
        print(f"      saved -> {save_path.relative_to(BASE)}")

    out = pd.concat(out_rows, ignore_index=True)
    out.to_csv(OUTCSV, index=False)
    print(f"\nDetrended residuals -> {OUTCSV.relative_to(BASE)}")

    # Per-line trend params (slope_se feeds the inversion's detrend-uncertainty
    # channel; the slope is in mGal/m, tilt anchored about x_mean).
    params = pd.DataFrame(param_rows, columns=["Line", "slope", "slope_se",
                                               "intercept", "x_mean", "chi2_red"])
    params.to_csv(TRENDCSV, index=False)
    print(f"Trend params       -> {TRENDCSV.relative_to(BASE)}")

    # Clean combined figure of the detrended residuals -- the exact data the
    # tube inversion fits (one panel per line, SE bars, S->N orientation).
    fig, axes = plt.subplots(len(LINES), 1, sharey=True,   # shared y -> lines directly comparable
                             figsize=(COMBINED_W_IN, COMBINED_PANEL_H_IN * len(LINES)))
    for ax, line_id in zip(np.atleast_1d(axes), LINES):
        g = out[out["Line"] == line_id].sort_values("dist")
        ax.axhline(0, color="0.6", lw=0.8, zorder=1)
        plot_points(ax, g["dist"], g["CBA_detrended"], g["SE"], g["StationType"],
                    LINE_COLORS[line_id], ms=3, capsize=2, elinewidth=1.0)
        ax.set_ylabel("Detrended CBA (mGal)")
        ax.set_title(f"Line {line_id}", fontweight="bold", loc="left")
        ax.grid(True, alpha=0.25, linestyle="--")
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
        # dist increases N->S from 0 (grav_utils) -> N already on the left
        ax.text(0.006, 0.96, "N", transform=ax.transAxes, ha="left", va="top",
                fontweight="bold", fontsize=11, color="0.3")
        ax.text(0.994, 0.96, "S", transform=ax.transAxes, ha="right", va="top",
                fontweight="bold", fontsize=11, color="0.3")
    np.atleast_1d(axes)[-1].set_xlabel("Distance along profile (m)")
    # One shared legend (all panels identical); neutral marker, colour = line.
    fig.legend(handles=[
        Line2D([0], [0], marker="o", color="0.3", linestyle="None", markersize=4,
               label=r"detrended CBA $\pm$ SE (colour = line)"),
        Line2D([0], [0], marker=TIE_MARKER, color="0.3", linestyle="None",
               markersize=5, label="tie station"),
    ], loc="lower center", ncol=2, frameon=True, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle("Detrended CBA residual (per line)", fontweight="bold")
    fig.tight_layout(rect=[0, 0.05, 1, 0.97])
    combo = FIG_DIR / "detrended_residuals.png"
    fig.savefig(combo, dpi=150, bbox_inches="tight")
    save_figure(fig, combo.stem, "Grav", vector=True)          # title-free thesis PDF
    print(f"Residual figure    -> {combo.relative_to(BASE)}")

    # Combined figure of the regional fits (the top panels of the per-line figures,
    # stacked): CBA + robust trend + 95% CI, one row per line.
    figf, axesf = plt.subplots(len(LINES), 1, sharey=True,   # shared y -> lines directly comparable
                               figsize=(COMBINED_W_IN, COMBINED_PANEL_H_IN * len(LINES)))
    for ax, p in zip(np.atleast_1d(axesf), fit_panels):
        x, y, se = p["x"], p["y"], p["se"]
        xm = p["xm"]
        plot_points(ax, x, y, se, p["stype"], p["color"], ms=3, capsize=2,
                    elinewidth=1.0)
        ax.plot(x, p["trend"], "--", color="0.35", lw=1.6, zorder=2)
        ax.fill_between(x, p["ym"] + (p["lo_km"] / 1000.0) * (x - xm),
                        p["ym"] + (p["hi_km"] / 1000.0) * (x - xm),
                        color="0.35", alpha=0.15, zorder=1)
        # Numbers (slope / CI / azimuth / chi2) live in the trend table, not here.
        ax.set_ylabel("CBA (mGal)")
        ax.set_title(f"Line {p['line_id']}", fontweight="bold", loc="left")
        ax.grid(True, alpha=0.25, linestyle="--")
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
        # dist increases N->S from 0 (grav_utils) -> N already on the left
        ax.text(0.006, 0.96, "N", transform=ax.transAxes, ha="left", va="top",
                fontweight="bold", fontsize=11, color="0.3")
        ax.text(0.994, 0.96, "S", transform=ax.transAxes, ha="right", va="top",
                fontweight="bold", fontsize=11, color="0.3")
    np.atleast_1d(axesf)[-1].set_xlabel("Distance along profile (m)")
    # One shared legend for all panels (neutral marker; colour = line).
    figf.legend(handles=[
        Line2D([0], [0], marker="o", color="0.3", linestyle="None", markersize=4,
               label=r"CBA $\pm$ SE (colour = line)"),
        Line2D([0], [0], marker=TIE_MARKER, color="0.3", linestyle="None",
               markersize=5, label="tie station"),
        Line2D([0], [0], color="0.35", linestyle="--", lw=1.6, label="robust trend"),
        mpatches.Patch(color="0.35", alpha=0.15, label="95% CI"),
    ], loc="lower center", ncol=4, frameon=True, bbox_to_anchor=(0.5, 0.0))
    figf.suptitle("Regional de-trend fits (per line)", fontweight="bold")
    figf.tight_layout(rect=[0, 0.05, 1, 0.97])
    fitscombo = FIG_DIR / "detrend_fits.png"
    figf.savefig(fitscombo, dpi=150, bbox_inches="tight")
    save_figure(figf, fitscombo.stem, "Grav", vector=True)     # title-free thesis PDF
    print(f"Fits figure        -> {fitscombo.relative_to(BASE)}")
    plt.show()


if __name__ == "__main__":
    main()

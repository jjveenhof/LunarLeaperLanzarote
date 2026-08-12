"""Shared building blocks for the terrain cross-section figures.

This is a LIBRARY: it defines things and runs nothing on import. It exists because
`plot_model_terrain.py` was simultaneously a script (a 250-line `main()` that writes a
thesis figure) and the de-facto library for its siblings -- `plot_freedepth_terrain.py`
imported it for the styling and the three helpers below, and `freedepth.py` had to import
it lazily INSIDE a function to avoid dragging a plotting script into a compute path.
Splitting the library half out removes both problems.

Who uses what:
  plot_model_terrain.py      styling + all three helpers  (the constrained figure)
  plot_freedepth_terrain.py  styling + gravity_profile, gpr_surface, posterior_envelope
  freedepth.py               gravity_profile only, for the LiDAR ceiling depth

Keeping the styling here is what makes the two terrain figures look like each other --
they are meant to be read side by side, so the palette, markers and panel letters must
be one definition, not two.
"""

import numpy as np
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))   # Code/Grav for grav_utils
import grav_utils as gu
import invert_tube as it

CORR = gu.PROC_DIR / "LL_gravity_corrections.csv"
# rho -> filename via grav_utils.rho_str, NOT a hardcoded "rho1p875" (finding [11]):
# a swept-density run must not silently read the canonical file.
WITHTC = gu.PROC_DIR / f"bouguer_anomaly_decay_rho{gu.rho_str(gu.RHO_DEFAULT)}_with_TC.csv"
GPR_GNSS = gu.GNSS_DIR / "Cleaned/CleanedGNSS_GPR_Lines.csv"

# Match the rest of the gravity plots: per-line QGIS palette + station-type marker
# (base square, tie triangle, regular circle). Model curves stay black, as in the
# invert_tube best-fit plots, so they read as "model" not "data".
LINE_COLORS = {2: "#0099FF", 3: "#FF5C00", 5: "#00CC80"}
STN_MARKER = {"base": "s", "tie": "v", "regular": "o"}
STN_SIZE = {"base": 7, "tie": 5, "regular": 5}   # tie matches regular (was 8: too big, hid error bars)
FIT_LS = {"circle": "-", "ellipse": "--"}
LIDAR_COLOR = "#9400D3"        # ground truth: violet, distinct from orange/green
                               # stations, black model curves and grey terrain
PICK_C = "#0072B2"             # GPR pick: solid blue line + band (not the dashed envelope)

# Panel letters baked into the figure (LaTeX sees one image; it cannot label the two
# stacked panels separately). a) = top anomaly panel, b) = bottom cross-section panel.
PANEL_LETTERS = ("a)", "b)")   # (top, bottom); set to None to switch the letters off
PANEL_LETTER_XY = (0.014, 0.965)   # axes-fraction pos from top-left; move if it crowds N
PANEL_LETTER_KW = dict(fontsize=12, fontweight="bold", va="top", ha="left", zorder=10)


def gravity_profile(line):
    """Gravity stations for a line: along-profile dist, elevation (GNSS, matched
    from the corrections file on E/N), plus the profile origin O and unit
    direction u so other datasets can be projected onto the same dist axis."""
    det = np.genfromtxt(it.DET, delimiter=",", names=True)
    m = det["Line"] == line
    dist, E, N, loc = (det["dist"][m], det["Easting"][m], det["Northing"][m],
                       det["loc_id"][m])
    corr = np.genfromtxt(CORR, delimiter=",", names=True)
    elev = np.array([corr["Elevation"][np.argmin((corr["Easting"] - e) ** 2
                                                  + (corr["Northing"] - n) ** 2)]
                     for e, n in zip(E, N)])
    # Station type (base/tie/regular) by (Line, loc_id) from the corrected file.
    w = np.genfromtxt(WITHTC, delimiter=",", names=True, dtype=None, encoding="utf-8")
    wm = w["Line"] == line
    wloc, wtype = w["loc_id"][wm], np.array([str(x) for x in w["StationType"][wm]])
    typ = np.array([wtype[np.where(wloc == lid)[0][0]] if lid in wloc else "regular"
                    for lid in loc])
    o = np.argsort(dist)
    dist, E, N, elev, typ = dist[o], E[o], N[o], elev[o], typ[o]
    # The gravity 'dist' is an exact linear (straight-axis PCA) projection of E,N,
    # so recover that map by regression and reuse it to put any other dataset on
    # the SAME axis (lines are straight to <1.5 m, so this is well posed).
    coef, *_ = np.linalg.lstsq(np.column_stack([E, N, np.ones_like(E)]), dist,
                               rcond=None)
    proj = lambda e, n: coef[0] * e + coef[1] * n + coef[2]
    return dist, elev, typ, proj


def posterior_envelope(outlines, cx, cz, nth=181, lo=16, hi=84):
    """Inner/outer +/-1 sigma (16th-84th percentile) envelope of a family of
    closed outlines, as radial percentiles about a common centre (cx, cz). This
    derives the band FROM the samples, so it agrees with the cloud everywhere --
    it shows the pick/velocity spread at the ceiling/floor and the lateral (x0)
    spread, unlike an at-fixed-geometry size scaling. Star-shaped about the centre
    is assumed (fine for the near-concentric tube family). Returns two closed
    curves (inner, outer)."""
    thg = np.linspace(-np.pi, np.pi, nth)
    R = np.empty((len(outlines), nth))
    for i, (xx, zz) in enumerate(outlines):
        th = np.arctan2(zz - cz, xx - cx)
        r = np.hypot(xx - cx, zz - cz)
        o = np.argsort(th)
        ths, rs = th[o], r[o]
        the = np.concatenate([ths - 2 * np.pi, ths, ths + 2 * np.pi])
        re = np.concatenate([rs, rs, rs])
        R[i] = np.interp(thg, the, re)
    rlo, rhi = np.percentile(R, lo, axis=0), np.percentile(R, hi, axis=0)
    return ((cx + rlo * np.cos(thg), cz + rlo * np.sin(thg)),
            (cx + rhi * np.cos(thg), cz + rhi * np.sin(thg)))


def gpr_surface(line, proj, xs, zs):
    """Dense GPR-line surface: the clean GNSS points of the GPR line (identified
    by the 'Line' column) projected onto the SAME straight axis as the gravity
    'dist' (via proj), so the two are exactly co-registered. Returns (dist, elev,
    rms-vs-stations) or None -- the RMS is a genuine independent cross-check."""
    if not GPR_GNSS.exists():
        return None
    g = np.genfromtxt(GPR_GNSS, delimiter=",", names=True, dtype=None,
                      encoding="utf-8")
    m = g["Line"] == line
    if not np.any(m):
        return None
    dist = proj(g["Easting"][m], g["Northing"][m])
    elev = g["Elevation"][m]
    o = np.argsort(dist)
    dist, elev = dist[o], elev[o]
    rms = np.sqrt(np.nanmean((np.interp(xs, dist, elev) - zs) ** 2))
    return dist, elev, rms

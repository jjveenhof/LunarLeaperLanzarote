"""
Shared helpers for the gravimetry pipeline.

Centralises everything that used to be copy-pasted across scripts:
  - Project paths (BASE, PROC_DIR, RESULTS_DIR)
  - rho filename formatting (rho_str)
  - WGS84 Somigliani normal gravity (normal_gravity)
  - Physical constants (FAC_GRAD, BOUGUER_K)
"""

import numpy as np
from pathlib import Path

BASE        = Path(__file__).resolve().parents[2]
PROC_DIR    = BASE / "Data/Gravimetry/Processed"
RESULTS_DIR = BASE / "Results/Grav"

# Output figure directories. Defined HERE so that "where does this plot land?" has one
# answer per topic. Scripts in subfolders (Inversion/, Inspect/, Adhoc/) used to each
# re-derive BASE with parents[3] while top-level scripts used parents[2] -- two spellings
# of the same path, and a trap for anyone moving a file between folders. Import these
# instead of rebuilding them; see the bootstrap note below.
INV_DIR     = RESULTS_DIR / "Inversion"          # inversion figures + artifacts
ART_DIR     = INV_DIR / "artifacts"              # inversion_io .npz artifacts
DETREND_DIR = RESULTS_DIR / "Detrend"
DECAY_DIR   = RESULTS_DIR / "Decay fitting"      # note the space -- matches disk
LSQ_DIR     = RESULTS_DIR / "LSQ"
LSQ_STATS   = LSQ_DIR / "Stats"
LSQ_LINES   = LSQ_DIR / "Lines"
CORR_DIR    = RESULTS_DIR / "Corrections"
BOUGUER_DIR = RESULTS_DIR / "Bouguer"

# Input data directories (read-only -- raw acquisition data, see the project CLAUDE.md)
GRAV_DIR    = BASE / "Data/Gravimetry"           # raw + combined, parent of Processed/
GNSS_DIR    = BASE / "Data/GNSS"

# Bootstrap for scripts in subfolders
# -----------------------------------
# Scripts are run directly (`python Inversion/plot_misfit.py`), not as a package, so a
# subfolder script cannot `import grav_utils` until Code/Grav is on sys.path. Each such
# script therefore carries ONE line before importing this module:
#
#     sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/Grav
#
# (parents[2] from Inversion/Inspect/Adhoc reaches Code/, for plot_utils.) That single
# bootstrap line is the only path arithmetic left outside this file; everything else --
# BASE and every directory under it -- comes from here.
# LiDAR cave cross-sections handed over by the LiDAR session -- ground truth for the
# inversion, and now also consumed by the GPR session. They are DATA, so they live
# under Data/ (outside the Code/ git repo) rather than next to the scripts.
LIDAR_DIR   = BASE / "Data/LiDAR"


# The one genuine cross-session data contract in the project: the LiDAR session WRITES
# these files, Grav and GPR READ them, and REFACTOR.md rule 8 protects the filenames by
# convention only. Assert the columns at the read site so a changed schema fails loudly
# here instead of silently producing a wrong overlay three plots downstream.
LIDAR_COLUMNS = ("x", "z", "easting", "northing")


def lidar_file(line):
    """Cave-outline CSV for a gravity line: columns x,z,easting,northing (the `x` is a
    legacy along-profile distance -- project easting/northing onto your own axis
    instead). Returns the path whether or not it exists; callers check."""
    return LIDAR_DIR / f"lidar_line{line}.csv"


def check_lidar_schema(path, required=LIDAR_COLUMNS):
    """Raise ValueError unless `path` has the expected LiDAR outline columns.

    Cheap (reads the header line only) and called by every LiDAR read in this session.
    A missing file is NOT an error -- callers already treat the overlay as optional and
    check existence themselves; this only polices the schema of a file that IS there.
    """
    p = Path(path)
    if not p.exists():
        return
    with open(p, "r", encoding="utf-8") as fh:
        header = fh.readline().strip().lstrip("﻿")
    cols = [c.strip() for c in header.split(",")]
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(
            f"{p.name}: LiDAR outline is missing column(s) {missing}. "
            f"Found {cols}, expected at least {list(required)}. This file is produced by "
            f"the LiDAR session and read by Grav and GPR -- if its schema really changed, "
            f"both readers and Code/REFACTOR.md rule 8 need updating together."
        )
    return cols


def load_lidar_outline(line):
    """Validated LiDAR cave outline for a gravity line, or None if the file is absent.

    Returns a numpy structured array (genfromtxt names=True), schema-checked first."""
    p = lidar_file(line)
    if not p.exists():
        return None
    check_lidar_schema(p)
    return np.genfromtxt(p, delimiter=",", names=True)

# Free-air gradient: dg/dh = -2g/R (standard geodetic value, valid at all latitudes)
# g ~ 9.807 m/s2, R ~ 6371 km -> 2*9.807/6371000 = 3.079e-6 m/s2/m = 0.3079 mGal/m
# The standard 0.3086 includes the ellipsoidal correction; at Lanzarote (29N) ~0.3085
FAC_GRAD = 0.3086         # mGal/m

# Newton's constant -- THE definition for this session. The Talwani forward model
# (Inversion/forward_polygon.py, forward_fem.py, inspect_2d_validity.py) imports this
# rather than restating it; it used to be spelled out in four places with two different
# values (6.674e-11 here, 6.6743e-11 in all three forward models).
G_NEWTON  = 6.6743e-11    # m3 kg-1 s-2 (CODATA)

# Bouguer slab factor: g_slab = 2*pi*G * (rho_SI) * h, converted to mGal
# 2*pi * G         = 2 * pi * 6.674e-11        = 4.194e-10  m3 kg-1 s-2 m-1
# rho conversion   = 1e3                        kg/m3 per g/cm3
# mGal conversion  = 1e5                        mGal per m/s2
# combined         = 4.194e-10 * 1e3 * 1e5      = 0.04192 mGal m-1 per g/cm3
#
# FROZEN: this is computed from G = 6.674e-11, the value used for every number in the
# submitted thesis -- NOT from G_NEWTON above. Recomputing it with the CODATA G shifts
# the Bouguer term by 4.5e-5 relative (max 0.009 uGal across all 130 stations, ~1000x
# below the smallest reported digit), so it would change no thesis number -- but it WOULD
# change every processed CSV at the 1e-8 level, so the on-disk chain would no longer
# bit-match the thesis. Kept pinned deliberately; see Code/Grav/QandA.md 2026-08-12.
# To unify, change 6.674e-11 to G_NEWTON here and re-baseline the golden master.
G_BOUGUER = 6.674e-11     # m3 kg-1 s-2 -- frozen at the thesis value, do not "correct"
BOUGUER_K = 2 * np.pi * G_BOUGUER * 1e3 * 1e5   # = 0.04192 mGal m-1 per g/cm3

# WGS84 Somigliani normal gravity constants
# (Blakely, Potential Theory in Gravity and Magnetic Applications)
G_E = 978032.67714        # mGal -- normal gravity at equator
K_S = 0.00193185138639
E2  = 0.00669437999013

# Default bulk density of the rock column (g/cm3) -- matches colleague
RHO_DEFAULT = 1.875


def rho_str(rho):
    """Format rho for filenames without rounding: 1.875 -> '1p875', 2.0 -> '2'."""
    return f"{rho:.3f}".rstrip("0").rstrip(".").replace(".", "p")


def sba_file(rho):
    """Path of the simple Bouguer anomaly file for a given rho."""
    return PROC_DIR / f"bouguer_anomaly_decay_rho{rho_str(rho)}.csv"


def normal_gravity(lat_deg):
    """WGS84 Somigliani formula. lat_deg in degrees, returns mGal."""
    phi = np.radians(lat_deg)
    sin2 = np.sin(phi) ** 2
    return G_E * (1 + K_S * sin2) / np.sqrt(1 - E2 * sin2)


def along_profile_distance(df):
    """
    Project all stations onto the line's principal axis (PCA of GNSS coords),
    returning a 'dist' column in metres. Stations without GNSS are linearly
    interpolated by station number.
    """
    df = df.copy().sort_values("Station").reset_index(drop=True)
    gnss = df[df["Easting"].notna()]

    if len(gnss) < 2:
        df["dist"] = df["Station"].astype(float)
        return df

    E = gnss["Easting"].values
    N = gnss["Northing"].values
    Ec = E - E.mean()
    Nc = N - N.mean()

    # Principal axis via 2x2 covariance eigen-decomposition
    cov      = np.cov(np.stack([Ec, Nc]))
    eigvals, eigvecs = np.linalg.eigh(cov)
    axis     = eigvecs[:, eigvals.argmax()]   # unit vector along line

    proj = Ec * axis[0] + Nc * axis[1]
    # Pin the sign so 'dist' increases toward the SOUTH, i.e. origin (0) at the
    # NORTHERN end. Plots then read N->S left->right WITHOUT inverting the x-axis,
    # matching the GPR sections, and the coordinate is deterministic (the PCA
    # eigenvector sign is otherwise arbitrary and differed line to line).
    if np.corrcoef(proj, N)[0, 1] > 0:         # proj grows northward -> flip
        proj = -proj
    proj -= proj.min()                         # origin (0) at the northern end

    df.loc[gnss.index, "dist"] = proj

    # Linear interpolation for GNSS-less stations (e.g. orphan bases)
    df["dist"] = (df.set_index("Station")["dist"]
                    .interpolate(method="index")
                    .values)
    return df

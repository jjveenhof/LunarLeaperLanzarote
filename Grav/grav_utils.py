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

# Free-air gradient: dg/dh = -2g/R (standard geodetic value, valid at all latitudes)
# g ~ 9.807 m/s2, R ~ 6371 km -> 2*9.807/6371000 = 3.079e-6 m/s2/m = 0.3079 mGal/m
# The standard 0.3086 includes the ellipsoidal correction; at Lanzarote (29N) ~0.3085
FAC_GRAD = 0.3086         # mGal/m

# Bouguer slab factor: g_slab = 2*pi*G * (rho_SI) * h, converted to mGal
# 2*pi * G         = 2 * pi * 6.674e-11        = 4.194e-10  m3 kg-1 s-2 m-1
# rho conversion   = 1e3                        kg/m3 per g/cm3
# mGal conversion  = 1e5                        mGal per m/s2
# combined         = 4.194e-10 * 1e3 * 1e5      = 0.04192 mGal m-1 per g/cm3
G_NEWTON  = 6.674e-11     # m3 kg-1 s-2
BOUGUER_K = 2 * np.pi * G_NEWTON * 1e3 * 1e5    # = 0.04192 mGal m-1 per g/cm3

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
    proj -= proj.min()                         # shift so origin = 0

    df.loc[gnss.index, "dist"] = proj

    # Linear interpolation for GNSS-less stations (e.g. orphan bases)
    df["dist"] = (df.set_index("Station")["dist"]
                    .interpolate(method="index")
                    .values)
    return df

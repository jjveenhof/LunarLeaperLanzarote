"""
Fast analytic 2D forward model: gravity of a uniform polygon (Talwani 1959).

Closed-form per-edge line integral -> exact for ANY 2D cross-section, vectorised
over sensors in pure numpy (microseconds, no pyGIMLi). An ellipse is just a
finely-sampled polygon; real cave outlines work the same way. This is what makes
fast uncertainty estimation (e.g. Monte-Carlo over the GPR depth picks) practical.

Conventions: surface is flat at depth 0; depth is positive DOWNWARD; the modelled
g_z is the void anomaly directly (compare to the detrended CBA residual, in mGal).

Runs in ANY env (no pyGIMLi needed):
    C:/Users/jj_ve/miniconda3/envs/GPR_plotting_LL/python.exe forward_polygon.py
"""

import numpy as np

G = 6.6743e-11          # m^3 kg^-1 s^-2
RHO_HOST = 1875.0       # kg/m^3
MGAL = 1e5              # 1 m/s^2 = 1e5 mGal


def polygon_gz(sensor_x, verts, rho_contrast=-RHO_HOST):
    """
    Vertical gravity (mGal) of a uniform 2D polygon at surface points sensor_x.

    sensor_x : (M,) along-profile positions on the flat surface (z = 0)
    verts    : (N, 2) polygon vertices (x, depth>0), any consistent ordering
    rho_contrast : void - host density (kg/m^3)
    """
    verts = np.asarray(verts, float)
    xs = np.asarray(sensor_x, float)[:, None]            # (M, 1)
    vx, vz = verts[:, 0], verts[:, 1]

    x1 = vx[None, :] - xs                                 # (M, N)
    z1 = vz[None, :] + np.zeros_like(xs)
    x2 = np.roll(vx, -1)[None, :] - xs
    z2 = np.roll(vz, -1)[None, :] + np.zeros_like(xs)

    dx, dz = x2 - x1, z2 - z1
    R = dx * dx + dz * dz
    R = np.where(R == 0.0, np.nan, R)                     # skip degenerate edges
    r1 = np.hypot(x1, z1)
    r2 = np.hypot(x2, z2)
    th1 = np.arctan2(z1, x1)
    th2 = np.arctan2(z2, x2)

    P = (x1 * z2 - x2 * z1) / R                           # = (x1 dz - z1 dx)/R
    Q = dx * (th1 - th2) + dz * np.log(r2 / r1)
    g = np.nansum(P * Q, axis=1)
    return 2.0 * G * rho_contrast * g * MGAL


def ellipse_vertices(a, b, x0, depth, n=180):
    """(n,2) vertices of an ellipse: semi-axes a (horizontal), b (vertical),
    centre (x0, depth)."""
    t = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([x0 + a * np.cos(t), depth + b * np.sin(t)])


def _cylinder_analytic(sensor_x, radius, depth, x0=0.0, rho_contrast=-RHO_HOST):
    """Exact g_z (mGal) of a 2D infinite horizontal cylinder (validation)."""
    x = np.asarray(sensor_x, float) - x0
    return 2 * np.pi * G * rho_contrast * radius**2 * depth / (x**2 + depth**2) * MGAL


def _selftest():
    x = np.arange(-200, 201, 2.0)

    print("== polygon (circle) vs exact analytic cylinder ==")
    for R, z, n in [(10.0, 30.0, 64), (10.0, 30.0, 256), (15.0, 25.0, 256)]:
        gz_poly = polygon_gz(x, ellipse_vertices(R, R, 0.0, z, n))
        gz_an = _cylinder_analytic(x, R, z)
        rel = np.max(np.abs(gz_poly - gz_an)) / np.max(np.abs(gz_an))
        print(f"  R={R:.0f} z={z:.0f} n={n:>3}  peak_poly={gz_poly[np.argmin(np.abs(x))]:+.4f}"
              f"  peak_an={gz_an[np.argmin(np.abs(x))]:+.4f}  max rel.err={rel:.2e}")

    print("\n== ellipse example (no analytic to compare; sanity) ==")
    gz = polygon_gz(x, ellipse_vertices(a=20.0, b=5.5, x0=0.0, depth=10.5, n=256))
    print(f"  a=20 b=5.5 z=10.5  peak={gz[np.argmin(np.abs(x))]:+.4f} mGal")


if __name__ == "__main__":
    _selftest()

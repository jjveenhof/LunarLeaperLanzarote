"""
2D forward model for the La Corona lava tube gravity anomaly.

Adapted from Yara Luginbuehl's Lunar-Leaper pyGIMLi model
(Other data and scripts/LL_YaraLug), stripped of the lunar/rille/regolith
specifics. Here we model only the ANOMALY: a homogeneous half-space (density
contrast 0) with a void (the tube, contrast = -rho_host) and a FLAT top
surface -- because our data is already terrain-corrected CBA, so topography
must NOT be re-introduced (that would double-count the terrain effect).

The modelled vertical response is therefore directly comparable to the
detrended CBA residual (no further corrections applied).

ENVIRONMENT: run with the `pygimli` conda env, NOT GPR_plotting_LL:
    C:/Users/jj_ve/miniconda3/envs/pygimli/python.exe

Self-test (python forward_lavatube.py) checks the pyGIMLi response against the
analytic 2D infinite horizontal cylinder, which also fixes the output units.
"""

import numpy as np
import pygimli as pg
import pygimli.meshtools as mt
from pygimli.physics.gravimetry import solveGravimetry

G = 6.6743e-11          # m^3 kg^-1 s^-2
RHO_HOST = 1875.0       # kg/m^3 -- same density as the Bouguer reduction
MGAL = 1e5              # 1 m/s^2 = 1e5 mGal


def lavatube_response(sensor_x, radius, depth, x0=0.0, rho_contrast=-RHO_HOST,
                      half_width=800.0, half_depth=300.0,
                      mesh_area=150.0, cave_area=3.0, quality=33):
    """
    Vertical gravity anomaly (mGal) of a circular void in a flat half-space.

    sensor_x : array, along-profile positions (m); surface is flat at y = 0
    radius   : tube radius (m)
    depth    : depth to tube centre (m, positive down)
    x0       : horizontal position of the tube centre (m)
    rho_contrast : void - host density (kg/m^3), i.e. -RHO_HOST for an air void
    """
    sensor_x = np.asarray(sensor_x, dtype=float)

    world = mt.createPolygon(
        [(-half_width, 0.0), (half_width, 0.0),
         (half_width, -half_depth), (-half_width, -half_depth)],
        isClosed=True, addNodes=3, marker=1, boundaryMarker=1)
    cave = mt.createCircle(pos=[x0, -depth], radius=radius, marker=2,
                           boundaryMarker=10, area=cave_area)
    mesh = mt.createMesh(world + cave, quality=quality, area=mesh_area)

    dRho = pg.solver.parseMapToCellArray([[1, 0.0], [2, rho_contrast]], mesh)

    pnts = np.column_stack([sensor_x, np.zeros_like(sensor_x)])
    dg, dgz = solveGravimetry(mesh, dRho, pnts, complete=True)
    # dgz columns are [dgx, dgy, dgz]; take the vertical component.
    gz = np.asarray(dgz)[:, 2] if np.ndim(dgz) == 2 else np.asarray(dg)[:, 2]
    return gz, mesh


def cylinder_analytic(sensor_x, radius, depth, x0=0.0, rho_contrast=-RHO_HOST):
    """Analytic g_z (mGal) of a 2D infinite horizontal cylinder (validation)."""
    x = np.asarray(sensor_x, float) - x0
    gz = 2 * np.pi * G * rho_contrast * radius**2 * depth / (x**2 + depth**2)
    return gz * MGAL


def _selftest():
    import time
    x = np.arange(-200, 201, 5.0)
    central = np.abs(x) <= 60          # where the signal is well above ~0
    for radius, depth in [(10.0, 30.0), (20.0, 50.0)]:
        t0 = time.time()
        gz_pg, mesh = lavatube_response(x, radius, depth)
        dt = time.time() - t0
        gz_an = cylinder_analytic(x, radius, depth)
        K = gz_an[central] / gz_pg[central]    # raw -> mGal factor, per point
        print(f"\nR={radius:.0f} z={depth:.0f}  cells={mesh.cellCount()}  "
              f"forward={dt:.1f}s")
        print(f"  analytic peak (mGal): {gz_an[np.argmin(np.abs(x))]:+.4f}")
        print(f"  scale K=mGal/raw  mean={K.mean():.4f}  std={K.std():.4f}  "
              f"(10*pi={10*np.pi:.4f})")


if __name__ == "__main__":
    _selftest()

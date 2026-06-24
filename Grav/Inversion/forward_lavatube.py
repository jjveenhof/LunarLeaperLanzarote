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


def build_model(radius, depth, x0=0.0, rho_contrast=-RHO_HOST,
                half_width=800.0, half_depth=300.0,
                mesh_area=150.0, cave_area=3.0, quality=33, n_segments=36):
    """
    Build the flat-top half-space + circular void model.

    radius   : tube radius (m)
    depth    : depth to tube centre (m, positive down)
    x0       : horizontal position of the tube centre (m)
    rho_contrast : void - host density (kg/m^3), i.e. -RHO_HOST for an air void
    n_segments   : polygon sides for the void (36 -> ~0.1% area error vs a circle)

    Returns (geom, mesh, dRho).
    """
    world = mt.createPolygon(
        [(-half_width, 0.0), (half_width, 0.0),
         (half_width, -half_depth), (-half_width, -half_depth)],
        isClosed=True, addNodes=3, marker=1, boundaryMarker=1)
    cave = mt.createCircle(pos=[x0, -depth], radius=radius, nSegments=n_segments,
                           marker=2, boundaryMarker=10, area=cave_area)
    geom = world + cave
    mesh = mt.createMesh(geom, quality=quality, area=mesh_area)
    dRho = pg.solver.parseMapToCellArray([[1, 0.0], [2, rho_contrast]], mesh)
    return geom, mesh, dRho


def lavatube_response(sensor_x, radius, depth, **kw):
    """
    Vertical gravity anomaly (mGal) of a circular void in a flat half-space,
    at along-profile positions sensor_x on the flat surface (y = 0).
    Extra keywords pass through to build_model. Returns (gz_mGal, mesh).
    """
    sensor_x = np.asarray(sensor_x, dtype=float)
    _, mesh, dRho = build_model(radius, depth, **kw)

    pnts = np.column_stack([sensor_x, np.zeros_like(sensor_x)])
    gvec = solveGravimetry(mesh, dRho, pnts, complete=True)
    # complete=True -> gvec[0] is the N x 3 [dgx, dgy, dgz] array (as Yara used).
    gz = np.asarray(gvec[0])[:, 2]
    return gz, mesh


def cylinder_analytic(sensor_x, radius, depth, x0=0.0, rho_contrast=-RHO_HOST):
    """Analytic g_z (mGal) of a 2D infinite horizontal cylinder (validation)."""
    x = np.asarray(sensor_x, float) - x0
    gz = 2 * np.pi * G * rho_contrast * radius**2 * depth / (x**2 + depth**2)
    return gz * MGAL


def _selftest():
    x = np.arange(-200, 201, 5.0)
    i0 = int(np.argmin(np.abs(x)))     # peak index (x = 0)

    print("== scale factor across geometry (peak x=0) ==")
    for radius, depth in [(10.0, 30.0), (20.0, 50.0), (15.0, 25.0)]:
        gz_pg, mesh = lavatube_response(x, radius, depth)
        gz_an = cylinder_analytic(x, radius, depth)
        K = gz_an[i0] / gz_pg[i0]
        print(f"  R={radius:>4.0f} z={depth:>4.0f}  cells={mesh.cellCount():>6}  "
              f"raw_peak={gz_pg[i0]:+.6g}  an_peak(mGal)={gz_an[i0]:+.4f}  "
              f"K=mGal/raw={K:.4f}")

    print(f"\n  reference constants: 10*pi={10*np.pi:.4f}  1e5={1e5:.0f}")

    print("\n== mesh convergence (R=10 z=30, raw peak) ==")
    for area in [600.0, 150.0, 40.0]:
        gz_pg, mesh = lavatube_response(x, 10.0, 30.0, mesh_area=area,
                                        cave_area=max(area / 30, 1.0))
        print(f"  mesh_area={area:>5.0f}  cells={mesh.cellCount():>6}  "
              f"raw_peak={gz_pg[i0]:+.6g}")


if __name__ == "__main__":
    _selftest()

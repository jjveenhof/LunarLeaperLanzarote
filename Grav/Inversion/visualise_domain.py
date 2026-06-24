"""
Visualise the forward-model domain: flat-top half-space, void and mesh.

Geometry uses the Line 3 GPR constraints (ceiling at 5 m, cave height 11 m ->
floor at 16 m), modelled here as a CIRCLE of radius 5.5 m at 10.5 m centre depth.
The width is what the inversion will solve for; this figure only shows the
gridding, extent and layout. Stations are deliberately NOT drawn: their position
relative to the tube centre is not known a priori (it comes from GPR or is fit).

Run with the pygimli env.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import pygimli as pg
from pathlib import Path
from forward_lavatube import build_model, RHO_HOST

BASE = Path(__file__).resolve().parents[3]

# --- Line 3 geometry (GPR ceiling + height; circular illustration) ------------
CEILING, HEIGHT = 5.0, 11.0          # m (GPR)
FLOOR = CEILING + HEIGHT             # 16 m
RADIUS = HEIGHT / 2.0                # 5.5 m
DEPTH = CEILING + RADIUS             # 10.5 m, to tube centre

geom, mesh, dRho = build_model(RADIUS, DEPTH)
print(f"mesh cells: {mesh.cellCount()}")

# --- plot ---------------------------------------------------------------------
VOID_C, HOST_C = "#08306b", "#deebf7"
cmap2 = mcolors.ListedColormap([VOID_C, HOST_C])   # low (-1875)->void, high (0)->host

# Zoom window from the tube extent (a few tube-widths wide, down past the floor).
zx = 45.0
zy0, zy1 = -(FLOOR + 12.0), 6.0

fig, (axf, axz) = plt.subplots(2, 1, figsize=(11, 8.5))

for ax, zoom in [(axf, False), (axz, True)]:
    # showMesh on both panels -- the full view shows cell-size variation.
    pg.show(mesh, dRho, ax=ax, cMap=cmap2, colorBar=False, showMesh=True)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("depth (m)")
    if zoom:
        ax.axhline(-CEILING, color="k", ls="--", lw=1.0)
        ax.axhline(-FLOOR, color="k", ls=":", lw=1.0)
        ax.set_xlim(-zx, zx)
        ax.set_ylim(zy0, zy1)
        ax.set_title("Zoom near the surface (mesh shown)")
    else:
        ax.add_patch(mpatches.Rectangle((-zx, zy0), 2 * zx, zy1 - zy0,
                     fill=False, ec="k", ls="--", lw=1.0))
        ax.set_title("Full modelling domain (1600 x 300 m); dashed box = zoom below")

handles = [
    mpatches.Patch(color=VOID_C, label=rf"void  $\Delta\rho=-{RHO_HOST:.0f}$ kg/m$^3$"),
    mpatches.Patch(color=HOST_C, label=r"host  $\Delta\rho=0$"),
    mlines.Line2D([], [], color="k", ls="--", label=f"GPR ceiling ({CEILING:.0f} m)"),
    mlines.Line2D([], [], color="k", ls=":", label=f"GPR floor ({FLOOR:.0f} m)"),
]
axz.legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.9)

fig.suptitle("Forward-model domain  --  Line 3 GPR constraints: "
             f"ceiling {CEILING:.0f} m, floor {FLOOR:.0f} m (circle R={RADIUS:.1f} m)",
             fontweight="bold")

out = BASE / "Results/Grav/Inversion"
out.mkdir(parents=True, exist_ok=True)
p = out / "model_domain.png"
fig.tight_layout()
fig.savefig(p, dpi=140, bbox_inches="tight")
print(f"saved -> {p.relative_to(BASE)}")

"""
How valid is the 2D (infinite-tube) assumption for Line 3?

Two things are conflated when we say "not 2D":
  (1) the tube has FINITE length  -- tested here,
  (2) a collapse PIT makes a localised 3D void -- NOT tested here (needs the pit
      position relative to the Line 3 crossing; handled separately).

We extrude the best-fit cross-section along the tube axis y over a finite length
L and integrate the 3D point-mass kernel analytically in y:

    int_{-L/2}^{L/2} z / (D^2 + y^2)^{3/2} dy = z * L / (D^2 * sqrt(D^2 + L^2/4))

with D^2 = (x_s - x_c)^2 + z_c^2. As L -> inf this gives 2/D^2 -> the 2D result.
The finite/infinite amplitude ratio per cell is F = 1/sqrt(1 + (2D/L)^2), so the
2D error is set by L relative to the depth D (~10 m here), NOT by it being a tube.

Run in any env (pure numpy).
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

G, MGAL, RHO = 6.6743e-11, 1e5, -1875.0
BASE = Path(__file__).resolve().parents[3]
FIG = BASE / "Results/Grav/Inversion"

# best-fit Line 3 ellipse cross-section
A, B, CZ, X0 = 8.5, 5.5, 10.5, 0.0        # half-width, half-height, centre depth, x at 0
xs = np.arange(-60, 61, 2.0)              # profile (tube crossing at 0)

# discretise the cross-section into cells
gx, gz = np.meshgrid(np.arange(-A, A, 0.4), np.arange(CZ - B, CZ + B, 0.4))
inside = ((gx - X0) / A) ** 2 + ((gz - CZ) / B) ** 2 <= 1.0
xc, zc = gx[inside], gz[inside]
dA = 0.4 * 0.4


def gz_finite(L):
    """gz (mGal) along xs for the cross-section extruded over length L (inf -> 2D)."""
    out = np.empty_like(xs)
    for i, x in enumerate(xs):
        D2 = (x - xc) ** 2 + zc ** 2
        if np.isinf(L):
            yint = 2.0 / D2                                  # 2D limit
        else:
            yint = L / (D2 * np.sqrt(D2 + L ** 2 / 4))
        out[i] = G * RHO * dA * np.sum(zc * yint) * MGAL
    return out


Ls = [25.0, 50.0, 100.0, 200.0, np.inf]
curves = {L: gz_finite(L) for L in Ls}
peak2d = curves[np.inf].min()

print("tube length L (m) | peak (mGal) | % of 2D")
for L in Ls:
    p = curves[L].min()
    print(f"  {('inf' if np.isinf(L) else f'{L:.0f}'):>14} | {p:+.4f}    | {100*p/peak2d:5.1f}%")

fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))
for L in Ls:
    lbl = "infinite (2D)" if np.isinf(L) else f"L = {L:.0f} m"
    a1.plot(xs, curves[L], label=lbl)
a1.set_xlabel("x across tube (m)"); a1.set_ylabel("g (mGal)")
a1.set_title("Anomaly vs finite tube length"); a1.legend(fontsize=8)
a1.grid(True, alpha=0.25, ls="--")

Lscan = np.arange(10, 300, 5.0)
ratio = [gz_finite(L).min() / peak2d for L in Lscan]
a2.plot(Lscan, np.array(ratio) * 100, color="#0099FF")
a2.axhline(100, color="0.6", ls="--", lw=0.8)
a2.set_xlabel("tube length L (m)"); a2.set_ylabel("peak as % of 2D")
a2.set_title(f"2D recovered for L >> depth (~{CZ:.0f} m)")
a2.grid(True, alpha=0.25, ls="--")

fig.suptitle("Line 3: finite-tube-length test of the 2D assumption", fontweight="bold")
fig.tight_layout()
FIG.mkdir(parents=True, exist_ok=True)
p = FIG / "inspect_2d_validity.png"
fig.savefig(p, dpi=140)
print(f"saved -> {p.relative_to(BASE)}")

"""
Diagnostic: illustrate the pyGIMLi-vs-analytic scaling issue.

For a circular void, the analytic 2D infinite-cylinder formula is EXACT outside
the body, so pyGIMLi (if used right, with correct units) should match it up to a
single constant factor for ALL geometries. We plot both, and the ratio, to show
that the factor is not a single constant -> something in the pyGIMLi setup is off.

Run with the pygimli env.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from forward_lavatube import lavatube_response, cylinder_analytic

BASE = Path(__file__).resolve().parents[3]   # Thesis Lunar Leaper/

x = np.arange(-200, 201, 5.0)
cases = [(10.0, 30.0), (20.0, 50.0), (15.0, 25.0)]
colors = ["#0099FF", "#FF5C00", "#00CC80"]

fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(10, 11))

for (R, z), c in zip(cases, colors):
    gz_pg, _ = lavatube_response(x, R, z)
    gz_an = cylinder_analytic(x, R, z)
    lbl = f"R={R:.0f}, z={z:.0f}"
    a1.plot(x, gz_an, color=c, label=lbl)
    a2.plot(x, gz_pg, color=c, label=lbl)
    ratio = gz_an / gz_pg
    a3.plot(x, ratio, color=c, label=f"{lbl}  (peak K={ratio[np.argmin(np.abs(x))]:.1f})")

a1.set_title("Analytic 2D cylinder (EXACT outside the body)")
a1.set_ylabel("g_z (mGal)")
a2.set_title("pyGIMLi raw output (same geometries)")
a2.set_ylabel("g_z (raw pyGIMLi units)")
a3.set_title("Ratio analytic / pyGIMLi  --  if it were just units, all 3 lines "
             "would lie on ONE flat horizontal line")
a3.set_ylabel("mGal per raw unit")
a3.set_xlabel("x (m)")
for a in (a1, a2, a3):
    a.grid(True, alpha=0.3, ls="--")
    a.legend(fontsize=8)

out = BASE / "Results/Grav/Inversion"
out.mkdir(parents=True, exist_ok=True)
p = out / "diag_pygimli_scaling.png"
fig.tight_layout()
fig.savefig(p, dpi=140, bbox_inches="tight")
print(f"saved -> {p.relative_to(BASE)}")

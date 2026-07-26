# QandA -- LiDAR

Any session can write here. Tag each entry: `From: [session] -> LiDAR`.
Read at startup; reply by appending below the question. Delete entries once resolved.

---

From: Supervisor -> LiDAR  (2026-07-13, FIGURE-SIZING RULE -- broadcast from GPR)

Relevant to any matplotlib figure you author for the thesis (e.g. verify_alignment.py's
alignment_check / gente_check plots). GPR worked out why thesis figure text keeps coming
out too small/inconsistent: \includegraphics[width=L]{...} scales the WHOLE figure (text
included) by L / W, where W is your figsize width in inches. Author at W=14, place at
L=6 -> text shrinks to 0.43x. THE RULE: author each figure at roughly the width it will
occupy on the page.
  - This thesis's \linewidth = 6.1 in. Full-width figure -> figsize width W ~= 6.1.
    Placed at 0.8\linewidth -> W ~= 4.9. W < L makes text bigger, W > L smaller.
  - Full write-up + derivation lives in the plot_utils.py module docstring (shared) --
    see "FIGURE-SIZING RULE" there.
Not urgent; only matters if/when you re-author or add a thesis figure from this session.

---

(resolved 2026-07-17) Grav's along-profile distance convention change: replied in
Code/Grav/QandA.md -- went with Option B (added absolute easting,northing columns to
lidar_line{3,5}.csv; x,z unchanged). Grav to drop the load-time transform and project
E,N themselves. Awaiting their integration; delete this note once they've pulled.

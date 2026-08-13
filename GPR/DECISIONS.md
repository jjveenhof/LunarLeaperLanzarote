# GPR -- decisions a successor cannot re-derive from the code

Each entry is a choice whose *reason* is invisible in the code: re-reading the scripts
would not reveal it, and a successor could innocently undo it. For WHAT the code does
and HOW to run it, see `README.md`; this file is only the WHY behind non-obvious
choices.

---

## 1. Wave velocity is v = 0.125 m/ns for BOTH L3 and L5 -- picked BLIND of LiDAR
Date settled: 2026-07-16.

Velocity was chosen by diffraction-collapse on the migration velocity scans
(`migrate_velocity_scan.py` HTMLs): the value that best focuses diffraction hyperbolae.
Diffraction collapse looks reasonable across ~0.10-0.13 m/ns; 0.125 is the single chosen
value, with a stated uncertainty of 0.015 m/ns in the thesis.

**Constraint that MUST be preserved: LiDAR may NOT be used to justify the velocity.** The
whole point of the GPR pick is that it is blind to the cave geometry, so it can then be
*validated* against the LiDAR ceiling depth independently. Using LiDAR to tune v would
collapse that validation into circular reasoning. A successor re-tuning v "because the
LiDAR says so" would silently break the argument the thesis rests on. Diffraction collapse
is the ONLY admissible evidence for the pick.

Both lines are flagged `migrate: true` at `velocity: 0.125` in their `_params.json`; L5 was
re-migrated from an earlier 0.11 to 0.125 on 2026-07-16.

## 2. Line 2 is deliberately NOT migrated
Line 2 stays a processed/topo profile only -- no migration pick, no `migrate: true`. This is
a data-quality decision, not an oversight, so do not "finish the job" by migrating it:
- fewest stacks of any line (weakest S/N),
- slack-tape positioning in the field (least trustworthy trace geometry),
- Line 2 100 MHz carries hardware spectral notches at ~75 and ~160 MHz (pulsEKKO antenna
  housing geometry, NOT geology). Those frequency bins are dead; SVD/eigenimage removal and
  spectral whitening were both trialled and neither removes them (see the two `plot_l2_*`
  figures and `Legacy/make_variant.py`). No processing fix exists.

## 3. Full 3-D petal migration is OUT OF SCOPE -- the method is 2-D Stolt on straight sub-segments
The flower petals curve, but they were migrated by running the existing 2-D Stolt code on
STRAIGHT sub-segments only (`SEGMENTS` in `plot_petal_migration_3d.py`), then draping the
results flat-datum in 3-D. This is a deliberate scope boundary: proper 3-D migration was
judged out of scope for the thesis. A successor should extend `SEGMENTS`, not reach for a
3-D migration algorithm, unless the scope is explicitly reopened.

## 4. The two `load_gnss_fp` copies stay separate -- do not merge them
`topo_correction.py` and `flowerpetal_io.py` each define an identical two-line
`load_gnss_fp`. This duplication is intentional; both call sites carry a comment saying so.
Merging them would either invert the dependency direction the phase-2 splits established
(a compute core importing from a plot-side module) or perturb the golden-mastered topo NPZ.
The duplicated content is the frozen 3-item list `['FP1','FP2','FP3']`, which cannot drift.
The near-identical `build_elevation_interp` / `build_track_interps` pair stays separate for
the same reason (see comments at both sites).

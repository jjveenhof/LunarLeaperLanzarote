# LiDAR session -- decision log

Why things are the way they are, for facts a successor cannot re-derive from the code
or CLAUDE.md alone. See `CLAUDE.md` for "what is true now"; this file is "why."

---

## `Transect contours/` is the canonical source for the L3/L5 cross-sections (2026-08-12)

`LiDAR La Corona/Transect contours/Tunnel segment for L{3,5} contour.txt` are dedicated,
denser slab extractions made specifically for `slice_tube.py` (L3: 1368 slab points vs
688 from a generic crop of `Reregistered clouds/PF_tube_after.txt`). `slice_tube.DEFAULT_SOURCE`
originally pointed line 3 at the generic crop instead -- a near-miss that reproduced the
right INTEGER area (203 either way) but a different exact outline (176 vertices vs the
deployed CSV's 172; area 203.16 vs 203.27). Found and fixed during the phase-2 refactor
when `goldenmaster.py` caught the byte-level mismatch; full trail in the root `QandA.md`
(2026-08-11/12 rule-3 thread) and `REFACTOR_FINDINGS.md`.

Line 5 was never affected -- its two candidate sources (`Transect contours/` and
`Reregistered clouds/Gente_tunnel_after.txt`) were verified to give IDENTICAL results
(2056 slab points, 180 vertices, 182 m^2 either way), so `DEFAULT_SOURCE[5]` was left on
the `Reregistered clouds/` export rather than switched for no reason.

**If a cross-section ever needs regenerating, use `Transect contours/` for line 3.** Do
not substitute a "close enough" crop from `Reregistered clouds/` -- it will round to the
same integer area and look fine, which is exactly how this got lost the first time.

## E,N are derived from ROUNDED x, not full-precision x (2026-08-12)

`lidar_line{3,5}.csv`'s `easting,northing` columns are computed from `x` AFTER `x` is
rounded to the CSV's write precision (4 decimals), not before. This is deliberate, not
an oversight -- see the comment at the rounding site in `slice_tube.py`'s `main()`.

Why: the deployed `lidar_line3.csv` (the one cited in the thesis) had its E,N columns
added by a one-off script, `augment_en.py`, that no longer exists anywhere in the
project -- I searched the whole tree and could not find it. That script read `x` back
OUT of the already-written, already-rounded CSV text and derived E,N from that rounded
value. A "more precise" live implementation (derive E,N from full-precision x, round
once at the end) produces E,N that differ from the deployed file by ~1e-4 m (0.1 mm) at
a couple of rows -- physically meaningless, but enough to fail `goldenmaster.py`'s
byte-exact check.

Two options existed: re-baseline the golden master to the "more precise" convention
(overwriting the only surviving copy of a file whose generator is lost), or make
`slice_tube.py` deliberately match the deployed convention going forward. Chose the
latter -- round-x-then-derive is also arguably the MORE internally consistent choice
anyway (a consumer reading `x` and a consumer reading `easting,northing` then agree on
the same point to the last written digit, which full-precision-then-round does not
guarantee). `slice_tube.py --line {3,5}` now reproduces both deployed CSVs bit-for-bit;
verified via `goldenmaster.py check` on a live (not `--no-write`) run of both lines.

**If this convention is ever "cleaned up" back to full-precision-then-round, it will
silently break `goldenmaster.py` by ~1e-4 m at ~2 rows.** That is expected, not a bug --
see the comment at the rounding site before "fixing" it.

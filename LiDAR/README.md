# LiDAR session

Point-cloud processing for the La Corona lava tube -- CloudCompare re-registration of the
scans at the two measured sites, and the Python tooling that verifies that registration
and derives the tube cross-sections used by the gravity inversion.

`DECISIONS.md` holds facts a successor cannot re-derive from the code; read it if
something here looks arbitrary. Thesis figure/table -> producer mapping is in
`Code/TRACEABILITY.md`.

## Run everything

```
python run_all.py
```

Regenerates every output that does not need a manual CloudCompare step:
`Data/LiDAR/lidar_line{3,5}.csv`, `alignment_check.png`, `gente_check.png`, and the
`gt_metrics.py` printed numbers including the vertical-budget table. Stops on the first
failure rather than running on with a broken step.

**Not covered:** the re-registration itself. See Reproducibility below before assuming
otherwise.

## Where things live

**Code (here, in git).** `las_tools.py`, `verify_alignment.py` + `verify_alignment_io.py`,
`slice_tube.py`, `recover_transform.py`, `gt_metrics.py`, `run_all.py`, the three
regression checks, and `alignment_transforms.txt` -- the reproducible record of every
final transform (net 4x4 per mover, component transforms, RMS, verification results).

**Data (large, outside git).** `../../LiDAR La Corona/` -- the originals `LaCorona.bin` and
`LaCoronaUnshifted.bin` (CloudCompare native CCB2), and `Transect contours/`, which holds
the canonical L3/L5 cross-section source exports. Use those, not a close-enough crop; see
`DECISIONS.md`.

**Scratch: there is none, deliberately.** `C:\Users\jj_ve\lidar_scratch` was deleted
2026-08-11 -- 579 MB of superseded CloudCompare re-exports read by nothing. Do not
recreate it: this project is handed over as a folder, so anything outside that folder is
invisible to whoever receives it and has no backup. Put bulky intermediates inside the
tree and gitignore them.

## The data

`LaCorona.bin` holds 5 substantial clouds plus many tiny marker objects. The site data is
a merged cloud carrying an `Original cloud index` scalar field (sources 0-6). At the
junction (~650630, 3227150) the three relevant subsets are:

| Index | Colour | What it is |
|---|---|---|
| 0 | blue | SE passage -- trusted, correct orientation |
| 1 | dark green | Big NW passage -- misaligned, swung anticlockwise |
| 2 | light green | Small junction patch, the "bandaid" between the two |

Cloud lineage: 1 = all data; 2 = surface sub-cloud removed; 3 = cropped to the fieldwork
area; 4 = cloud 3 with distance-to-surface computed and nonsensical points deleted. Cloud
0 (the one with RGB) is unrelated regional topography about 7 km north.

## CloudCompare workflow (the alignment task)

Blue is the reference; the greens move to it. **Not a rigid body** -- align in sequence:
first move light green (idx 2) onto blue (idx 0), then dark green (idx 1) onto the moved
idx 2. Hoped to be a Z-axis-only rotation plus horizontal translation; check residuals for
any tilt.

Work on a copy (`LaCorona_aligning.bin`). Split the working crop by `Original cloud index`
via Edit > Scalar fields > Filter By Value, then use the interactive Translate/Rotate tool
with rotation locked to Z, copying each 4x4 matrix out of the Console as you go. The crop
must include enough of blue's SE length to constrain the swing angle -- the junction patch
alone is not enough.

Export aligned clouds as ASCII XYZ (File > Save As > ASCII cloud). Target CRS is EPSG:4083
(REGCAN95 / UTM zone 28N), already shifted to match the GPR and GNSS data.

## The Python tooling

- **`las_tools.py`** -- reads X/Y/Z and `Original cloud index` straight from LAS byte
  offsets, because laspy cannot parse these clouds' points (a duplicate "C2C absolute
  distances" field). Asserts loudly rather than silently misreading if a file's header,
  record layout, or the scalar field's byte width differs from what it assumes.
- **`verify_alignment.py`** (CLI + plotting) and **`verify_alignment_io.py`** (loaders and
  `residual()`, split out 2026-08-11 so the data side is readable without the ~220 lines of
  multi-panel plotting). Produces NN residuals and the before/after thesis figures:
  `alignment_check.png` (Puerta Falsa) and `gente_check.png` (`--gente`). Each has
  before/after plan panels plus W-E and N-S cross-sections with Z shared per row.
  `--las CLOUD.las` gives the single-cloud baseline. Residuals are reported by distance
  threshold, which isolates the genuine overlap; the baseline idx2 -> idx0 is mean 8.7 /
  median 5.6 m.
- **`gt_metrics.py`** -- registration-quality metrics for the two measured jameos on three
  beats: how far off (rotation-aware point displacement), tie to independent RTK/drone
  control, and internal surface fit. Establishes the ground-truth **vertical** accuracy of
  the L3/L5 cross-sections at ~0.2 m (RSS chains: L3 0.24 m, L5 0.21 m). Also generates
  `tab:lidar-vertical-budget` -- all 7 cells trace to this script's own printed output, so
  the table cannot go stale silently. *Caveat in its docstring: it uses feature-vertical at
  Puerta Falsa's shaft edge but local-plane vertical only on the smooth drone surface.
  These are not interchangeable -- a plane fit at PF's rim returns garbage.*
- **`slice_tube.py`** -- slices the corrected tube in each gravity line's vertical plane
  and writes the cross-section CSV. `DEFAULT_SOURCE` names the canonical input export per
  line (see `DECISIONS.md`).
- **`recover_transform.py`** -- recovers a net 4x4 transform from before/after exports via
  scalar-field point matching.

## Reproducibility

**Verifying the existing registration is fully reproducible; redoing it from scratch is
not.** Stated plainly so a successor does not go looking:

- **Verify (deterministic).** `alignment_transforms.txt` records the exact net 4x4 and RMS
  for every step. Apply a matrix to the corresponding raw subset in CloudCompare (Edit >
  Apply Transformation) and it lands on the delivered export, with no by-eye judgement
  involved. `slice_tube.py`, `gt_metrics.py` and the `verify_alignment.py` figures are then
  deterministic given those clouds, and `run_all.py` regenerates all of them in one command.
- **Redo from scratch (e.g. for newly scanned data) -- NOT reproducible as documented.**
  The workflow above starts from a manual by-eye rotate/translate that seeds the ICP fit. A
  different seed could converge to a different local optimum, especially for the ~51 degree
  Puerta Falsa swing. No recorded procedure removes the operator from that first step.

### Regression checks

Run after any code change, not as routine regeneration. Three checks, each catching a
different failure mode -- none subsumes another. None are collected by `pytest` (no
`tests/` folder here), so run each directly:

```
python goldenmaster.py check --verbose      # 1. did a tracked output's VALUES change?
python test_goldenmaster_coverage.py        # 2. is every actual output file tracked?
python test_slice_tube.py                   # 3. do the outline AREAS still round right?
```

1. **`goldenmaster.py`** -- byte/float-exact diff of `Data/LiDAR/lidar_line{3,5}.csv`
   against a frozen snapshot in `_goldenmaster/` (gitignored). A FAIL means a published
   number changed: stop, do not "fix" it, find out why first.
2. **`test_goldenmaster_coverage.py`** -- asserts every file in `Data/LiDAR/` is matched by
   a `SOURCES` glob, closing the gap where a NEW output could go silently unprotected
   (`goldenmaster.py check` reports an untracked file as "NEW" but still exits PASS).
3. **`test_slice_tube.py`** -- re-derives the L3/L5 outline areas from the source clouds
   and asserts they still round to the thesis-reported 203 / 182 m^2. Catches a change in
   the extraction logic itself, which the CSV diff cannot see because the area is not a
   written column -- and which a tolerance test alone could not either. See `DECISIONS.md`
   for the near-miss this exists because of.

## Cross-session contract: `Data/LiDAR/lidar_line{3,5}.csv`

Columns `x,z,easting,northing` -- x = distance along the gravity line, z = absolute
REGCAN95 elevation, easting/northing = absolute EPSG:4083 per vertex so the Grav session
can project onto its own profile axis.

Written here by `slice_tube.py`. Read by `Grav/grav_utils.py` (feeding the inversion's
terrain plots) and `GPR/plot_lidar_cave_overlay.py`. Both consumers assert the column
schema on load via `grav_utils.check_lidar_schema()`, added 2026-08-12, so a rename or
reorder here fails immediately and legibly in both rather than silently producing a wrong
figure. Renaming these files or their columns is still a cross-session change -- update
every reader in the same commit.

## Registration record

All alignment and derived products are done. The full transform record is in
`alignment_transforms.txt`.

1. **Puerta Falsa junction alignment** (2026-06-16). idx0 blue as reference; StitchMove
   (idx2) and TubeMove (idx1) re-registered by eye plus Z-locked ICP -- stitch RMS 0.54 m
   at blue's sparsity floor, tube RMS 1.6 cm. Both greens needed an identical -1.07 m Z
   shift, a real green-vs-blue elevation offset. Exports in `Reregistered clouds/`.
2. **Puerta Falsa RTK georef correction** (2026-06-16). Cave pre-shifted from the original
   bad georeference by -1109.17 E / +6901.27 N cumulative, then pinned to RTK rim truth
   (-9.17 E / +1.27 N) and validated against an independent drone surface. The rest of the
   6-7 km tube stays approximate: the dataset is internally inconsistent, so no single
   rigid fit aligns all jameos.
3. **Jameo de la Gente local re-georef** (2026-06-30), for the L5 gravity line ~870 m NW.
   Tunnel (idx5) and Jameo (idx6) re-registered to drone/RTK in a bridge pattern. Net 4x4s
   recovered frame-safe by `recover_transform.py` -- Jameo 7.6 m move plus a 1.83 degree
   tilt fix at RMS 2.9 cm; Tunnel 6.5 m, Z-locked, RMS 0.01 cm; drone topo -0.35 m datum drop.
4. **Tube cross-sections for gravity** (2026-06-30; E,N added 2026-07-17; output moved to
   `Data/LiDAR/` on 2026-08-11 because it is data consumed cross-session, not a `Code/`
   artifact). Areas 203 m^2 (L3) and 182 m^2 (L5); centres match the gravity x0 (76 vs 73,
   51 vs 50). Validated by the Grav session.
5. **La Gente depth map and footprint** (2026-06-30). Corrected-Tunnel cave-top raster
   `QGIS project/caveheight_clean_laGente.tif` (2 m cells, ceiling = max Z) plus the
   plan-view envelope `Reregistered clouds/Gente_envelope.shp`, handed to QGIS for the
   overburden map.

## Deliberately not built

**A single merged whole-cave deliverable** (decision 2026-07-01). The cave is consumed
piecewise -- cross-sections, depth maps, footprints, the 3-D plot -- and the two measured
sites are locally exact. A merged product would be approximate along the 6-7 km between
them and add no thesis value. The dataset has several other internal misalignments away
from the measurement sites; those are left unfixed, with no bearing on the gravity or GPR
lines. Re-registering the full tube end-to-end would be a reasonable separate project. It
was not a gap in the thesis.

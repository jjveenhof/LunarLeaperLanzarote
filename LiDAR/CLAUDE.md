# LiDAR Session

BEFORE ANYTHING ELSE: read QandA.md in this directory (it holds a hand-over from the
previous session).

This file is loaded by sessions opened in `Code/LiDAR/`. The root CLAUDE.md (loaded
automatically alongside this) covers overall project structure, CRS, environment, and
working conventions. The project root "Thesis Lunar Leaper" is two levels up.

This session covers CloudCompare processing, point-cloud data preparation, and the
Python verification tooling for the La Corona LiDAR. (Moved here 2026-06-15 from
`LiDAR La Corona/` so the docs live inside the git repo, consistent with the other
Code/<method> sessions.)

QandA.md entries directed here are tagged `From: [session] -> LiDAR`.

## Locations
- Code (here, in git): `Code/LiDAR/` -- `las_tools.py`, `verify_alignment.py`.
- Data (large, outside git, in OneDrive): `../../LiDAR La Corona/` -- originals
  `LaCorona.bin` and `LaCoronaUnshifted.bin` (CloudCompare native CCB2 format).
- Scratch (large derived exports, OUTSIDE OneDrive): `C:\Users\jj_ve\lidar_scratch\`.
  Keep bulky LAS/ASCII exports here so they do not churn OneDrive sync.

## Data Description
`LaCorona.bin` holds 5 substantial clouds plus many tiny marker objects. The site data
is a merged cloud carrying an `Original cloud index` scalar field (sources 0-6). For
the alignment task the three relevant subsets at the junction (~650630, 3227150) are:
- idx 0 = BLUE: SE passage, trusted/correct orientation.
- idx 1 = DARK GREEN: big NW passage, misaligned (swung anticlockwise).
- idx 2 = LIGHT GREEN: small junction patch, the "bandaid" between blue and dark green.
Cloud lineage: 1 = all data; 2 = surface sub-cloud removed; 3 = cropped to fieldwork
area; 4 = cloud 3 with distance-to-surface computed and nonsensical points deleted.
Cloud 0 (with RGB) is unrelated regional topography ~7 km north. Full detail in the
session memory files (lacorona-bin-structure, lacorona-alignment-task).

## CloudCompare Workflow (alignment task)
Goal: re-align the misaligned scans at the fieldwork site by eye. BLUE is correct;
move the greens to it. NOT a rigid body -- align in sequence: first move LIGHT GREEN
(idx2) onto BLUE (idx0), then move DARK GREEN (idx1) onto the moved idx2. Hoped to be
a Z-axis-only rotation (+ horizontal translation); verify residuals for any tilt.
Steps: work on a copy (`LaCorona_aligning.bin`); split the working crop by
`Original cloud index` via Edit > Scalar fields > Filter By Value; use the interactive
Translate/Rotate tool with Rotation locked to Z; copy each 4x4 matrix from the Console
for reproducibility. The crop must include enough of BLUE's SE length to fix the swing
angle, not just the junction patch.

## Python verification tooling
- `las_tools.py`: reads X/Y/Z + `Original cloud index` straight from LAS byte offsets
  (laspy cannot parse these clouds' points -- duplicate "C2C absolute distances" field).
- `verify_alignment.py`: residuals + a 2x2 figure (TOP XY, projected SIDE, two thin-slice
  cross-sections with compass labels and the cut lines drawn on the TOP plan). Two modes:
  default reads the three aligned ASCII exports; `--las CLOUD.las` reads a single LAS with
  all subsets (baseline). Residuals reported by distance threshold (isolates the genuine
  overlap). Baseline (pre-alignment) idx2->idx0 residual ~ mean 8.7 m / median 5.6 m.
- `alignment_transforms.md`: the reproducible record of the final transforms (net 4x4 per
  mover, component transforms, RMS, verification results).
- Run with the env python (see root CLAUDE.md). Pass Windows-form paths.

## Export Convention
Export aligned point cloud as ASCII XYZ from CloudCompare (File > Save As > ASCII cloud).
Target CRS: EPSG:4083 (REGCAN95 / UTM zone 27N) -- already shifted to match GPR/GNSS.

## Current Focus
Junction alignment DONE and verified (2026-06-16). Crop "Cave around Puerta Falsa" split
by index into ReferenceCloud (idx0 blue), StitchMove (idx2), TubeMove (idx1). Aligned by
eye (coarse) + Z-locked ICP (fine): stitch RMS 0.54 m (at blue's sparsity floor ~0.46 m),
tube RMS 1.6 cm (mm fit in the 20% overlap). Tube ICP first diverged at 50% overlap --
fix was setting the overlap parameter to the true ~20%. Net 4x4 transforms + verification
recorded in `alignment_transforms.md`. Aligned ASCII exports in
`LiDAR La Corona/Reregistered clouds/` (true EPSG:4083). Both greens needed an identical
-1.07 m Z shift -> likely a real elevation offset of the green scans vs blue.

Next: user wants to do further CloudCompare steps before assembling a deliverable. Final
deliverable (merge of moved idx1+idx2 + untouched idx0, export ASCII XYZ EPSG:4083) is
PARKED.

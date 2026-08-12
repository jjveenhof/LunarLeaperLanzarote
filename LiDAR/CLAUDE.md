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
- Code (here, in git): `Code/LiDAR/` -- `las_tools.py`, `verify_alignment.py` +
  `verify_alignment_io.py`, `slice_tube.py`, `recover_transform.py`, `gt_metrics.py`,
  `run_all.py` (one-command entry point), `test_slice_tube.py` + `goldenmaster.py`
  (regression checks -- see "Reproducibility" below).
- Data (large, outside git, in OneDrive): `../../LiDAR La Corona/` -- originals
  `LaCorona.bin` and `LaCoronaUnshifted.bin` (CloudCompare native CCB2 format).
- Scratch: there is no longer an external scratch folder. `C:\Users\jj_ve\lidar_scratch`
  was DELETED 2026-08-11 -- 579 MB of superseded 15 Jun CloudCompare split-by-index
  re-exports of `LaCorona.bin` plus throwaway probe scripts, read by nothing in `Code/`
  (audited in `REFACTOR_FINDINGS.md`, "Phase 2"). Anything it held is a mechanical
  re-export of the `.bin` above. Do not recreate it: the successor receives the project
  folder, so a scratch area outside that folder is invisible to them and unbacked-up.
  Put bulky intermediates inside the tree instead, and gitignore them.

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
  Fails loud (assert) rather than silently misreading if a file's header/record layout,
  or the scalar field's byte width, does not match what this reader assumes.
- `verify_alignment.py` (CLI + plotting) + `verify_alignment_io.py` (loaders +
  `residual()`, split out 2026-08-11 so the data side can be read without the ~220
  lines of multi-panel plotting): NN residuals + before/after comparison figures for
  the thesis -- `alignment_check.png` (Puerta Falsa) and `gente_check.png` (`--gente`,
  Jameo de la Gente), each: a)/b) before/after plan panels + W-E/N-S cross-sections (Z
  shared per row), authored at page width (~6.1 in, figure-sizing rule) and saved
  title-free to thesis-overleaf `Appendices/Lidar reregistering` at 450 dpi.
  `--las CLOUD.las` gives the single-cloud baseline 2x2. Residuals reported by distance
  threshold (isolates the genuine overlap); baseline idx2->idx0 ~ mean 8.7 / median 5.6 m.
- `gt_metrics.py`: registration-quality metrics for the two measured jameos on three beats --
  (1) how-far-off (rotation-aware point displacement), (2) tie to independent RTK/drone control,
  (3) internal surface fit. Establishes the ground-truth VERTICAL accuracy of the L3/L5
  cross-sections ~0.2 m (RSS chains: L3 0.24, L5 0.21 m). NOTE: uses feature-vertical at PF's
  shaft edge but local-plane vertical ONLY on the smooth drone surface -- not interchangeable
  (a plane fit at PF's rim returns garbage); see its docstring. **Also generates
  `tab:lidar-vertical-budget`** (the "VERTICAL BUDGET" print block, added 2026-08-12) --
  all 7 table cells (3 chain links + RSS, both sites) trace to this script's own printed
  output, so the table cannot go stale silently; re-run and diff against `main.tex` to check.
- `alignment_transforms.txt`: the reproducible record of the final transforms (net 4x4 per
  mover, component transforms, RMS, verification results).
- `run_all.py`: one command that regenerates every output below that doesn't need
  CloudCompare -- both cross-section CSVs, both verification figures, the ground-truth
  metrics. See "Reproducibility" below for what it does NOT cover.
- Run with the env python (see root CLAUDE.md). Pass Windows-form paths.

## Reproducibility

**Verifying the existing registration IS fully reproducible; redoing it from scratch
is NOT.** Worth stating plainly rather than leaving a successor to discover it:

- **Verify** (deterministic): `alignment_transforms.txt` records the exact net 4x4
  matrix + RMS for every registration step. Apply a matrix to the corresponding raw
  subset in CloudCompare (Edit > Apply Transformation) and it lands on the delivered
  export -- no by-eye judgement involved. `slice_tube.py`, `gt_metrics.py`, and the
  figures in `verify_alignment.py` are then deterministic given those clouds, and
  `run_all.py` regenerates all of them in one command.
- **Redo from scratch** (e.g. re-registering newly scanned data): NOT reproducible as
  documented. The CloudCompare Workflow above (and the initial coarse step in
  `alignment_transforms.txt` sec. 2/4) starts from a manual by-eye rotate/translate
  that seeds the ICP fit. A different by-eye seed could converge to a different local
  optimum, especially for the ~51 degree Puerta Falsa swing -- there is no recorded
  procedure that removes the operator from that first step.

**Regression checks** (run after any code change, not as routine regeneration --
see `Code/REFACTOR.md` rule 0 for the golden-master discipline):
- `goldenmaster.py {snapshot,check}`: byte/float-exact check on `Data/LiDAR/lidar_line{3,5}.csv`.
- `test_slice_tube.py`: asserts the L3/L5 outline AREAS (203 / 182 m^2) reproduce --
  not covered by the CSV check above, since the area itself isn't a tracked column.
- **Known gap** (2026-08-11, see `REFACTOR_FINDINGS.md` and the root `QandA.md` rule-3
  thread): a fresh `slice_tube.py` run against the CURRENT `PF_tube_after.txt` does
  NOT byte-reproduce the deployed `lidar_line3.csv` (176 vs 173 outline vertices, area
  203.16 vs the frozen 203 m^2 -- same integer, different exact outline). The deployed
  CSV was almost certainly built from a differently-formatted copy of the corrected
  tube export that no longer exists on disk. Open with the author; do not "fix" it by
  regenerating over the deployed file.

## Export Convention
Export aligned point cloud as ASCII XYZ from CloudCompare (File > Save As > ASCII cloud).
Target CRS: EPSG:4083 (REGCAN95 / UTM zone 28N) -- already shifted to match GPR/GNSS.

## Plot tuning: generate once, then ask -- never self-iterate
Claude CANNOT reliably judge whether a figure looks nice, is aligned, well spaced,
or the right text size. So do NOT try, and do NOT loop on appearance.
When making or adjusting a thesis plot:
  1. Generate the plot ONCE.
  2. STOP. Do not regenerate to chase a better look, and do not spend effort
     guessing what "should" be tuned -- you are bad at judging that.
  3. ASK the user what they want to tune (clip, aspect, text size, colours,
     spacing, ...).
  4. Add knobs for EXACTLY what the user names (module constant or CLI flag, with
     an inline comment on effect direction), regenerate ONCE, hand back.
Do NOT pre-expose every possible parameter -- add a knob only when asked. Re-run a
plot on your own ONLY for correctness (crash, wrong data, a value the user changed),
never to evaluate appearance. Processing is fast; the cost to avoid is Claude
deciding what to tune and iterating on its own taste.

## Current Focus
All alignment + derived products DONE. Full transform record in `alignment_transforms.txt`.

1. **Puerta Falsa junction alignment** (2026-06-16). idx0 blue = reference; StitchMove
   (idx2) + TubeMove (idx1) re-registered by eye + Z-locked ICP (stitch RMS 0.54 m at
   blue's sparsity floor; tube RMS 1.6 cm). Both greens needed an identical -1.07 m Z
   shift (a real green-vs-blue elevation offset). Exports in `Reregistered clouds/`.
2. **Puerta Falsa RTK georef correction** (2026-06-16). Cave manually pre-shifted from
   the author's bad georef by -1109.17 E / +6901.27 N (cumulative), then pinned to RTK
   rim truth (-9.17 E / +1.27 N). Validated by an independent drone surface. Rest of the
   6-7 km tube stays approximate (internally inconsistent dataset -> a single rigid fit
   cannot align all jameos).
3. **Jameo de la Gente local re-georef** (2026-06-30), for the L5 gravity line ~870 m NW.
   Tunnel (idx5) + Jameo (idx6) re-registered to drone/RTK (bridge pattern). Net 4x4s
   recovered frame-safe by `recover_transform.py` (Jameo 7.6 m move + 1.83 deg tilt fix,
   RMS 2.9 cm; Tunnel 6.5 m, Z-locked, RMS 0.01 cm; Topo drone = -0.35 m datum drop).
4. **Tube cross-sections for gravity** (2026-06-30; E,N added 2026-07-17; output path
   moved to `Data/LiDAR/` 2026-08-11 -- it is DATA, consumed cross-session, not a
   Code/ artifact). `slice_tube.py` slices the corrected tube/Tunnel in each gravity
   line's vertical plane -> `Data/LiDAR/lidar_line{3,5}.csv`, columns
   `x,z,easting,northing` (x=dist along line, z=ABSOLUTE REGCAN95 elevation,
   E,N=absolute EPSG:4083 per vertex so Grav projects onto their own profile axis --
   see QandA). Areas: L3 203, L5 182 m^2. Centres match gravity x0 (76 vs 73; 51 vs 50).
   Validated by Grav. Ground-truth vertical accuracy ~0.2 m (see `gt_metrics.py`), fed to the
   Discussion via the root QandA handoff. See "Reproducibility" below for a known gap
   in regenerating this file exactly.
5. **La Gente depth map + footprint** (2026-06-30). Corrected-Tunnel cave-top raster
   `QGIS project/caveheight_clean_laGente.tif` (2 m, ceiling = max Z) + plan-view envelope
   `Reregistered clouds/Gente_envelope.shp`, handed to QGIS for the overburden map
   (surface - cave-top, masked). Both lack an embedded CRS -> assign EPSG:4083 on load.

Tools added: `slice_tube.py` (line-plane cross-section + area + per-vertex E,N),
`recover_transform.py` (net 4x4 from before/after exports via scalar-field point matching),
`gt_metrics.py` (three-beat registration-quality metrics; ground-truth vertical accuracy).

DROPPED (decision 2026-07-01): the single merged whole-cave deliverable is NOT being
built. The cave is consumed piecewise (cross-sections, depth maps, footprints, 3D plot),
and the two measured sites (Puerta Falsa, Jameo de la Gente) are locally exact -- a merged
product would only be approximate along the 6-7 km tube between them and add no thesis
value. The dataset also has several OTHER internal misalignments away from the measurement
sites; these are left unfixed (out of scope, no bearing on the gravity/GPR lines). Possible
future summer project: re-register the full tube end-to-end. Do not re-open for the thesis.

# La Corona junction re-alignment -- transform record

Manual + ICP re-alignment of the misaligned scans at the Puerta Falsa fieldwork site.
Done by eye (coarse) then Z-locked ICP (fine) in CloudCompare, working on a copy
(`LaCorona_aligning.bin`). Reference = BLUE (idx0, SE passage, trusted). Movers aligned
in sequence: StitchMove (idx2) -> ReferenceCloud, then TubeMove (idx1) -> moved StitchMove.

Coordinate note: matrices are in CloudCompare's **shifted local frame**
(global shift = -651100, -3227000, 0). Target CRS EPSG:4083 (REGCAN95 / UTM 28N).
Crop used: "Cave around Puerta Falsa", split by `Original cloud index` via Filter By Value.

Date: 2026-06-15.

## Verification (verify_alignment_asc.py, 2026-06-16)

Exported aligned subsets to `LiDAR La Corona/Reregistered clouds/` as CC ASCII
(ReferenceCloud.txt, StitchMoved.txt, TubeMoved.txt), true EPSG:4083 coords.
Independent nearest-neighbour residuals + top/side/cross-section plots (alignment_check.png):
- tube->stitch: ~20% of tube pts (the true overlap) within 0.3 m, mean NN 0.006 m -> mm fit.
- stitch->ref: closest pts ~0.25-0.5 m = blue's sparsity floor (~0.46 m); as good as data allows.
- Plots: blue+stitch+tube form one continuous passage; tube cross-section rings coincide;
  blue ceiling line is level -> no meaningful residual tilt. Z-rotation + horizontal
  translation model confirmed sufficient.

---

## StitchMove (idx2, light-green junction patch) -> ReferenceCloud (idx0, blue)

Applied as four sequential transforms (3 manual + 1 ICP). ICP: 70% partial overlap,
farthest-point removal on, Z rotation, Tz enabled. Final RMS 0.535834 m on 7791 pts.
RMS floor set by blue's sparsity (surface density ~1.2 pts/m^2 -> spacing ~0.91 m ->
floor ~0.46 m), so 0.54 m is essentially at the floor = aligned as well as data allows.

Net composite matrix (original -> final), M = T4 . T3 . T2 . T1:

```
 0.962344244   0.271834122   0.000000000   -53.757933412
-0.271834122   0.962344244   0.000000000  -118.812743345
 0.000000000   0.000000000   1.000000000    -1.074063122
 0.000000000   0.000000000   0.000000000     1.000000000
```

- Net Z-rotation: -15.7734 deg (clockwise)
- Net translation (local frame): (-53.7579, -118.8127, -1.0741) m
- Net vertical shift -1.07 m -- sanity-check against cross-section plots.

Component transforms (time order):
1. 18:15:54 coarse: Z -16.08 deg, translate (-54.622135, -121.378937, 0)
2. 18:20:32 nudge: translate (0, 0, -0.800000)
3. 18:24:42 nudge: translate (-0.300000, 0, 0)
4. 18:35:34 ICP: Z +0.305 deg, translate (0.518416, 2.856354, -0.274063)

---

## Georef correction at Puerta Falsa (2026-06-16)

Separate from the junction re-registration above. The author's LiDAR had no valid
georeferencing; it was manually shifted earlier (~ -1100 m W / +6900 m N) to fit jameos
to a Google basemap. That left a residual ~4-7 m eastward offset (basemap-judged), worse
near jameos because surface points past the rim biased the fit. Corrected here against
RTK truth at the Puerta Falsa jameo:
- RTK rim trace (25 pts, `Line=Edge`) + 1 plumb tie point, cm accuracy, EPSG:4083,
  extracted from `Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv` to
  `Reregistered clouds/PuertaFalsa_edge_RTK.xyz` and `_plumb_RTK.xyz`.
- Plumb pick on the (corrected-junction) cloud was ~9.17 m E / 1.27 m S of RTK truth.
- Fit done on the CORRECTED junction (full data is internally inconsistent at the rim).
  TRANSLATION ONLY (no rotation -- a 20 m rim arc cannot constrain rotation safely over a
  6-7 km lever arm). Plumb-derived translation also seats the edge arc -> two RTK features
  agree, no large rotational residual.

Applied translation (to be propagated to the ENTIRE dataset via Edit > Apply transformation):

```
1 0 0  -9.170000076294
0 1 0   1.269999980927
0 0 1   0.000000000000
0 0 0   1.000000000000
```

- dE = -9.17 m (move west), dN = +1.27 m (move north), dZ = 0 (elevations preserved).
- Scope: anchors Puerta Falsa to RTK; rest of cave stays approximate (dataset is internally
  inconsistent, so per-jameo offsets are NOT uniform -- a single translation cannot fix all).
- VALIDATION: an independent, separately-georeferenced drone surface topo (RGB) aligns
  perfectly with the RTK rim after correction -> third independent dataset confirms the
  georef (RTK edge + RTK plumb + drone all agree).
- Applied to the full cave + junction. NOTE: envelope polylines do NOT auto-move with their
  cloud -- shift their vertices by the same matrix or regenerate them after moving.
- TODO: remove the original misaligned idx1/idx2 from the full cave (duplicate junction);
  regenerate the final envelope from the corrected, georeferenced cloud.
- LIMITATION (accepted): a single rigid translation cannot align all jameos -- the source
  LiDAR is internally inconsistent. After anchoring to RTK at Puerta Falsa, Jameo de la
  Gente (~1 km west) sits ~5-6 m too far west. This offset is attributed to the LiDAR's
  internal coregistration error, NOT the basemap: Google imagery error varies smoothly over
  ~1 km (no mosaic seam between the jameos, low-relief terrain), and the basemap is
  independently confirmed accurate at Puerta Falsa (RTK + drone). The internal distortion is
  directly evidenced by the re-registration the fieldwork junction required. Kept as-is: the
  fieldwork site is exact; the rest is approximate by the dataset's own error. Do NOT
  least-squares-balance it away -- that would degrade the one RTK-validated anchor for
  cosmetics elsewhere.

## Cumulative georef: author's raw LiDAR -> final frame

Pure translation (two manual shifts, they commute). Applies to the bulk dataset (idx0 and
unmodified parts); the junction movers idx1/idx2 carry their own re-registration on top
(see their sections). The -1100/+6900 are the exact values applied in CloudCompare for the
jameo fit; the -9.17/+1.27 RTK edge fit then pinned the final position -> cumulative is exact
and RTK-validated at Puerta Falsa.

```
1 0 0  -1109.17     (= -1100 west  +  -9.17 RTK correction)
0 1 0   6901.27     (= +6900 north +  +1.27 RTK correction)
0 0 1      0.00
0 0 0      1.00
```

- dE = -1109.17 m, dN = +6901.27 m, dZ = 0 (EPSG:4083 / REGCAN95 UTM 28N).

---

## TubeMove (idx1, dark-green NW passage) -> moved StitchMove

Applied as three sequential transforms (2 manual + 1 ICP). First ICP attempt diverged
(RMS 3 m, slid east) because Final overlap was set to 50% while true overlap is small --
ICP dragged the tube to force 50% coverage. Fix: set Final overlap to the real value
(20%) and farthest-point removal off; then it snapped in tight. Tube and stitch have
similar (high) densities, so NO sparsity floor here -> RMS is a real fit, not floor.
ICP: 40% selection at 20% overlap, Z rotation, Tz enabled. Final RMS 0.0162089 m (1.6 cm).

Net composite matrix (original -> final), M = T3 . T2 . T1:

```
 0.626818114   0.779165623   0.000000000  -289.144916444
-0.779165623   0.626818114   0.000000000  -307.683458856
 0.000000000   0.000000000   1.000000000    -1.074082971
 0.000000000   0.000000000   0.000000000     1.000000000
```

- Net Z-rotation: -51.1842 deg (clockwise)
- Net translation (local frame): (-289.1449, -307.6835, -1.0741) m
- Net vertical shift -1.0741 m -- IDENTICAL to the stitch's -1.0741 m. Both greens needed
  the same vertical drop to match blue -> likely a real systematic elevation offset of the
  green scans vs blue, not drift.

Component transforms (time order):
1. 19:07:12 coarse: Z -50.79 deg, translate (-285.918488, -306.484375, 0)
2. 19:07:43 nudge: translate (0, 0, -1.100000)
3. 19:15:23 ICP: Z -0.381 deg, translate (-1.195382, -3.106518, 0.025917)

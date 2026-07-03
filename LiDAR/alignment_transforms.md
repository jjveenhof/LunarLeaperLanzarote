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

## Jameo de la Gente local re-georeference (2026-06, DONE)

Second, independent local anchor (~870 m NW of Puerta Falsa), for the Line 5 gravity
cross-section. Lower precision than Puerta Falsa (no cm-RTK rim survey here). Bridge-cloud
pattern again: drone (truth-ish) <- Red (idx6, jameo+surface, bridge) <- Orange (idx5, tube).

Subclouds: idx5 = "Tunnel around la Gente" (cave), idx6 = "La Gente and Surface" (jameo+surface).

Truth hierarchy established here:
- RTK GNSS lines L5 (N-S) + L2 (NE-SW), cm-accurate -> absolute datum (but sparse, lines only).
  Exported to `Reregistered clouds/Line5_GNSS_RTK.xyz`, `Line2_GNSS_RTK.xyz`.
- Drone topo -> correct SHAPE + areal coverage + horizontal, but a UNIFORM ~1 m vertical bias
  (sits ~1 m above RTK; confirmed uniform in both E-W and N-S). So: drone shape + RTK datum.
  NOTE the drone vertical bias is LOCAL (Puerta Falsa drone vertical was fine) -> depth maps
  carry a spatially-varying vertical caveat, NOT a global 1 m offset.
- LiDAR (Red/Orange) -> cave geometry only; internally inconsistent (XY slip ~7 m here, Z
  offset, AND a real W-high/E-low tilt + spurious curled edges on Red).

Method:
- Red: coarse translate -> full-rotation ICP to the drone (NOT Z-locked -- must tip out the
  tilt) on the trimmed core (flared edges cropped off first, they bias the fit) -> then a
  uniform -~1 m Z shift to drop from the drone's biased level onto the RTK-true elevation.
- Orange: ICP to the corrected Red on the pit overlap (true overlap % small, like Puerta Falsa).

For the science: gravity compares cross-sectional AREA, and <0.5 m vertical is datum choice,
so absolute vertical to ~tens of cm is plenty.

Reference clouds: drone crop "Topo around La Gente" (later re-extracted larger to cover the
whole cave); RTK lines `Line5_GNSS_RTK.xyz` + `Line2_GNSS_RTK.xyz`. C2C lines->drone gave
drone ~+0.35 m above RTK (uniform E-W and N-S) -> -0.35 m datum drop applied to the cave + the
local drone crop (NOT the full drone). Drone-RTK gap full C2C 0.84 m is mostly drone sparsity;
Z-component -0.35 m is the real offset.

RECIPE (ordered CloudCompare steps; the single net 4x4 is best taken from an original->final
rigid fit, NOT by multiplying these -- the global shift flips LaCorona->drone after the first
ICP and the full-rotation ICP rotates about a far origin, so naive matrix multiplication of the
logged numbers is wrong):

Jameo (idx6, "La Gente and Surface"):
1. coarse translate (+6.0, -4.5, 0)
2. Z-locked ICP -> Topo (drone), RMS 1.086 m (floor; drone ~2 m). dZ -1.252 m.
3. -0.35 m Z datum drop (with the group)
4. FULL-rotation ICP -> Topo, RMS 0.951 m. Fixed a real W-high/E-low tilt (~1.83 deg about
   the N-S axis; verified balanced residuals + seats at RTK height). [matrix has a huge Z
   column = far-origin rotation bookkeeping, NOT a real lift.]

Tunnel (idx5, "Tunnel around la Gente"):
1. -0.35 m Z datum drop (with the group)
2. coarse translate (+6.0, -3.0, -1.5)
3. [first Tunnel->Jameo ICP slid ~70 m (corridor-slide, RMS 3.1) -> reverted with its exact
   inverse; these two CANCEL, excluded from the net]
4. pit-crop ICP: cropped Tunnel to the pit/throat, ICP Tunnel_pit -> Jameo (RMS 0.315 m, no
   slide), then that 4x4 applied to the FULL Tunnel. Net horizontal ~2.7 m, dZ +0.10 m.

Result: Jameo seats on the drone/RTK surface (tilt out); Tunnel continues smoothly out of the
pit. Lower precision than Puerta Falsa (drone-anchored ~1 m horizontal, RTK datum to ~tens of
cm). For the L5 gravity cross-section, area is the metric, so this is plenty.

### NET 4x4 PER CLOUD (2026-06-30, recovered frame-safe)

Recovered NOT by multiplying the logged steps (mixed CC frames -- see RECIPE note)
but by a rigid Kabsch fit of session-start -> final point positions, matching the
same physical points across the before/after ASCII exports via their preserved
scalar-field signatures (tool: `recover_transform.py`). Source exports in
`LiDAR La Corona/Clouds to reconstruct transformations/` (OriginalJameo.txt,
Jameo.txt, OriginalTunnel.txt) + the L5 crop for Tunnel's final state.

"Session-start" = the Puerta-Falsa-corrected cave (cumulative -1109.17 E / +6901.27 N
already applied to the bulk, idx5/idx6 being unmodified bulk); these matrices are the
LOCAL Jameo re-registration move ON TOP of that, in true EPSG:4083 coords. To
reproduce in CC: Edit > Apply Transformation with the 4x4 below (exact). NOTE the
4x4 translation column is huge -- that is rotation-about-coordinate-origin
bookkeeping, NOT a physical move; the REAL displacement is the centroid move (~6-8 m).

**Jameo (idx6, "La Gente and Surface")** -- fit RMS 2.86 cm over 331,936 pts (100%):
- Real move (centroid): dE +6.208, dN -4.366, dZ -1.899 m (|horiz| 7.59 m)
- Rotation about centroid: Z-rot +0.2780 deg, tilt-about-N +1.8298 deg (the real
  W-high/E-low tip, fixed by the full-rotation ICP), tilt-about-E +0.13 deg
- Centroid (true coords): (649683.0, 3227541.5, 143.4)
- Net 4x4 (session-start -> final, true EPSG:4083):
```
 0.999478300  -0.004778698  -0.031942014   15773.172634230
 0.004850212   0.999985901   0.002161779   -3110.270699651
 0.031931234  -0.002315576   0.999487386  -13273.385419780
 0.000000000   0.000000000   0.000000000       1.000000000
```

**Tunnel (idx5, "Tunnel around la Gente")** -- fit RMS 0.01 cm over 48,056 pts:
- Real move (centroid): dE +5.720, dN -3.088, dZ -1.754 m (|horiz| 6.50 m)
- Rotation about centroid: Z-rot -0.1033 deg, tilt 0.000 deg (Z-locked, as intended)
- Centroid (true coords): (649758.9, 3227500.3, 121.0)
- Net 4x4 (session-start -> final, true EPSG:4083):
```
 0.999998375   0.001802879  -0.000000057   -5812.017424234
-0.001802879   0.999998375   0.000000051    1173.594651702
 0.000000057  -0.000000051   1.000000000      -1.626051712
 0.000000000   0.000000000   0.000000000       1.000000000
```

**Topo (local drone crop "Topo around La Gente")** -- pure datum drop, no fit needed:
```
1 0 0   0.00
0 1 0   0.00
0 0 1  -0.35
0 0 0   1.00
```
(the -0.35 m C2C datum drop applied to the drone-vs-RTK level; idx5/idx6 received this
same drop, already folded into their dZ above.)

### Coregistration check (2026-07-01, verify_alignment.py --gente)

Independent nearest-neighbour residuals on the corrected exports (Tunnel + Jameo +
drone TopoLaGente.xyz + RTK lines L5/L2). Figure: `Reregistered clouds/gente_check.png`
(TOP plan, projected SIDE, two cross-sections through the pit centre; role colours
drone=blue truth, Jameo=gold bridge, Tunnel=green mover -- as at Puerta Falsa). These
are NN residuals (a coregistration indicator, floored by the sparser cloud's spacing),
NOT rigid-fit RMS:

- **Tunnel <-> Jameo** (internal, at the pit throat): within 0.5 m, mean 0.26 m /
  RMS 0.29 m (18% of tunnel pts overlap; the tube runs well past the jameo). p5 0.17 m.
  The two LiDAR scans agree at the skylight.
- **Jameo <-> drone** (surface fit -- jameo registered to the drone): drone->Jameo
  (dense ref = real surface separation) within 1 m RMS 0.30 m, median 0.17 m. The
  reverse jameo->drone is 0.67-0.88 m, floored by the drone's ~2 m spacing (this is the
  direction the full-rotation ICP reported, ~0.95 m). So the jameo sits on the drone to
  ~0.3 m; larger figures are drone sparsity, not disagreement.
- **drone -> RTK** (absolute datum): RTK L5 p5 0.21 m, RTK L2 p5 0.24 m; sub-metre
  throughout, at the drone's ~2 m sampling floor. Confirms the -0.35 m datum drop -- the
  surface now sits on RTK truth, and the tunnel hangs correctly beneath it.

Conclusion: the Jameo de la Gente re-georef is validated by three independent datasets
(internal LiDAR pit agreement, drone surface fit, RTK absolute datum), consistent with
Puerta Falsa. Lower precision than Puerta Falsa (drone-anchored, no cm-RTK rim survey
here), but area is the gravity metric and <0.5 m vertical is datum choice, so ample.

---

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

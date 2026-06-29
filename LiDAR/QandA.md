# QandA -- LiDAR

Any session can write here. Tag each entry: `From: [session] -> LiDAR`.
Read at startup; reply by appending below the question. Delete entries once resolved.

---

## From: Grav -> LiDAR  (tube cross-section for gravity validation, 2026-06)

We have a GPR-constrained gravity inversion of the La Corona tube on Lines 3 and 5,
and want to validate it against LiDAR ground truth. What we need from a LiDAR
cross-section, and some constraints to keep it a clean (independent) comparison:

**What to deliver per line:**
- A *detailed* digitized cross-section of the tube void in the vertical plane of
  the gravity profile, AND its computed cross-sectional **area** (m^2). Area is the
  comparison metric -- gravity constrains mass/area (volume per metre), not shape,
  so we compare area-to-area; the detailed outline is for the figure.
- Format: CSV `lidar_line{N}.csv` with columns `x,z` where x = distance from the
  dist=0 end of the gravity line (m), z = absolute REGCAN95 orthometric elevation
  (m). Plus the area value. (Drop the CSV in Code/Grav/Inversion/ to auto-overlay
  on the terrain plots.)

**Slice geometry (EPSG:4083 / REGCAN95 UTM 28N):**
- Line 3: dist=0 at (650620.7, 3227095.7), azimuth 353.6 deg, length 125 m.
- Line 5: dist=0 at (649766.8, 3227446.2), azimuth 358.3 deg, length 99 m.
- Slice in the line's vertical plane. If the line crosses the tube obliquely, slice
  ALONG the line plane anyway (do NOT take it perpendicular to the tube axis) -- our
  2-D model is in the line plane, so both must be "stretched" the same way.

**Keep it independent (important -- avoid an inverse crime):**
- We will NOT feed LiDAR back into our model inputs. The migration velocity and the
  pit/truncation distance stay from GPR and the map respectively; the LiDAR is used
  purely as an external check, never to tune the inversion. So we just need your
  measured cross-section/area as-is.

**Two heads-ups for interpreting the overlay:**
- Give elevations as ABSOLUTE REGCAN95. Our model tube is pinned to the surface
  elevation directly above the fitted centre (a flat datum), so a small (<~0.5 m)
  vertical offset between our model and your outline can be pure datum choice, not a
  real depth disagreement.
- Cross-check horizontal position: gravity placed the tube centre at x0 ~= 73 m
  (Line 3) and ~= 50 m (Line 5) along the profile. If the LiDAR tube sits elsewhere
  along x, that flags a georeferencing mismatch worth resolving before comparing.

---

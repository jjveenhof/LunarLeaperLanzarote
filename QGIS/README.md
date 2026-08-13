# QGIS

Geospatial visualisation for the La Corona survey: overview maps of where the data was
collected, the roof-thickness (overburden) rasters, and the print layouts that became
thesis figures. `DECISIONS.md` holds the load-bearing "why"; this file is everything else.

Thesis figure -> layout mapping is in `Code/TRACEABILITY.md`.

## What this folder produces

Two things, and they are not the same kind of thing:

1. **`points_to_lines.py`** -- the only code here (~100 lines). Converts the raw GNSS
   point CSVs into GeoJSON line layers. Deterministic, golden-mastered, trivial to re-run.
2. **The QGIS project itself** (`QGIS project/FieldworkReporting.qgz` and its layer files)
   -- overview maps, the overburden rasters, and the print layouts. This is NOT code and
   NOT reproducible by running anything (see Rasters below). A successor can *verify* it
   by opening the project and checking layers against this file, but cannot regenerate
   the rasters unattended.

The `.qgz` projects and their layer data live in `QGIS project/` at the project root --
from this folder, `../../QGIS project/`. It was renamed from plain `QGIS/` on 2026-08-11
because it collided with this code folder. Layer paths inside the `.qgz` are all relative
(`./x.shp`, `../Data/...`), so the rename did not break them -- but do not move that
folder to a different depth. `.qgs`/`.qgz` files are XML (zipped, for `.qgz`) and readable
directly, though PyQGIS is the reliable way to parse them; see `DECISIONS.md`.

## How to run the code

```
python points_to_lines.py
```

Reads `Data/GNSS/Cleaned/CleanedGNSS_GPR_{Lines,FlowerPetals}.csv`, writes
`Data/GNSS/Cleaned/GPR_{Lines,FlowerPetals}.geojson`. The order field varies by line:
`Time` for L2 and FP1/2/3, `Meter` for L3 and L5. Re-run if the GNSS data changes; the
QGIS project loads the two GeoJSONs live, so nothing else is needed for them to update.

**Verification** -- run both after any edit to `points_to_lines.py`:
```
python goldenmaster.py check --verbose      # tracked outputs still bit-identical?
python test_goldenmaster_coverage.py        # is every declared output actually tracked?
```
Both should PASS on an unmodified copy.

## The QGIS project

### Project files

- **`FieldworkReporting.qgz` -- the main active project.** 35 layers, 7 print layouts, 4
  of which are thesis figures. Despite the name, this is the current one.
- **Stale, ignore:** `Research module report.qgz` (unchanged since February; 8 of its 10
  layers point at a `La Corona Cave/` folder that no longer exists; zero print layouts)
  and `Fieldworkplanning*.qgz` (pre-fieldwork planning). The naming is actively
  misleading -- see `DECISIONS.md`.

Three print layouts exist but publish nothing: `ResearchModule` (empty),
`OverviewFieldworkArea` (superseded by the `...NoLegend` variant), and
`FlowerPetalOutreach` (outreach material).

### Rasters

`QGIS project/cavebottom.tif`, `cavetop.tif` -- LiDAR-derived cave ceiling/floor depth.

> **The overburden rasters are a MANUAL ARTIFACT -- nothing regenerates them.** They are
> the product of hand-driven GUI steps (Align Rasters, the Processing raster calculator,
> GDAL Rasterize). The recipe below is complete and every input is in `QGIS project/`, so
> they can be verified and re-made by hand -- budget 15-20 min per area rather than
> looking for a script that does not exist.

Roof-thickness maps, three areas, all EPSG:4083, 2 m cells.

**Recipe:** overburden = ground surface (`drone_topo.tif`) - cave ceiling. Align the
surface onto the ceiling grid (Align Rasters, bilinear, clip to ceiling extent -- or just
set reference layer = ceiling in the Processing raster calculator, which resamples on the
fly). Subtract; ceiling nodata propagates to depth nodata, so it self-clips to the
footprint. Mask jameos and open rims to nodata by burning `QGIS project/Jameos.shp` with
GDAL Rasterize (overwrite, value = nodata). Style singleband pseudocolor 1-36 m,
clip-out-of-range so anything under 1 m (jameos, negatives) goes transparent.

> **Gotcha:** burn a SEPARATELY SAVED copy. Copy-pasting a layer in QGIS keeps the same
> source file, so the burn hits the original.

Raw pre-mask subtractions are kept beside each final as `cavetop_clean*.tif` (no
`_masked`); ceilings are `caveheight_clean*.tif`. The finals used in figures:

| Raster | Area | Notes |
|---|---|---|
| `cavetop_clean_masked.tif` | Full cave | Depth min -10.7 / mean 17.0 / max 36.3 m. Reliable near the fieldwork site, rougher west -- the source LiDAR's horizontal accuracy degrades westward (Jameo de la Gente is ~5-6 m off; see `LiDAR/alignment_transforms.txt`). |
| `cavetop_clean_masked_PuertaFalsa.tif` | Puerta Falsa junction | RTK-anchored, so no westward caveat. |
| `cavetop_clean_masked_LaGente.tif` | Jameo de la Gente / L5 | Ceiling re-registered ~6-7 m. Surface used a -0.35 m drone correction (local ~+0.35 m drone bias vs RTK). Sanity check: at L5 (E~649766, N~3227500) overburden is ~13 m, matching the LiDAR cross-section. |

`QGIS project/Jameos.shp` -- hand-digitized jameo/open-rim polygons, the nodata burn mask.

**CRS on exports (consolidated 2026-08-11).** Several CloudCompare and other exports never
got an embedded or sidecar CRS even though their coordinates are already correct
EPSG:4083. They need it ASSIGNED, never reprojected. All of the following are now fixed on
disk, so no by-hand assignment step is needed:
- `QGIS project/caveheight_clean_laGente.tif` -- fixed with `gdal_edit.py -a_srs EPSG:4083`.
  An earlier "Assign projection" done in a live QGIS session was never written to the file.
- `.prj` sidecars written (WKT copied from the already-correct `Jameos.prj`) for
  `LiDAR La Corona/Reregistered clouds/Gente_envelope.shp`, `.../PuertaFalsaCleanEnvelope.shp`,
  `LiDAR La Corona/Tube Envelope - Cleaned and surface removed.shp` (used in three
  thesis-figure layouts), `QGIS project/envelope z-flat.shp`, and
  `QGIS project/Legacy/All GPR surveys.shp`.

**DTM.** `Data/IGN data/DTM/MDT02-REGCAN95-HU28-1080-{2,4}-COB2.tif` are the two 2 m IGN
tiles; `Data/IGN data/Processed/MergedDTM.sdat` is the merged product -- use that one.
Styled as two layers: an elevation colour ramp (tv-a from qpt-city, 0-669 m, transparent
below 0.8 m) sitting ABOVE a hillshade (azimuth 315, altitude 45). Both use Multiply blend
mode and bilinear resampling to avoid blockiness.

### Vector layers

- `QGIS project/Envelope - x flat_new.shp`, `Envelope - y flat_new.shp`, `envelope z-flat.shp`
  -- lava tube outline from LiDAR, styled white.
- `QGIS project/Fieldwork Area.shp` -- fieldwork area bounding box; dashed outline.
- `Data/GNSS/Cleaned/GPR_Lines.geojson`, `GPR_FlowerPetals.geojson` -- produced by
  `points_to_lines.py` from the `CleanedGNSS_GPR_*.csv` files beside them.
- `QGIS project/Gravimetry Alessandro.shp` -- reference gravity survey from a previous study.
- `QGIS project/Legacy/` -- planning-stage shapefiles and the two pre-fieldwork
  `Fieldworkplanning*.qgz` projects, moved there 2026-08-11 after confirming nothing
  current references them. Browse only if chasing history; do not load into the live
  project as a shortcut (see `DECISIONS.md`).

### Gravity stations

Loaded from the gravimetry pipeline's CSV outputs in `Data/Gravimetry/Processed/`. Styled
by line, with different symbols for base, tie and regular stations. L3 and L4 share a base
station, drawn as nested squares (outer L3 colour, inner L4 colour).

## Conventions

**CRS:** EPSG:4083 (REGCAN95 / UTM zone 28N) for all layers and exports. The IGN DTM tiles
are HU28 and QGIS reprojects them on the fly.

**Colour palette** (colourblind-friendly, Okabe-Ito inspired):

| Element | Hex |
|---|---|
| L2 | `#0099FF` blue |
| L5 | `#00CC80` green |
| L3 | `#FF5C00` orange-red |
| L4 / flower petals | `#FF4DB8` magenta |
| Annotation (reserved) | `#FFC400` gold |
| Cave outline | `#FFFFFF` white |

## Structure

Deliberately flat -- 115 lines of code across two scripts does not warrant a `tests/` or
`Legacy/` subfolder. (The `Legacy/` under `QGIS project/` is project data, a different
thing, described above.)

- `points_to_lines.py` -- the pipeline.
- `goldenmaster.py`, `_goldenmaster/` -- byte-exact output tracking.
- `test_goldenmaster_coverage.py` -- asserts the golden master's manifest is complete.
- `DECISIONS.md` -- why, for facts not re-derivable from the code or this file.

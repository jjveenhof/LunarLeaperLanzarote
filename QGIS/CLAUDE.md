# QGIS Session

BEFORE ANYTHING ELSE: read QandA.md in this directory.

This file is loaded by sessions opened in Code/QGIS/. The root CLAUDE.md
(loaded automatically alongside this) covers the overall project structure,
CRS, environment, and working conventions.

QandA.md entries directed here are tagged `From: [session] -> QGIS`.

QGIS project and layer files live at QGIS/ in the project root. From this
session's working directory that is ../../QGIS/ (or use the full path).
QGIS .qgs/.qgz files are XML and readable directly. Geodata (shapefiles,
rasters) can be processed via Python with geopandas/rasterio.

## Overview
QGIS is used for geospatial visualisation: overview plots of data collection
locations, CRS EPSG:4083 (REGCAN95 / UTM zone 28N) visualisation, and
cross-method spatial context.

## Key Layers / Project Files

### QGIS Project Files (under QGIS/ at project root)
- `Research module report.qgz` -- main active project; contains all print layouts
- `FieldworkReporting.qgz` -- earlier reporting project
- `Fieldworkplanning.qgz`, `Fieldworkplanning2.qgz` -- pre-fieldwork planning; mostly ignore

### Rasters
- `QGIS/cavebottom.tif`, `cavetop.tif` -- LiDAR-derived cave depth rasters (depth of cave ceiling/floor)
Roof-thickness (overburden) workflow, full cave + Puerta Falsa junction (both EPSG:4083, 2 m cells):
overburden = ground surface - cave ceiling. Align the surface onto the ceiling grid (Raster > Align
Rasters, bilinear, clip to ceiling extent), subtract (depth = surface - ceiling; ceiling nodata ->
depth nodata, so it self-clips to the cave footprint), then mask the jameos/open rims to nodata by
burning the `QGIS/Jameos.shp` polygons with GDAL Rasterize (overwrite with fixed value = nodata).
Style singleband pseudocolor 1-36 m, clip-out-of-range so <1 m (jameos + negatives) is transparent.
NOTE: the mask burn must target a SEPARATELY SAVED copy -- copy-pasting a layer in QGIS keeps the same
source file, so the burn hits the original. Files:
- `QGIS/caveheight_clean.tif` -- full-cave CEILING (MAX height, cave footprint only, empties nodata)
- `QGIS/drone_topo.tif` -- ground SURFACE; `QGIS/drone_topo_rasterAligned.tif` = aligned to full-cave grid
- `QGIS/cavetop_clean.tif` -- full-cave depth (raw subtraction, before masking). Min -10.7 / mean 17.0 / max 36.3 m
- `QGIS/cavetop_clean_masked.tif` -- full-cave ROOF-THICKNESS map, jameos masked (FINAL, used in figures).
  CAPTION CAVEAT: reliable near the fieldwork site, rougher to the west (source LiDAR horizontal accuracy
  degrades westward, Jameo de la Gente ~5-6 m off -- see Code/LiDAR/alignment_transforms.md).
- `QGIS/caveheight_clean_PuertaFalsa.tif` -- CEILING of the re-registered junction tube at Puerta Falsa
  (RTK-anchored fieldwork section only); `QGIS/drone_topo_rasterAligned2.tif` = surface aligned to its grid
- `QGIS/cavetop_clean_PuertaFalsa.tif` -- junction depth (raw subtraction, before masking)
- `QGIS/cavetop_clean_masked_PuertaFalsa.tif` -- junction ROOF-THICKNESS map, jameos masked (FINAL).
  Exactly georeferenced (RTK at Puerta Falsa) -- NO westward-accuracy caveat.
- `QGIS/Jameos.shp` -- hand-digitized jameo/open-rim polygons used as the nodata burn mask (EPSG:4083)
- `Data/IGN data/DTM/MDT02-REGCAN95-HU28-1080-2-COB2.tif` -- 2m DTM tile 1 (IGN)
- `Data/IGN data/DTM/MDT02-REGCAN95-HU28-1080-4-COB2.tif` -- 2m DTM tile 2 (IGN)
- `Data/IGN data/Processed/MergedDTM.sdat` -- merged DTM (use this in QGIS)
DTM is styled as two layers: elevation color ramp (tv-a from qpt-city, 0-669m, transparent below 0.8m) on top of hillshade (azimuth 315, altitude 45), both with Multiply blend mode.

### Vector Layers
- `QGIS/Envelope - x flat_new.shp`, `Envelope - y flat_new.shp`, `envelope z-flat.shp` -- lava tube outline from LiDAR; styled white (#FFFFFF)
- `QGIS/Fieldwork Area.shp` -- fieldwork area bounding box polygon; dashed outline, annotation color
- `QGIS/All GPR surveys.shp` -- aggregated GPR survey locations (legacy points)
- `Data/GNSS/Cleaned/GPR_Lines.geojson` -- GPR survey lines (L2, L3, L5) converted from GNSS points via Code/QGIS/points_to_lines.py
- `Data/GNSS/Cleaned/GPR_FlowerPetals.geojson` -- flower petal GPR surveys (FP1, FP2, FP3)
- `Data/GNSS/Cleaned/CleanedGNSS_GPR_Lines.csv` -- original GPR GNSS points with Line and Meter columns
- `Data/GNSS/Cleaned/CleanedGNSS_GPR_FlowerPetals.csv` -- original flower petal GNSS points
- `QGIS/Gravimetry Alessandro.shp` -- reference gravity survey from previous study
- Various named GPR line shapefiles in QGIS/ (ContextLine, FlowerPetalLine, CentreLines, etc.) -- planned/reference GPR lines from earlier planning stage

### Gravity Station Data
Loaded from gravimetry pipeline CSV outputs (Data/Gravimetry/Processed/). Stations styled by line with different symbols for base, tie, and regular stations. L3 and L4 share a base station -- styled as nested squares (outer L3 color, inner L4 color).

## Conventions

### CRS
EPSG:4083 (REGCAN95 / UTM zone 28N) -- project CRS for all layers and exports.
Note: IGN DTM tiles are in HU28 (UTM zone 28N) but QGIS reprojects on the fly.

### Color Palette (colorblind-friendly, Okabe-Ito inspired)
- L2: #0099FF (blue)
- L5: #00CC80 (green)
- L3: #FF5C00 (orange-red)
- L4 / Flower Petals: #FF4DB8 (magenta)
- Annotation (reserved): #FFC400 (gold)
- Cave outline: #FFFFFF (white)

### GPR Lines Script
`Code/QGIS/points_to_lines.py` converts GNSS CSVs to GeoJSON lines.
Order field varies by line: Time for L2 and FP1/2/3, Meter for L3 and L5.
Re-run if GNSS data changes; outputs to Data/GNSS/Cleaned/.

### Layer Blending for DEM
Elevation color layer sits ABOVE hillshade (not below). Both use Multiply blend mode.
Bilinear resampling on both layers to avoid blockiness.

## Current Focus
Building print layout figures for thesis:
1. Fieldwork overview map -- satellite basemap, gravity stations, GPR lines, cave outline. Nearly complete; print layout started.
2. Regional DEM map -- hillshade + elevation color, cave outline, fieldwork area box, Lanzarote locator inset. In progress.
3. Zoomed detail maps (NW and SE clusters) -- planned, not started.

# QGIS Session

BEFORE ANYTHING ELSE: read QandA.md in this directory.

This file is loaded by sessions opened in Code/QGIS/. The root CLAUDE.md
(loaded automatically alongside this) covers the overall project structure,
CRS, environment, and working conventions.

At the start of each session, read QandA.md in this directory for pending questions or
tasks. Any session (supervisor, Grav, GPR) can write here -- entries are tagged
`From: [session] -> QGIS`. To ask another session something, write into their QandA.md.
Delete entries from your own QandA.md once resolved.

QGIS project and layer files live at QGIS/ in the project root. From this
session's working directory that is ../../QGIS/ (or use the full path).
QGIS .qgs/.qgz files are XML and readable directly. Geodata (shapefiles,
rasters) can be processed via Python with geopandas/rasterio.

## Overview
QGIS is used for geospatial visualisation: overview plots of data collection
locations, CRS EPSG:4083 (REGCAN95 / UTM zone 27N) visualisation, and
cross-method spatial context.

## Key Layers / Project Files

### QGIS Project Files (under QGIS/ at project root)
- `Research module report.qgz` -- main active project; contains all print layouts
- `FieldworkReporting.qgz` -- earlier reporting project
- `Fieldworkplanning.qgz`, `Fieldworkplanning2.qgz` -- pre-fieldwork planning; mostly ignore

### Rasters
- `QGIS/cavebottom.tif`, `cavetop.tif` -- LiDAR-derived cave depth rasters (depth of cave ceiling/floor)
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
EPSG:4083 (REGCAN95 / UTM zone 27N) -- project CRS for all layers and exports.
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

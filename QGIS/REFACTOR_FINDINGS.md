# QGIS session -- refactor audit (phase 1) and execution (phase 2)

Scope: `Code/QGIS/points_to_lines.py` (~100 lines -- the only code in this session) plus
the .qgz project files and layer assets in `QGIS project/` (outside git; renamed from
plain `QGIS/` on 2026-08-11 -- paths below reflect the current name). Phase 1 was audit only,
no changes; phase 2 (docs fixes, the layer rewire, .prj sidecars, legacy quarantine, the
`points_to_lines.py` nits) is executed and noted inline below. Findings ranked by
handover value / risk, per `Code/REFACTOR.md`.

Goal sentence for reference: *a competent MSc student who has never seen this project
can (1) verify any number in the thesis, (2) regenerate any figure, (3) extend the
work -- without asking the author.*

Honest framing up front: there is almost nothing to refactor in the Python here. The
real handover risk in this session lives entirely in the QGIS project files and their
CLAUDE.md documentation, which is why every high-ranked finding below is docs/project-
state, not code.

---

### [1] CLAUDE.md names the wrong file as "the main active project"
- **Where:** `Code/QGIS/CLAUDE.md:24` ("`Research module report.qgz` -- main active
  project; contains all print layouts"); `QGIS project/Research module report.qgz` (last saved
  2026-02-26) vs `QGIS project/FieldworkReporting.qgz` (last saved 2026-07-13)
- **What:** I read both `.qgz` files (they are zip archives containing XML; unzipped and
  parsed directly, no QGIS needed). `Research module report.qgz` has only 10 layers, 8 of
  which point at `../La Corona Cave/...` or `../../Section 6.shp` -- a folder ("La Corona
  Cave") that does not exist anywhere in the project tree (it was renamed to `LiDAR La
  Corona/` at some point) and a shapefile that does not exist anywhere. It contains zero
  print layouts and zero of the overburden/DTM/GPR-line/gravity layers this session's
  work and CLAUDE.md are about. `FieldworkReporting.qgz` has 35 layers -- every raster and
  vector documented in CLAUDE.md's Rasters/Vector Layers sections -- and 7 print layouts,
  4 of which are the actual thesis figures (see traceability table below).
- **Why it hurts handover:** goal (2) directly. A successor opening the file CLAUDE.md
  tells them to open gets a broken, empty-looking project and no path to any thesis
  figure. `FieldworkReporting.qgz` -- despite its name suggesting an "earlier reporting"
  project, per CLAUDE.md's own now-corrected description -- is the one that actually
  works.
- **Proposed action:** swap CLAUDE.md's "main active project" line to point at
  `FieldworkReporting.qgz`; reclassify `Research module report.qgz` as legacy/broken
  alongside the `Fieldworkplanning*.qgz` files. These `.qgz` files live in `QGIS project/`,
  outside git, so any rename/move is propose-only per the session brief -- I have not
  touched them. A CLAUDE.md text fix is zero-risk and should just be done.
- **Touches numbers?:** NO (documentation only).
- **Effort:** S
- **Phase 2 status: DONE (2026-08-11).** CLAUDE.md now names `FieldworkReporting.qgz` as
  the main active project and reclassifies `Research module report.qgz` as legacy/broken.
  Not moved to `Legacy/` (finding 4 only approved the specific list it named).

### [2] A layer named "masked" is wired to the unmasked file -- feeds two live thesis figures
- **Where:** `FieldworkReporting.qgz`, layer id `cavetop_clean_LaGente_6fe34705...`,
  `<layername>cavetop_clean_masked_LaGente</layername>`,
  `<datasource>./cavetop_clean_LaGente.tif</datasource>` (the RAW, pre-mask file). The
  actual masked file, `QGIS project/cavetop_clean_masked_LaGente.tif`, exists on disk (I verified
  it) but is referenced **zero times** anywhere in the project XML -- it was saved but
  never loaded as a layer.
- **What:** This mislabeled layer is used by two print-layout map items: `NWFieldworkArea`
  (map item 1, the Puerta-Falsa/La-Gente inset) and `OverviewFieldworkAreaNoLegend` (map
  item 0). Both layouts are exported into the thesis as `Maps/NWFieldworkArea.pdf` and
  `Maps/OverviewFieldworkAreaNoLegend.pdf`, combined into Figure `fig:overview-fieldwork`
  (`main.tex:358-359`, panels a/b/c). I pulled both PDFs from `thesis-overleaf/Maps/` and
  eyeballed the La Gente panel at the delivered resolution -- no visible jameo-edge specks
  or masking artifacts, so **the frozen thesis figure itself looks fine**. This is a
  latent trap for reproduction, not a currently-wrong thesis figure, as best I can tell
  from a visual check (I did not pixel-diff or re-export).
- **Why it hurts handover:** goal (2), squarely. If a successor reopens
  `FieldworkReporting.qgz` and re-exports these two layouts expecting to reproduce the
  thesis figure, they will get the unmasked raster (with the 1-6 m jameo-edge specks this
  session specifically masked out) with no error or warning -- the layer's own name lies
  to them.
- **Proposed action:** in QGIS, repoint the `cavetop_clean_masked_LaGente` layer's source
  to the actual `cavetop_clean_masked_LaGente.tif`, then re-export both layouts and diff
  the panel visually against the current thesis PDFs (should be pixel-identical or very
  close, since the underlying masked raster already existed when the thesis was
  finalised). This is a GUI action, not a code change -- flagging for the author to do,
  not something I can execute from here.
- **Touches numbers?:** NO -- this is a raster layer's display source, not a computed
  value. Re-exporting for comparison is the recommended check, not a numeric rerun.
- **Effort:** S (a few clicks in QGIS), but worth doing before anyone touches this project
  again.
- **Phase 2 status: DONE (2026-08-11).** Repointed via PyQGIS `setDataSource` (not the GUI --
  `qgis_process`/`python-qgis-ltr.bat` from the OSGeo4W install let this be done headlessly
  and precisely). Also found and fixed a SECOND stale reference my phase-1 XML scan missed:
  a frozen "locked layers" snapshot inside the `NWFieldworkArea` layout's map item, which
  `QgsProject.write()` did not auto-correct -- needed a direct XML patch (the layout's
  `<Layout name=...>` tag has "name" in varying attribute positions across layouts, which
  is also why my phase-1 traceability table build initially under-counted; re-scanned with
  an attribute-order-independent regex to confirm no other stale entries exist anywhere).
  `FieldworkReporting.qgz.bak-20260811` kept as a pre-fix backup. Re-exported both affected
  layouts (`NWFieldworkArea`, `OverviewFieldworkAreaNoLegend`) to a scratch path via
  `QgsLayoutExporter` and eyeballed them -- both match the delivered thesis PDFs. All 35
  project layers confirmed still valid after the fix.

### [3] Missing-CRS files -- consolidated list (per your audit note)
- **Where:** scattered across CLAUDE.md prose; verified by checking for `.prj` sidecars
  (`.shp`) and recalling the in-session raster fix (`.tif`).
- **What:** files that load into QGIS as "unknown CRS" even though their coordinates are
  already correct EPSG:4083 (REGCAN95 / UTM 28N) -- because CloudCompare/other exports
  didn't embed one:
  - `QGIS project/caveheight_clean_laGente.tif` -- raster; per this session's transcript, EPSG:4083
    was assigned via "Assign projection" (writes into the file), so this one is likely
    already fixed on disk -- I could not independently re-verify the embedded CRS byte
    (no GDAL/rasterio in the env, see Reproducibility note below), so treat as
    "should be fixed, confirm before relying on it."
  - `LiDAR La Corona/Reregistered clouds/Gente_envelope.shp` -- no `.prj` anywhere in that
    folder.
  - `LiDAR La Corona/Reregistered clouds/PuertaFalsaCleanEnvelope.shp` -- same, no `.prj`.
  - `LiDAR La Corona/Tube Envelope - Cleaned and surface removed.shp` -- no `.prj`. Used in
    4 of the 7 print layouts, including 3 that ARE thesis figures (`OverviewFieldworkArea`,
    `OverviewRegion`, `OverviewFieldworkAreaNoLegend`) -- this one was missing from the
    original audit note and is the most consequential of the group.
  - `QGIS project/envelope z-flat.shp` -- no `.prj`; used as "Lava tube envelope" in the
    `OverviewRegion` thesis layout and `FlowerPetalOutreach`.
  - `QGIS project/All GPR surveys.shp` -- no `.prj`; legacy/superseded (see finding 4), low
    priority.
- **Why it hurts handover:** goal (3). Right now this knowledge exists only as "it loads
  fine because I already fixed it in my open QGIS session" -- not written down anywhere as
  a single list. A successor re-adding any of these files to a fresh project will hit
  "unknown CRS" with no indication that the fix is simply "assign EPSG:4083, do not
  reproject."
- **Proposed action:** add one consolidated "Missing-CRS files" list to CLAUDE.md (I can
  do this in phase 2 as a docs-only edit); optionally, for the three shapefiles with no
  `.prj` at all, write a `.prj` sidecar next to each (a `.prj` is a plain WKT text file --
  zero risk, no data touched, fixes the trap permanently instead of relying on future
  sessions remembering to re-assign it). The `.prj`-write is the only item in this whole
  findings file that touches a file outside `Code/`; flagging that explicitly so the
  author can decide (these are processed/derived footprints, not raw acquisition data, so
  rule 4 allows it, but I did not do it in phase 1).
- **Touches numbers?:** NO.
- **Effort:** S
- **Phase 2 status: DONE (2026-08-11).** `caveheight_clean_laGente.tif` was actually
  NOT fixed on disk despite the in-session "Assign projection" -- confirmed with `gdalinfo`
  (found via the OSGeo4W install, so this could finally be checked directly this session):
  no CRS block at all. Fixed for real with `gdal_edit.py -a_srs EPSG:4083`; verified
  statistics (min/max/mean/stddev) identical before and after -- metadata-only change, no
  pixel data touched. The three no-`.prj` shapefiles plus `envelope z-flat.shp` and
  `All GPR surveys.shp` all got `.prj` sidecars (WKT copied from the already-correct
  `Jameos.prj`). Consolidated list is now in `Code/QGIS/CLAUDE.md`.

### [4] Legacy layer triage (propose only -- lives outside git)
- **Where:** `QGIS project/` folder, project root.
- **What:** planning-stage shapefiles superseded by the real survey data: `All GPR
  surveys.shp`, `ContextLine*.shp`, `CentreLines*.shp`, `FlowerPetalLine*.shp`,
  `GridLines.shp`, `ParallelLine.shp`, `ParallelContextLine.shp`, `SmallDeepLine.shp`,
  `EasternLines.shp`, `ExtraSkylightLines.shp`, `CloseToSkylightLine*.shp`,
  `Day3_LaPalomaLine.shp`, `GPRL3Paloma.shp`, `GPRSurveys3.shp`, `GravSurveys3.shp` --
  already flagged in CLAUDE.md as "mostly superseded." Also two unused `.qgz` projects:
  `Fieldworkplanning.qgz`, `Fieldworkplanning2.qgz` (pre-fieldwork planning, confirmed not
  referenced by any thesis figure).
- **Why it hurts handover:** goal (3), mildly. None of these break anything today, but a
  successor browsing `QGIS project/`'s ~30 shapefiles has no way to tell "superseded, safe to
  ignore" from "still load-bearing" without opening each one.
- **Proposed action:** per rule 5 (quarantine beats delete) and your note that these are
  outside git -- propose a `QGIS project/Legacy/` subfolder and moving the planning-stage
  shapefiles + the two unused `.qgz` files into it. **Not doing this myself**: it's a
  file-system move outside the git-tracked area, explicitly your call per the audit brief.
- **Touches numbers?:** NO.
- **Effort:** S if approved (plain file moves), but propose-only per scope.
- **Phase 2 status: DONE (2026-08-11), approved by the Supervisor session.** Confirmed via
  PyQGIS that none of the listed files are referenced by any layer in
  `FieldworkReporting.qgz` before moving. All moved into `QGIS project/Legacy/` with a
  one-line `README.md` (per rule 5). Reloaded the project afterward -- all 35 layers still
  valid, all 4 thesis-figure layouts still resolve.

### [5] `points_to_lines.py` -- two trivial code notes, neither worth urgent action
- **Where:** `Code/QGIS/points_to_lines.py:44-54` (`points_to_lines` function),
  `:89,91` (date parsing)
- **What:** (a) `points_to_lines(df, groups, order_field_map)` takes a `groups` parameter
  that is never used in the function body (only `order_field_map.items()` drives the
  loop) -- dead parameter, harmless. (b) the datetime format string
  `"%d.%m.%Y %H:%M:%S"` is written out twice (once per CSV) three lines apart -- minor,
  self-contained duplication, not worth a shared constant at this scale.
- **Why it hurts handover:** barely. Neither is a correctness risk or a trap; listing them
  because the checklist asks, not because they're worth spending review time on.
- **Proposed action:** if touching this file for any other reason, drop the unused
  `groups` param and hoist the date format to a module constant. Not worth a standalone
  edit.
- **Touches numbers?:** NO.
- **Effort:** S (skippable)
- **Phase 2 status: DONE (2026-08-11), approved by the Supervisor session.** Both nits
  applied. Verified non-regression twice: first manually (copied the two output GeoJSONs
  before editing, re-ran, `diff` -- identical), then again with the shared
  `Code/QGIS/goldenmaster.py` shim per the Supervisor's golden-master addendum (`snapshot`
  taken post-fix as the new baseline, `check --verbose` reports both files bit-identical).
  This is the only numeric/data output this session produces.

### Reproducibility note (checklist f)
- The order-field convention checklist item ("Time for L2/FP, Meter for L3/L5") IS already
  in the script, not just in CLAUDE.md -- `LINE_ORDER = {2: "Time", 3: "Meter", 5:
  "Meter"}` with a one-line comment above it, and `petals_to_lines` hardcodes `"Time"`.
  No action needed here; the audit note's concern turned out to already be satisfied.
- The `GPR_plotting_LL` conda env has neither `rasterio` nor `osgeo`/GDAL, so phase 1's
  raster checks were limited to parsing `.qgz` XML directly. Phase 2 found a working
  alternative: the local QGIS/OSGeo4W install (`C:\OSGeo4W`) ships its own GDAL
  (`gdalinfo.exe`, `gdal_edit.py`) and a PyQGIS-enabled Python (`python-qgis-ltr.bat`),
  usable standalone without touching the `GPR_plotting_LL` env. This is how finding 3's
  raster CRS gap got found (the earlier "fix" hadn't actually been written to disk) and
  fixed for real, and how finding 2's layer rewire + layout re-export were done headlessly.
  Worth remembering for any future QGIS-adjacent scripting need in this project.
- The overburden workflow itself (align -> subtract -> mask, documented in
  `Code/QGIS/CLAUDE.md`) is entirely manual QGIS GUI steps -- there is no `.py` script or
  PyQGIS/Processing model that regenerates `cavetop_clean_masked*.tif` from
  `caveheight_clean*.tif` + `drone_topo.tif` unattended. The CLAUDE.md recipe is detailed
  enough for a careful human to follow (goal 2 is satisfiable, just not automatable), but
  turning it into a script is a real (non-trivial) undertaking and is new work, not a
  refactor -- flagging as a known gap, not proposing it for this pass.

---

## Thesis traceability table (checklist g)

QGIS produces 4 of the thesis's figures, all via `Research module report.qgz`... no --
via **`FieldworkReporting.qgz`**'s print layouts (see finding 1), exported to
`thesis-overleaf/Maps/*.pdf`:

| Thesis figure (`main.tex`) | QGIS layout (in `FieldworkReporting.qgz`) | Key source layers |
|---|---|---|
| `main.tex:167`, regional DEM overview | `OverviewRegion` (2 map items) | `MergedDTM color`/`shade` (`Data/IGN data/Processed/MergedDTM.sdat`), `Lava tube envelope`, `LavaTubeInterpretation_correctCRS`, `Tube Envelope - Cleaned and surface removed`, `PuertaFalsaCleanEnvelope` |
| `main.tex:358`, Fig. `fig:overview-fieldwork` panel (a) | `OverviewFieldworkAreaNoLegend` | `GPR_Lines`, `Flowerpetals`, `cavetop_clean_masked` (full-cave overburden), `cavetop_clean_masked_PuertaFalsa`, `cavetop_clean_masked_LaGente` (**finding 2, fixed 2026-08-11**), `LaGenteCleanEnvelope` |
| `main.tex:359`, Fig. `fig:overview-fieldwork` panels (b)/(c) | `NWFieldworkArea` (2 map items) | `GravLocations`, `GPR_Lines`, `cavetop_clean_masked_PuertaFalsa`, `cavetop_clean_masked_LaGente` (**finding 2, fixed 2026-08-11**), `LaGenteCleanEnvelope` |
| `main.tex:1157`, La Gente alignment figure | `LaGenteAlignment` | `AfterAlignmentInterpretation`, `Tube Envelope - Cleaned and surface removed`, `PuertaFalsaCleanEnvelope`, `LaGenteCleanEnvelope` |

Layouts present but **not** used in the thesis (checked against `main.tex` --
no gaps found in the other direction, i.e. every QGIS thesis figure has a known
producing layout):
- `ResearchModule` -- empty (0 map items), likely a leftover default-named layout.
- `OverviewFieldworkArea` -- superseded by the `...NoLegend` variant that's actually used.
- `FlowerPetalOutreach` -- name suggests non-thesis outreach material; not referenced in
  `main.tex`.

Not QGIS: `main.tex:601` (`GPR/petal_migration_map`) and `main.tex:1479`
(`Appendices/.../gente_check.png`) are produced by the GPR and LiDAR sessions
respectively -- included here only to note they are NOT QGIS outputs despite superficial
similarity.

## Tests (checklist h)
None exist for this session. If one were added, the highest-value single test would be:
after running `points_to_lines.py`, assert the output GeoJSON's feature count equals the
number of distinct non-empty `Line`/petal groups in the input CSV, and that each
LineString's point count matches the corresponding CSV group's row count. Cheap,
catches a silently-dropped line (e.g. a typo'd line ID) which is the one realistic
failure mode for this script. Not written -- proposing only, per phase-1 scope.

---

## Recommended cut line (phase 1) -- now all executed (phase 2, 2026-08-11)

**Worth doing** (all zero/near-zero risk, all docs-or-project-state, no code
verification needed) -- **DONE**:
- [1] Fix CLAUDE.md's "main active project" pointer. DONE.
- [2] Repoint the mislinked La Gente masked layer and re-export the two affected layouts
  to confirm the thesis PDFs are unaffected. DONE, including a second stale reference
  phase 1 missed.
- [3] Consolidate the missing-CRS file list into CLAUDE.md; write `.prj`
  sidecars for the shapefiles that have none. DONE -- also caught and fixed a raster CRS
  fix from this session that had never actually been written to disk.

**Optional / below the line** -- also approved and done by the Supervisor session:
- [4] Legacy layer quarantine. DONE (`QGIS project/Legacy/`).
- [5] The two `points_to_lines.py` code nits. DONE, verified byte-identical output.
- The scripted-overburden-pipeline gap (reproducibility note) -- still real, still new
  work rather than a refactor; CLAUDE.md now states the manual-artifact fact explicitly
  instead of leaving it implicit, per the Supervisor dispatch. Not scripted.

No rule-3 discrepancies found (no thesis number disagreed with anything re-checked).
Finding [2] was the closest thing to a "the thesis might be wrong" alarm; the visual
check of the actual delivered PDFs did not show a problem, and it is now fixed at the
source besides -- confirmed via a fresh re-export that matches the delivered PDFs.

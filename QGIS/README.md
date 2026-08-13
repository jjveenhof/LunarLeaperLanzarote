# QGIS session

What this session's code does, how to run it, and which thesis figures come from where.
See `CLAUDE.md` for the full reference (layer inventory, styling conventions, the
overburden recipe) and `DECISIONS.md` for load-bearing "why," not "what."

## What this session produces

Two things, and they are not the same kind of thing:

1. **`points_to_lines.py`** -- the only code here (~100 lines). Converts the raw GNSS
   point CSVs into GeoJSON line layers for QGIS. Deterministic, golden-mastered, trivial
   to re-run.
2. **The QGIS project itself** (`QGIS project/FieldworkReporting.qgz` and its layer
   files) -- overview maps, the overburden/roof-thickness rasters, and the print layouts
   that become thesis figures. This is NOT code and NOT reproducible by running anything
   -- see "Manual artifact" in `CLAUDE.md`'s Rasters section and the corresponding
   `DECISIONS.md` entry. A successor can VERIFY it (open the project, check layers
   against this file) but cannot regenerate the rasters unattended.

## How to run the code

```
C:\Users\jj_ve\miniconda3\envs\GPR_plotting_LL\python.exe points_to_lines.py
```
from `Code/QGIS/`. Reads `Data/GNSS/Cleaned/CleanedGNSS_GPR_{Lines,FlowerPetals}.csv`,
writes `Data/GNSS/Cleaned/GPR_{Lines,FlowerPetals}.geojson`. Re-run if the GNSS data
changes; the QGIS project loads those two GeoJSONs live, so no further step is needed
for them to show up on the map.

**Verification:**
```
python goldenmaster.py check --verbose      # tracked outputs still bit-identical?
python test_goldenmaster_coverage.py        # is every declared output actually tracked?
```
Both should PASS on an unmodified checkout. Run both after any edit to
`points_to_lines.py`.

## Thesis figure traceability

QGIS produces 4 of the thesis's figures, all via print layouts in
`QGIS project/FieldworkReporting.qgz` (NOT `Research module report.qgz` -- see
`DECISIONS.md`), exported to `thesis-overleaf/Maps/*.pdf`:

| Thesis figure (`main.tex`) | QGIS layout | Key source layers |
|---|---|---|
| `main.tex:167`, regional DEM overview | `OverviewRegion` | `MergedDTM color`/`shade`, `Lava tube envelope`, `Tube Envelope - Cleaned and surface removed`, `PuertaFalsaCleanEnvelope` |
| `main.tex:358`, Fig. `fig:overview-fieldwork` panel (a) | `OverviewFieldworkAreaNoLegend` | `GPR_Lines`, `Flowerpetals`, `cavetop_clean_masked` (full-cave overburden), `cavetop_clean_masked_PuertaFalsa`, `cavetop_clean_masked_LaGente`, `LaGenteCleanEnvelope` |
| `main.tex:359`, Fig. `fig:overview-fieldwork` panels (b)/(c) | `NWFieldworkArea` | `GravLocations`, `GPR_Lines`, `cavetop_clean_masked_PuertaFalsa`, `cavetop_clean_masked_LaGente`, `LaGenteCleanEnvelope` |
| `main.tex:1157`, La Gente alignment figure | `LaGenteAlignment` | `AfterAlignmentInterpretation`, `Tube Envelope - Cleaned and surface removed`, `PuertaFalsaCleanEnvelope`, `LaGenteCleanEnvelope` |

Layouts present in the project but **not** in the thesis -- do not mistake these for
producing anything published:
- `ResearchModule` -- empty (0 map items).
- `OverviewFieldworkArea` -- superseded by the `...NoLegend` variant above.
- `FlowerPetalOutreach` -- non-thesis outreach material.

Not QGIS, despite living under a similar `Maps/`-adjacent naming pattern: `main.tex:601`
(`GPR/petal_migration_map`) and `main.tex:1479`
(`Appendices/.../gente_check.png`) are produced by the GPR and LiDAR sessions
respectively.

Full audit trail (how each of the above was verified, including two bugs found and
fixed): `REFACTOR_FINDINGS.md`.

## Structure

Deliberately flat -- 115 lines of code across two scripts does not warrant a `tests/` or
`Legacy/` subfolder here (the project-data `Legacy/` lives under `QGIS project/`, a
different, non-code folder, and is documented in `CLAUDE.md`).

- `points_to_lines.py` -- the pipeline.
- `goldenmaster.py`, `_goldenmaster/` -- byte-exact output tracking.
- `test_goldenmaster_coverage.py` -- asserts the golden master's manifest is complete
  (catches a future output silently going untracked).
- `CLAUDE.md` -- full reference: layer inventory, styling, the overburden recipe.
- `DECISIONS.md` -- why, for facts not re-derivable from the code or CLAUDE.md.
- `QandA.md` -- session inbox, gitignored, ephemeral. Load-bearing threads get migrated
  out to `DECISIONS.md` before they're pruned.
- `REFACTOR_FINDINGS.md` -- the phase-1/2 audit trail.

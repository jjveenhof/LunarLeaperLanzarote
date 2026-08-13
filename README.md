# La Corona lava tube -- subsurface characterisation

Processing code for an MSc Applied Geophysics thesis (TU Delft / ETH Zurich) on mapping
the La Corona lava tube, Lanzarote, using ground-penetrating radar, relative gravimetry
and LiDAR. Fieldwork April-May 2026; thesis submitted 2026-08-03.

The scientific spine is the **GPR-constrained gravity inversion** of the tube
cross-section, validated against the LiDAR ground truth. Everything else either feeds
that or documents it.

## Start here

1. Build the environment (below) and confirm `python -c "import numpy, pyproj"` works.
2. Read the `README.md` of whichever method you need -- `Grav/`, `GPR/`, `LiDAR/`,
   `QGIS/`. Each one gives the single command to run that method, the map from thesis
   figure/table to producing script, and what cannot be run because it was done by hand.
3. Before changing anything, run that session's `goldenmaster.py check`. It must PASS on
   an untouched copy. If it does not, stop and find out why before you edit -- something
   is already different from what the thesis reports.

## Environment

```
conda env create -f environment.yml
conda activate lacorona-lunarleaper-thesis
```

`environment.yml` is a hand-curated spec, not a `conda env export` dump: it lists what
the code actually imports, pinned to the versions the thesis results were produced with.
It also pins the one external geophysics dependency, `gdp`
(`georadar-data-processing`, public GitLab, LGPL v3), **by commit hash** -- installing
it needs network access.

Two deliberate omissions, so you do not go looking for a mistake:

- **`pygimli`** is not included. Only `Grav/Inversion/forward_fem.py` uses it, as an
  independent cross-check of the analytic forward model. Everything in the thesis runs
  without it.
- **GDAL / rasterio** are not included. Raster inspection is done with a separate
  OSGeo4W QGIS install -- see `QGIS/DECISIONS.md`.

Scripts are plain ASCII throughout; Greek and maths in figure labels go through
matplotlib mathtext (`r"$\Delta\rho$"`), never literal Unicode.

## How the project is laid out

This folder (`Code/`) is the git repository. **The data is not in it** -- it sits
alongside, in the parent folder, because raw acquisition data is large and
irreplaceable:

```
Thesis Lunar Leaper/
  Code/            <- this repo
  Data/            GPR/, GNSS/, Gravimetry/, LiDAR/, IGN data/
  Results/         browse PNGs of every figure
  LiDAR La Corona/ raw point clouds (~2.7 GB)
  QGIS project/    .qgz projects, shapefiles, rasters
```

Scripts locate the data by walking up from their own location, so the tree must be kept
intact -- moving `Code/` on its own breaks every path.

**Raw acquisition data is irreplaceable and must never be overwritten:**
`Data/GPR/Stitched/`, raw `Data/GNSS/`, `Data/Gravimetry/Field data` and Notes, and
`LiDAR La Corona/*.bin`. Everything under `Data/*/Processed/`, `Data/*/Topo/` and
`Results/` is regenerable -- overwriting those is what the pipeline is for.

Thesis LaTeX and the final figure PDFs live outside this tree entirely. Figure-writing
code reads the location from the `THESIS_REPO` environment variable; if it is unset and
the fallback path is absent, the scripts still run, write the browse PNGs into
`Results/`, and print a one-time warning instead of the PDFs.

## The four method folders

| Folder | Produces | Run it with | Cost |
|---|---|---|---|
| `LiDAR/` | tube cross-sections `Data/LiDAR/lidar_line{3,5}.csv`, registration checks | `python run_all.py` | seconds |
| `GPR/` | processed / topo-corrected / migrated sections, tube picks, 3-D scenes | `python run_all.py` | minutes (`--no-scans` to skip the slow velocity scans) |
| `Grav/` | corrected gravity anomalies, then the tube inversion | `python run_pipeline.py`, then `cd Inversion && python run_inversion.py` | ~2 min per inversion case |
| `QGIS/` | GNSS line GeoJSONs for the map project | `python points_to_lines.py` | seconds |

### Run order

`LiDAR` and `GPR` before `Grav`. The inversion consumes both:
`Data/LiDAR/lidar_line{3,5}.csv` (ground truth and terrain overlay) and
`Data/GPR/Migration/tube_picks.csv` (the GPR depth prior that makes the inversion
"GPR-constrained"). `QGIS` is independent -- it only needs the cleaned GNSS CSVs.

The one formal cross-session data contract is `Data/LiDAR/lidar_line{3,5}.csv`, columns
`x,z,easting,northing`. LiDAR writes it; `Grav/grav_utils.py` and
`GPR/plot_lidar_cave_overlay.py` read it, and both assert the schema on load so a
changed column fails immediately instead of silently producing a wrong figure. Do not
rename these files or their columns without updating every reader.

## What cannot be reproduced by running something

Be aware of these before concluding a script is missing:

- **The LiDAR re-registration** was done in CloudCompare, seeded by eye and finished with
  ICP. The resulting 4x4 matrices are recorded in `LiDAR/alignment_transforms.txt`, which
  lets you *verify* the registration; it cannot be regenerated unattended.
- **The GPR processing parameters** (`*_params.json`) were tuned in a notebook, and the
  migration velocity was picked by hand off an interactive scan. `GPR/run_all.py` reads
  the saved choices and prints the steps it cannot do; see `GPR/MANUAL_ARTIFACTS.md`.
- **The QGIS overburden rasters and print layouts** are a GUI product. The recipe and
  every input are documented, but no script exists and one was deliberately not written
  -- see `QGIS/DECISIONS.md`.

These are documented decisions, not gaps.

## Verifying you have not changed a published number

The thesis is frozen. Every session carries a **golden master**: a bit-exact snapshot of
its numerical outputs, compared at zero tolerance.

```
python goldenmaster.py check        # in any session folder
```

It compares values, never figures -- PNG and PDF bytes differ between runs even with
identical data, so figures are verified through the numbers behind them. It also refuses
to silently re-baseline: taking a new snapshot is an explicit, separate command.

Alongside it, each session has a coverage check asserting that the golden master's
manifest is *complete*, so a newly added output cannot go quietly unprotected. In `Grav/`
and `GPR/` these run under `python -m pytest tests/`; in `LiDAR/` and `QGIS/` they are
run directly as scripts.

> **The snapshots are gitignored.** `_goldenmaster/` folders travel with a *copy of this
> folder* but are lost in a fresh `git clone`. If you cloned and the checks report
> nothing to compare against, that is why -- get the snapshots from the folder, do not
> generate new ones and assume they are the baseline.

## Conventions

- CRS is **EPSG:4083** (REGCAN95 / UTM zone 28N) throughout. Elevations are REGCAN95
  orthometric heights.
- Each session folder holds a `DECISIONS.md`: dated entries for choices that the code
  cannot explain on its own. Read it before concluding something was done arbitrarily.
- Where a constant is hardcoded because the thesis froze it, the code says so. Those are
  not cleanup targets.

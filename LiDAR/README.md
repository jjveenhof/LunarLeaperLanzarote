# LiDAR session

Point-cloud processing for the La Corona lava tube (CloudCompare re-registration) and the
Python tooling that verifies it and derives the tube cross-sections used by the gravity
inversion. See `CLAUDE.md` for full detail (data layout, byte-level LAS format, the
CloudCompare workflow); `DECISIONS.md` for facts a successor cannot re-derive from the
code; this file for how to run things and where each thesis number/figure comes from.

## Run everything

```
python run_all.py
```

Regenerates every output that does not require a manual CloudCompare step:
`Data/LiDAR/lidar_line{3,5}.csv` (both lines), `alignment_check.png`, `gente_check.png`,
and the `gt_metrics.py` printed numbers (including the vertical-budget table). Uses the
env python automatically if run with it (see root `CLAUDE.md` for the path). Stops on the
first failure rather than running on with a broken step.

**Not covered by `run_all.py`:** the CloudCompare re-registration itself is manual (by
eye + ICP) and cannot be scripted -- see `CLAUDE.md`'s CloudCompare Workflow section and
`DECISIONS.md`'s "redo-from-scratch is not reproducible" entry before assuming otherwise.

## Regression checks (run after any code change, not as routine regeneration)

Three checks, each catching a different failure mode. Run all three -- none subsumes
another. None of them are collected by `pytest` automatically (no `tests/` folder, no
`test_*` naming convention beyond the filename) -- run each directly:

```
python goldenmaster.py check --verbose      # 1. did a tracked output's VALUES change?
python test_goldenmaster_coverage.py        # 2. is every actual output file tracked?
python test_slice_tube.py                   # 3. do the outline AREAS still round right?
```

1. **`goldenmaster.py`** -- byte/float-exact diff of `Data/LiDAR/lidar_line{3,5}.csv`
   against a frozen snapshot (`_goldenmaster/`, gitignored). `snapshot` once before
   editing, `check` after. A FAIL here means a tracked number changed -- STOP, do not
   "fix" it, escalate per `Code/REFACTOR.md` rule 3.
2. **`test_goldenmaster_coverage.py`** -- asserts every file actually in `Data/LiDAR/`
   is matched by a `goldenmaster.py` `SOURCES` glob. Closes the gap where a NEW output
   file could go silently unprotected (goldenmaster.py's own `check` reports an
   untracked file as "NEW" but still exits PASS).
3. **`test_slice_tube.py`** -- re-derives the L3/L5 outline areas from the source point
   clouds and asserts they still round to the thesis-reported 203 / 182 m^2. Catches a
   change in the outline-extraction logic itself, which the CSV diff above cannot see
   (the area isn't a written column) and a tolerance test alone cannot either -- see
   `DECISIONS.md`'s canonical-source entry for the near-miss this exists because of.

## Thesis traceability

| Thesis artifact | Label | Producer |
|---|---|---|
| Puerta Falsa before/after figure | `fig:puertafalsa-check` (`main.tex:1129`) | `verify_alignment.py` (default mode) |
| La Gente before/after figure | `fig:lagente-check` (`main.tex:1480`) | `verify_alignment.py --gente` |
| Vertical-residual RSS table (0.24 / 0.21 m) | `tab:lidar-vertical-budget` (`main.tex:1137`) | `gt_metrics.py` |
| L3/L5 cross-section areas (203 / 182 m^2) | inversion results tables (`main.tex:937-938,1044`) | `slice_tube.py` -> `Data/LiDAR/lidar_line{3,5}.csv` |
| Sauro comparison figure | `fig:sauro-check` (`main.tex:1475`) | external (Sauro et al. 2020 scan) -- not this session's code |
| Flower-petal 3D snapshots w/ LiDAR ground truth | `fig:fp3d*`, `fig:fp3d-mig*` (`main.tex:1373,1406`) | GPR session's `plot_flowerpetal_3d.py`, consuming `PF_junction_subsampled.xyz` |
| Overburden / envelope maps | (QGIS session figures) | `Reregistered clouds/Gente_envelope.shp`, `QGIS project/caveheight_clean_laGente.tif` -- produced here, handed to QGIS |

## Cross-session contract: `Data/LiDAR/lidar_line{3,5}.csv`

Columns `x,z,easting,northing` (x = distance along the gravity line, z = absolute
REGCAN95 elevation, easting/northing = absolute EPSG:4083 per vertex). Written here by
`slice_tube.py`; read by `Grav/grav_utils.py::lidar_file()` (via
`Inversion/plot_model_terrain.py`) and `GPR/plot_lidar_cave_overlay.py`. Both readers
already access columns BY NAME (pandas `Ld["easting"]`, `np.genfromtxt(..., names=True)`
then `lid['easting']`), so a column rename here fails loudly (KeyError) in either
consumer rather than silently misreading -- an explicit schema assertion at each read
site was considered (`REFACTOR.md` phase 3 item 3b) and not added, since it would be a
cross-session change (rule 8) for a case the existing by-name access already guards.
Renaming or reordering these columns is still a cross-session change: propose it in a
`QandA.md`, do not just do it (rule 8).

## What's here

- `slice_tube.py` -- oblique vertical-plane slice of the corrected tube through a
  gravity line; writes the CSV above. `DEFAULT_SOURCE` names the canonical input export
  per line (see `DECISIONS.md`).
- `verify_alignment.py` + `verify_alignment_io.py` -- before/after registration figures
  and NN residuals (plotting / data-loading split).
- `gt_metrics.py` -- registration-quality + ground-truth vertical accuracy metrics;
  also generates `tab:lidar-vertical-budget`.
- `las_tools.py` -- raw byte-offset LAS reader (laspy cannot parse these clouds).
- `recover_transform.py` -- recovers a net 4x4 transform from before/after exports.
- `run_all.py`, `goldenmaster.py`, `test_slice_tube.py`, `test_goldenmaster_coverage.py`
  -- see above.
- `alignment_transforms.txt` -- the recorded 4x4 matrices for every registration step
  (the reproducibility record; see `DECISIONS.md`).
- `DECISIONS.md` -- why things are the way they are.
- `QandA.md` -- cross-session coordination (gitignored; load-bearing facts get migrated
  out of it into `DECISIONS.md`, not left here).

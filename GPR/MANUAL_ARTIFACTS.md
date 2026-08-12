# GPR manual artifacts -- NOT reproducible by any script

These thesis figures are **hand-made browser captures of interactive 3D HTML**, not
`save_figure` PDF outputs. A successor who greps for a producing script will find none
-- that is expected. To "regenerate" one you open the HTML, match the camera/gain, and
screenshot (and, for the two annotated ones, re-annotate by hand). Do not spend time
trying to script these.

The interactive HTMLs themselves ARE script-produced and fully reproducible:
- `flowerpetal_unmigrated_3d.html` <- `plot_flowerpetal_3d.py`
- `flowerpetal_migrated_3d.html`   <- `plot_petal_migration_3d.py`
(both write to `Results/GPR/FlowerPetals3D/`). Only the still capture is manual.

## Annotated stills (hand-drawn annotations on top of a screenshot)
| thesis file (thesis-overleaf/GPR/) | main.tex label | source HTML | how made |
|---|---|---|---|
| FP3D_mig_SE_annotated.pdf | fig:fp3d-mig-snapshots-a | flowerpetal_migrated_3d.html | SE-facing view, screenshot, annotated by hand |
| FP3D_mig_NE_annotated.pdf | fig:fp3d-mig-snapshots-b | flowerpetal_migrated_3d.html | NE-facing view, screenshot, annotated by hand |

## Plain stills (screenshots, no annotation) -- Appendices/Flowerpetals/*.png
| thesis file | main.tex label | source HTML |
|---|---|---|
| FP3D_allLines.png | fig:fp3d-a | flowerpetal_unmigrated_3d.html |
| FP3D_allLinesWithLidar.png | fig:fp3d-b | flowerpetal_unmigrated_3d.html |
| FP3D_L3WithLidar.png | fig:fp3d-c | flowerpetal_unmigrated_3d.html |
| FP3D_FP2BackWithLidar.png | fig:fp3d-d | flowerpetal_unmigrated_3d.html |
| FP3D_mig_allLines.png | fig:fp3d-mig-a | flowerpetal_migrated_3d.html |
| FP3D_mig_allLinesWithLidar.png | fig:fp3d-mig-b | flowerpetal_migrated_3d.html |
| FP3D_mig_L3WithLidar.png | fig:fp3d-mig-c | flowerpetal_migrated_3d.html |
| FP3D_mig_FP2BackWithLidar.png | fig:fp3d-mig-d | flowerpetal_migrated_3d.html |

## Other manual steps in the pipeline (not figures, but human-in-the-loop)
- **Migration velocity pick** -- read by eye off the Stolt velocity-scan HTML
  (`migrate_velocity_scan.py --line <s>`), then written into the profile's params as
  `velocity` + `migrate: true` + `migration_gain`. See CLAUDE.md Conventions.
- **Processing params** -- tuned in `GPRProcessing.ipynb` and saved as
  `Data/GPR/Processed/{stem}_params.json`. The saved JSONs are the source of truth;
  `run_pipeline.py` replays them without the notebook. See README run order.

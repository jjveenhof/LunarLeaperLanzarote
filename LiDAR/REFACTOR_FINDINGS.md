# LiDAR session -- Phase 1 refactor audit

Scope: `Code/LiDAR/` (5 scripts, 998 lines). Audit only -- no code changed. Findings
ranked by handover value / risk, per `Code/REFACTOR.md`.

Goal sentence for reference: *a competent MSc student who has never seen this project
can (1) verify any number in the thesis, (2) regenerate any figure, (3) extend the
work -- without asking the author.*

---

### [1] `slice_tube.py` writes to a path nobody reads anymore -- a silent-failure trap
- **Where:** `slice_tube.py:12` (docstring), `slice_tube.py:31` (`GRAV_INV` constant),
  `CLAUDE.md:106` (Current Focus #4)
- **What:** `slice_tube.py` still targets `Code/Grav/Inversion/lidar_line{N}.csv`. The
  files actually consumed by the inversion now live at `Data/LiDAR/lidar_line{3,5}.csv`
  (confirmed: `Code/Grav/grav_utils.py:20,27` `lidar_file()` and
  `Code/Grav/Inversion/plot_model_terrain.py:22-30` both read `Data/LiDAR/`; I verified
  the file at that path is byte-identical in content to what I produced this session).
  `Code/Grav/Inversion/lidar_line{3,5}.csv` no longer exists at all -- someone (Grav
  session, per `grav_utils.py:17-19`'s comment "now also consumed by the GPR session ...
  they live under Data/") relocated the deliverable to `Data/` without the LiDAR-side
  producer script or its CLAUDE.md being updated to match.
- **Why it hurts handover:** goal (2)/(3). If a successor re-runs `slice_tube.py`
  exactly as documented, it silently writes a file at a location nothing reads --
  no error, no warning, and the actually-consumed CSV goes stale with no signal that
  anything is wrong. This is the single most likely "I changed the input, why didn't
  the inversion move?" support request this session could generate.
- **Proposed action:** point `GRAV_INV` (rename to `LIDAR_OUT` or similar) at
  `BASE / "Data/LiDAR"`, update the docstring, and fix `CLAUDE.md:106`. Cheap, one
  constant + two doc lines.
- **Touches numbers?:** NO if done as a path-only change (do not re-run; the two CSVs
  at `Data/LiDAR/` are already correct and validated -- just point future runs there).
- **Effort:** S

### [2] `las_tools.py`'s raw byte-offset reader has no fail-fast check
- **Where:** `las_tools.py:41-68` (`read_las_xyz_oci`), esp. `:61-67`
- **What:** The module docstring (`:4-9`) and function docstring (`:42,46`) clearly
  state WHY this exists (laspy chokes on a duplicate "C2C absolute distances" field) --
  that part is good. But the actual parse has zero validation: no assertion on LAS
  point-data-record format id, no check that `off_pts`/`pt_len`/`n` (read from fixed
  header byte offsets `:51-53`) are sane, and no check that the "Original cloud index"
  extra dimension is actually 4 bytes before `.view(np.float32)` casts it (`:67`). Any
  LAS with a different point-record layout, or where that scalar field isn't a 4-byte
  float, will silently produce wrong X/Y/Z or wrong cloud-index numbers rather than
  erroring.
- **Why it hurts handover:** goal (3), directly named in the assignment brief. A
  successor extending the work to a new LAS export (a very plausible next step -- more
  of the tube re-registered) gets silently wrong coordinates with no signal.
- **Proposed action:** add 2-3 asserts: point-format id / expected `pt_len` range via
  laspy header (already opened in `_oci_offset`, `:30`), and `d.num_bytes == 4` for the
  matched extra dimension in `_oci_offset` (`:35-37`) before the caller relies on the
  float32 view. Fail loud with a message naming the assumption.
- **Touches numbers?:** NO (adds guards only; does not change parse logic for the
  files currently in use, which already satisfy the assumptions).
- **Effort:** S

### [3] `PF_junction_subsampled.xyz` likely still carries the pre-RTK-pin ~9 m error
- **Where:** `LiDAR La Corona/Reregistered clouds/PF_junction_subsampled.xyz`
  (file, not code); consumed by GPR's `plot_flowerpetal_3d.py` per `CLAUDE.md`'s
  "Current Focus" item 5 note in the GPR session and thesis figures at
  `main.tex:1373,1406` (captions "with LiDAR ground truth", "the true tube ceiling
  clearly intersect with the GPR reflector").
- **What:** File timestamp is **16 Jun** (pre-fix). The other three Puerta Falsa
  exports that had the same "copied before the RTK nudge" bug (`PF_ref_after.txt`,
  `PF_stitch_after.txt`, `PF_tube_after.txt`) were corrected and re-exported **11 Jul**
  (this session, the `-9.17 E / +1.27 N` shift). `PF_junction_subsampled.xyz` was never
  touched -- it is the same export vintage/format as the other three pre-fix files and
  was explicitly flagged mid-session as deferred ("leave downstream consequences for
  now"), then never revisited. Not present at all in `CLAUDE.md`'s Current Focus list,
  so a successor has no record this is an open question.
- **Why it hurts handover:** goal (1). Two thesis figure captions
  (`main.tex:1373,1406`) make a specific spatial claim ("the true tube ceiling clearly
  intersect with the GPR reflector") using this cloud. If it is off by ~9 m, that claim
  needs re-checking before a defence answers a question about it.
- **Proposed action:** NOT a code fix -- a verification task. Diff
  `PF_junction_subsampled.xyz` against one of the corrected `PF_*_after.txt` files on a
  shared identifiable feature (or just re-export the subsample from the now-corrected
  full cloud). Recommend flagging to the user directly rather than silently folding
  into phase 2, since it may be defence-relevant. Per REFACTOR.md rule 3, if you confirm
  a real discrepancy this becomes a root-QandA STOP, not a routine finding.
- **Touches numbers?:** Unresolved -- exactly the point. Possibly YES.
- **Effort:** S to check, unknown to fix (re-export from CloudCompare if confirmed off).

### [4] `verify_alignment.py` has a real compute/plot seam (503 lines)
- **Where:** `verify_alignment.py` -- loaders `:93-207` (~115 lines) + `residual()`
  `:208-224` (~17 lines) = compute/stats block; plotting helpers + `plot()`
  `:227-444` (~220 lines); `main()` CLI/orchestration `:445-503` (~60 lines).
- **What:** Same shape as the `Inversion/` split that already happened (compute vs
  plotting, cited as the proven precedent in REFACTOR.md). Currently one file mixing
  data loading, residual statistics, and ~220 lines of multi-panel thesis-figure
  plotting code.
- **Why it hurts handover:** goal (3). A successor wanting to add a third
  before/after comparison (a third site, say) has to read through 220 lines of
  plotting internals to find the ~115 lines of loader/stats logic they actually need
  to extend, and vice versa for someone who just wants the residual numbers without
  the plotting machinery.
- **Proposed action:** split into `verify_alignment_io.py` (loaders + `residual()`)
  and keep plotting + CLI in `verify_alignment.py`, importing the io module. Assess
  only -- do not act in phase 1.
- **Touches numbers?:** YES if executed carelessly (name it: `alignment_check.png` +
  `gente_check.png` printed residual stats, both reproducible by re-running each mode).
  A phase-2 split must re-run both modes and diff the printed numbers + eyeball the two
  figures once.
- **Effort:** M

### [5] `gt_metrics.py`'s plane-vs-feature vertical warning -- CONFIRMED correctly placed (no action)
- **Where:** `gt_metrics.py:91-97` (docstring of `vertical_offset_to_plane`, the
  risky function itself) and `:110-115` (`vertical_offset_at_feature`, the safe
  alternative it points to); call sites at `:136` (feature, correct) and inside
  `la_gente()` (plane, correct).
- **What:** The assignment asked me to verify this warning is where someone would
  actually hit it, not only at the top of the file. Checked: it is on the function
  itself, not just the module docstring, and the function that would misfire at
  Puerta Falsa's shaft edge (`vertical_offset_to_plane`) explicitly says so and points
  to the correct alternative. This is the right place -- a successor calling the
  function reads the warning inline, not buried in module-level prose.
- **Why it hurts handover:** N/A -- reporting as CONFIRMED GOOD per the assignment's
  explicit request, not a problem.
- **Proposed action:** none.
- **Touches numbers?:** N/A
- **Effort:** N/A (no-op finding)

---

## Thesis traceability table

Built per checklist item (g). No gaps found for LiDAR-authored figures/tables --
reporting the full map since the checklist asks for it regardless.

| Thesis artifact | Label | Producer |
|---|---|---|
| Puerta Falsa before/after figure | `fig:puertafalsa-check` (`main.tex:1129`) | `verify_alignment.py` (default mode) |
| La Gente before/after figure | `fig:lagente-check` (`main.tex:1480`) | `verify_alignment.py --gente` |
| Vertical-residual RSS table (0.24 / 0.21 m) | `tab:lidar-vertical-budget` (`main.tex:1137`) | `gt_metrics.py` -- exact numeric match confirmed |
| L3/L5 cross-section areas (203 / 182 m^2) | inversion results tables `main.tex:937-938,1044` | `slice_tube.py` -> `Data/LiDAR/lidar_line{3,5}.csv` (see finding 1 for the stale write path) |
| Sauro comparison figure | `fig:sauro-check` (`main.tex:1475`) | external (Sauro et al. 2020 scan) -- not LiDAR-session code, correctly so |
| Flower-petal 3D snapshots w/ LiDAR ground truth | `fig:fp3d*`, `fig:fp3d-mig*` (`main.tex:1373,1406`) | GPR session's `plot_flowerpetal_3d.py`, consuming `PF_junction_subsampled.xyz` -- see finding 3 |
| Overburden / envelope maps | (QGIS session figures) | `Reregistered clouds/Gente_envelope.shp`, `QGIS/caveheight_clean_laGente.tif` -- produced by LiDAR session, handed to QGIS |

---

## Reproducibility note (checklist f) -- the manual-CloudCompare question

The assignment specifically asked: given only `alignment_transforms.txt` + the raw
`.bin`, could a successor reproduce `lidar_line{3,5}.csv` and the 203/182 m^2 areas?

**Two different claims, worth separating clearly (currently the docs read as one):**
- **Verify the existing result:** YES, fully reproducible. `alignment_transforms.txt`
  records the exact net 4x4 matrices (with RMS) for every registration step; a
  successor applies them directly in CloudCompare (Edit > Apply Transformation) to the
  raw subsets and lands on the delivered clouds -- no by-eye step needed to verify.
  `slice_tube.py` + `gt_metrics.py` are then deterministic given those clouds.
- **Redo the registration from scratch (e.g. on newly scanned data):** NOT
  reproducible as documented. The CloudCompare Workflow section of `CLAUDE.md` (and
  the initial coarse step in `alignment_transforms.txt` sec. 2/4) explicitly starts
  from a manual by-eye rotate/translate that seeds the ICP fit. A different by-eye seed
  could converge to a different local optimum, especially for the ~51 degree Puerta
  Falsa swing.
- **Proposed action:** one sentence in `CLAUDE.md` distinguishing "apply the recorded
  matrix to verify/reproduce the delivered result" (deterministic) from "the by-eye
  recipe if re-registering new data" (semi-reproducible, operator-dependent). Cheap,
  closes a real ambiguity a successor would otherwise have to guess at.
- **Effort:** S

---

## Recommended cut line

Above the line -- clearly worth doing in phase 2:
1. Fix `slice_tube.py`'s stale output path (finding 1)
2. Add fail-fast asserts to `las_tools.py` (finding 2)
3. Verify (and if needed, re-export) `PF_junction_subsampled.xyz` (finding 3) --
   recommend doing this FIRST and separately, since it may be a rule-3 STOP
4. The reproducibility-note sentence in `CLAUDE.md`

Below the line -- honestly optional:
5. The `verify_alignment.py` compute/plot split (finding 4) -- real seam, but the
   file is not painful to navigate today and the split carries re-verification risk
   for marginal benefit at this project's remaining lifespan. Only worth it if the
   session continues to grow this file.

No dead code, no cross-session duplication beyond the intentional and already-clean
reuse (`gt_metrics.py` imports `kabsch` from `recover_transform.py` rather than
copy-pasting it), and no untested/untestable script found beyond what's already noted
above -- `gt_metrics.py`'s "order check" print (`gt_metrics.py`, tube before/after
rigid-fit RMS) already functions as an inline self-test; the one test I'd propose
adding is a small script-level assertion that `slice_tube.py --no-write` reproduces
the frozen areas (203 / 182 m^2) within a tight tolerance, catching exactly the kind
of silent drift in finding 1 -- propose only, not written.

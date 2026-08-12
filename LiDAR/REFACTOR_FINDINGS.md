# LiDAR session -- Phase 1 refactor audit (+ phase 2 addenda)

Scope: `Code/LiDAR/` (5 scripts, 998 lines). Findings ranked by handover value / risk,
per `Code/REFACTOR.md`. Phase-1 content below is unedited except finding [3], updated
2026-08-11 after direct verification (see its entry). New phase-2 material is appended
at the end, dated.

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

### [3] `PF_junction_subsampled.xyz` -- CHECKED 2026-08-11, hypothesis REFUTED, no action
- **Where:** `LiDAR La Corona/Reregistered clouds/PF_junction_subsampled.xyz`
  (file, not code); consumed by GPR's `plot_flowerpetal_3d.py`, thesis figures at
  `main.tex:1373,1406`.
- **What:** Phase-1 flagged this as circumstantially likely to carry the pre-RTK-pin
  ~9.17 E / -1.27 N offset (same file timestamp era -- 16 Jun -- as the three sibling
  exports that DID have that bug). Directly verified per Supervisor's phase-2 priority-1
  instruction: nearest-neighbour (horizontal, E/N only) from 50,000 sampled points of
  `PF_junction_subsampled.xyz` to the corrected cave (`PF_ref_after.txt` +
  `PF_stitch_after.txt` + `PF_tube_after.txt`) gives **median 0.00 m, mean 0.00 m** --
  the file already matches the corrected registration essentially exactly. Applying the
  recorded `-9.17 E / +1.27 N` pin on top makes it WORSE (median 0.17 m, mean 0.62 m),
  confirming the file is not shifted and should not be. The 16 Jun timestamp was a red
  herring -- it does not establish CloudCompare export order relative to the RTK-pin
  application; the file content is what settles it, and it settles clean.
- **Why it hurts handover:** N/A -- reporting as CONFIRMED CLEAN, not a problem.
  `main.tex:1373,1406`'s claim is unaffected; no rule-3 escalation needed.
- **Proposed action:** none for the file itself. Still recommend a one-line note in
  `CLAUDE.md`'s Current Focus recording that `PF_junction_subsampled.xyz` was audited
  and confirmed post-RTK-pin (2026-08-11), so this doesn't get re-flagged as a mystery
  by a future audit -- cheap, closes the loop.
- **Touches numbers?:** NO (verification only; nothing changed).
- **Effort:** S (already done)

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
| Overburden / envelope maps | (QGIS session figures) | `Reregistered clouds/Gente_envelope.shp`, `QGIS project/caveheight_clean_laGente.tif` -- produced by LiDAR session, handed to QGIS |

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

---

## Phase 2 -- `C:\Users\jj_ve\lidar_scratch` audit (2026-08-11)

Per the new handover model, this folder is OUTSIDE the delivered project tree and has
no backup -- anything here that a script depends on must move in, or the successor
never gets it. Full inventory + cross-check against every `Code/LiDAR/` script:

**Contents (all timestamped 15 Jun -- the day the LiDAR session started, one day
BEFORE any actual alignment work began on 16 Jun per `CLAUDE.md`'s Current Focus):**
- 46 `LaCorona_N_...las` files (~550 MB total) -- a one-time CloudCompare export of
  the raw merged cloud split by `Original cloud index` (idx 0..45; most are the tiny
  marker objects noted in `CLAUDE.md`'s Data Description, a handful are the 5
  substantial clouds).
- `stray_subsampled_bins/` -- 30 matching `..._RANDOM_SUBSAMPLED_...bin` files
  (~44 MB), same split, subsampled for quick viewing.
- 7 tiny one-off exploration scripts (`cloud_inspect.py`, `dims.py`, `headers.py`,
  `idx_in_34.py`, `junction.py`, `probe.py`, `split_view.py`; ~9 KB combined) and 3
  diagnostic PNGs (`junction.png`, `junction_check.png`, `split_top.png`; ~1.4 MB) --
  first-look exploration of the cloud structure, before the CloudCompare workflow in
  `CLAUDE.md` was settled.

**Cross-check -- is any of it consumed?** Grepped all of `Code/` for
`lidar_scratch`: only `CLAUDE.md` (describing the folder's PURPOSE) and
`REFACTOR.md` (this task) mention it. Zero references from `las_tools.py`,
`verify_alignment.py`, `slice_tube.py`, `recover_transform.py`, or `gt_metrics.py` --
none of them hardcode a `lidar_scratch` path (`las_tools.py`'s CLI takes paths as
`sys.argv`, not a hardcoded default).

**Verdict: nothing here is load-bearing.** The entire folder is a superseded,
one-time investigation dump that predates the actual registration work -- the real
decision record for that work is `alignment_transforms.txt`, in git. Regenerability is
moot for the same reason (nothing depends on it), but for completeness: the LAS/bin
exports are trivial re-exports of `LaCorona.bin` (still safe in OneDrive), so nothing
here is irreplaceable in the sense the data-safety rule cares about.

**Proposed action (NOT executed -- awaiting confirmation per rule 5):**
- The 46 LAS + 30 subsampled bins (~594 MB): no reason to move them into the project
  tree. Recommend simply leaving `lidar_scratch` behind (nothing depends on it, so
  its absence from the handover changes nothing) or deleting it outright -- author's
  call, since rule 5 makes an outright delete something only the author approves.
- The 7 small scripts + 3 PNGs (~1.4 MB): borderline decision-history value ("this is
  how the cloud structure was first explored"), but `alignment_transforms.txt` already
  captures the actual decisions that mattered, so this is low-value. If the author
  wants it preserved anyway, propose copying to `Code/LiDAR/Legacy/lidar_scratch_exploration/`
  with a one-line header per rule 5; otherwise fine to leave behind too.
- Either way: no code or CLAUDE.md change is required as a result of this audit --
  there is no gap to document, since nothing reads from this location.

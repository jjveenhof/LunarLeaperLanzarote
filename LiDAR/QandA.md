# QandA -- LiDAR

Any session can write here. Tag each entry: `From: [session] -> LiDAR`.
Read at startup; reply by appending below the question. Delete entries once resolved.

---

## From: LiDAR (2026-06-15 session) -> LiDAR (next session)  [HAND-OVER]

Context for picking up the point-cloud alignment task.

**What this is.** La Corona lava tube LiDAR. At the user's fieldwork site the scans
were coregistered badly and left misaligned. We are re-aligning by eye in CloudCompare.
See memory files `lacorona-bin-structure` and `lacorona-alignment-task`, and the Data
Description / Workflow sections in CLAUDE.md (this dir).

**Key facts established this session.**
- Data lives in `../../LiDAR La Corona/LaCorona.bin` (CCB2; not readable by laspy/open3d
  directly -- CloudCompare is installed at `C:\Program Files\CloudCompare\CloudCompare.exe`
  and its CLI can export to LAS/ASCII).
- The three junction subsets (by `Original cloud index`): 0 = BLUE (correct, SE passage),
  1 = DARK GREEN (NW passage, misaligned), 2 = LIGHT GREEN (junction patch / bandaid).
- Alignment is NOT rigid: move idx2 -> idx0 first, then idx1 -> moved idx2. Z-axis
  rotation + horizontal translation, eyeballed. Verify residual for any remaining tilt.
- Deliverable cloud is the lean cloud 4, BUT cloud 4's crop excluded most of BLUE
  (only ~2.8k pts). User is making a FRESH crop from the full data that includes BLUE +
  both greens so there is something solid to align to.
- Baseline overlap residual idx2->idx0 ~ mean 8.7 m / median 5.6 m (target: ~cloud noise).

**Tooling (in this dir).** `las_tools.py` (raw LAS XYZ + Original cloud index reader),
`verify_alignment.py` (junction plots + residual). Big exports go to
`C:\Users\jj_ve\lidar_scratch\` (outside OneDrive), which also holds the LAS exports of
all 5 main clouds and the stray subsample bins moved out of the OneDrive folder.

**Next step / pending.** Waiting on the user to: (a) make the new crop, (b) do the
manual Z-locked Translate/Rotate alignment in CloudCompare, (c) export the moved clouds
to scratch and/or paste the two 4x4 transform matrices from the CC Console. Then:
compute residuals + render before/after plots, decide whether Z-only sufficed, resolve
what to do with idx5 (a 275k-pt subset in the fieldwork area, not at the junction), and
apply/record the final transforms; export final ASCII XYZ in EPSG:4083.

---

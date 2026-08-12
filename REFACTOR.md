# Post-submission refactor -- shared protocol

Written by the Supervisor session, 2026-08-03. Read this before starting the refactor
task in your QandA.md. Your QandA entry gives the per-session scope; this file gives the
method, the safety rules, and the deliverable format. They are the same for every session.

## Goal: HANDOVER

The thesis is SUBMITTED. Nothing here is about improving the result. The target is:

> A competent MSc student who has never seen this project can (1) verify any number in
> the thesis, (2) regenerate any figure, (3) extend the work -- without asking the author.

Judge every proposed change against that sentence. "Cleaner" is not a reason. "A
successor would waste an hour here" is a reason.

## HARD RULES -- do not break these

1. **The thesis is frozen.** No refactor may change any number, table value, or figure
   content that appears in the thesis. Appearance changes are also out (see rule 6).

2. **Prove non-regression, do not assume it.** Before editing a script, run it and keep
   its outputs. After editing, re-run and compare:
   - Numerical artifacts (CSV, NPZ) are the real check -- compare with
     `np.allclose` / exact string match on non-float columns. These MUST match.
   - Figures: do NOT byte-diff PNG/PDF (timestamps and font hinting differ between runs
     even with identical data). Verify the numbers the figure is drawn from instead, and
     eyeball the image once.
   - If a script has no numerical output, say so in the findings and treat the change as
     higher risk.

3. **A discrepancy is a STOP, not a fix.** If re-running produces a different number than
   the thesis reports, do NOT quietly correct anything. Write it to the root
   `QandA.md` tagged `From: [your session] -> Supervisor` immediately and stop that
   thread. A latent bug found now matters for the defence -- the author needs to know
   before he stands in front of the committee, and he decides what to do about it.

4. **Read-only on data.** The refactor touches `Code/` only. Raw acquisition data
   (`Data/GPR/Stitched/`, raw `Data/GNSS/`, `Data/Gravimetry/Field data` + Notes,
   `LiDAR La Corona/*.bin`) is irreplaceable and outside scope. Regenerating
   `Data/*/Processed/` or `Results/` is fine.

5. **Quarantine beats delete.** Superseded scripts carry decision history -- that history
   IS handover value ("we tried this, it didn't work"). Move them to the session's
   `Adhoc/` or `Legacy/` folder with a one-line header saying what it was for and why it
   is not in the main chain. Propose an outright delete only for genuinely empty or
   duplicated files, and list it separately so the author can veto.

6. **The plot-tuning rule still applies.** Do not restyle, resize, recolour, or "improve"
   any figure. If a refactor would change a figure's appearance, that is a regression.

7. **ASCII only**, and keep using the env python
   (`/c/Users/jj_ve/miniconda3/envs/GPR_plotting_LL/python.exe`). Do not change the
   environment or upgrade dependencies.

8. **Do not rename output data files.** Output filenames are documented in the CLAUDE.md
   files and consumed across sessions (e.g. Grav reads `Data/LiDAR/lidar_line{3,5}.csv`).
   Renaming an output is a cross-session change -- propose it in findings, never just do it.

9. **Never commit.** The author commits. Ask him to, after each phase.

## Phase 1 -- AUDIT ONLY. No edits.

Do not change a single line of code in phase 1. Produce
`Code/<YourMethod>/REFACTOR_FINDINGS.md` and then report back in your QandA.md.

### Use Explore subagents for the survey

You have explicit permission (from the author, via this plan) to spawn `Explore`
subagents for the phase-1 survey, and to run several in parallel. This is the whole
point: they read the files and hand you conclusions, so the file contents never enter
your context. Do not use them in phase 2 -- by then you already know the code, and a
cold agent would just re-derive it.

Give each agent one narrow question and tell it to report file:line evidence. Good
splits: one agent per checklist item below, or one per subfolder. Ask for "medium"
breadth for a single folder, "very thorough" when it must chase naming variants.

### Checklist -- what to look for

- **a. Entry points and run order.** Is there one obvious command that reproduces
  everything? Map the real dependency graph: script -> inputs -> outputs -> which script
  consumes them next. Flag any step that only exists in someone's head or in a notebook.

- **b. Dead and superseded code.** Scripts nothing calls, functions nothing imports,
  legacy configs, commented-out blocks. Classify each: DELETE / QUARANTINE / KEEP (and
  if KEEP, does it need a header note explaining why it survives?).

- **c. Duplication.** Copy-pasted helpers that should live in the existing shared modules
  (`Code/plot_utils.py`, `Grav/grav_utils.py`, `GPR/gpr_constants.py`). Also duplication
  ACROSS sessions -- if two methods hand-roll the same thing, say so; the Supervisor will
  decide whether it belongs in `Code/plot_utils.py`.

- **d. Hardcoded values.** Magic numbers, absolute paths, hardcoded line/station names.
  Highest priority: any constant that also appears in a CLAUDE.md or in another script --
  those are drift bombs (the doc and the code can disagree silently). Note where a value
  is deliberately hardcoded because the thesis froze it; that is fine, but it should say so.

- **e. Oversized scripts.** Files over ~350 lines. Ask whether the file does one job or
  several. Propose a split ONLY where there is a real seam (compute vs plotting is the
  proven one -- see the `Inversion/` refactor that produced `inversion_io.py`). Do not
  split for line count alone.

- **f. Reproducibility gaps.** Undocumented manual steps, missing inputs, outputs that
  cannot be regenerated, steps that live only in a notebook, external dependencies with
  no version pinned. For handover this is the highest-value category.

- **g. Thesis traceability.** Which script produces which thesis figure and table. Build
  the table even where nothing else needs refactoring -- this is arguably THE handover
  artifact. Figure/table labels are in `C:\Users\jj_ve\thesis-overleaf\main.tex`; the
  PDFs land in that repo's figure folders. Report gaps (a thesis figure with no known
  producing script) loudly.

- **h. Tests.** What exists, what it covers, and the single test a successor would most
  want that does not exist. Do not write it yet -- propose it.

### Findings format

One entry per finding, ranked. Keep it skimmable -- the author reads all four of these.

```
### [rank] Short title
- **Where:** path/to/file.py:120-180
- **What:** one sentence, factual.
- **Why it hurts handover:** one sentence tied to the goal sentence at the top.
- **Proposed action:** concrete.
- **Touches numbers?:** NO / YES (if YES, name the verification artifact to diff)
- **Effort:** S / M / L
```

Rank by handover value divided by risk. A docs-only fix that closes a reproducibility
gap outranks a satisfying but risky restructure. Put a "recommended cut line" in the
list: above it, worth doing; below it, honestly optional. Do not pad the list.

## Phase 2 -- EXECUTE, only after the author approves

He will approve a subset. Work strictly in this order, committing (i.e. asking him to
commit) between stages:

1. **Zero-risk:** docstrings, headers, the traceability table, README, quarantine moves,
   naming consistency. Nothing that can change a number.
2. **Low-risk:** extracting duplicated helpers into the existing shared modules, with the
   phase-2 verification from rule 2 after each extraction.
3. **Structural:** file splits. One script at a time. Verify after each. If verification
   is awkward because the script emits no numbers, say so and consider leaving it.

Stop and report if the approved list turns out to be wrong once you are inside the code.
Discovering that a "dead" script is actually load-bearing is a good outcome, not a failure.

## Out of scope for all sessions

- Any new analysis, or re-running an analysis to get a better answer.
- Figure restyling of any kind.
- Environment or dependency changes.
- Renaming output data files (propose only -- rule 8).
- Anything in `Other data and scripts/` (other people's code).
- The Supervisor session owns the cross-cutting items: a top-level `Code/README.md`, the
  environment spec, `.gitignore` coverage, and `Grav/Tests` vs `GPR/tests` naming. Do not
  do these yourself -- flag them if you hit them and move on.

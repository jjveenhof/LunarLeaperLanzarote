# Phase 3 -- documentation consolidation

Written by the Supervisor session, 2026-08-12, on the author's instruction. Phases 1
(audit) and 2 (execute) are about CODE. Phase 3 is about the WORDS, and it is the last
thing that happens before handover.

**Do not start Phase 3 until your Phase 2 items are done and committed.** Consolidating
documentation while the code it describes is still moving means doing it twice.

## Why this phase exists

`Code/` currently holds 17 markdown files, ~3,100 lines. The root `README.md` -- the one
file a successor opens first -- is empty. Along the way we have accumulated three parallel
layers that describe the same events:

- `REFACTOR_FINDINGS.md` -- what we found
- `QandA.md` -- what we decided
- `CLAUDE.md` -- what is true now

Only the third has any value after 2026-08-17. The first two are process scaffolding for a
job that ends. Meanwhile the `CLAUDE.md` files have grown into research journals: real
decision history, genuinely valuable, but mixed in with the operating instructions so that
a newcomer cannot tell settled fact from working note. The Grav session flagged exactly
this in its own finding [20]; the author confirmed it project-wide.

## The test to apply to every line

> **Does this stop a successor from making a mistake, or does it only tell them what we
> did?**

Keep the first. Cut the second.

- "velocity_sigma is 0.015 m/ns" -- FACT. Keep, in the reference doc.
- "velocity_sigma was 0.010 until 2026-07-29" -- HISTORY. Cut, unless a number in the
  thesis depends on knowing it.
- "L5's near-pure hyperbola is a COINCIDENCE -- do not claim it obeys theory" -- this is
  the FIRST kind wearing the clothes of the second. It prevents a wrong claim. KEEP, and
  keep it prominent.
- "Build appendix grids at their FINAL width or 7 pt text lands at 2.7 pt" -- a trap that
  bit us once and would bite again. KEEP.

When a line is genuinely ambiguous, keep it. The failure mode we are avoiding is a
successor who cannot find the operating instructions inside the journal -- not a successor
who reads one paragraph of history too many.

## Target end state

```
Code/
  README.md              <- THE entry point. Currently EMPTY; this is the biggest single gap.
  REPRODUCE.md           <- one command per method, in order, with expected outputs (Supervisor)
  TRACEABILITY.md        <- consolidated thesis figure/table -> script map (Supervisor)
  environment.yml        <- already written
  goldenmaster.py        <- already written, shared
  <Method>/
    README.md            <- what this session does, pipeline order, file contracts, gotchas
    DECISIONS.md         <- why we chose this, what we ruled out, what must not be re-litigated
```

`README.md` answers "how do I run this". `DECISIONS.md` answers "why is it like this, and
what will I get wrong if I change it". A successor reads the README to work and the
DECISIONS file when they want to question a result. Splitting on that seam is the whole
point -- both documents get shorter and each becomes skimmable.

### On deleting the CLAUDE.md files

Yes, they go -- but by CONVERSION, not deletion. `CLAUDE.md` is an artifact of how this
project was built (topic-split Claude Code sessions) and means nothing to a human
successor who opens the folder. Its CONTENT is most of what the new README and DECISIONS
files are made of.

Per session: `CLAUDE.md` -> split into `README.md` + `DECISIONS.md` -> delete `CLAUDE.md`.
Nothing is lost; it is redistributed.

The root `CLAUDE.md` (project level, outside git) is the one exception -- see the ordering
note below.

## Per-session work

Each session does its own. The Supervisor does the root-level files and the final read.

1. **Split your `CLAUDE.md`.** Reference material -> `README.md`. Reasoning, falsified
   hypotheses, "do not re-open" decisions -> `DECISIONS.md`. Apply the test above to every
   line as you move it; this is a rewrite, not a copy-paste with a heading between the
   halves. Expect to cut 20-40% outright.
2. **Write the run instructions properly** in `README.md`: the exact commands, in order,
   with what each produces and where it lands. Your Phase 2 "one runnable entry point"
   item feeds straight into this.
3. **State what is NOT reproducible**, plainly, where a successor will hit it -- the
   manual CloudCompare registration (LiDAR), the manual QGIS raster workflow (QGIS), any
   hand-maintained input such as `tube_picks.csv` (GPR). Each session already has this
   from Phase 2; make sure it survives the split and is not buried.
4. **Prune your code comments** to the same test. Comments that narrate a previous
   approach ("was 16.8 in wide", "used to use the settled rule") go, UNLESS the old
   approach is a trap someone could fall back into -- then rewrite them as a warning about
   the present, not a note about the past.
5. **Delete `REFACTOR_FINDINGS.md` and `QandA.md`** once everything in them is closed.
   Before deleting, check for anything recorded ONLY there and nowhere else -- the LiDAR
   `lidar_scratch` inventory is the known case, and the `PF_junction_subsampled.xyz`
   verification result is another. Anything in that category moves into `DECISIONS.md`
   first. Then delete. Do not archive them into a folder; that just moves the clutter.
6. **Report to the Supervisor** when done, with the final line count.

## Supervisor-owned

- `Code/README.md` -- the entry point: what the project is, what the thesis concluded, how
  to install the environment, how to run each method, where the data lives, what is
  reproducible and what is not. Short. It routes; it does not explain.
- `Code/REPRODUCE.md` and `Code/TRACEABILITY.md` -- already owed from Phase 2.
- Delete `Code/REFACTOR.md`, the root `QandA.md`, and **this file**. Phase 3 is finished
  when the plan for Phase 3 no longer exists. Writing another markdown file about deleting
  markdown files is only defensible if it removes itself at the end.
- Fold the root `CLAUDE.md` into `Code/README.md`. It sits outside git and holds real
  operating knowledge (CRS, environment path, data-safety rules) that a successor needs.

## Rules

1. **No code behaviour changes in Phase 3.** Docs and comments only. If you find a real
   bug while reading, report it -- do not fix it inside a documentation pass.
2. **The golden master stays in place** until the very end. It costs nothing and it is the
   only thing standing between a "harmless comment edit" and a silent regression. Run
   `check` once at the end of your Phase 3 and confirm it still passes.
3. **Rule 3 still applies.** A number that no longer reproduces is a STOP-and-escalate.
4. **Do not delete anything whose only copy is the thing you are deleting.** Check first.
   This is the one genuinely irreversible act in Phase 3.
5. **Never commit.** The author commits.

## Definition of done

A competent MSc student who has never seen this project can, from the folder alone:
install the environment, run each method end to end, find which script made any thesis
figure, and know which parts they cannot regenerate and why -- without opening a single
file whose name contains REFACTOR, QandA, or CLAUDE, because none exist any more.

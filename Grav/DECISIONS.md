# Grav -- decisions a successor cannot re-derive from the code

Each entry is a choice whose *reason* is invisible in the code: re-reading the scripts
would not reveal it, and a successor could innocently undo it. Recorded here because the
working discussion lived in `QandA.md`, which is gitignored and does not survive handover.

This is NOT a duplicate of `CLAUDE.md`'s "Current Focus" section -- that section is a
proper decision journal (density-sweep / beta1 mechanism, the velocity-channel redesign,
the settled-rule history) and stays exactly as it is; read it for the SCIENCE decisions.
This file is the narrower set of decisions that came out of the post-submission refactor
(2026-08) and would otherwise have been lost with the QandA.md threads that found them.

---

## 1. `BOUGUER_K` is pinned at the thesis `G = 6.674e-11`, NOT the CODATA `6.6743e-11`
Date settled: 2026-08-12 (`grav_utils.py`).

`grav_utils.G_NEWTON = 6.6743e-11` (CODATA) is used by the forward models
(`forward_polygon.py`, `forward_fem.py`, `inspect_2d_validity.py`). The Bouguer slab
constant does NOT use it: `grav_utils.G_BOUGUER = 6.674e-11` is kept as a second, separate
constant, with `BOUGUER_K` built from `G_BOUGUER`.

**Do not "fix" this by switching `BOUGUER_K` to `G_NEWTON`.** The two differ by 4.5e-5
relative -- max 0.009 uGal across all 130 stations, ~1000x below the smallest reported
digit, so no thesis number would move. But it WOULD shift every processed CSV at the
~1e-8 level, which fails `goldenmaster.py check` against the 2026-08 baseline and forces a
re-baseline -- the one operation the golden master deliberately refuses, because its whole
value is "still produces the SUBMITTED thesis". After a re-baseline, PASS would only mean
"matches whatever this refactor produced", which is a materially weaker guarantee.
A successor WILL notice the "wrong" `G` and want to fix it; this entry is what stops them.

## 2. `tab:tc_perline`'s "Station SE" column is the median `SE_lsq` over NON-BASE stations
Date settled: 2026-08-12 (`make_thesis_tables.py`, function `tc_perline`).

The base station's `SE_lsq` is EXACTLY 0.0 by datum definition (it is not measured, it
is fixed). Averaging it in with the other stations drags any summary statistic toward
zero. The thesis column excludes it; `make_thesis_tables.py` does too, and rounds
half-up (`round_half_up`, NOT Python/numpy's round-half-to-even) when comparing against
the printed thesis values.

This one cost a real (later-retracted) escalation: computing the column over ALL
stations gives 0.012 / 0.015 / 0.012 / 0.026 instead of the thesis's
0.014 / 0.020 / 0.014 / 0.029, which looks exactly like a stale pipeline. It is not --
it is the base-station structural zero. Re-deriving this column from scratch will
reproduce the same wrong answer unless the exclusion is remembered.

One cell remains genuinely different and is fine to leave alone: L4 Station SE is 0.013
today vs the thesis's 0.014, because the raw median (0.013541) sits on the 3-dp rounding
boundary and the 2026-08-01 `TAU_MIN` fix (item 4 below) moved it to 0.013447. Worth
0.0001 mGal; not worth chasing further.

## 3. The SE chain (`SE_lsq`, `SE_SBA`, `SE_elev`) has been stable since at least 2026-06-11
Verified 2026-08-12 by rebuilding the pipeline at commit `ed6f723` (2026-06-11, the commit
that first integrated the terrain correction) in a scratch worktree and comparing SE
statistics against the current pipeline: identical except for the single L4 rounding-
boundary cell in item 2. So if a future SE-related discrepancy shows up, the uncertainty
CHAIN is not a suspect going back to mid-June -- look at what changed instead (station
exclusions, the settled-rule fix, or something newer).

Method note, worth repeating if this kind of archaeology is needed again: reconstruct the
old pipeline in a **detached `git worktree`** pointed at a **scratch copy of `Data/`**
(never the real `Processed/` -- old code will overwrite it), with `THESIS_REPO` redirected
to a throwaway folder so old plotting code cannot touch the real Overleaf clone. This
leaves the working tree, the real data and the thesis repo completely untouched.

## 4. One Discussion sentence (`main.tex:1002`) quotes PRE-2026-07-30 inversion SEs
The Discussion's first "multi-method approach" paragraph says L3 circle/ellipse/L5 circle
SEs of 40/28/35. Every other place in the thesis (`tab:inversion-results`, the Conclusion,
`tab:se-budget`) says 41/24/36. The ellipse value (28) is the tell: it is unreachable with
the current inversion engine at any plausible `velocity_sigma` (24-25 m^2), but the
pre-2026-07-30 engine (multiplicative velocity scaling, before the common-mode depth-shift
redesign recorded in `CLAUDE.md`) gives 27.1-27.2 -- close enough, together with the
qualitative direction, to be confident this is simply a sentence nobody swept after the
velocity channel was fixed. **Do not "fix" `main.tex`** -- the thesis is frozen; this is
answer-in-your-pocket material for the defence, not an edit.

## 5. `freedepth.py`'s parallel `.npz` artifact format was NOT folded into `inversion_io`
This was finding [14] in `REFACTOR_FINDINGS.md`, explicitly left undone in phase 2 --
not missed. `freedepth.py` persists the full chi2 CUBE (ceiling x size x x0), which
`inversion_io`'s per-case artifact format has no slot for; `plot_freedepth_terrain.py`
reads the cube directly. Folding it in is a real seam, but it is the only phase-2 item
that would touch the free-depth artifacts the terrain twin depends on, so it was left
for a dedicated pass rather than rushed alongside everything else. If picking this up,
re-run `plot_freedepth_terrain.py` for both lines and diff the figures' input numbers,
not just the golden master (the cube's shape carries information the per-case format
would need to preserve some other way).

## 6. Do not unify the per-line colour palette / station-marker maps yourself
`plot_utils.py` (colour palette, `plot_utils.py`) is owned by the Supervisor session, not
Grav -- flagged, not fixed, in `REFACTOR_FINDINGS.md` finding [8]. The tie-station marker
specifically differs between `Legacy/visualise_lines.py` (`^`) and
`Inversion/plot_model_terrain.py`/`terrain_common.py` (`v`); harmonising it would change
the appearance of an already-published figure (REFACTOR.md rule 6). If asked to unify the
palette later, that discrepancy needs an explicit decision, not a silent pick.

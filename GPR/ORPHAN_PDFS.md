# Orphan GPR PDFs in `thesis-overleaf/GPR/` -- author's call to prune

Phase-2 deliverable (2026-08-12). These PDFs exist in the Overleaf `GPR/` folder but
are NOT `\includegraphics`'d anywhere in `main.tex`. **Nothing here was deleted** --
the thesis is frozen and the Overleaf repo is the author's to touch (rule 8). This is
just the list so he can prune if he wants a clean handover.

Cross-check method: `ls GPR/*.pdf` vs every `\includegraphics{GPR/...}` in main.tex.

## Produced-but-unused (a script still makes them; thesis just doesn't include them)
| PDF | produced by | why unused |
|---|---|---|
| Line3_50MHz_picks.pdf | plot_picks.py | thesis uses the combined `_dual_freq_migrated_picks` instead |
| Line3_100MHz_picks.pdf | plot_picks.py | same |
| Line5_50MHz_picks.pdf | plot_picks.py | same |
| Line5_100MHz_picks.pdf | plot_picks.py | same |
| Line3_dual_freq_migrated.pdf | plot_dual_freq.py (plain migrated) | thesis uses the `_picks` annotated variant |
| Line5_dual_freq_migrated.pdf | plot_dual_freq.py (plain migrated) | same |
| Line3_dual_freq_topo.pdf | plot_dual_freq.py --stage topo (run by run_pipeline for all lines) | thesis only includes Line2's dual-freq-topo |
| Line5_dual_freq_topo.pdf | plot_dual_freq.py --stage topo | same |

Note: these regenerate every time `run_all.py` / `run_pipeline.py` runs, so deleting them
from Overleaf is cosmetic -- they'd reappear if the pipeline is re-run into that folder.
`plot_picks.py` itself is the only producer with no live thesis consumer at all; consider
noting it as "diagnostic, not a thesis figure" (it was superseded by the dual-freq picks).

## Stale: unproduced AND unused (no current script emits these -- leftovers)
| PDF | status |
|---|---|
| arrival_chart.pdf | no producing script found anywhere; superseded by `gpr_arrivals_schematic.pdf` (the merged schematic) |
| multiples_schematic.pdf | no producing script (plot_multiples_schematic.py outputs `gpr_arrivals_schematic`, not this name); stale name |

These two are safe to delete from Overleaf -- nothing makes or uses them. The others are
regenerable, so pruning is optional.

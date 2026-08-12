# Code/GPR/Adhoc -- quarantined, not part of the reproduce chain

Moved here in the phase-2 handover refactor (F9, 2026-08-11). Nothing in the live
pipeline reads any of this. Kept (not deleted) for decision history -- rule 5.

## `make_variant.py`
Ad-hoc tool that reprocesses a profile with parameter overrides under a variant
stem. It generated the L2 / SVD-notch trial. Its conclusion -- the Line 2 100 MHz
spectral notch is a hardware artifact that SVD removal and spectral whitening do
NOT fix -- is preserved in `Code/GPR/CLAUDE.md` (Current Focus) and in the two
thesis-evidence figures `plot_l2_spectral_diagnostics.py` / `plot_l2_svd_whiten.py`.
It was written to run from `Code/GPR/` (imports assume that dir on sys.path); move
it back if you ever need to run it.

## `Line5_100MHz_svd1_*` (6 files)
The output artifacts of that trial (the `--suffix svd1` run = `n_svd=1` on
Line5_100MHz). These carried a stale `velocity: 0.11` that disagreed with the
settled 0.125; they are NOT a live profile and nothing consumes the `svd1` stem.
Original locations before quarantine:

| file | came from |
|---|---|
| Line5_100MHz_svd1_params.json | Data/GPR/Processed/ |
| Line5_100MHz_svd1_processed.npz | Data/GPR/Processed/ |
| Line5_100MHz_svd1_topo.json | Data/GPR/Topo/ |
| Line5_100MHz_svd1_topo.npz | Data/GPR/Topo/ |
| Line5_100MHz_svd1_topo.png | Results/GPR/Topo/ |
| Line5_100MHz_svd1_stolt_velocity_scan.html | Results/GPR/Migration/ |

The author may delete this whole folder if the decision history is no longer wanted.

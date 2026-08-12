"""
run_all.py -- one command to regenerate every LiDAR-session output that depends only
on the already-corrected point clouds (no manual CloudCompare work).

Runs, in order:
  1. slice_tube.py --line 3, --line 5   -> Data/LiDAR/lidar_line{3,5}.csv
     (the ground-truth cross-sections the Grav inversion is validated against)
  2. verify_alignment.py (default)      -> alignment_check.png (Puerta Falsa figure)
  3. verify_alignment.py --gente        -> gente_check.png (La Gente figure)
  4. gt_metrics.py                      -> ground-truth accuracy numbers (printed)

Each step's inputs are the corrected exports in `LiDAR La Corona/Reregistered clouds/`
(and `Clouds to reconstruct transformations/` for the Gente before/after pair) --
see slice_tube.DEFAULT_SOURCE for the canonical line->export mapping and
CLAUDE.md's "reproducibility" note for what IS and is NOT regenerable this way.

NOT covered here (deliberately -- these are checks, not regeneration, or require a
GUI step this script cannot do):
  - The CloudCompare alignment itself: manual, by eye + ICP; see CLAUDE.md's
    CloudCompare Workflow section and alignment_transforms.txt for the recorded
    matrices. Applying those matrices in CloudCompare is how a successor VERIFIES the
    delivered registration; it is not automatable from here.
  - test_slice_tube.py (the area-regression assertion) and goldenmaster.py (the CSV
    diff) -- run those explicitly as part of a refactor step, not as routine
    regeneration; see REFACTOR.md rule 0.

Run: python run_all.py
"""
import subprocess
import sys
from pathlib import Path

from slice_tube import DEFAULT_SOURCE

HERE = Path(__file__).resolve().parent
PY = sys.executable


def run(*args, label):
    # flush before the child inherits stdout, else the parent's headers and the
    # child's own prints interleave out of order in the terminal
    print(f"\n{'='*70}\n{label}\n{'='*70}", flush=True)
    r = subprocess.run([PY, *args], cwd=HERE)
    if r.returncode != 0:
        print(f"\nFAILED: {label} (exit {r.returncode}) -- stopping.")
        sys.exit(r.returncode)


def main():
    for line, (xyz_path, _expected_area) in sorted(DEFAULT_SOURCE.items()):
        run("slice_tube.py", "--line", str(line), "--xyz", str(xyz_path),
            label=f"1. slice_tube.py --line {line}  (cross-section CSV)")

    run("verify_alignment.py",
        label="2. verify_alignment.py  (Puerta Falsa figure)")
    run("verify_alignment.py", "--gente",
        label="3. verify_alignment.py --gente  (La Gente figure)")
    run("gt_metrics.py",
        label="4. gt_metrics.py  (ground-truth accuracy numbers)")

    print(f"\n{'='*70}\nDone. Cross-sections written to Data/LiDAR/, figures to "
          f"'LiDAR La Corona/Reregistered clouds/' + thesis-overleaf, ground-truth "
          f"metrics printed above.\n{'='*70}")


if __name__ == "__main__":
    main()

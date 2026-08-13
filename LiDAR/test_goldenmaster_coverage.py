"""
test_goldenmaster_coverage.py -- asserts the golden master's SOURCES globs cover every
numerical output this folder actually writes.

goldenmaster.py protects what is IN its manifest; nothing checks the manifest is
complete. A successor who adds a script writing a new file to Data/LiDAR/ gets no
protection and no warning -- goldenmaster.py check would just report it under "NEW" and
still PASS. This is the same class of gap that let slice_tube.py silently read the wrong
point cloud for weeks (see DECISIONS.md, "Transect contours/ is the canonical source"):
a near-miss that nothing was checking for isn't caught by a tolerance, only by coverage.

This test does NOT replace goldenmaster.py check -- it answers a different question
("is anything in Data/LiDAR/ going untracked?") rather than "did a tracked file change?".
Run both; see README.md, Regression checks.

Run: python test_goldenmaster_coverage.py
"""
import sys
from pathlib import Path

from goldenmaster import SOURCES, DATA_LIDAR


def main():
    if not DATA_LIDAR.is_dir():
        print(f"SKIP -- {DATA_LIDAR} does not exist (nothing generated yet).")
        return 0

    tracked = set()
    for _tag, root, pattern in SOURCES:
        tracked.update(p.name for p in Path(root).glob(pattern))

    on_disk = {p.name for p in DATA_LIDAR.glob("*") if p.is_file()}
    untracked = sorted(on_disk - tracked)

    if untracked:
        print("FAIL -- files in Data/LiDAR/ are not covered by any goldenmaster.py "
              "SOURCES glob, so a change to them would never be caught:")
        for name in untracked:
            print(f"  {name}")
        print("\nAdd a SOURCES entry in goldenmaster.py (or a --no-write test if this "
              "output is genuinely not meant to be tracked). Do not ignore this.")
        return 1

    print(f"PASS -- all {len(on_disk)} file(s) in {DATA_LIDAR} are covered by "
          f"goldenmaster.py's SOURCES.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

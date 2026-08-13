"""
test_goldenmaster_coverage.py -- asserts goldenmaster.py's SOURCES glob covers every
output file points_to_lines.py actually writes.

goldenmaster.py protects what is IN its manifest; nothing checks the manifest is
complete. A successor who adds a third output to points_to_lines.py (or renames one of
the two current ones) gets no protection and no warning unless the new name still
happens to match "GPR_*.geojson".

Unlike LiDAR's version of this check, this one does NOT glob DATA_DIR and diff against
SOURCES -- Data/GNSS/Cleaned/ also holds this script's INPUT CSVs
(CleanedGNSS_GPR_Lines.csv, CleanedGNSS_GPR_FlowerPetals.csv), which are not tracked by
goldenmaster.py and never should be, so a directory scan would false-positive on them
every run. Instead this checks points_to_lines.py's own declared OUTPUT_FILES constant
against goldenmaster.py's SOURCES patterns directly -- see README.md, Verification.

This test does NOT replace goldenmaster.py check -- it answers "is a declared output
going untracked?" rather than "did a tracked file change?". Run both.

Run: python test_goldenmaster_coverage.py
"""
import fnmatch
import sys

from goldenmaster import SOURCES
from points_to_lines import OUTPUT_FILES


def main():
    patterns = [pattern for _tag, _root, pattern in SOURCES]
    uncovered = [name for name in OUTPUT_FILES
                 if not any(fnmatch.fnmatch(name, p) for p in patterns)]

    if uncovered:
        print("FAIL -- points_to_lines.py declares output file(s) not covered by any "
              "goldenmaster.py SOURCES glob, so a change to them would never be caught:")
        for name in uncovered:
            print(f"  {name}")
        print("\nAdd a SOURCES entry in goldenmaster.py. Do not ignore this.")
        return 1

    print(f"PASS -- all {len(OUTPUT_FILES)} declared output(s) in points_to_lines.py "
          f"are covered by goldenmaster.py's SOURCES.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

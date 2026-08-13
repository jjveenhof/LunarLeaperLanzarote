"""
test_slice_tube.py -- executable regression check for slice_tube.py's outline areas.

The L3/L5 cross-sectional areas (203 / 182 m^2, frozen in the thesis) are printed by
slice_tube.py but never written to a tracked file, so goldenmaster.py's CSV check
(x,z,easting,northing) does not catch a change in outline_by_angle()/polygon_area()
itself. This re-runs the same pipeline against the corrected Puerta Falsa / La Gente
exports and asserts the areas match, closing that gap.

Run: python test_slice_tube.py
"""
import sys

import numpy as np

from slice_tube import (LINE_GEOM, DEFAULT_SOURCE, load_xyz, project_to_line,
                         outline_by_angle, polygon_area)

# (line, source export, frozen thesis area m^2) -- from slice_tube.DEFAULT_SOURCE,
# the one place this mapping is defined (see main.tex results tables for the areas)
CASES = [(line, path, area) for line, (path, area) in sorted(DEFAULT_SOURCE.items())]
# 0.5, not 1.0: the thesis area is the ROUNDED integer, so this test's job is "does the
# unrounded area still round to that integer" -- 0.5 is the exact bound for that, no
# looser. (goldenmaster.py separately gives byte-exact protection on the written CSV;
# this test is the human-readable "does the number in the thesis still hold" check.)
# Confirmed both lines are nowhere near this bound (203.27, 182.00) -- see DECISIONS.md.
TOL_M2 = 0.5


def area_for(line, xyz_path, halfwidth=1.0, nbins=180):
    geom = LINE_GEOM[line]
    d = load_xyz(xyz_path)
    dist, perp = project_to_line(d[:, 0], d[:, 1], geom["origin"], geom["azimuth"])
    m = np.abs(perp) < halfwidth
    x, z = dist[m], d[m, 2]
    ox, oz = outline_by_angle(x, z, nbins)
    return polygon_area(ox, oz)


def main():
    failed = False
    for line, xyz_path, expected in CASES:
        area = area_for(line, xyz_path)
        ok = abs(area - expected) <= TOL_M2
        print(f"Line {line}: area = {area:.1f} m^2  (expected {expected}, "
              f"{'OK' if ok else 'FAIL'})")
        failed |= not ok

    if failed:
        print("\nFAIL -- an area drifted from the frozen thesis value. Stop and "
              "find out WHY before going further. Do not 'fix' it.")
        return 1
    print("\nPASS -- both areas match the frozen thesis values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

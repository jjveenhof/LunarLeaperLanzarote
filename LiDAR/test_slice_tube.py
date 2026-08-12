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
TOL_M2 = 1.0   # thesis values are reported to the nearest integer m^2


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
              "escalate to the root QandA.md (REFACTOR.md rule 3). Do not 'fix' it.")
        return 1
    print("\nPASS -- both areas match the frozen thesis values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Golden-master shim for the LiDAR outputs. See Code/goldenmaster.py for the shared
implementation, comparison rules, and rationale.

Covers: Data/LiDAR/lidar_line{3,5}.csv (the cross-section CSVs this folder produces
and Grav consumes; x,z,easting,northing checked column-by-column via np.allclose).

NOT covered here: the L3/L5 outline AREAS (203 / 182 m^2) are printed by slice_tube.py,
not written to a tracked file -- see the `--no-write` assertion test in slice_tube.py
instead, which is the other half of the verification pair here.

Usage (from Code/LiDAR/):
    python goldenmaster.py snapshot     # once, BEFORE editing anything
    python goldenmaster.py check        # after every change
    python goldenmaster.py check --verbose
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/ for goldenmaster
import goldenmaster as gm

GM_DIR = Path(__file__).resolve().parent / "_goldenmaster"
DATA_LIDAR = Path(__file__).resolve().parents[2] / "Data/LiDAR"
SOURCES = [("crosssections", DATA_LIDAR, "lidar_line*.csv")]

if __name__ == "__main__":
    sys.exit(gm.main(GM_DIR, SOURCES, "the LiDAR outputs"))

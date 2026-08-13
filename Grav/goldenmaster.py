"""
Golden-master snapshot + comparison for the GRAVIMETRY outputs.

    python goldenmaster.py snapshot     # once, BEFORE editing anything
    python goldenmaster.py check        # after every change
    python goldenmaster.py check --verbose

The machinery lives in Code/goldenmaster.py and is shared by all four method folders (this file
was its original home; promoted 2026-08-11 so there is ONE implementation of the check
that certifies every change). Behaviour is unchanged and the existing snapshot in
_goldenmaster/ stays valid -- the tags below are the same three it was written with.

This file declares only WHICH outputs the gravimetry code owns. Everything else --
comparison rules, tolerance, reporting, the refusal to re-baseline -- is documented in
Code/goldenmaster.py.

Covered outputs (everything numerical the gravimetry code produces):
  - Data/Gravimetry/Processed/*.csv          pipeline chain, all rho variants
  - Results/Grav/Inversion/artifacts/*.npz   inversion artifacts (inversion_io)
  - Results/Grav/Inversion/freedepth_*.npz   free-depth cubes

Figures are deliberately NOT covered -- see Code/goldenmaster.py for why.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/ for goldenmaster
import goldenmaster as gm                                       # noqa: E402

import grav_utils as gu                                         # noqa: E402

GM_DIR = Path(__file__).resolve().parent / "_goldenmaster"

# (tag, source directory, glob). Tag is the subfolder inside _goldenmaster/ -- do not
# rename these, an existing snapshot is keyed on them.
SOURCES = [
    ("processed", gu.PROC_DIR, "*.csv"),
    ("artifacts", gu.RESULTS_DIR / "Inversion/artifacts", "*.npz"),
    ("freedepth", gu.RESULTS_DIR / "Inversion", "freedepth_*.npz"),
]


if __name__ == "__main__":
    sys.exit(gm.main(GM_DIR, SOURCES, "the gravimetry outputs"))

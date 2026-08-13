"""
Golden-master shim for the GPR outputs -- see Code/goldenmaster.py for the machinery.

Declares WHICH GPR outputs are frozen against regression (see Code/GPR/README.md
rule 0). The comparison logic (npz key-by-key, absolute tolerance, NaN patterns,
missing/extra = failure) lives in the shared module so all four method folders verify the
same way; do not fork it.

Usage (from Code/GPR/):
    python goldenmaster.py snapshot          # once, BEFORE editing anything
    python goldenmaster.py check             # after every change
    python goldenmaster.py check --verbose

Snapshot lands in Code/GPR/_goldenmaster/ (gitignored by the shared module).

NB: tube_picks.csv is a hand-maintained INPUT, not a pipeline output -- deliberately
NOT tracked here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Code/ for goldenmaster
import goldenmaster as gm

GM_DIR = Path(__file__).resolve().parent / "_goldenmaster"
DATA = Path(__file__).resolve().parents[2] / "Data" / "GPR"
SOURCES = [
    ("Processed", DATA / "Processed", "*_processed.npz"),
    ("Topo",      DATA / "Topo",      "*_topo.npz"),
    ("Migration", DATA / "Migration", "*_migrated.npz"),
]

if __name__ == "__main__":
    sys.exit(gm.main(GM_DIR, SOURCES, "the GPR outputs"))

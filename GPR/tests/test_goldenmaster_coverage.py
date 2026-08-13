"""
test_goldenmaster_coverage.py
The golden master protects what is in its manifest, but
nothing checks the manifest is COMPLETE. A successor who adds a script that writes a new
numerical output gets no protection and no warning -- this test closes that gap.

It re-uses goldenmaster.py's own SOURCES list (not a second copy of the glob patterns),
so it cannot itself drift from what `python goldenmaster.py check` actually verifies.

Skips (does not fail) if a source directory does not exist yet -- that is a "nothing
generated" state, not an untracked-output state.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import goldenmaster as gm


def test_no_untracked_npz_outputs():
    """Every *.npz file actually on disk in a golden-master source directory must be
    matched by that source's own glob pattern. If a new script starts writing, say,
    Data/GPR/Processed/{stem}_foo.npz, this test fails loudly instead of the file
    silently having zero regression protection."""
    untracked = []
    for tag, root, pattern in gm.SOURCES:
        root = Path(root)
        if not root.is_dir():
            continue
        tracked = set(root.glob(pattern))
        for p in sorted(root.glob('*.npz')):
            if p not in tracked:
                untracked.append((tag, p.name))

    assert not untracked, (
        "Untracked .npz output(s) found -- the golden master gives these NO regression "
        "protection. Either they belong to a real new output (extend goldenmaster.py's "
        "SOURCES and re-snapshot) or they are stray/leftover files:\n" +
        "\n".join("  {}/{}".format(tag, name) for tag, name in untracked))


def test_sources_nonempty():
    """A source glob that matches nothing is a silent no-op, not a pass -- catch the
    case where a directory was renamed/moved and the golden master quietly stopped
    covering anything."""
    empty = []
    for tag, root, pattern in gm.SOURCES:
        root = Path(root)
        if not root.is_dir() or not list(root.glob(pattern)):
            empty.append(tag)
    assert not empty, (
        "Golden-master source(s) matched zero files: {}. Check goldenmaster.py's "
        "SOURCES paths/patterns are still correct.".format(empty))

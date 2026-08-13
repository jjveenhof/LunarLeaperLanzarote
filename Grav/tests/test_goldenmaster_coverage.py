"""
test_goldenmaster_coverage.py -- asserts goldenmaster.py's SOURCES globs cover every
numerical output the gravimetry code actually writes.

goldenmaster.py protects what is IN its manifest; nothing checks the manifest is
COMPLETE. A successor who adds a script that writes a new .csv to Data/Gravimetry/Processed/
or a new .npz to Results/Grav/Inversion/ gets no protection and no warning --
`goldenmaster.py check` would report it under "NEW" and still PASS. This is the same class
of gap that let a wrong point cloud pass silently for weeks elsewhere in the project (see
see Code/Grav/README.md): a near-miss nothing was checking for isn't caught by a
tolerance, only by coverage.

This does NOT replace `python goldenmaster.py check` -- it answers a different question
("is anything going untracked?") rather than "did a tracked file change?". Run both.

Run: python tests/test_goldenmaster_coverage.py   (or: pytest tests/test_goldenmaster_coverage.py)
"""
import importlib.util
import sys
from pathlib import Path

# NOT a plain `import goldenmaster` -- Code/Grav/goldenmaster.py (the shim) itself
# does `import goldenmaster as gm` internally to reach the SHARED Code/goldenmaster.py.
# If this test also imports a module literally named "goldenmaster" while Code/Grav is on
# sys.path, Python's module cache resolves the shim's internal import back to the shim
# itself (still mid-import), silently handing it a copy of ITSELF instead of the shared
# module -- so `gm.main` / `gm._iter_sources` / `gm.check` go missing with no error at the
# import site. Loading the shim by file path under a private name sidesteps the collision
# without touching goldenmaster.py (shared or shim) to work around it.
_GRAV_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_GRAV_DIR))      # the shim's own `from grav_utils import ...` needs this
_spec = importlib.util.spec_from_file_location("_grav_goldenmaster_shim",
                                               _GRAV_DIR / "goldenmaster.py")
shim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shim)

SOURCES = shim.SOURCES         # this folder's (tag, root, pattern) list
gm = shim.gm                   # the shared Code/goldenmaster.py -- reached via the shim's
                               # own `import goldenmaster as gm`, which is a distinct
                               # object from `shim` itself (see the collision note above)


def find_untracked():
    """Files with a tracked EXTENSION sitting in a tracked ROOT, but not matched by that
    root's own glob. Extension-scoped (not "every file"), so browse PNGs and other
    deliberately-uncovered outputs in the same directories do not trip this.

    Results/Grav/Inversion/ is the interesting case: two SOURCES tags ("artifacts" and
    "freedepth") share it, one scoped to a subfolder and one to a `freedepth_*.npz`
    prefix. A new script writing e.g. Results/Grav/Inversion/some_other_thing.npz
    would sit in a tracked root, match no tracked pattern, and go unnoticed without
    this check."""
    ext_by_root = {}                      # root -> set of extensions tracked here
    tracked = set()
    for _tag, root, pattern in SOURCES:
        root = Path(root)
        ext = Path(pattern).suffix
        ext_by_root.setdefault(root, set()).add(ext)
        if root.is_dir():
            tracked.update(root.glob(pattern))

    untracked = []
    for root, exts in ext_by_root.items():
        if not root.is_dir():
            continue
        for ext in exts:
            for p in sorted(root.glob(f"*{ext}")):
                if p not in tracked:
                    untracked.append(p)
    return untracked


def main():
    untracked = find_untracked()
    if untracked:
        print(f"FAIL -- {len(untracked)} file(s) share a tracked directory and extension "
              f"with goldenmaster.py's SOURCES but match no SOURCES glob, so a change to "
              f"them would never be caught:")
        for p in untracked:
            print(f"  {p}")
        print("\nEither extend SOURCES in goldenmaster.py and re-snapshot (a real new "
              "output), or this is a stray file that does not belong here. Do not ignore.")
        return 1

    empty = [tag for tag, root, pattern in SOURCES
             if not Path(root).is_dir() or not list(Path(root).glob(pattern))]
    if empty:
        print(f"FAIL -- SOURCES tag(s) matched ZERO files: {empty}. A glob matching "
              f"nothing is a silent no-op, not a pass -- check the path/pattern in "
              f"goldenmaster.py is still correct (a renamed or moved directory would "
              f"look exactly like this).")
        return 1

    n = sum(1 for _ in gm._iter_sources(SOURCES))
    print(f"PASS -- all {n} tracked file(s) across {len(SOURCES)} SOURCES entries are "
          f"covered, and no SOURCES glob is empty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def test_no_untracked_outputs():
    untracked = find_untracked()
    assert not untracked, (
        "Untracked output(s) found in a golden-master source directory -- see module "
        "docstring. Files:\n" + "\n".join(f"  {p}" for p in untracked))


def test_sources_nonempty():
    empty = [tag for tag, root, pattern in SOURCES
             if not Path(root).is_dir() or not list(Path(root).glob(pattern))]
    assert not empty, f"Golden-master source(s) matched zero files: {empty}"

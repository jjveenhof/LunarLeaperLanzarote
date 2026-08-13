"""
Golden-master snapshot + comparison, shared by all four method folders.

Regression safety net for the whole of Code/ (see Code/README.md). The thesis is frozen,
so any change to this code must leave the NUMBERS bit-for-bit where they were. Each
method folder freezes its current outputs once, then re-checks them after each edit.

This module holds the machinery. It is NOT run directly -- each method folder has a thin
`goldenmaster.py` shim that declares WHICH files it owns and calls `main()` here:

    # Code/<Method>/goldenmaster.py
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # Code/
    import goldenmaster as gm

    SOURCES = [("processed", SOME_DIR, "*.csv"), ...]

    if __name__ == "__main__":
        sys.exit(gm.main(pathlib.Path(__file__).resolve().parent / "_goldenmaster",
                         SOURCES, "the gravimetry outputs"))

Then, from that folder:

    python goldenmaster.py snapshot     # once, BEFORE editing anything
    python goldenmaster.py check        # after every change
    python goldenmaster.py check --verbose

There is one implementation on purpose: this is the script that certifies every other
change, and four divergent copies of the thing that checks for divergence would be worse
than none.

Figures are deliberately NOT covered: PNG/PDF bytes differ run to run even with identical
data (timestamps, font hinting), so what gets verified is the numbers a figure is drawn
from, not the image.

Comparison rules:
  - .csv                   column-by-column; floats via np.allclose(rtol=0, atol=ATOL)
  - .npz                   key-by-key; float arrays via the same absolute tolerance
  - anything else          byte-exact (GeoJSON, .txt, .xyz -- no float re-parsing, so a
                           formatting change shows up as the change it is)
  - non-float data         exact equality (strings, ints, station labels)
  - NaN pattern            must match; a NaN becoming a number is a real change
  - missing / extra / reshaped file  -> FAILURE, not a warning

Absolute (not relative) tolerance is deliberate: a value that is exactly zero at a datum
-- e.g. Grav_lsq at the base station -- must stay exactly zero, and rtol would let it
drift.

Exit code 0 = identical, 1 = deviation. A deviation STOPS the work in progress and is
investigated and explained -- it is never quietly fixed or re-baselined.

Snapshots live in Code/<Method>/_goldenmaster/ and are gitignored by their own
.gitignore (a few MB of regenerable output). NOTE: because they are gitignored, they do
NOT survive a `git clone` -- re-run `snapshot` to rebuild a baseline there.
"""

import argparse
import filecmp
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

# Absolute tolerance for float comparison. Gravity values are mGal (O(1e-3) resolution),
# areas are m^2 (O(1)), GPR amplitudes are normalised O(1) -- so 1e-12 is far below any
# physically meaningful change while still absorbing pure floating-point re-association
# from moving code between modules.
ATOL = 1e-12


def _iter_sources(sources):
    """Yield (tag, path) for every tracked file currently on disk."""
    for tag, root, pattern in sources:
        root = Path(root)
        if not root.is_dir():
            continue
        for p in sorted(root.glob(pattern)):
            yield tag, p


def snapshot(gm_dir, sources):
    gm_dir = Path(gm_dir)
    if gm_dir.exists():
        print(f"Snapshot already exists at {gm_dir}")
        print("Refusing to overwrite -- a golden master is only valid if it predates the")
        print("first edit. Delete it by hand if you really mean to re-baseline.")
        return 1

    gm_dir.mkdir(parents=True)
    # Self-contained ignore: keeps the snapshot out of git without touching the shared
    # Code/.gitignore.
    (gm_dir / ".gitignore").write_text("*\n")

    n = 0
    for tag, p in _iter_sources(sources):
        dest = gm_dir / tag
        dest.mkdir(exist_ok=True)
        shutil.copy2(p, dest / p.name)
        n += 1

    print(f"Snapshot written: {n} files -> {gm_dir}")
    for tag, root, pattern in sources:
        d = gm_dir / tag
        count = len(list(d.glob("*"))) if d.is_dir() else 0
        print(f"  {tag:12s} {count:3d}  ({Path(root) / pattern})")
    if n == 0:
        print("\nWARNING: nothing matched. Check the SOURCES globs in this folder's shim"
              " -- an empty snapshot silently certifies nothing.")
        return 1
    return 0


def _cmp_csv(ref, cur):
    """Compare two CSVs. Returns a list of difference strings (empty = identical)."""
    a = pd.read_csv(ref)
    b = pd.read_csv(cur)

    if list(a.columns) != list(b.columns):
        only_ref = [c for c in a.columns if c not in b.columns]
        only_cur = [c for c in b.columns if c not in a.columns]
        return [f"columns differ (missing {only_ref}, new {only_cur})"]
    if len(a) != len(b):
        return [f"row count {len(a)} -> {len(b)}"]

    diffs = []
    for col in a.columns:
        ca, cb = a[col], b[col]
        if pd.api.types.is_numeric_dtype(ca) and pd.api.types.is_numeric_dtype(cb):
            va, vb = ca.to_numpy(float), cb.to_numpy(float)
            # NaN must line up in the same places -- a NaN turning into a number is a
            # real change (a station gaining or losing a correction).
            if not np.array_equal(np.isnan(va), np.isnan(vb)):
                diffs.append(f"{col}: NaN pattern changed")
                continue
            if not np.allclose(va, vb, rtol=0, atol=ATOL, equal_nan=True):
                d = np.nanmax(np.abs(va - vb))
                i = int(np.nanargmax(np.abs(va - vb)))
                diffs.append(f"{col}: max |d| = {d:.3e} at row {i} "
                             f"({va[i]!r} -> {vb[i]!r})")
        else:
            neq = (ca.astype(str) != cb.astype(str))
            if neq.any():
                i = int(neq.to_numpy().argmax())
                diffs.append(f"{col}: {neq.sum()} cells differ, first at row {i} "
                             f"({ca.iloc[i]!r} -> {cb.iloc[i]!r})")
    return diffs


def _cmp_npz(ref, cur):
    """Compare two .npz archives key by key."""
    a = np.load(ref, allow_pickle=True)
    b = np.load(cur, allow_pickle=True)

    ka, kb = set(a.files), set(b.files)
    if ka != kb:
        return [f"keys differ (missing {sorted(ka - kb)}, new {sorted(kb - ka)})"]

    diffs = []
    for k in sorted(ka):
        va, vb = a[k], b[k]
        if va.shape != vb.shape:
            diffs.append(f"{k}: shape {va.shape} -> {vb.shape}")
            continue
        if va.dtype.kind in "fc" and vb.dtype.kind in "fc":
            if not np.array_equal(np.isnan(va), np.isnan(vb)):
                diffs.append(f"{k}: NaN pattern changed")
                continue
            if not np.allclose(va, vb, rtol=0, atol=ATOL, equal_nan=True):
                d = np.nanmax(np.abs(va - vb))
                diffs.append(f"{k}: max |d| = {d:.3e}")
        elif not np.array_equal(va, vb):
            diffs.append(f"{k}: values differ")
    return diffs


def _cmp_bytes(ref, cur):
    """Byte-exact fallback for formats we do not parse (GeoJSON, .txt, .xyz).

    Stricter than the parsed comparators on purpose: for these, a formatting change IS a
    change worth seeing, because nothing downstream re-derives them from structure.
    """
    if filecmp.cmp(ref, cur, shallow=False):
        return []
    sr, sc = Path(ref).stat().st_size, Path(cur).stat().st_size
    if sr != sc:
        return [f"bytes differ (size {sr} -> {sc})"]
    return ["bytes differ (same size, content changed)"]


def _compare(ref, cur):
    if ref.suffix == ".npz":
        return _cmp_npz(ref, cur)
    if ref.suffix == ".csv":
        return _cmp_csv(ref, cur)
    return _cmp_bytes(ref, cur)


def check(gm_dir, sources, verbose=False):
    gm_dir = Path(gm_dir)
    if not gm_dir.is_dir():
        print(f"No snapshot at {gm_dir}. Run `python goldenmaster.py snapshot` first.")
        return 1

    ref_files = {}
    for tag, _, _ in sources:
        d = gm_dir / tag
        if d.is_dir():
            for p in sorted(d.glob("*")):
                if p.name != ".gitignore":
                    ref_files[(tag, p.name)] = p

    cur_files = {(tag, p.name): p for tag, p in _iter_sources(sources)}

    missing = sorted(set(ref_files) - set(cur_files))
    extra   = sorted(set(cur_files) - set(ref_files))
    shared  = sorted(set(ref_files) & set(cur_files))

    failures = []
    for key in shared:
        ref, cur = ref_files[key], cur_files[key]
        try:
            diffs = _compare(ref, cur)
        except Exception as exc:                       # unreadable is also a failure
            diffs = [f"comparison raised {type(exc).__name__}: {exc}"]
        if diffs:
            failures.append((key, diffs))
        elif verbose:
            print(f"  OK   {key[0]}/{key[1]}")

    print(f"Compared {len(shared)} files against {gm_dir}")

    if missing:
        print(f"\nMISSING ({len(missing)}) -- in the snapshot but not on disk now:")
        for tag, name in missing:
            print(f"  {tag}/{name}")
    if extra:
        print(f"\nNEW ({len(extra)}) -- on disk now but not in the snapshot:")
        for tag, name in extra:
            print(f"  {tag}/{name}")
    if failures:
        print(f"\nDEVIATIONS ({len(failures)} files):")
        for (tag, name), diffs in failures:
            print(f"  {tag}/{name}")
            for d in diffs:
                print(f"      {d}")

    if failures or missing:
        print("\nFAIL -- stop and find out WHY a published number moved "
              "before going further. Do not 'fix' the number.")
        return 1

    if extra:
        print("\nPASS (with new files) -- every tracked output is unchanged; the new "
              "files above are not covered by the snapshot.")
    else:
        print("\nPASS -- every tracked output is bit-identical to the golden master.")
    return 0


def main(gm_dir, sources, description="these outputs"):
    """argparse entry point for a per-folder shim. Returns an exit code."""
    ap = argparse.ArgumentParser(
        description=f"Golden-master snapshot/check for {description}.")
    ap.add_argument("action", choices=["snapshot", "check"])
    ap.add_argument("--verbose", action="store_true",
                    help="list every file compared, not just the failures")
    args = ap.parse_args()
    if args.action == "snapshot":
        return snapshot(gm_dir, sources)
    return check(gm_dir, sources, args.verbose)

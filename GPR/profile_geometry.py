"""
profile_geometry.py
Canonical handling of the flip_x display convention (North on the left).

run_pipeline.py bakes flip_x by reversing the DATA columns of a flagged profile
(currently Line3_50/100MHz) but leaves dist_axis in acquisition order -- so
_processed.npz (and everything derived from it: topo, migrated) is internally
inconsistent: data column i no longer corresponds to dist_axis[i]. That is a
deliberate, unchanged design choice (see the root QandA flip_x thread) -- this
module does not touch the bake.

Every consumer that attaches per-trace geometry (GNSS E/N, elevation) to a
profile's traces must reconcile this before pairing column i of the data with
position i of the geometry. The convention, used consistently from here on:

    reverse the GEOMETRY, never the data.

load_flip(profile_key) is the single source of truth for whether a profile was
flipped; reconcile_geometry() applies the reversal to any number of per-trace
arrays in one call.
"""
from pathlib import Path
import json

HERE     = Path(__file__).parent
PROC_DIR = HERE / '../../Data/GPR/Processed'


def load_flip(profile_key):
    """Read flip_x from the saved params (Data/GPR/Processed/{profile_key}_params.json).
    Returns False if the params file or the key is missing."""
    params_path = PROC_DIR / (profile_key + '_params.json')
    if params_path.exists():
        with open(str(params_path), encoding='utf-8') as f:
            return bool(json.load(f).get('flip_x', False))
    return False


def reconcile_geometry(profile_key, *arrays):
    """Reverse each per-trace geometry array (E, N, elevation, gnss_m, ...) iff
    profile_key was baked with flip_x, so it aligns column-for-column with the
    DATA in _processed.npz (data was flipped at bake time; dist_axis was not).
    Pass any number of 1D arrays; returns a tuple in the same order, reversed
    identically (or unchanged) so relative correspondence between them is kept.
    """
    if not load_flip(profile_key):
        return arrays
    return tuple(a[::-1] for a in arrays)

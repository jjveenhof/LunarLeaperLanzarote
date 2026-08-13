"""
Closed-form round-trip test for the LSQ network adjustment.

`drift_correction_lsq.solve_line` is the largest unasserted module here and
EVERY downstream number inherits it -- the station anomalies, the Bouguer chain, the
detrended residual, and therefore the inversion. Before this file, `Code/Grav/` contained
zero `assert` statements: the only other `test_` file is a print script bound to live
data, which cannot fail.

The test builds a synthetic network where the true answer is known by construction,
solves it, and asserts the solver recovers exactly what was injected:

    Grav_est[i] = g_{loc(i)} + d_{loop(i)} * (t_i - t0_j) + s_{loop(i)}

with the datum g_0 = 0. With noise-free observations and an over-determined system the
weighted LS solution must reproduce (g, d, s) to machine precision, so the tolerances are
1e-10, not "close enough".

What each test pins down:
  test_roundtrip_two_loops   parameters recovered; the datum station is EXACTLY 0.0;
                             residuals and chi2_red vanish on noise-free data
  test_shared_base           two loops sharing a base station stay on ONE datum -- the
                             case at drift_correction_lsq.py:82-92, and the reason Lines
                             3 and 4 are tied together
  test_drift_is_removed      a pure drift ramp with no real anomaly returns g == 0
                             everywhere (drift is not absorbed into the anomalies)
  test_weighting             a badly-measured station is pulled toward the well-measured
                             ones, i.e. SE_est actually weights the fit

Run:  python Tests/test_solve_line.py        (or: pytest Tests/test_solve_line.py)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # Code/Grav
from drift_correction_lsq import solve_line

TOL = 1e-10


def make_obs(rows, line=99):
    """Assemble the frame solve_line expects. `rows` are (loc_id, loop_id, t, g_obs, se).

    Only the columns solve_line reads matter numerically; the rest are carried through
    to the result frame and are filled with placeholders.
    """
    recs = []
    for i, (loc_id, loop_id, t, g_obs, se) in enumerate(rows):
        recs.append(dict(
            Line=line, Station=100 + i, loc_id=loc_id, loop_id=float(loop_id),
            t_line_min=float(t), t0_min=0.0,
            Grav_est=float(g_obs), SE_est=float(se),
            Easting=0.0, Northing=0.0, Elevation=0.0, HorizErr=0.0, VertErr=0.0,
            Date="2026/04/24", Time_first="12:00:00",
            StationType="base" if loc_id == 0 else "regular", Notes="",
        ))
    return pd.DataFrame(recs)


def synth(g_true, d_true, s_true, schedule, se=0.01):
    """Noise-free observations from the forward model the solver inverts."""
    rows = []
    for loc_id, loop_id, t in schedule:
        g = g_true[loc_id] + d_true[loop_id] * t + s_true[loop_id]
        rows.append((loc_id, loop_id, t, g, se))
    return make_obs(rows)


def test_roundtrip_two_loops():
    """Inject known anomalies, drifts and offsets; assert exact recovery."""
    g_true = {0: 0.0, 1: 0.150, 2: -0.080, 3: 0.045}
    d_true = {1: 0.0020, 2: -0.0035}          # mGal/min
    s_true = {1: 0.010, 2: -0.004}            # mGal
    # Each loop opens and closes on the base, so both loops are tied to the datum.
    schedule = [(0, 1, 0.0), (1, 1, 12.0), (2, 1, 25.0), (0, 1, 40.0),
                (0, 2, 0.0), (2, 2, 15.0), (3, 2, 28.0), (0, 2, 45.0)]
    obs = synth(g_true, d_true, s_true, schedule)

    res, loops, chi2_red = solve_line(obs)
    assert res is not None, "solver returned no result on a well-posed network"

    # Anomalies, per location
    got = {int(r.loc_id): r.Grav_lsq for r in res.itertuples()}
    for loc_id, want in g_true.items():
        assert abs(got[loc_id] - want) < TOL, \
            f"loc {loc_id}: recovered {got[loc_id]!r}, injected {want!r}"

    # The datum is EXACTLY zero, not merely small -- downstream code relies on it.
    base = res[res["loc_id"] == 0]
    assert (base["Grav_lsq"] == 0.0).all(), "base station is not exactly 0"
    assert (base["SE_lsq"] == 0.0).all(), "base station SE is not exactly 0"

    # Loop drift and offset
    for r in loops.itertuples():
        want_d = d_true[int(r.loop_id)] * 60.0            # stored as mGal/h
        want_s = s_true[int(r.loop_id)] * 1000.0          # stored as microGal
        assert abs(r.drift_mGal_h - want_d) < TOL, \
            f"loop {r.loop_id} drift: {r.drift_mGal_h} vs {want_d}"
        assert abs(r.offset_microGal - want_s) < TOL, \
            f"loop {r.loop_id} offset: {r.offset_microGal} vs {want_s}"

    # Noise-free data -> zero misfit
    assert np.abs(res["residual"].values).max() < TOL, "non-zero residuals on exact data"
    assert chi2_red < TOL, f"chi2_red = {chi2_red}, expected ~0"


def test_shared_base():
    """Two loops sharing the base station stay on ONE datum.

    This is the configuration at drift_correction_lsq.py:82-92 and the reason Lines 3
    and 4 are not independently datumed. If the shared base were mishandled, each loop
    would float on its own offset and the cross-loop anomalies would be inconsistent.
    """
    g_true = {0: 0.0, 1: 0.200, 2: 0.060}
    d_true = {1: 0.0010, 2: 0.0050}
    s_true = {1: 0.000, 2: 0.025}
    # Station 2 is visited in BOTH loops -- the only thing tying them together besides
    # the base. Its recovered anomaly must be single-valued.
    schedule = [(0, 1, 0.0), (1, 1, 10.0), (2, 1, 20.0), (0, 1, 30.0),
                (0, 2, 0.0), (2, 2, 18.0), (1, 2, 33.0), (0, 2, 50.0)]
    res, loops, chi2_red = solve_line(synth(g_true, d_true, s_true, schedule))
    assert res is not None, "solver failed on a well-posed shared-base network"

    for loc_id, want in g_true.items():
        vals = res[res["loc_id"] == loc_id]["Grav_lsq"].unique()
        assert len(vals) == 1, f"loc {loc_id} got {len(vals)} different anomalies: {vals}"
        assert abs(vals[0] - want) < TOL, f"loc {loc_id}: {vals[0]} vs {want}"
    assert chi2_red < TOL


def test_drift_is_removed():
    """Pure instrument drift, no real anomaly -> every anomaly must come back 0.

    The failure this guards against is drift leaking into the anomalies, which would
    put a spurious along-profile ramp into the CBA and straight into the detrend step.
    """
    g_true = {0: 0.0, 1: 0.0, 2: 0.0}
    d_true = {1: 0.0080, 2: 0.0080}           # strong drift
    s_true = {1: 0.0, 2: 0.0}
    schedule = [(0, 1, 0.0), (1, 1, 10.0), (2, 1, 20.0), (0, 1, 30.0),
                (0, 2, 0.0), (2, 2, 12.0), (1, 2, 24.0), (0, 2, 36.0)]
    res, loops, _ = solve_line(synth(g_true, d_true, s_true, schedule))
    assert res is not None, "solver failed on a well-posed network"

    assert np.abs(res["Grav_lsq"].values).max() < TOL, \
        "drift leaked into the station anomalies"
    for r in loops.itertuples():
        want = 0.0080 * 60.0
        assert abs(r.drift_mGal_h - want) < TOL, \
            f"loop {r.loop_id} drift: {r.drift_mGal_h} vs {want}"


def test_weighting():
    """SE_est must actually weight the solution.

    Two independent measurements of the same station disagree; the solution has to land
    much nearer the precise one. Without weighting it would sit halfway.
    """
    g_true = {0: 0.0, 1: 0.100, 2: 0.0}
    d_true = {1: 0.0, 2: 0.0}
    s_true = {1: 0.0, 2: 0.0}
    schedule = [(0, 1, 0.0), (1, 1, 10.0), (2, 1, 20.0), (0, 1, 30.0),
                (0, 2, 0.0), (1, 2, 10.0), (2, 2, 20.0), (0, 2, 30.0)]
    obs = synth(g_true, d_true, s_true, schedule)

    # Corrupt loop 2's visit to station 1 by +0.5 mGal, but declare it 100x less precise.
    bad = (obs["loc_id"] == 1) & (obs["loop_id"] == 2.0)
    obs.loc[bad, "Grav_est"] += 0.5
    obs.loc[bad, "SE_est"] = 1.0                     # vs 0.01 elsewhere

    res, _, _ = solve_line(obs)
    assert res is not None, "solver failed on a weighted network"
    got = res[res["loc_id"] == 1]["Grav_lsq"].iloc[0]
    assert abs(got - 0.100) < 0.01, \
        f"recovered {got:.4f}; the 100x-less-precise outlier dominated the fit"
    assert got < 0.35, "solution sits near the unweighted mean -- weights ignored"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())

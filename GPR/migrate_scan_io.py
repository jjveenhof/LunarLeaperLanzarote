"""
migrate_scan_io.py
Compute core of the Stolt migration scan -- the numeric half of the F11 split
(compute/plot split). All the migration MATH lives here; migrate_velocity_scan.py keeps
the CLI, the interactive velocity-scan HTML, and the static/before-after PNGs.

Split so a successor can migrate a section from Python without the plotting layer,
and so the compute path has one home. The numbers are unchanged from the pre-split
migrate_velocity_scan.py -- verified byte-identical against the golden master.

ALSO A LIBRARY: plot_petal_migration_3d imports `live_sample_taper` and the padding/
taper constants (`PAD_T_FACTOR`, `PAD_X_TRACES`, `TAPER_W`, `TAPER_T_FRAC`) to migrate
the petal segments with the same machinery. migrate_velocity_scan re-exports these
names, so its existing `from migrate_velocity_scan import ...` keeps working too.
Change these signatures/values with care.
"""

import sys
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve
from scipy.signal.windows import hann as _hann_win

sys.path.insert(0, str(Path(__file__).parent))
from stolt_migration import stolt_migration_2d
from topo_correction import apply_topo_correction

# Stolt parameters (match Cedric's notebook defaults)
PAD_T_FACTOR = 2.0    # one-sided time padding multiplier
PAD_X_TRACES = 40     # one-sided spatial padding [traces]
TAPER_W      = 5      # raised-cosine spatial edge taper [traces]
TAPER_T_FRAC = 0.10   # raised-cosine time edge taper fraction
# Live-sample (data-driven) taper at zero<->live boundaries (Hann half-widths)
LIVE_TAPER_X = 5      # [traces]
LIVE_TAPER_T = 25     # [samples]


def live_sample_taper(section):
    """Smooth Hann taper wherever live signal abuts the zero-filled (shifted)
    regions, suppressing FFT leakage from sharp amplitude edges.  Returns the
    tapered section and the boolean dead-trace mask (all-zero columns)."""
    trace_is_dead = ~np.any(section != 0, axis=0)
    mask_live = (section != 0).astype(np.float64)

    def _hann1d(hw):
        if hw <= 0:
            return np.array([1.0])
        return _hann_win(2 * int(hw) + 1)

    k_t = _hann1d(LIVE_TAPER_T)
    k_x = _hann1d(LIVE_TAPER_X)
    kernel = k_t[:, None] * k_x[None, :]
    kernel /= kernel.sum()
    taper = np.clip(fftconvolve(mask_live, kernel, mode='same'), 0.0, 1.0)
    return section * taper, trace_is_dead


def tgain_weights(t):
    """Per-sample weight basis for the gdp 'linear' display gain:
    travel_time = (k+1)/sfreq, sfreq = 1000/dt MHz, so travel_time = (k+1)*dt/1000.
    The browser raises this vector to the gain exponent (matches display_gain /
    the notebook / the 3D plot)."""
    dt = float(t[1] - t[0])
    sfreq = 1000.0 / dt
    return (np.arange(len(t)) + 1) / sfreq


def norm99(a):
    s = float(np.percentile(np.abs(a), 99))
    return a / s if s > 0 else a


def build_section(data0, t, elevations, v, no_live_taper=False):
    """Topo-correct the processed data at velocity v, then live-sample taper.
    Recomputing the static shift per v pins the surface to depth
    (ref_elev - elev) regardless of v, so it stays under the surface line.
    Returns (section, dead_trace_mask)."""
    corrected, _shifts, _re = apply_topo_correction(data0, t, elevations, v)
    if no_live_taper:
        return corrected, ~np.any(corrected != 0, axis=0)
    return live_sample_taper(corrected)


def migrate_at_velocity(data0, x, t, elevations, v, no_live_taper=False):
    """Topo-correct + Stolt-migrate `data0` at velocity v (m/ns).

    Returns (mig, section, dead, depth):
      mig     -- migrated section (nt x nx), dead traces blanked to zero
      section -- the topo-corrected migration INPUT (before/after top panel)
      dead    -- boolean dead-trace mask
      depth   -- depth axis below datum [m] = t * v/2
    Numerically identical to the pre-split inline path in migrate_velocity_scan.
    """
    dt = float(t[1] - t[0])
    dx = float(x[1] - x[0])
    nt, nx = data0.shape
    pad_x_mult   = (nx + PAD_X_TRACES) / nx
    taper_frac_x = TAPER_W / nx

    section, dead = build_section(data0, t, elevations, v, no_live_taper)
    mig = stolt_migration_2d(
        section, dt=dt, dx=dx, velocity=float(v),
        dz=0.5 * v * dt, nz=nt,
        exploding_reflector=True, apply_jacobian=True,
        pad_t=PAD_T_FACTOR, pad_x=pad_x_mult,
        taper_t=TAPER_T_FRAC, taper_x=taper_frac_x,
        depth_padding=2.0)
    if dead.any():
        mig[:, dead] = 0.0
    depth = t * (0.5 * v)
    return mig, section, dead, depth


def save_migrated_npz(out_npz, mig, x, depth, ref_elev, elevations, v):
    """Persist a single-velocity migrated section (thesis-input NPZ). Field layout
    frozen: data (float32), dist_axis, depth_axis, ref_elev, elevations, velocity."""
    out_npz = Path(out_npz)
    out_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez(str(out_npz),
             data=mig.astype(np.float32),
             dist_axis=x,
             depth_axis=depth,
             ref_elev=np.float64(ref_elev),
             elevations=elevations,
             velocity=np.float64(v))
    return out_npz

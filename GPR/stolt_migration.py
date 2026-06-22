"""
stolt_migration.py
2-D constant-velocity Stolt (frequency-wavenumber) migration for zero-offset GPR.

This is a faithful extraction of the migration core written by Dr. Cedric Schmelzbach (Applied Geophysics, ETH Zurich) -- see
  Other data and scripts/Cedric 2D migration/F_GPR_2D_Migration.2.ipynb
The function and its helpers are copied verbatim (numpy backend only, the cupy
path dropped) so the velocity-scan tool and any other script share ONE, vetted,
professor-supplied implementation rather than a home-grown re-derivation.

Key properties (per the source notebook, which passes a point-diffractor
focusing test and a spike -> semicircle impulse test):
  - exploding-reflector half-velocity vm = v/2 (correct for zero-offset GPR);
  - Stolt dispersion remap f = vm * sqrt(kx^2 + kz^2) per lateral wavenumber;
  - optional |kz|/|k| Jacobian to preserve relative amplitudes;
  - one-sided zero padding (data at the near/t=0 edge, zeros appended at the far
    boundary) so t=0 and the near survey edge are left untouched;
  - raised-cosine edge taper before padding to suppress spectral leakage;
  - depth over-padding to push the wrap-around mirror beyond the output range.

Output is a DEPTH section (nz, nx); depth = TWT * vm.
"""

from __future__ import annotations

import numpy as np


def next_pow2(n):
    n = int(n)
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def cosine_taper_1d(n, frac):
    frac = float(frac)
    if frac <= 0.0:
        return np.ones(n, dtype=float)
    frac = min(frac, 0.5)
    m = int(round(frac * n))
    if m < 1:
        return np.ones(n, dtype=float)
    w = np.ones(n, dtype=float)
    ramp = np.sin(0.5 * np.pi * (np.arange(m, dtype=float) + 1.0) / m) ** 2
    w[:m]  = ramp
    w[-m:] = ramp[::-1]
    return w


def apply_separable_taper_2d(data, taper_t=0.0, taper_x=0.0):
    d = np.asarray(data)
    nt, nx = d.shape
    wt = cosine_taper_1d(nt, taper_t)[:, None]
    wx = cosine_taper_1d(nx, taper_x)[None, :]
    return d * wt * wx


def _interp1_complex_regular(x, y, xi):
    xi  = np.asarray(xi)
    yi  = np.zeros(xi.shape, dtype=y.dtype)
    idx = np.searchsorted(x, xi, side="right") - 1
    valid = (idx >= 0) & (idx < x.size - 1)
    iv  = idx[valid]
    w   = (xi[valid] - x[iv]) / (x[iv + 1] - x[iv])
    yi[valid] = (1.0 - w) * y[iv] + w * y[iv + 1]
    return yi


def stolt_migration_2d(
    data,
    dt,
    dx,
    velocity,
    dz=None,
    nz=None,
    exploding_reflector=True,
    apply_jacobian=True,
    pad_t=1.0,
    pad_x=1.0,
    taper_t=0.0,
    taper_x=0.0,
    pad_to_pow2=True,
    depth_padding=2.0,
):
    """2-D constant-velocity Stolt migration for zero-offset GPR data.

    data     : (nt, nx) input section (units of dt, dx consistent: ns, m)
    dt       : time sampling interval (ns)
    dx       : trace spacing (m)
    velocity : EM propagation velocity (m/ns)
    dz, nz   : output depth sampling / count (default vm*dt, nt)
    exploding_reflector : use vm = velocity/2 (correct for zero-offset GPR)
    apply_jacobian      : scale by |kz|/|k| to preserve relative amplitudes
    pad_t, pad_x        : one-sided padding multipliers (>1 cuts wrap-around)
    taper_t, taper_x    : raised-cosine edge taper fraction (before padding)
    depth_padding       : internal depth over-sampling (push mirror out of view)

    Returns the migrated depth section (nz, nx).
    """
    d = np.asarray(data)
    if d.ndim != 2:
        raise ValueError("data must have shape (nt, nx)")

    nt0, nx0 = map(int, d.shape)
    vm = 0.5 * velocity if exploding_reflector else velocity

    if dz is None:
        dz = vm * dt
    if nz is None:
        nz = nt0

    # Edge taper before padding to reduce spectral leakage
    d = apply_separable_taper_2d(d, taper_t=taper_t, taper_x=taper_x)

    # One-sided padded sizes: data at START, zeros at END (preserves t=0 / near edge)
    ntp = max(nt0, int(np.ceil(nt0 * pad_t)))
    nxp = max(nx0, int(np.ceil(nx0 * pad_x)))
    if pad_to_pow2:
        ntp = next_pow2(ntp)
        nxp = next_pow2(nxp)

    dp = np.zeros((ntp, nxp), dtype=d.dtype)
    dp[:nt0, :nx0] = d

    # Forward 2-D FFT: rfft in time, full FFT in x
    D = np.fft.rfft(dp, axis=0)
    D = np.fft.fft(D,  axis=1)

    f  = np.fft.rfftfreq(ntp, d=dt)   # positive temporal frequencies
    fx = np.fft.fftfreq(nxp,  d=dx)   # lateral wavenumbers

    # Over-padded depth-wavenumber axis (pushes wrap-around mirror beyond output)
    nzfft = max(nz, int(np.ceil(nz * depth_padding)))
    if pad_to_pow2:
        nzfft = next_pow2(nzfft)
    fz = np.fft.fftfreq(nzfft, d=dz)

    # Stolt remap: for each kx, interpolate D(f, kx) onto the kz grid
    I_k = np.zeros((nzfft, nxp), dtype=D.dtype)
    for ix in range(nxp):
        fx_i     = fx[ix]
        rho      = np.sqrt(fx_i**2 + fz**2)   # |k| = sqrt(kx^2 + kz^2)
        f_target = vm * rho                    # Stolt dispersion relation
        spec     = _interp1_complex_regular(f, D[:, ix], f_target)
        if apply_jacobian:
            scale       = np.zeros_like(rho)
            mask        = rho > 0
            scale[mask] = np.abs(fz[mask]) / rho[mask]   # |kz| / |k|
            spec        = spec * scale
        I_k[:, ix] = spec

    # Inverse 2-D FFT; imaginary residual is numerical noise
    image_full = np.fft.ifftn(I_k, axes=(0, 1)).real

    # Crop to requested depth range and original lateral extent
    return image_full[:nz, :nx0]

"""Artifact I/O for the GPR-constrained tube inversion -- the seam that DETACHES
compute from plotting. `run_inversion.py` writes one .npz per (line, mode,
truncation); the plot scripts load it and never re-run the grid search or the Monte
Carlo. The engine (invert_tube.py) stays pure; this module is just persistence.

One record = one .npz. Scalars are stored as 0-d arrays (unwrapped to float/int on
load), `mode` as a string array, and `truncate=None` as NaN.
"""
import numpy as np
import invert_tube as it

ART = it.FIG / "artifacts"

# scalar keys unwrapped to float on load (everything that is not an array / int / str)
_FLOAT_KEYS = ("ceiling", "floor", "velocity", "velocity_sigma", "sigma_pick",
               "slope_se", "density", "size", "x0", "area", "chi2min", "chi2red",
               "size_lo", "size_hi", "baseline", "se_data", "se_pick", "se_vel",
               "se_det", "se_tot", "area_se_data", "area_se_pick", "area_se_vel",
               "area_se_det", "area_se_tot")


def artifact_path(line, mode, truncate=None):
    tag = "" if truncate is None else f"_trunc{int(truncate)}"
    return ART / f"inv_line{line}_{mode}{tag}.npz"


def save_artifact(path, *, line, mode, cfg, ceiling, floor, sizes, x0s, res, u,
                  baseline, ensemble, ens_seed):
    """Persist one inversion result. `res` is invert()'s dict, `u` is
    size_area_se()'s dict, `ensemble` is sample_ensemble()'s (n, 4) array."""
    ART.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        line=line, mode=mode, ceiling=ceiling, floor=floor,
        truncate=(np.nan if cfg.truncate is None else cfg.truncate),
        velocity=cfg.velocity, velocity_sigma=cfg.velocity_sigma,
        sigma_pick=cfg.sigma_pick, slope_se=cfg.slope_se, density=it.DENSITY,
        sizes=sizes, x0s=x0s, chi2=res["chi2"],
        size=res["size"], x0=res["x0"], area=u["area"],
        chi2min=res["chi2min"], dof=res["dof"], chi2red=res["chi2red"],
        size_lo=res["size_lo"], size_hi=res["size_hi"], baseline=baseline,
        se_data=u["se_data"], se_pick=u["se_pick"], se_vel=u["se_vel"],
        se_det=u["se_det"], se_tot=u["se_tot"],
        area_se_data=u["area_se_data"], area_se_pick=u["area_se_pick"],
        area_se_vel=u["area_se_vel"], area_se_det=u["area_se_det"],
        area_se_tot=u["area_se_tot"],
        ensemble=ensemble, ens_seed=ens_seed, ens_n=len(ensemble),
    )
    return path


def load_artifact(line, mode, truncate=None):
    """Load one inversion artifact into a plain dict (arrays kept, scalars unwrapped)."""
    p = artifact_path(line, mode, truncate)
    if not p.exists():
        raise FileNotFoundError(f"no inversion artifact at {p} -- run run_inversion.py first")
    z = np.load(p, allow_pickle=False)
    d = {k: z[k] for k in z.files}
    d["mode"] = str(d["mode"])
    for k in ("line", "dof", "ens_n", "ens_seed"):
        d[k] = int(d[k])
    d["truncate"] = None if np.isnan(d["truncate"]) else float(d["truncate"])
    for k in _FLOAT_KEYS:
        d[k] = float(d[k])
    return d


def cfg_of(d):
    """Rebuild the InvCfg from a loaded artifact, for the cheap forward evaluations
    the plot scripts still need (best-fit + ensemble anomaly curves)."""
    return it.InvCfg(velocity=d["velocity"], velocity_sigma=d["velocity_sigma"],
                     sigma_pick=d["sigma_pick"], slope_se=d["slope_se"],
                     truncate=d["truncate"])

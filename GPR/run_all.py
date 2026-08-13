"""
run_all.py
ONE command to regenerate every DETERMINISTIC GPR output for the thesis.

It runs `run_pipeline.py` (raw -> processed -> topo -> migrated NPZ/PNG -> dual-freq
-> flowerpetal 3D HTML -> velocity-scan HTMLs) and then every standalone figure
script that `run_pipeline.py` does not call itself. Each step is a subprocess; a
failure is reported but does not stop the rest, and a summary is printed at the end.

WHAT THIS DOES NOT DO (genuinely manual, human-in-the-loop -- see README.md):
  1. Stitch raw field files       -> GPRFieldVisual.ipynb  (writes Data/GPR/Stitched/*_raw.npz)
  2. Tune + save processing params -> GPRProcessing.ipynb   (writes Data/GPR/Processed/*_params.json)
  3. Pick the migration velocity by eye off the Stolt velocity-scan HTML, then set
     `velocity` + `migrate: true` + `migration_gain` in that profile's params JSON.
  4. Screenshot the 3D HTMLs for the thesis stills (the FP3D_* PNGs/PDFs).

So the reproduce chain is: (1) and (2) by hand ONCE -> `python run_all.py` regenerates
everything scriptable -> (3)/(4) by hand where a human decision or a browser is required.
Prerequisite: the raw NPZs and the `_params.json` files must already exist.

Usage:
  python run_all.py              # everything (slow: rebuilds the velocity-scan HTMLs)
  python run_all.py --no-scans   # skip the slow velocity-scan HTMLs
"""

import sys
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable

# Standalone deterministic figure/QC scripts NOT invoked by run_pipeline.py.
# (run_pipeline already does: processed/topo NPZ, dual-freq topo for all lines,
#  migrated NPZ/PNG + before/after + dual-freq migrated, flowerpetal 3D HTML,
#  velocity-scan HTMLs.)
FIGURE_STEPS = [
    ['plot_processing_steps.py', 'Line3_50MHz'],
    ['plot_processing_steps.py', 'Line3_100MHz'],
    ['plot_processing_steps.py', 'Line5_50MHz'],
    ['plot_processing_steps.py', 'Line5_100MHz'],
    ['plot_l2_spectral_diagnostics.py'],
    ['plot_l2_svd_whiten.py'],
    ['plot_multiples_schematic.py'],
    ['plot_petal_map.py'],
    ['plot_petal_migration_map.py'],
    ['plot_petal_migration_3d.py'],
    ['plot_lidar_cave_overlay.py'],
    ['check_polarity.py'],
    ['compare_intersections.py'],
]


def run(cmd, label):
    print('\n=== {} ==='.format(label))
    r = subprocess.run([PY] + cmd, cwd=str(HERE))
    ok = (r.returncode == 0)
    print('  {} ({})'.format('OK' if ok else 'FAILED', ' '.join(cmd)))
    return ok


def main():
    no_scans = '--no-scans' in sys.argv
    results = []

    pipe = ['run_pipeline.py'] + (['--no-scans'] if no_scans else [])
    results.append(('run_pipeline.py', run(pipe, 'PIPELINE: ' + ' '.join(pipe))))

    for step in FIGURE_STEPS:
        results.append((' '.join(step), run(step, 'FIGURE: ' + ' '.join(step))))

    print('\n==================== SUMMARY ====================')
    n_ok = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print('  {:4s} {}'.format('OK' if ok else 'FAIL', name))
    print('  {}/{} steps succeeded'.format(n_ok, len(results)))
    print('\nManual steps still required (see README.md): 3D-HTML screenshots,')
    print('the velocity pick, and the two notebooks that produce raw NPZs + params JSONs.')
    sys.exit(0 if n_ok == len(results) else 1)


if __name__ == '__main__':
    main()

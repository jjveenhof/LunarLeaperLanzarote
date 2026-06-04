"""
test_normalisation.py
Verifies that tracewise-rms-window normalisation uses only the window region
to compute the scaling factor, then applies it to the full trace.

Synthetic setup:
  - 2 traces, each with a strong direct wave at early times (~10x amplitude)
    and weak reflections at late times.
  - Trace 1 has a stronger direct wave than Trace 2 to confirm inter-trace
    equalisation.
  - Window is set to late times only (after the direct wave).

Expected results:
  - Full-trace RMS: dominated by direct wave, poor equalisation of reflections.
  - Window RMS: ignores direct wave, equalises the reflection amplitudes.
"""

import sys
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent /
    'Other data and scripts' / 'Tube X' / 'GPR' / 'scripts' /
    'georadar-data-processing'))
from gdp.preprocessing.normalizing import normalize_data

# ---- synthetic data ----------------------------------------------------------
n_samples  = 200
n_traces   = 2
direct_end = 40   # direct wave occupies samples 0-39
data       = np.zeros((n_samples, n_traces))

t  = np.arange(direct_end)
t2 = np.arange(n_samples - direct_end)

data[:direct_end, 0] = 8.0 * np.sin(2 * np.pi * t  / 10)   # trace 1: amplitude 8
data[:direct_end, 1] = 4.0 * np.sin(2 * np.pi * t  / 10)   # trace 2: amplitude 4
data[direct_end:, 0] = 1.0 * np.sin(2 * np.pi * t2 / 20)
data[direct_end:, 1] = 1.0 * np.sin(2 * np.pi * t2 / 20)

# ---- normalise ---------------------------------------------------------------
window = (direct_end, n_samples)

out_full   = normalize_data(data.copy(), typ='tracewise-rms',        window=window)
out_window = normalize_data(data.copy(), typ='tracewise-rms-window',  window=window)

# ---- print report ------------------------------------------------------------
def rms(x):
    return float(np.sqrt(np.mean(x**2)))

print('=== Input data ===')
for i in range(n_traces):
    print(f'  Trace {i+1}  direct-wave RMS: {rms(data[:direct_end, i]):.3f}'
          f'   reflection RMS: {rms(data[direct_end:, i]):.3f}')

print('\n=== tracewise-rms (full trace, window param IGNORED) ===')
for i in range(n_traces):
    print(f'  Trace {i+1}  direct-wave RMS: {rms(out_full[:direct_end, i]):.3f}'
          f'   reflection RMS: {rms(out_full[direct_end:, i]):.3f}')

print('\n=== tracewise-rms-window (window = late times only) ===')
for i in range(n_traces):
    print(f'  Trace {i+1}  direct-wave RMS: {rms(out_window[:direct_end, i]):.3f}'
          f'   reflection RMS: {rms(out_window[direct_end:, i]):.3f}')

print('\n=== Key check ===')
r1 = rms(out_window[direct_end:, 0])
r2 = rms(out_window[direct_end:, 1])
print(f'  Reflection RMS after window-norm -- trace 1: {r1:.4f}  trace 2: {r2:.4f}')
if abs(r1 - r2) < 1e-6:
    print('  PASS: reflections are equalised (same RMS) despite different direct waves.')
else:
    print('  FAIL: reflections differ -- window norm not working as expected.')

# ---- plot --------------------------------------------------------------------
samples = np.arange(n_samples)
colors  = ['steelblue', 'tomato']
labels  = ['Trace 1 (strong direct wave)', 'Trace 2 (weak direct wave)']

fig, axes = plt.subplots(1, 3, figsize=(14, 5), sharey=False)
fig.suptitle('Normalisation test -- synthetic data', fontsize=12)

datasets = [
    (data,       'Raw data'),
    (out_full,   'tracewise-rms\n(full trace, window ignored)'),
    (out_window, 'tracewise-rms-window\n(late-time window only)'),
]

for ax, (d, title), show_window in zip(axes, datasets, [False, False, True]):
    for i in range(n_traces):
        ax.plot(d[:, i], samples, color=colors[i], label=labels[i], lw=1.2)
    if show_window:
        ax.axhline(direct_end, color='gray', linestyle='--', lw=0.8, label='Window start')
        ax.axhspan(direct_end, n_samples, alpha=0.06, color='green', label='Norm window')
    ax.set_title(title, fontsize=10)
    ax.set_xlabel('Amplitude')
    ax.invert_yaxis()
    ax.set_ylabel('Sample index')
    ax.set_ylim(n_samples, 0)

axes[2].legend(fontsize=8, loc='lower right')

# Annotate reflection RMS on the two normalised panels
for ax, d in zip(axes[1:], [out_full, out_window]):
    for i, c in enumerate(colors):
        r = rms(d[direct_end:, i])
        ax.text(0.02, 0.02 + i * 0.07, f'T{i+1} refl. RMS={r:.3f}',
                transform=ax.transAxes, color=c, fontsize=8)

plt.tight_layout()
plt.show()

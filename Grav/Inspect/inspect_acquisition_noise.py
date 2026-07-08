"""
Acquisition-noise diagnostic: per-cycle CG-5 SD and the within-cycle standard
error SE = SD / sqrt(DUR) (N = DUR one-per-second readings, per the CG-5 manual),
per line, from the cleaned cycle-level file. Justifies the per-line cycle-duration
(DUR) choices: DUR was lengthened when the noise (SD) rose and shortened when it
fell, keeping the within-cycle SE roughly bounded.

NOTE: no 1/sqrt(6) sample-rate factor -- the CG-5 does not instruct it, and the
6 Hz samples are autocorrelated, so N = DUR (per-second readings) is the effective
count. This within-cycle SE turns out close to the real per-station uncertainty
(decay-fit SE_est) for the tuned lines, and diverges only where DUR was
insufficient (L2 st0-8, 30 s) -- discuss that station-SE excess in processing.

Reads Data/Gravimetry/Processed/filtered_gravimetry_all.csv (cleaned, cycles kept
separate). Notes column may contain commas, so columns are indexed positionally.
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
SRC = BASE / "Data/Gravimetry/Processed/filtered_gravimetry_all.csv"
OUT = BASE / "Results/Grav/acquisition_noise.png"


def load():
    line, stn, sd, dur = [], [], [], []
    with open(SRC, encoding="utf-8") as fh:
        h = fh.readline().rstrip("\n").split(",")
        iL, iS, iSD, iD = (h.index(c) for c in ("Line", "Station", "SD", "Dur"))
        for ln in fh:
            f = ln.rstrip("\n").split(",")
            try:
                line.append(int(float(f[iL]))); stn.append(int(float(f[iS])))
                sd.append(float(f[iSD]) * 1000.0)          # mGal -> uGal
                dur.append(float(f[iD]))
            except ValueError:
                pass
    return map(np.array, (line, stn, sd, dur))


def main():
    L, S, SD, DUR = load()
    SE = SD / np.sqrt(DUR)                                  # within-cycle SE (uGal)
    groups = [("L2 st0-8\n(30 s)", (L == 2) & (S <= 8)),
              ("L2 st9-37\n(60 s)", (L == 2) & (S >= 9)),
              ("L3\n(45 s)", L == 3), ("L4\n(30 s)", L == 4), ("L5\n(30 s)", L == 5)]
    labels = [g[0] for g in groups]
    sd_d = [SD[m] for _, m in groups]
    se_d = [SE[m] for _, m in groups]
    pos = np.arange(len(groups))

    print(f"{'group':16s} {'medSD':>6} {'medSE':>6}  (uGal)")
    for (lab, m) in groups:
        print(f"{lab.replace(chr(10), ' '):16s} {np.median(SD[m]):6.1f} {np.median(SE[m]):6.2f}")

    fig, ax = plt.subplots(figsize=(10, 5.5))
    C_SD, C_SE = "#0099FF", "#FF5C00"

    def box(data, at, color):
        bp = ax.boxplot(data, positions=at, widths=0.32, patch_artist=True,
                        showfliers=True, medianprops=dict(color="k", lw=1.6),
                        flierprops=dict(marker=".", ms=3, mfc="0.6", mec="0.6"))
        for p in bp["boxes"]:
            p.set(facecolor=color, alpha=0.5)
        return bp

    # SD and SE share one axis (same units) -- SE = SD/sqrt(DUR) sits well below SD.
    box(sd_d, pos - 0.19, C_SD)
    box(se_d, pos + 0.19, C_SE)
    ax.set_xticks(pos); ax.set_xticklabels(labels)
    ax.set_ylabel("gravity noise (uGal)")
    ax.set_ylim(0, None)
    ax.grid(True, axis="y", alpha=0.2, ls="--")
    ax.legend(handles=[mpatches.Patch(color=C_SD, alpha=0.5, label="per-cycle SD (noise)"),
                       mpatches.Patch(color=C_SE, alpha=0.5,
                                      label=r"within-cycle SE $=$ SD$/\sqrt{\mathrm{DUR}}$")],
              fontsize=8, loc="upper right")
    ax.set_title("Cycle noise and within-cycle precision per line "
                 "(DUR tuned to the noise)", fontweight="bold", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"saved -> {OUT.relative_to(BASE)}")


if __name__ == "__main__":
    main()

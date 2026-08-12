"""
gpr_constants.py
Shared constants used across GPR processing scripts. This module imports nothing
from the project, so any script can import it without a cycle. Centralised here
(phase-2 F6/F10) so a value cannot silently drift between copies -- the same
discipline that keeps SEGMENTS drift-proof.
"""

V_DEFAULT = 0.125   # wave velocity in m/ns; fallback when not in params.
                    # Set to the Line 3 migration-picked velocity (2026-07-01).

V_AIR = 0.3         # m/ns, air velocity for the air-gap floor-depth correction
                    # (plot_dual_freq.cave_geometry). Display/print only -- never
                    # baked into an NPZ.

# Antenna midpoint offsets: distance from the back antenna (on the metre mark) to
# the rig midpoint, in metres. Added to a profile's dist_axis to get the GNSS metre.
OFFSET_50MHZ  = 1.10    # 2.2 m rig
OFFSET_100MHZ = 0.425   # 0.85 m rig

# Where each 100 MHz section starts on its line (metre). The 50 MHz sections start
# at 0; the 100 MHz ones start further along, so this both maps them to GNSS metres
# (topo_correction.dist_to_gnss_metre) and offsets them for the dual-freq plot
# (plot_dual_freq.X_OFFSET_100MHZ). Same physical number, one source.
SECTION_START_100MHZ = {
    'Line2': 0.0,    # both frequencies share the same start
    'Line3': 60.0,
    'Line5': 30.0,   # profile reversed in GPRFieldVisual (now runs 30->80 m)
}

# Line 2 100 MHz hardware notch centres (MHz) -- pulsEKKO antenna housing artifact,
# not geology. Guide lines only (plot_l2_spectral_diagnostics / plot_l2_svd_whiten).
NOTCH_FREQS_MHZ = [75.0, 160.0]

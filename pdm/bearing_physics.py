"""Bearing fault characteristic frequencies from rolling-element geometry.

Formulas and geometry are the ones locked in docs/Laporan_Progres_Case2.docx
section 4.1. Bearing model: Rexnord ZA-2115 (NASA IMS test rig), double row,
16 rolling elements, shaft speed 2000 RPM.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BearingGeometry:
    n: int          # number of rolling elements
    pitch_diameter_mm: float   # D
    roller_diameter_mm: float  # d
    contact_angle_deg: float   # phi
    shaft_rpm: float


REXNORD_ZA2115 = BearingGeometry(
    n=16,
    pitch_diameter_mm=71.501,   # 2.815 in
    roller_diameter_mm=8.4074,  # 0.331 in
    contact_angle_deg=15.17,
    shaft_rpm=2000.0,
)


def shaft_freq_hz(geo: BearingGeometry = REXNORD_ZA2115) -> float:
    return geo.shaft_rpm / 60.0


def _ratio_cos_phi(geo: BearingGeometry) -> float:
    return (geo.roller_diameter_mm / geo.pitch_diameter_mm) * math.cos(
        math.radians(geo.contact_angle_deg)
    )


def bpfo(geo: BearingGeometry = REXNORD_ZA2115) -> float:
    """Ball Pass Frequency, Outer race."""
    fr = shaft_freq_hz(geo)
    return (geo.n / 2) * fr * (1 - _ratio_cos_phi(geo))


def bpfi(geo: BearingGeometry = REXNORD_ZA2115) -> float:
    """Ball Pass Frequency, Inner race."""
    fr = shaft_freq_hz(geo)
    return (geo.n / 2) * fr * (1 + _ratio_cos_phi(geo))


def bsf(geo: BearingGeometry = REXNORD_ZA2115) -> float:
    """Ball Spin Frequency."""
    fr = shaft_freq_hz(geo)
    ratio = _ratio_cos_phi(geo)
    return (geo.pitch_diameter_mm / (2 * geo.roller_diameter_mm)) * fr * (1 - ratio ** 2)


def ftf(geo: BearingGeometry = REXNORD_ZA2115) -> float:
    """Fundamental Train Frequency (cage frequency)."""
    fr = shaft_freq_hz(geo)
    return (fr / 2) * (1 - _ratio_cos_phi(geo))


def fault_frequencies(geo: BearingGeometry = REXNORD_ZA2115) -> dict:
    return {
        "BPFO": bpfo(geo),
        "BPFI": bpfi(geo),
        "BSF": bsf(geo),
        "FTF": ftf(geo),
    }


if __name__ == "__main__":
    freqs = fault_frequencies()
    print("Reference values (Laporan Progres Case2 sec.4/7): "
          "BPFO~236.4 BPFI~296.9 BSF~139.9 FTF~14.8 Hz")
    for name, val in freqs.items():
        print(f"{name}: {val:.1f} Hz")

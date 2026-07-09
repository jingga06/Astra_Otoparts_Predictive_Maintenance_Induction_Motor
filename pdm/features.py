"""Per-snapshot feature extraction: time-domain stats + envelope analysis.

Matches the methodology in docs/Proposal_Final_Case2.docx (slide 4-5) and
docs/Laporan_Progres_Case2.docx sec.5:
  time-domain: RMS, kurtosis, skewness, crest factor
  envelope analysis: band-pass (2-10 kHz) -> Hilbert envelope -> FFT of
  envelope -> peak energy near each bearing fault frequency (BPFO/BPFI/BSF).

One raw file = one 1-second snapshot = one feature-extraction window; no
extra re-windowing is applied (the dataset's own 10-minute cadence is the
time axis for every downstream stage).
"""

import numpy as np
from scipy import stats
from scipy.signal import butter, filtfilt, hilbert

ENVELOPE_BAND_HZ = (2000.0, 10000.0)
PEAK_SEARCH_TOL_HZ = 3.0  # +/- tolerance window around each fault frequency


def time_domain_features(x: np.ndarray) -> dict:
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    kurt = float(stats.kurtosis(x, fisher=False, bias=False))
    skew = float(stats.skew(x, bias=False))
    peak = float(np.max(np.abs(x)))
    crest = peak / rms if rms > 0 else 0.0
    return {"rms": rms, "kurtosis": kurt, "skewness": skew, "crest_factor": crest}


def _bandpass(x: np.ndarray, fs: int, band=ENVELOPE_BAND_HZ) -> np.ndarray:
    nyq = fs / 2.0
    low, high = band[0] / nyq, min(band[1], nyq * 0.98) / nyq
    b, a = butter(4, [low, high], btype="band")
    return filtfilt(b, a, x)


def envelope_spectrum(x: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (freqs, magnitude) of the FFT of the Hilbert envelope of the
    band-passed signal — the standard bearing-diagnostics pipeline."""
    filtered = _bandpass(x, fs)
    envelope = np.abs(hilbert(filtered))
    envelope = envelope - envelope.mean()
    n = len(envelope)
    spectrum = np.abs(np.fft.rfft(envelope))
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    return freqs, spectrum


def band_energy(freqs: np.ndarray, spectrum: np.ndarray, target_hz: float,
                 tol_hz: float = PEAK_SEARCH_TOL_HZ) -> float:
    """Sum of squared magnitude in a small window around target_hz."""
    mask = (freqs >= target_hz - tol_hz) & (freqs <= target_hz + tol_hz)
    if not np.any(mask):
        return 0.0
    return float(np.sum(spectrum[mask] ** 2))


def extract_features(x: np.ndarray, fs: int, fault_freqs: dict) -> dict:
    feats = time_domain_features(x)
    freqs, spectrum = envelope_spectrum(x, fs)
    feats["bpfo_energy"] = band_energy(freqs, spectrum, fault_freqs["BPFO"])
    feats["bpfi_energy"] = band_energy(freqs, spectrum, fault_freqs["BPFI"])
    feats["bsf_energy"] = band_energy(freqs, spectrum, fault_freqs["BSF"])
    return feats

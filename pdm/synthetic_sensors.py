"""Synthetic temperature & current channels for the multi-parameter demo.

The NASA IMS Bearing dataset only records vibration. Astra's brief asks for
multi-parameter monitoring (temperature, current, ...), so these two extra
channels are synthesized here - but not as independent random noise. Each is
driven by the row's own `hi_norm` (health index, in "sigma above this run's
healthy baseline" - see pdm/health_index.py), the same degradation signal the
vibration-only pipeline already computes, passed through an EWMA lag and a
gain that are deliberately different per sensor:

  - Temperature has a slow thermal-mass lag (heat builds up gradually as
    bearing friction increases) and the largest gain - temperature is a
    "clean", high-signal indicator in real induction motors.
  - Current has an even slower electrical/mechanical lag and a small, noisy
    gain - rising motor load current from bearing drag is a real but weak
    and indirect effect, deliberately the least clean of the three signals.

This keeps the synthetic channels physically defensible (they move together
with vibration-driven degradation, at different speeds/strengths, the way
real sensors would). They do NOT feed into the Isolation Forest anomaly model
or the PCA Health Index (pdm/anomaly.py, pdm/health_index.py stay vibration-
only, so their already-validated 3-sigma / RUL behaviour is untouched) - but
they ARE included as voting/persistence candidate columns in pdm/alarm.py, so
a genuinely elevated temperature/current reading can now contribute to (or
confirm) an alarm, even though the values themselves are lagged transforms of
the same vibration-based health index, not independent physical sensors.
"""

import hashlib

import numpy as np
import pandas as pd

BASE_TEMPERATURE_C = 38.0   # typical force-lubricated bearing housing temp, idle/healthy
TEMPERATURE_NOISE_STD = 0.35
TEMPERATURE_GAIN = 2.8       # deg C per sigma of (lagged) degradation
TEMPERATURE_LAG_ALPHA = 0.03  # slower EWMA = more thermal lag
TEMPERATURE_MAX_RISE = 32.0   # cap: healthy ~38C, worst-case ~70C (realistic alarm range)

BASE_CURRENT_A = 4.1        # nominal running current, small induction motor
CURRENT_NOISE_STD = 0.12
CURRENT_GAIN = 0.9
CURRENT_LAG_ALPHA = 0.05
CURRENT_MAX_RISE = 3.0


def _seed(run_key: str, bearing_id: int) -> int:
    digest = hashlib.sha256(f"{run_key}_bearing{bearing_id}".encode()).hexdigest()
    return int(digest[:8], 16)


def generate(df: pd.DataFrame, run_key: str, bearing_id: int) -> pd.DataFrame:
    """Return a copy of df with temperature_c and current_a columns added."""
    rng = np.random.default_rng(_seed(run_key, bearing_id))
    n = len(df)
    degradation = np.clip(df["hi_norm"].to_numpy(), 0.0, None)

    temp_drive = pd.Series(degradation).ewm(alpha=TEMPERATURE_LAG_ALPHA, adjust=False).mean().to_numpy()
    temp_rise = np.clip(TEMPERATURE_GAIN * temp_drive, 0.0, TEMPERATURE_MAX_RISE)
    temperature_c = BASE_TEMPERATURE_C + temp_rise + rng.normal(0.0, TEMPERATURE_NOISE_STD, n)

    current_drive = pd.Series(degradation).ewm(alpha=CURRENT_LAG_ALPHA, adjust=False).mean().to_numpy()
    current_rise = np.clip(CURRENT_GAIN * current_drive, 0.0, CURRENT_MAX_RISE)
    current_a = BASE_CURRENT_A + current_rise + rng.normal(0.0, CURRENT_NOISE_STD, n)

    out = df.copy()
    out["temperature_c"] = temperature_c
    out["current_a"] = current_a
    return out

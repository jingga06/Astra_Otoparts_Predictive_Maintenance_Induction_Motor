"""Live-simulation demo layer (dosen feedback: show the system ingesting +
retraining on new data continuously, not just replaying a frozen historical
run). Reuses the existing, already-validated pipeline (pdm/anomaly.py,
pdm/health_index.py, pdm/alarm.py, pdm/rul.py, pdm/synthetic_sensors.py)
UNCHANGED - this module only adds the pieces needed to (a) seed a live run
from an existing historical bearing's artifact CSV, (b) synthesize plausible
NEW feature rows continuing the degradation trend past where the real NASA
data ends, and (c) re-run the existing fit/annotate functions on the growing
dataframe each cycle (a genuine refit, not just re-scoring).

Honesty note: temperature/current were already synthetic (see
synthetic_sensors.py); the 6 vibration features generated here for future
snapshots are ALSO synthetic (there is no new raw vibration signal once the
real NASA run ends) - each is a simple linear continuation of its own
historical relationship to hi_norm (the same PCA health index), plus noise
sized to that relationship's residual. This demonstrates the live-ingest/
retrain CAPABILITY the system would need once Astra provides real sensor
data, not a claim that the numbers below are real sensor readings.
"""

import numpy as np
import pandas as pd

from pdm import alarm, anomaly, health_index, rul
from pdm.anomaly import FEATURE_COLUMNS
from pdm.synthetic_sensors import generate as generate_synthetic_sensors

STEP_MINUTES = 10  # matches the NASA IMS dataset's own snapshot cadence
RAW_COLUMNS = ["timestamp", "elapsed_hours", "filepath"] + FEATURE_COLUMNS + ["is_synthetic_snapshot"]


def seed_from_history(history_df: pd.DataFrame, cutoff_index: int | None = None,
                       margin_rows: int = 20) -> pd.DataFrame:
    """Truncate an already-built artifacts/<run>_bearing<n>.csv at cutoff_index
    (default: just before its first historical alarm, so the live demo has a
    'healthy -> starting to degrade' story to play out in a reasonable number
    of cycles) and keep only the raw columns needed to re-run the pipeline
    from scratch."""
    if cutoff_index is None:
        alarm_idx = np.flatnonzero(history_df["is_alarm"].to_numpy())
        cutoff_index = int(max(margin_rows, alarm_idx[0] - margin_rows)) if len(alarm_idx) else len(history_df) // 2

    seed = history_df.iloc[:cutoff_index][["timestamp", "elapsed_hours", "filepath"] + FEATURE_COLUMNS].copy()
    seed["is_synthetic_snapshot"] = False
    return seed.reset_index(drop=True)


def fit_feature_trend(df: pd.DataFrame, hi_norm: np.ndarray) -> dict:
    """Simple per-feature linear fit vs hi_norm (degree-1 polyfit), refit each
    cycle from everything accumulated so far - NOT a replacement for the real
    PCA health index, just a way to synthesize plausible future raw feature
    values consistent with a target future hi_norm."""
    trend = {}
    for col in FEATURE_COLUMNS:
        y = df[col].to_numpy()
        b, a = np.polyfit(hi_norm, y, 1)
        resid_std = float(np.std(y - (a + b * hi_norm)))
        trend[col] = (float(a), float(b), max(resid_std, 1e-9))
    return trend


def _project_hi_norm(hi_norm: np.ndarray, n_new: int, tail_n: int = 30) -> np.ndarray:
    """Linear continuation of the most recent hi_norm trend (its own local
    slope, not the validated RUL exponential curve in pdm/rul.py -
    deliberately kept separate so nothing here can perturb that already-
    validated fit)."""
    tail = hi_norm[-tail_n:]
    x = np.arange(len(tail))
    b, a = np.polyfit(x, tail, 1)
    resid_std = float(np.std(tail - (a + b * x)))
    future_x = np.arange(len(tail), len(tail) + n_new)
    trend = a + b * future_x
    noise = np.random.default_rng().normal(0.0, max(resid_std, 1e-6), n_new)
    return trend + noise


def generate_next_batch(df_so_far: pd.DataFrame, hi_norm: np.ndarray,
                         feature_trend: dict, n_new: int,
                         step_minutes: int = STEP_MINUTES) -> pd.DataFrame:
    """New synthetic snapshots continuing the timeline, driven by a projected
    hi_norm trajectory (see _project_hi_norm) - see module docstring for the
    honesty note on why these are synthetic, same spirit as
    pdm/synthetic_sensors.py's temperature/current."""
    rng = np.random.default_rng()
    hi_future = _project_hi_norm(hi_norm, n_new)

    last_row = df_so_far.iloc[-1]
    last_hours = float(last_row["elapsed_hours"])
    last_ts = pd.Timestamp(last_row["timestamp"])
    step_hours = step_minutes / 60.0

    new_hours = last_hours + step_hours * np.arange(1, n_new + 1)
    new_ts = [last_ts + pd.Timedelta(minutes=step_minutes * i) for i in range(1, n_new + 1)]

    data = {"timestamp": new_ts, "elapsed_hours": new_hours, "filepath": [""] * n_new}
    for col in FEATURE_COLUMNS:
        a, b, resid_std = feature_trend[col]
        data[col] = a + b * hi_future + rng.normal(0.0, resid_std, n_new)
    data["is_synthetic_snapshot"] = [True] * n_new
    return pd.DataFrame(data)


def retrain_cycle(df: pd.DataFrame, frozen_healthy_end_idx: int, et: float,
                   alarm_columns: list) -> pd.DataFrame:
    """Re-run the existing, unchanged pipeline (anomaly -> health_index ->
    synthetic sensors -> alarm (vibration-only trigger + widened display) ->
    RUL) on the full accumulated dataframe, with the healthy baseline pinned
    to the SAME absolute rows used since the very first cycle - anomaly.fit
    only accepts a fraction, so it's back-computed each cycle from the frozen
    absolute index; health_index.fit/alarm.evaluate already take an absolute
    index natively (see scripts/build_artifacts.py for the reference pattern
    this mirrors)."""
    n = len(df)
    healthy_fraction_live = frozen_healthy_end_idx / n

    anomaly_model = anomaly.fit(df, healthy_fraction=healthy_fraction_live)
    df = anomaly.annotate(df, anomaly_model)

    hi_model = health_index.fit(df, frozen_healthy_end_idx)
    df = health_index.annotate(df, hi_model)

    df = generate_synthetic_sensors(df, "live", 0)

    rul_trigger_alarm = alarm.evaluate(df, frozen_healthy_end_idx, columns=FEATURE_COLUMNS)["is_alarm"]
    df = alarm.evaluate(df, frozen_healthy_end_idx, columns=alarm_columns)
    df["rul_trigger_alarm"] = rul_trigger_alarm

    rul_res = rul.compute(df, df["rul_trigger_alarm"], df["hi_norm"].to_numpy(), et)
    df = rul.annotate(df, rul_res)

    return df

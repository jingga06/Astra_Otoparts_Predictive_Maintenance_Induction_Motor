"""Augment already-built artifacts with synthetic temperature/current columns.

Runs fast (no raw-signal feature extraction, no re-fit of any model) -
it only reads the cached per-bearing CSVs scripts/build_artifacts.py already
produced, adds temperature_c/current_a (see pdm/synthetic_sensors.py), and
writes them back. Does not touch hi_norm, health_score, alarm_level, rul_*
or any *_models.joblib / summary.csv - the locked vibration-only pipeline
and its already-validated numbers are unaffected.

Usage (from src/):
    python -m scripts.add_synthetic_sensors
"""

from pathlib import Path

import pandas as pd

from pdm.data_loader import RUN_SPECS
from pdm.synthetic_sensors import generate

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts"


def main():
    for run_key, spec in RUN_SPECS.items():
        for bearing_id in range(1, spec.n_bearings + 1):
            path = ARTIFACTS_DIR / f"{run_key}_bearing{bearing_id}.csv"
            df = pd.read_csv(path, parse_dates=["timestamp"])
            df = generate(df, run_key, bearing_id)
            df.to_csv(path, index=False)
            print(f"  updated {path.name}: +temperature_c, +current_a")


if __name__ == "__main__":
    main()

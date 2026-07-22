"""Live-simulation demo loop (see pdm/live_simulator.py for the design/honesty
note). Runs standalone, separate from the Streamlit dashboard process - the
dashboard just reads artifacts/live_bearing.csv, which this script keeps
growing and overwriting every cycle.

Usage (from project root, in its own terminal, left running during the demo):
    python -m scripts.run_live_simulation                  # demo-fast: 10 new snapshots / 15s
    python -m scripts.run_live_simulation --real-time       # literal dosen cadence: 60 / 30 min
"""

import argparse
import time
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from pdm.anomaly import FEATURE_COLUMNS
from pdm.live_simulator import (
    STEP_MINUTES,
    fit_feature_trend,
    generate_next_batch,
    retrain_cycle,
    seed_from_history,
)

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts"
ALARM_COLUMNS = FEATURE_COLUMNS + ["temperature_c", "current_a"]
LIVE_OUTPUT_PATH = ARTIFACTS_DIR / "live_bearing.csv"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="test3", help="Historical run to seed from (default: test3)")
    parser.add_argument("--bearing", type=int, default=3, help="Bearing to seed from (default: 3 - holdout failing bearing)")
    parser.add_argument("--batch-size", type=int, default=None, help="New snapshots per cycle")
    parser.add_argument("--interval-seconds", type=float, default=None, help="Seconds between cycles")
    parser.add_argument("--cutoff-hours", type=float, default=None,
                         help="Override where the live seed starts (default: just before the historical alarm)")
    parser.add_argument("--real-time", action="store_true",
                         help="Literal cadence dosen suggested: 60 new snapshots every 30 minutes, "
                              "instead of the sped-up demo defaults.")
    args = parser.parse_args()

    batch_size = args.batch_size or (60 if args.real_time else 10)
    interval_seconds = args.interval_seconds or (1800 if args.real_time else 15)

    history_path = ARTIFACTS_DIR / f"{args.run}_bearing{args.bearing}.csv"
    if not history_path.exists():
        raise SystemExit(
            f"{history_path} not found - run `python -m scripts.build_artifacts --all` first."
        )
    history_df = pd.read_csv(history_path, parse_dates=["timestamp"])

    cutoff_index = None
    if args.cutoff_hours is not None:
        cutoff_index = int(np.searchsorted(history_df["elapsed_hours"].to_numpy(), args.cutoff_hours))

    models_path = ARTIFACTS_DIR / f"{args.run}_bearing{args.bearing}_models.joblib"
    et = joblib.load(models_path)["rul_result"].et

    raw_df = seed_from_history(history_df, cutoff_index=cutoff_index)
    frozen_healthy_end_idx = max(20, int(0.5 * len(raw_df)))

    print(
        f"Live simulation seeded from {args.run} bearing {args.bearing}: "
        f"{len(raw_df)} snapshots, batch_size={batch_size}, interval={interval_seconds}s, "
        f"{'REAL-TIME (30 min/60 snapshot cadence)' if args.real_time else 'DEMO SPEED'}"
    )

    full_df = retrain_cycle(raw_df.copy(), frozen_healthy_end_idx, et, ALARM_COLUMNS)
    full_df.to_csv(LIVE_OUTPUT_PATH, index=False)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] initial retrain done - {len(full_df)} snapshots")

    while True:
        time.sleep(interval_seconds)

        hi_col = full_df["hi_norm"].to_numpy()
        trend = fit_feature_trend(full_df, hi_col)
        new_rows = generate_next_batch(full_df, hi_col, trend, batch_size, STEP_MINUTES)
        raw_df = pd.concat([raw_df, new_rows], ignore_index=True)

        full_df = retrain_cycle(raw_df.copy(), frozen_healthy_end_idx, et, ALARM_COLUMNS)
        full_df.to_csv(LIVE_OUTPUT_PATH, index=False)

        current = full_df.iloc[-1]
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] {len(full_df)} snapshots - "
            f"health={current['health_score']:.0f} - alarm={current['alarm_level']} - "
            f"{current['alarm_reason']}"
        )


if __name__ == "__main__":
    main()

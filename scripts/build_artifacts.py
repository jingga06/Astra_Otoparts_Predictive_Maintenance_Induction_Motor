"""Precompute pipeline: raw NASA IMS files -> cached feature/HI/RUL tables.

Usage (from src/):
    python -m scripts.build_artifacts --all

Produces, per (run, bearing):
    artifacts/<run>_bearing<n>.csv        - full annotated time series
    artifacts/<run>_bearing<n>_models.joblib - fitted scaler/IsolationForest/PCA

Also prints a summary table (lead time, false-alarm episode counts,
RUL RMSE) so results can be sanity-checked against docs/Proposal_Final_Case2.docx.
"""

import argparse
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from pdm import alarm, anomaly, health_index, rul
from pdm.bearing_physics import fault_frequencies
from pdm.data_loader import RUN_SPECS, list_snapshots, load_channel, FS_HZ
from pdm.features import extract_features

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts"
FAULT_FREQS = fault_frequencies()


def build_feature_table(run_key: str, bearing_id: int, log_every: int = 100) -> pd.DataFrame:
    snap_df = list_snapshots(run_key)
    n = len(snap_df)
    print(f"[{run_key} bearing {bearing_id}] extracting features for {n} snapshots...")
    t0 = time.time()
    rows = []
    for i, filepath in enumerate(snap_df["filepath"]):
        x = load_channel(filepath, bearing_id)
        feats = extract_features(x, FS_HZ, FAULT_FREQS)
        rows.append(feats)
        if (i + 1) % log_every == 0 or (i + 1) == n:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (n - i - 1) / rate if rate > 0 else float("nan")
            print(f"  {i + 1}/{n}  ({rate:.1f} files/s, ETA {eta / 60:.1f} min)")
    feat_df = pd.DataFrame(rows)
    out = pd.concat([snap_df.reset_index(drop=True), feat_df], axis=1)
    return out


def process_bearing(run_key: str, bearing_id: int) -> dict:
    df = build_feature_table(run_key, bearing_id)

    anomaly_model = anomaly.fit(df)
    df = anomaly.annotate(df, anomaly_model)

    hi_model = health_index.fit(df, anomaly_model.healthy_end_idx)
    df = health_index.annotate(df, hi_model)

    df = alarm.evaluate(df, anomaly_model.healthy_end_idx)

    return {
        "run_key": run_key,
        "bearing_id": bearing_id,
        "df": df,
        "anomaly_model": anomaly_model,
        "hi_model": hi_model,
        "healthy_end_idx": anomaly_model.healthy_end_idx,
    }


def attach_rul(result: dict, et: float) -> dict:
    df = result["df"]
    # RUL is fit on hi_norm ("sigma above this run's own healthy baseline"),
    # not raw hi_smoothed - each bearing/run has its own independently-fit
    # PCA scale, so a cross-run ET only makes sense once both runs are put
    # on a comparable, healthy-baseline-relative scale (see health_index.py).
    rul_res = rul.compute(df, df["is_alarm"], df["hi_norm"].to_numpy(), et)
    df = rul.annotate(df, rul_res)
    result["df"] = df
    result["rul_result"] = rul_res
    return result


def save_result(result: dict) -> None:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    run_key, bearing_id = result["run_key"], result["bearing_id"]
    stem = f"{run_key}_bearing{bearing_id}"
    result["df"].to_csv(ARTIFACTS_DIR / f"{stem}.csv", index=False)
    joblib.dump(
        {
            "anomaly_model": result["anomaly_model"],
            "hi_model": result["hi_model"],
            "healthy_end_idx": result["healthy_end_idx"],
            "rul_result": result.get("rul_result"),
        },
        ARTIFACTS_DIR / f"{stem}_models.joblib",
    )
    print(f"  saved artifacts/{stem}.csv (+ models.joblib)")


def summarize(result: dict) -> dict:
    df = result["df"]
    n = len(df)
    lead_time_h = None
    tidx = result["rul_result"].trigger_idx if result.get("rul_result") else None
    if tidx is not None:
        lead_time_h = float(df["elapsed_hours"].iloc[-1] - df["elapsed_hours"].iloc[tidx])

    baseline_episodes = alarm.count_episodes(df["baseline_alarm"])
    final_episodes = alarm.count_episodes(df["is_alarm"])

    rmse = None
    tail_n = max(1, int(n * 0.10))
    tail = df.iloc[-tail_n:]
    true_remaining = df["elapsed_hours"].iloc[-1] - tail["elapsed_hours"]
    pred = tail["rul_hours"]
    valid = pred.notna()
    if valid.sum() > 0:
        rmse = float(np.sqrt(np.mean((pred[valid] - true_remaining[valid]) ** 2)))

    return {
        "run": result["run_key"],
        "bearing": result["bearing_id"],
        "run_length_h": round(float(df["elapsed_hours"].iloc[-1]), 1),
        "lead_time_h": round(lead_time_h, 1) if lead_time_h is not None else None,
        "baseline_alarm_episodes": baseline_episodes,
        "final_alarm_episodes": final_episodes,
        "rul_rmse_last10pct_h": round(rmse, 2) if rmse is not None else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="process all runs/bearings")
    args = parser.parse_args()

    print("Bearing fault frequencies (sanity check vs Laporan Progres):")
    for name, freq in FAULT_FREQS.items():
        print(f"  {name}: {freq:.1f} Hz")
    print()

    results = {}
    for run_key, spec in RUN_SPECS.items():
        for bearing_id in range(1, spec.n_bearings + 1):
            results[(run_key, bearing_id)] = process_bearing(run_key, bearing_id)

    # Cross-run failure threshold: each run's ET comes from the OTHER run's
    # failing-bearing Health Index at end-of-life (no self-leakage).
    et_source = {}
    for run_key, spec in RUN_SPECS.items():
        failing = results[(run_key, spec.failing_bearing)]
        et_source[run_key] = failing["df"]["hi_norm"].to_numpy()

    run_keys = list(RUN_SPECS.keys())
    summaries = []
    for (run_key, bearing_id), result in results.items():
        other_run = [k for k in run_keys if k != run_key][0]
        et = rul.failure_threshold_from_other_run(et_source[other_run])
        result = attach_rul(result, et)
        save_result(result)
        summaries.append(summarize(result))

    print("\n=== Summary (compare against Proposal_Final_Case2.docx table) ===")
    summary_df = pd.DataFrame(summaries)
    print(summary_df.to_string(index=False))
    summary_df.to_csv(ARTIFACTS_DIR / "summary.csv", index=False)


if __name__ == "__main__":
    main()

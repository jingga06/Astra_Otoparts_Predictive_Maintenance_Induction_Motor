"""False-alarm reduction: persistence rule + multi-parameter voting.

Proposal sec.6.4 / "Bukti Metodologi: Cerita Holdout":
  - voting: alarm immediately if >= 2 features are abnormal at the same time
  - persistence: a single abnormal feature must hold for N consecutive
    windows before it counts as an alarm (debounce)
  - both burn-in and persistence window are SCALED TO RUN LENGTH
    (burn_in = 5% of run, persistence = 0.5% of run, floor 3) so the same
    logic works unmodified on a 164h run and a 1073h run.

Also emits a "baseline_alarm" column (any single feature over 3-sigma, no
persistence/voting) purely so the false-alarm-count comparison in the build
script can reproduce the "single-threshold vs persistence+voting" table.
"""

import numpy as np
import pandas as pd

from pdm.anomaly import FEATURE_COLUMNS, N_SIGMA

PERSISTENCE_FRACTION = 0.005
BURN_IN_FRACTION = 0.05
MIN_PERSISTENCE_WINDOWS = 3
VOTING_CONFIRM_WINDOWS = 2  # a voting trigger (>=2 features abnormal at once) must hold for
                             # this many consecutive windows before it counts as a real alarm -
                             # a single noisy row that coincidentally trips 2 correlated features
                             # for one snapshot is not evidence of a fault, and left unguarded it
                             # can fire the RUL trigger far too early (see Laporan Progres /
                             # troubleshooting notes: this is what caused an ~800h-early RUL
                             # trigger on the Test 3 holdout run, wrecking the exponential fit)


def _feature_zscores(df: pd.DataFrame, healthy_end_idx: int,
                      columns=FEATURE_COLUMNS) -> pd.DataFrame:
    healthy = df.iloc[:healthy_end_idx]
    z = pd.DataFrame(index=df.index)
    for col in columns:
        mu = healthy[col].mean()
        sigma = healthy[col].std()
        sigma = sigma if sigma > 1e-12 else 1e-12
        z[col] = (df[col] - mu) / sigma
    return z


def evaluate(df: pd.DataFrame, healthy_end_idx: int,
             columns=FEATURE_COLUMNS, n_sigma: float = N_SIGMA) -> pd.DataFrame:
    """Adds n_abnormal_features, baseline_alarm, is_alarm, alarm_level,
    alarm_reason columns."""
    out = df.copy()
    n = len(out)

    z = _feature_zscores(out, healthy_end_idx, columns)
    abnormal = z.abs() > n_sigma
    n_abnormal = abnormal.sum(axis=1).to_numpy()
    out["n_abnormal_features"] = n_abnormal
    out["baseline_alarm"] = n_abnormal >= 1  # single-threshold comparison baseline

    persistence_n = max(MIN_PERSISTENCE_WINDOWS, round(PERSISTENCE_FRACTION * n))
    burn_in = round(BURN_IN_FRACTION * n)
    # Recovery must be just as deliberate as triggering, otherwise a single
    # noisy "back to normal" row chops one real episode into several - this
    # sticky/hysteresis behaviour is what actually collapses many baseline
    # blips into a handful of persistence+voting episodes (Proposal sec.6.4).
    recovery_n = persistence_n

    levels = np.empty(n, dtype=object)
    reasons = np.empty(n, dtype=object)
    consecutive_abnormal = 0
    consecutive_normal = 0
    consecutive_voting = 0
    state = "NORMAL"

    for i in range(n):
        if i < burn_in:
            levels[i] = "NORMAL"
            reasons[i] = "Burn-in / baseline calibration period"
            consecutive_abnormal = 0
            consecutive_normal = 0
            consecutive_voting = 0
            state = "NORMAL"
            continue

        k = n_abnormal[i]
        if k >= 2:
            cols_abnormal = [c for c in columns if abnormal.iloc[i][c]]
            consecutive_voting += 1
            consecutive_normal = 0
            if consecutive_voting >= VOTING_CONFIRM_WINDOWS:
                consecutive_abnormal = persistence_n  # voting bypasses the persistence wait
                state = "CRITICAL"
                reasons[i] = (
                    f"Voting: {k} parameters abnormal for {consecutive_voting} consecutive "
                    f"windows ({', '.join(cols_abnormal)})"
                )
            else:
                reasons[i] = (
                    f"Voting building confirmation ({consecutive_voting}/{VOTING_CONFIRM_WINDOWS}): "
                    f"{k} parameters abnormal ({', '.join(cols_abnormal)})"
                )
                # state intentionally unchanged - a single noisy row hitting 2
                # correlated features shouldn't alone flip status
        elif k == 1:
            consecutive_abnormal += 1
            consecutive_normal = 0
            consecutive_voting = 0
            col_abnormal = [c for c in columns if abnormal.iloc[i][c]][0]
            if state == "CRITICAL":
                # Was in the strongest state; a single-feature reading now
                # doesn't clear it outright, downgrade to WARNING instead.
                state = "WARNING"
                reasons[i] = f"{col_abnormal} still abnormal (downgraded from voting alarm)"
            elif state == "WARNING" or consecutive_abnormal >= persistence_n:
                state = "WARNING"
                reasons[i] = (
                    f"Persistence: {col_abnormal} abnormal for "
                    f"{consecutive_abnormal} consecutive windows (>= {persistence_n})"
                )
            else:
                reasons[i] = f"Building persistence ({consecutive_abnormal}/{persistence_n})"
        else:
            consecutive_abnormal = 0
            consecutive_normal += 1
            consecutive_voting = 0
            if state != "NORMAL" and consecutive_normal < recovery_n:
                reasons[i] = (
                    f"Recovering - confirming normal ({consecutive_normal}/{recovery_n}) "
                    f"before clearing {state}"
                )
                # state unchanged: stay alarmed until recovery is confirmed
            else:
                state = "NORMAL"
                reasons[i] = "All parameters within normal range"

        levels[i] = state

    out["alarm_level"] = levels
    out["alarm_reason"] = reasons
    out["is_alarm"] = out["alarm_level"].isin(["WARNING", "CRITICAL"])
    return out


def count_episodes(is_alarm: pd.Series) -> int:
    """Count contiguous True runs (episodes) in a boolean series."""
    arr = is_alarm.to_numpy().astype(int)
    if len(arr) == 0:
        return 0
    diffs = np.diff(arr)
    starts = int(np.sum(diffs == 1)) + (1 if arr[0] == 1 else 0)
    return starts

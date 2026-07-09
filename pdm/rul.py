"""Branch B (part 2): Remaining Useful Life estimation.

Laporan Progres sec.6.3 / Proposal slide 9:
  - RUL is only computed after degradation has been triggered. Per the
    Blueprint's own rule ("skor anomali melewati control limit -> mulai
    hitung RUL"), the trigger/knee point IS the first persistence-confirmed
    alarm from alarm.evaluate() - reusing that event keeps the dashboard's
    alarm and RUL stories tied to the same detection, not two separate
    heuristics.
  - Post-knee: fit HI(t) = p1*exp(p2*t) + p3, refit as each new snapshot
    arrives (here: precomputed for the whole run so dashboard replay is
    instant).
  - Failure threshold ET is taken from ANOTHER run's observed HI at failure
    (cross-run transfer), never from the run's own future - avoids leakage
    and matches the proposal's "transferred across machines" framing.
  - EOL = (1/p2) * ln((ET - p3) / p1); RUL(t) = EOL - t.
  - Pre-knee, RUL is undefined ("monitoring, not stable yet").
"""

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

MIN_POINTS_FOR_FIT = 5
MAX_EXPONENT = 50.0  # clip guard: exp(50) ~ 5e21, plenty of headroom, never overflows
REFIT_STRIDE = 5      # only re-run curve_fit every N snapshots, hold params between
MAX_FIT_WINDOW = 400   # cap points passed to curve_fit (sliding window, not full history) -
                        # keeps each call's cost bounded on long holdout runs (Test 3: 6300+ rows)
MIN_GROWTH_FACTOR = 1.3  # the fitted exponential must grow >=30% across its own fit window,
                           # otherwise p2 is essentially unidentifiable (near-flat data lets
                           # least-squares wander to a tiny p2, which then blows EOL up to
                           # millions of "hours" when extrapolated - reject those, don't report
                           # a RUL number until the curve shows real, self-consistent curvature)
MAX_RUL_MULTIPLE = 20.0    # sanity ceiling: never report RUL beyond 20x the run's own elapsed
                            # time so far - anything past that is not an actionable maintenance
                            # number and should read as "not stable yet" instead


def _model(t, p1, p2, p3):
    exponent = np.clip(p2 * t, -MAX_EXPONENT, MAX_EXPONENT)
    return p1 * np.exp(exponent) + p3


def trigger_index(is_alarm: pd.Series):
    """First persistence/voting-confirmed alarm index, or None if the run
    never alarms (healthy bearing)."""
    idx = np.flatnonzero(is_alarm.to_numpy())
    return int(idx[0]) if len(idx) else None


def failure_threshold_from_other_run(other_hi_smoothed: np.ndarray, tail: int = 5) -> float:
    """ET = mean Health Index over the last `tail` snapshots of another
    run's failure (that run's own end-of-life value)."""
    return float(np.mean(other_hi_smoothed[-tail:]))


@dataclass
class RulResult:
    trigger_idx: int | None
    et: float
    rul_hours: np.ndarray       # NaN where undefined
    fitted_hi: np.ndarray        # NaN where undefined; the exponential curve itself


def compute(df: pd.DataFrame, is_alarm: pd.Series, hi_smoothed: np.ndarray,
            et: float) -> RulResult:
    n = len(df)
    t = df["elapsed_hours"].to_numpy()
    rul_hours = np.full(n, np.nan)
    fitted_hi = np.full(n, np.nan)

    tidx = trigger_index(is_alarm)
    if tidx is None:
        return RulResult(trigger_idx=None, et=et, rul_hours=rul_hours, fitted_hi=fitted_hi)

    t0 = t[tidx]
    p0 = None
    last_good = None
    for i in range(tidx, n):
        n_points = i - tidx + 1
        if n_points < MIN_POINTS_FOR_FIT:
            continue

        due_for_refit = last_good is None or (i - tidx) % REFIT_STRIDE == 0 or i == n - 1
        tau_i = t[i] - t0

        if due_for_refit:
            # Sliding window (most recent MAX_FIT_WINDOW points), not full
            # history since knee - bounds per-call cost on long holdout runs
            # while still weighting the current degradation regime more.
            win_start = max(tidx, i - MAX_FIT_WINDOW + 1)
            tau_win = t[win_start:i + 1] - t0
            hi_win = hi_smoothed[win_start:i + 1]

            # Cheap pre-filter: skip the expensive curve_fit entirely unless
            # this window shows a real positive trend. A flat/noisy window
            # (e.g. a false-triggered healthy bearing) would otherwise force
            # curve_fit to grind through its full iteration budget hunting
            # for curvature that isn't there - correlation is ~1000x cheaper
            # and rejects those windows outright.
            trend = np.corrcoef(tau_win, hi_win)[0, 1] if np.std(hi_win) > 1e-9 else 0.0

            if trend >= 0.3:
                if p0 is None:
                    span = max(hi_win[-1] - hi_win[0], 1e-6)
                    duration = max(tau_win[-1] - tau_win[0], 1e-3)
                    p0 = (max(span, 1e-3), 1.0 / duration, hi_win[0])

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        fit_result, _ = curve_fit(
                            _model, tau_win, hi_win, p0=p0,
                            maxfev=800,
                            bounds=([0, 1e-6, -np.inf], [np.inf, 5.0, np.inf]),
                        )
                        if np.all(np.isfinite(fit_result)):
                            # Always warm-start from the latest convergent
                            # fit, even a rejected one - otherwise p0 goes
                            # stale and curve_fit has to search much harder
                            # from an increasingly wrong starting point.
                            p0 = tuple(fit_result)

                            fit_p1, fit_p2, _ = fit_result
                            window_duration = tau_win[-1] - tau_win[0]
                            growth_factor = np.exp(np.clip(fit_p2 * window_duration, -50, 50))
                            # Only REPORT fits where the curve visibly moves
                            # across its own window - p2 is otherwise
                            # unidentifiable and extrapolating it (1/p2 in
                            # the EOL formula) explodes to a meaningless value.
                            if growth_factor >= MIN_GROWTH_FACTOR:
                                last_good = fit_result
                    except Exception:
                        pass  # keep last_good; try again next refit

        if last_good is None:
            continue

        p1, p2, p3 = last_good
        fitted_hi[i] = _model(tau_i, p1, p2, p3)

        arg = (et - p3) / p1
        if arg > 0 and p2 > 0:
            eol_tau = (1.0 / p2) * np.log(arg)
            rul = eol_tau - tau_i
            elapsed_since_trigger = max(tau_i, 1.0)
            if 0 < rul <= MAX_RUL_MULTIPLE * elapsed_since_trigger:
                rul_hours[i] = rul
            elif rul <= 0:
                rul_hours[i] = 0.0
            # else: leave NaN - "not stable enough to give an actionable number"

    return RulResult(trigger_idx=tidx, et=et, rul_hours=rul_hours, fitted_hi=fitted_hi)


def annotate(df: pd.DataFrame, rul_result: RulResult) -> pd.DataFrame:
    """Adds rul_hours (display-smoothed), rul_hours_raw, hi_fitted, rul_status.

    The exponential refit can wobble point-to-point on noisy/oscillating
    degradation (the proposal's own §Transparency flags this as a known
    single-exponential limitation) - a short rolling median removes that
    single-point jitter for display without changing the underlying fit.
    """
    out = df.copy()
    raw = pd.Series(rul_result.rul_hours)
    # Trailing (not centered) window: a live replay must never smooth using
    # future snapshots it wouldn't have seen yet.
    smoothed = raw.rolling(5, min_periods=1).median()
    smoothed[raw.isna()] = np.nan

    out["rul_hours_raw"] = raw.to_numpy()
    out["rul_hours"] = smoothed.to_numpy()
    out["hi_fitted"] = rul_result.fitted_hi
    out["rul_status"] = np.where(
        np.isnan(rul_result.rul_hours), "monitoring_not_stable", "estimated"
    )
    return out

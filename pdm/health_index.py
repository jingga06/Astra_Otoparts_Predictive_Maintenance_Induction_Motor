"""Branch B (part 1): PCA-based Health Index.

Laporan Progres sec.6.2: features that pass a monotonicity check are fused
with PCA; the first principal component becomes a one-dimensional Health
Index, smoothed with EWMA, then scaled to a 0-100 score for the dashboard.
"PCA over hand-picked weights" because PCA derives the contribution of each
feature from the data itself (Proposal slide 8).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from pdm.anomaly import FEATURE_COLUMNS, EWMA_ALPHA

MONOTONICITY_THRESHOLD = 0.5  # |spearman r| vs elapsed_hours


@dataclass
class HealthIndexModel:
    selected_columns: list
    scaler: StandardScaler
    pca: PCA
    sign: float
    healthy_baseline: float
    healthy_std: float
    worst_observed: float

    def transform_raw(self, df: pd.DataFrame) -> np.ndarray:
        X = self.scaler.transform(df[self.selected_columns].to_numpy())
        pc1 = self.pca.transform(X)[:, 0]
        return self.sign * pc1


def select_monotonic_features(df: pd.DataFrame, candidates=FEATURE_COLUMNS,
                               threshold: float = MONOTONICITY_THRESHOLD) -> list:
    selected = []
    for col in candidates:
        r, _ = spearmanr(df[col].to_numpy(), df["elapsed_hours"].to_numpy())
        if abs(r) >= threshold:
            selected.append(col)
    if not selected:
        # Fallback: keep the single strongest feature so the pipeline never dies.
        corrs = {
            col: abs(spearmanr(df[col].to_numpy(), df["elapsed_hours"].to_numpy())[0])
            for col in candidates
        }
        selected = [max(corrs, key=corrs.get)]
    return selected


def fit(df: pd.DataFrame, healthy_end_idx: int) -> HealthIndexModel:
    selected = select_monotonic_features(df)
    healthy_df = df.iloc[:healthy_end_idx]

    scaler = StandardScaler()
    X_healthy = scaler.fit_transform(healthy_df[selected].to_numpy())

    pca = PCA(n_components=1, random_state=42)
    pca.fit(X_healthy)

    # Orient sign so the health index increases with elapsed time (degradation).
    X_full = scaler.transform(df[selected].to_numpy())
    pc1_full = pca.transform(X_full)[:, 0]
    r, _ = spearmanr(pc1_full, df["elapsed_hours"].to_numpy())
    sign = 1.0 if r >= 0 else -1.0

    raw_full = sign * pc1_full
    healthy_baseline = float(np.mean(raw_full[:healthy_end_idx]))
    healthy_std = float(np.std(raw_full[:healthy_end_idx]))
    # Anchor "worst" to this run's own end-of-life value (last few snapshots),
    # not the global max - a mid-run transient spike shouldn't saturate the
    # 0-100 scale and cause a misleading late-run "recovery" in the score.
    # Floored at a multiple of healthy noise so a bearing that never
    # degrades (tail stays near baseline) doesn't get a near-zero span,
    # which would make its health score hypersensitive to plain noise.
    tail_worst = float(np.mean(raw_full[-5:]))
    worst_observed = max(tail_worst, healthy_baseline + 6.0 * max(healthy_std, 1e-9))

    return HealthIndexModel(
        selected_columns=selected,
        scaler=scaler,
        pca=pca,
        sign=sign,
        healthy_baseline=healthy_baseline,
        healthy_std=max(healthy_std, 1e-9),
        worst_observed=worst_observed,
    )


def annotate(df: pd.DataFrame, hi_model: HealthIndexModel) -> pd.DataFrame:
    """Adds hi_raw, hi_smoothed, hi_norm, health_score (0-100, 100=healthiest) columns.

    hi_smoothed is on an arbitrary per-bearing PCA scale (each bearing/run
    fits its own PCA independently, so raw units are NOT comparable across
    runs). hi_norm re-expresses it in "standard deviations above this run's
    OWN healthy baseline" - a scale that IS comparable across runs using
    only backward-looking healthy-period statistics (no future leakage) -
    this is what the cross-run RUL failure threshold (ET) is defined on.
    health_score (0-100) stays a separate, purely-for-display normalization.
    """
    out = df.copy()
    raw = hi_model.transform_raw(df)
    smoothed = pd.Series(raw).ewm(alpha=EWMA_ALPHA, adjust=False).mean().to_numpy()
    out["hi_raw"] = raw
    out["hi_smoothed"] = smoothed
    out["hi_norm"] = (smoothed - hi_model.healthy_baseline) / hi_model.healthy_std

    span = max(hi_model.worst_observed - hi_model.healthy_baseline, 1e-9)
    normalized_bad = (smoothed - hi_model.healthy_baseline) / span
    out["health_score"] = 100.0 * np.clip(1.0 - normalized_bad, 0.0, 1.0)
    return out

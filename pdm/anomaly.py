"""Branch A: unsupervised anomaly detection.

Isolation Forest trained ONLY on the healthy portion of a run (Laporan
Progres sec.6.1 / Blueprint: "latih HANYA data sehat"). Alarm threshold is
statistical (healthy-score mean + 3*std), not an arbitrary number - this is
the literal "3 standard deviation" rule Miss already approved.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

FEATURE_COLUMNS = [
    "rms", "kurtosis", "crest_factor", "bpfo_energy", "bpfi_energy", "bsf_energy",
]
HEALTHY_FRACTION = 0.5   # first 50% of the run = healthy baseline (Blueprint: 60-70%, we use a
                          # conservative 50% cut so the model never sees degrading data)
EWMA_ALPHA = 0.2
N_SIGMA = 3.0


@dataclass
class AnomalyModel:
    scaler: StandardScaler
    model: IsolationForest
    healthy_score_mean: float
    healthy_score_std: float
    threshold: float
    healthy_end_idx: int

    def score(self, df: pd.DataFrame) -> np.ndarray:
        X = self.scaler.transform(df[FEATURE_COLUMNS].to_numpy())
        # score_samples: higher = more normal. Flip so higher = more anomalous.
        return -self.model.score_samples(X)


def fit(df: pd.DataFrame, healthy_fraction: float = HEALTHY_FRACTION,
        random_state: int = 42) -> AnomalyModel:
    n = len(df)
    healthy_end_idx = max(20, int(n * healthy_fraction))
    healthy_df = df.iloc[:healthy_end_idx]

    scaler = StandardScaler()
    X_healthy = scaler.fit_transform(healthy_df[FEATURE_COLUMNS].to_numpy())

    model = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=random_state,
    )
    model.fit(X_healthy)

    healthy_scores = -model.score_samples(X_healthy)
    mean, std = float(np.mean(healthy_scores)), float(np.std(healthy_scores))
    threshold = mean + N_SIGMA * std

    return AnomalyModel(
        scaler=scaler,
        model=model,
        healthy_score_mean=mean,
        healthy_score_std=std,
        threshold=threshold,
        healthy_end_idx=healthy_end_idx,
    )


def smooth(scores: np.ndarray, alpha: float = EWMA_ALPHA) -> np.ndarray:
    return pd.Series(scores).ewm(alpha=alpha, adjust=False).mean().to_numpy()


def annotate(df: pd.DataFrame, anomaly_model: AnomalyModel) -> pd.DataFrame:
    """Adds anomaly_score_raw, anomaly_score, is_anomaly columns."""
    out = df.copy()
    raw = anomaly_model.score(df)
    out["anomaly_score_raw"] = raw
    out["anomaly_score"] = smooth(raw)
    out["is_anomaly"] = out["anomaly_score"] > anomaly_model.threshold
    return out

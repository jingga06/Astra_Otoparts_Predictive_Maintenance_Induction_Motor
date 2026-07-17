"""Discovery and reading of raw NASA IMS Bearing snapshot files.

Dataset layout (see docs/Readme Document for IMS Bearing Data.pdf):
- Each file = one 1-second vibration snapshot, 20480 points @ 20 kHz.
- Test 2 and Test 3 both have 4 channels, one per bearing (bearing N -> column N-1).
- Filenames are timestamps: "YYYY.MM.DD.HH.MM.SS".

Only Test 2 and Test 3 are wired up here (see plan: Test 1 has a different
8-channel layout and different fault types, out of scope for this prototype).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"

FS_HZ = 20000
SNAPSHOT_LEN = 20480


@dataclass(frozen=True)
class RunSpec:
    key: str            # e.g. "test2"
    label: str           # human label
    folder: str           # data/<folder>
    n_bearings: int
    failing_bearing: int
    failure_mode: str


RUN_SPECS = {
    "test2": RunSpec(
        key="test2",
        label="Test 2 (dev run)",
        folder="2nd_test",
        n_bearings=4,
        failing_bearing=1,
        failure_mode="outer_race",
    ),
    "test3": RunSpec(
        key="test3",
        label="Test 3 (holdout run)",
        folder="3rd_test",
        n_bearings=4,
        failing_bearing=3,
        failure_mode="outer_race",
    ),
}


def _parse_timestamp(filename: str) -> datetime:
    return datetime.strptime(filename, "%Y.%m.%d.%H.%M.%S")


def list_snapshots(run_key: str) -> pd.DataFrame:
    """Return a timestamp-sorted table of snapshot files for a run.

    Columns: timestamp, filepath, elapsed_hours (since first snapshot).
    """
    spec = RUN_SPECS[run_key]
    run_dir = DATA_ROOT / spec.folder
    files = [p for p in run_dir.iterdir() if p.is_file()]
    rows = []
    for p in files:
        try:
            ts = _parse_timestamp(p.name)
        except ValueError:
            continue
        rows.append((ts, p))
    rows.sort(key=lambda r: r[0])
    if not rows:
        raise FileNotFoundError(f"No snapshot files found under {run_dir}")
    t0 = rows[0][0]
    df = pd.DataFrame(
        {
            "timestamp": [r[0] for r in rows],
            "filepath": [str(r[1]) for r in rows],
        }
    )
    df["elapsed_hours"] = (df["timestamp"] - t0).dt.total_seconds() / 3600.0
    return df


def load_channel(filepath: str, bearing_id: int) -> np.ndarray:
    """Read one snapshot file and return the 1-D signal for a given bearing (1-indexed)."""
    data = np.loadtxt(filepath, dtype=np.float32)
    col = bearing_id - 1
    if data.ndim == 1:
        # Defensive: single-channel file
        return data
    return data[:, col]

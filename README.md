# SentinelPM - Predictive Maintenance for Induction Motor Bearings

Case 2 · Bootcamp AOP Winteq · PT Astra Otoparts Tbk

SentinelPM continuously monitors induction motor bearings and detects early
signs of degradation, before an actual failure occurs, using vibration,
temperature, and current data. It combines an Isolation Forest anomaly
detector with a PCA-based Health Index, a persistence-and-voting alarm rule,
and an exponential Remaining Useful Life (RUL) estimator.

See [`SentinelPM_Report.docx`](./SentinelPM_Report.docx) for full technical
documentation, architecture, methodology, validation results, and honestly
disclosed limitations.

**Dataset:** [NASA IMS Bearing Dataset](https://data.nasa.gov/dataset/ims-bearings)

---

## Why this matters

Bearings account for roughly 41-42% of induction motor failures (IEEE-IAS /
EPRI). Most plants only react once a fault is already obvious, by then,
there's little room to schedule maintenance without disrupting production.
SentinelPM is built to catch degradation early enough that maintenance
becomes a scheduling decision instead of an emergency, while keeping false
alarms low enough that technicians still trust the alerts they see.

---

## How it works

1. **Feature extraction** - raw vibration signals are summarized into
   time-domain features (RMS, kurtosis, crest factor) and physics-based
   fault frequencies (BPFO, BPFI, BSF), calculated directly from bearing
   geometry, not guessed.
2. **Anomaly detection** - an Isolation Forest, trained only on healthy
   data, flags abnormal vibration patterns.
3. **Health Index (PCA)** - six degradation-sensitive features are combined
   into a single 0–100 health score.
4. **Alarm logic** - a persistence + voting rule across vibration,
   temperature, and current avoids false alarms from momentary noise.
5. **RUL estimation** - once an alarm fires, an exponential degradation
   curve projects the remaining useful life, with the failure threshold
   honestly borrowed from a separate holdout recording (no peeking at the
   future).
6. **Dashboard** - a bilingual (ID) Streamlit dashboard for fleet overview,
   per-machine detail, trend charts, and a live simulation mode.

Full methodology and equations are in `SentinelPM_Report.docx`.

---

## Results

- Validated on an honest train/holdout split (Test 2 to build, Test 3 never
  touched until the system was finished).
- Outer-race fault location physically confirmed, envelope spectrum shows
  a sharp peak exactly at the calculated BPFO frequency (236.4 Hz).
- Reduced alarm noise from dozens of false-positive episodes down to a
  handful, compared to a naive single-threshold approach.
- Live Simulation mode proven to ingest continuously growing data and
  retrain itself automatically, without manual intervention.

Known limitations (data is currently the public NASA dataset, not real
Astra sensor data; RUL accuracy drops for non-monotonic degradation
patterns) are disclosed in full in the report rather than glossed over.

---

## 1. Requirements

- Python 3.10 or newer (developed/tested on Python 3.13)
- pip

Install dependencies:

```bash
pip install -r requirements.txt
```

(If `requirements.txt` doesn't fully match your environment, regenerate it
from your working virtual environment with `pip freeze > requirements.txt`.)

---

## 2. Project Structure (expected)

```
.
├── app/
│   ├── dashboard.py          # Streamlit dashboard entry point
│   └── theme.py              # Visual styling / theme
├── pdm/
│   ├── features.py           # Vibration feature extraction
│   ├── health_index.py       # PCA-based Health Score
│   ├── anomaly.py            # Isolation Forest + 3-sigma threshold
│   ├── alarm.py               # Persistence + voting alarm logic
│   ├── rul.py                # Remaining Useful Life estimation
│   ├── synthetic_sensors.py  # Temperature/current synthesis
│   ├── bearing_physics.py    # Fault-frequency calculations (BPFO/BPFI/BSF/FTF)
│   ├── data_loader.py        # Dataset loading utilities
│   └── live_simulator.py     # Live Simulation data generator + retrain loop
├── scripts/
│   ├── build_artifacts.py    # Rebuilds all processed data + trained models
│   └── run_live_simulation.py# Standalone Live Simulation process
├── artifacts/                # Generated CSVs, trained models (.joblib), summary.csv
├── data/                     # Raw NASA IMS Bearing dataset (1st_test/2nd_test/3rd_test)
├── requirements.txt
└── README.md
```

---

## 3. First-Time Setup: Build the Artifacts

Before the dashboard can display anything, the processed data and trained
models need to be built once from the raw dataset:

```bash
python -m scripts.build_artifacts --all
```

This reads the raw NASA IMS Bearing data (`data/1st_test`, `data/2nd_test`,
`data/3rd_test`), computes vibration features, trains the Isolation Forest
and Health Index models per bearing, evaluates the alarm logic, fits RUL
curves, and writes the results to `artifacts/` (per-bearing CSVs, `.joblib`
model files, and `summary.csv`).

> If `artifacts/*.csv` and `*.joblib` files are already included in this
> submission, you can skip this step and go straight to Section 4, unless
> you want to verify the pipeline reproduces the same results from scratch.

---

## 4. Running the Dashboard

```bash
streamlit run app/dashboard.py
```

This opens the dashboard in your default browser (typically at
`http://localhost:8501`). From the sidebar, you can switch between:

- **Ringkasan Armada** (Fleet Overview) - status of all 8 bearings at once
- **Detail Mesin** (Machine Detail) - Health Score, Alarm Status, RUL, and the
  Trend / Signal Detail / Sensors / Alerts & Recommendation tabs for a single
  bearing
- **Live Simulation** - see Section 5 below; this page only shows live
  progress if the simulator (Section 5) has been started separately

---

## 5. Running the Live Simulation (optional, for the "Live Simulation" page)

The Live Simulation page reads from a file that is continuously updated by a
**separate, standalone process**, it does not run automatically when you
start the dashboard. To see it in action:

1. Open a **second terminal** (keep the dashboard running in the first one).
2. Run:

   ```bash
   python -m scripts.run_live_simulation
   ```

3. Let it run for a few minutes before opening the "Live Simulation" page in
   the dashboard, so there's visible progress (new snapshots, retrained
   model, and eventually an escalating alarm) to show.
4. Stop it anytime with `Ctrl+C`. It runs as an infinite loop until stopped.

**Optional flag:** `python -m scripts.run_live_simulation --real-time` uses
the literal cadence of ~60 data points per 30 minutes instead of the
accelerated demo cadence (~10 data points every ~15 seconds).

**To restart the simulation from a clean "Normal" state:** delete
`artifacts/live_bearing.csv` before starting `run_live_simulation.py` again, otherwise it will continue from wherever the last run left off (which may
already be at "Critical").

---

## 6. Troubleshooting

- **No sound on the Critical Alert banner:** modern browsers block
  autoplaying audio until the user has clicked anywhere on the page at least
  once. Click anywhere on the dashboard once, and the next alarm sound will
  play normally. This is a browser security restriction, not a bug.
- **Live Simulation page shows no data / stale timestamp:** make sure
  `scripts.run_live_simulation` is actually running in a separate terminal, the dashboard only reads the file it produces and does not generate data
  on its own.
- **Import errors on startup:** double-check you're running commands from
  the project's root folder (so `pdm` and `app` are importable as packages),
  and that `pip install -r requirements.txt` completed without errors.

---

## 7. Notes on Data Honesty

- **Vibration** is the only real sensor data, from the public NASA IMS
  Bearing Dataset (Rexnord ZA-2115 bearings, 2000 RPM).
- **Temperature and current** are synthetically generated from the same
  vibration-based health index (time lag + noise) — see
  `pdm/synthetic_sensors.py` and `SentinelPM_Report.docx` for full rationale.
- The **Live Simulation** page demonstrates the retraining *mechanism*, not
  a live connection to physical Astra sensors.

---

## Team — Famasya

President University · Information Systems, Data Science Concentration

| Name | 
|---|
| Fatwa Putri Jingga |
| Marsha Aulia Rizky |
| Syakira Lathifa Awliya |

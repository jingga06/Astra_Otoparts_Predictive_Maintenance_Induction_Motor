"""Generates illustrative PNG charts (from real cached pipeline output) for
the mega user guide docx. These mirror what the live Streamlit dashboard
shows, since we cannot screenshot a running browser session directly.

Run: python -m scripts.generate_guide_assets   (from src/)
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pdm.bearing_physics import fault_frequencies
from pdm.data_loader import load_channel, FS_HZ
from pdm.features import envelope_spectrum

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
ASSETS = Path(__file__).resolve().parents[2] / "docs" / "assets"
ASSETS.mkdir(exist_ok=True, parents=True)

NAVY = "#0F172A"
BLUE = "#0369A1"
GREY = "#64748B"
RED = "#DC2626"
AMBER = "#D97706"
GREEN = "#16A34A"
BG = "#F8FAFC"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.edgecolor": "#CBD5E1",
    "axes.labelcolor": NAVY,
    "text.color": NAVY,
    "xtick.color": GREY,
    "ytick.color": GREY,
    "axes.facecolor": "white",
    "figure.facecolor": "white",
})

df = pd.read_csv(ARTIFACTS / "test2_bearing1.csv")
trigger_idx = int(np.flatnonzero(df["is_alarm"].to_numpy())[0])
FAULT_FREQS = fault_frequencies()


def savefig(fig, name, dpi=160):
    path = ASSETS / name
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", path)


# ------------------------------------------------------------------ 1. Health score trend
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(df["elapsed_hours"], df["health_score"], color=BLUE, linewidth=1.8, label="Health Score")
alarm_mask = df["is_alarm"]
ax.scatter(df.loc[alarm_mask, "elapsed_hours"], df.loc[alarm_mask, "health_score"],
           color=RED, s=8, zorder=5, label="Alarm aktif")
ax.axvline(df["elapsed_hours"].iloc[trigger_idx], color=AMBER, linestyle="--", linewidth=1.3,
           label="Trigger pertama (mulai hitung RUL)")
ax.set_xlabel("Waktu berjalan (jam)")
ax.set_ylabel("Health Score (0-100)")
ax.set_ylim(-5, 105)
ax.set_title("Contoh isi Tab \"Trend\" - grafik kiri: Health Score", color=NAVY, fontweight="bold")
ax.legend(loc="lower left", fontsize=8, frameon=False)
ax.grid(alpha=0.25)
savefig(fig, "01_health_score_trend.png")

# ------------------------------------------------------------------ 2. Anomaly score vs threshold
healthy_end = int(len(df) * 0.5)
# reconstruct an approximate threshold display line (mean+3std of anomaly score on healthy part)
thr = df["anomaly_score"].iloc[:healthy_end].mean() + 3 * df["anomaly_score"].iloc[:healthy_end].std()
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(df["elapsed_hours"], df["anomaly_score"], color=GREY, linewidth=1.5, label="Anomaly score")
ax.axhline(thr, color=RED, linestyle="--", linewidth=1.3, label="Ambang 3-sigma")
ax.axvline(df["elapsed_hours"].iloc[trigger_idx], color=AMBER, linestyle="--", linewidth=1.3)
ax.fill_between(df["elapsed_hours"], thr, df["anomaly_score"].max() * 1.05,
                 color=RED, alpha=0.05)
ax.set_xlabel("Waktu berjalan (jam)")
ax.set_ylabel("Skor anomali (makin tinggi makin buruk)")
ax.set_title("Contoh isi Tab \"Trend\" - grafik kanan: Anomaly score vs ambang 3-sigma",
              color=NAVY, fontweight="bold")
ax.legend(loc="upper left", fontsize=8, frameon=False)
ax.grid(alpha=0.25)
savefig(fig, "02_anomaly_vs_threshold.png")

# ------------------------------------------------------------------ 3. Raw vibration: healthy vs late
x_healthy = load_channel(df["filepath"].iloc[10], 1)
x_late = load_channel(df["filepath"].iloc[len(df) - 5], 1)
fig, axes = plt.subplots(1, 2, figsize=(10, 3.5), sharey=False)
t_ms = np.arange(2000) / FS_HZ * 1000
axes[0].plot(t_ms, x_healthy[:2000], color=GREEN, linewidth=0.6)
axes[0].set_title("Saat SEHAT (jam ke-%.1f)" % df["elapsed_hours"].iloc[10], color=NAVY, fontsize=10)
axes[0].set_xlabel("Waktu (ms)")
axes[0].set_ylabel("Getaran (g)")
axes[0].set_ylim(-1, 1)
axes[1].plot(t_ms, x_late[:2000], color=RED, linewidth=0.6)
axes[1].set_title("MENJELANG GAGAL (jam ke-%.1f)" % df["elapsed_hours"].iloc[len(df) - 5],
                   color=NAVY, fontsize=10)
axes[1].set_xlabel("Waktu (ms)")
axes[1].set_ylim(-1, 1)
fig.suptitle("Contoh isi Tab \"Signal Detail\" - grafik kiri: sinyal getaran mentah",
             color=NAVY, fontweight="bold")
for ax in axes:
    ax.grid(alpha=0.25)
fig.tight_layout()
savefig(fig, "03_raw_vibration_compare.png")

# ------------------------------------------------------------------ 4. Envelope spectrum
freqs, spec_late = envelope_spectrum(x_late, FS_HZ)
_, spec_healthy = envelope_spectrum(x_healthy, FS_HZ)
mask = freqs <= 500
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(freqs[mask], spec_healthy[mask], color=GREEN, linewidth=1, label="Saat sehat", alpha=0.8)
ax.plot(freqs[mask], spec_late[mask], color=NAVY, linewidth=1.3, label="Menjelang gagal")
for label, f in FAULT_FREQS.items():
    if f <= 500:
        ax.axvline(f, color=RED, linestyle=":", linewidth=1)
        ax.text(f, ax.get_ylim()[1] * 0.92, label, color=RED, fontsize=8, ha="center")
ax.set_xlabel("Frekuensi (Hz)")
ax.set_ylabel("Magnitudo FFT selubung (envelope)")
ax.set_title("Contoh isi Tab \"Signal Detail\" - grafik kanan: Envelope spectrum",
              color=NAVY, fontweight="bold")
ax.legend(loc="upper right", fontsize=8, frameon=False)
ax.grid(alpha=0.25)
savefig(fig, "04_envelope_spectrum.png")

# ------------------------------------------------------------------ 5. Pipeline diagram (boxes + arrows)
fig, ax = plt.subplots(figsize=(10, 3.2))
ax.axis("off")
stages = [
    "Sinyal getaran\nmentah (20 kHz)",
    "Ekstraksi fitur\n(RMS, kurtosis,\nBPFO/BPFI/BSF)",
    "Deteksi anomali\n(Isolation Forest,\nambang 3-sigma)",
    "Alarm\n(persistence\n+ voting)",
]
stages_b = [
    "Health Index\n(PCA, skala 0-100)",
    "Estimasi RUL\n(fit eksponensial,\nsetelah trigger)",
]
x0 = 0.03
w = 0.19
gap = 0.045
colors_top = [BLUE, BLUE, NAVY, RED]
for i, (s, c) in enumerate(zip(stages, colors_top)):
    x = x0 + i * (w + gap)
    ax.add_patch(plt.Rectangle((x, 0.55), w, 0.35, facecolor=c, edgecolor="none"))
    ax.text(x + w / 2, 0.725, s, ha="center", va="center", color="white", fontsize=8.3, fontweight="bold")
    if i < len(stages) - 1:
        ax.annotate("", xy=(x + w + gap * 0.15, 0.725), xytext=(x + w, 0.725),
                     arrowprops=dict(arrowstyle="->", color=GREY, lw=1.4))
# branch B row
x_branch_start = x0 + 2 * (w + gap)
ax.annotate("", xy=(x_branch_start + w / 2, 0.5), xytext=(x_branch_start + w / 2, 0.55),
            arrowprops=dict(arrowstyle="-", color=GREY, lw=1.2, linestyle="dashed"))
for i, s in enumerate(stages_b):
    x = x_branch_start + i * (w + gap)
    ax.add_patch(plt.Rectangle((x, 0.08), w, 0.35, facecolor=GREEN, edgecolor="none"))
    ax.text(x + w / 2, 0.255, s, ha="center", va="center", color="white", fontsize=8.3, fontweight="bold")
    if i < len(stages_b) - 1:
        ax.annotate("", xy=(x + w + gap * 0.15, 0.255), xytext=(x + w, 0.255),
                     arrowprops=dict(arrowstyle="->", color=GREY, lw=1.4))
ax.text(x0 - 0.01, 0.725, "Cabang A:\nDeteksi", ha="right", va="center", fontsize=8, color=GREY, style="italic")
ax.text(x0 - 0.01, 0.255, "Cabang B:\nPrediksi", ha="right", va="center", fontsize=8, color=GREY, style="italic")
ax.set_xlim(-0.12, 1.02)
ax.set_ylim(0, 1)
ax.set_title("Alur Pipeline: Dua Cabang, Satu Cerita", color=NAVY, fontweight="bold", fontsize=12)
savefig(fig, "05_pipeline_diagram.png")

# ------------------------------------------------------------------ 6. KPI card mockup
fig, axes = plt.subplots(1, 3, figsize=(10, 2.6))
row_ex = df.iloc[trigger_idx]
kpi_data = [
    ("HEALTH SCORE", f"{row_ex['health_score']:.1f}", GREEN if row_ex['health_score'] > 70 else (AMBER if row_ex['health_score'] > 40 else RED)),
    ("ALARM STATUS", row_ex["alarm_level"], RED if row_ex["alarm_level"] == "CRITICAL" else (AMBER if row_ex["alarm_level"] == "WARNING" else GREEN)),
    ("REMAINING USEFUL LIFE", "Monitoring" if pd.isna(row_ex["rul_hours"]) else f"{row_ex['rul_hours']:.1f} jam", NAVY),
]
for ax, (label, value, color) in zip(axes, kpi_data):
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor="#E2E8F0", linewidth=1.5))
    ax.text(0.08, 0.78, label, fontsize=8, color=GREY, fontweight="bold")
    ax.text(0.08, 0.4, str(value), fontsize=20, color=color, fontweight="bold")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
fig.suptitle(f"Contoh 3 Kartu KPI (diambil di jam ke-{row_ex['elapsed_hours']:.1f}, saat trigger)",
             color=NAVY, fontweight="bold")
fig.tight_layout()
savefig(fig, "06_kpi_cards_mockup.png")

print("done - all assets generated in", ASSETS)

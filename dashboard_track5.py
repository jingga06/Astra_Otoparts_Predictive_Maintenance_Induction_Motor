"""
Track 5 - Dashboard Streamlit (Prototipe v2)
Case 2: Predictive Maintenance Motor Induksi - Bootcamp AOP Winteq
Jingga

Versi ini mengimplementasikan LOGIKA ASLI yang sudah dikunci tim (bukan lagi
placeholder sembarangan), mengacu ke Laporan Progres Case 2 (Regan):
- Bagian 6.4 Reduksi False Alarm -> persistence rule (debounce) + voting rule (multi-condition)
- Bagian 6.3 Estimasi RUL -> tren degradasi diproyeksikan ke depan sampai batas gagal
- Bagian 6.2 Health Index -> skor kesehatan gabungan dari beberapa parameter

CATATAN: Health Score di sini masih HEURISTIK SEDERHANA (bukan output model
Marsha yang sebenarnya/LSTM Autoencoder), karena model asli belum di-share ke
Track 5. Begitu Marsha kasih fungsi/hasil modelnya, tinggal ganti fungsi
`hitung_health_score()` di bawah dengan pemanggilan model asli - struktur
alarm & RUL di bawahnya TIDAK perlu diubah karena dia cuma butuh angka
Health Score sebagai input, tidak peduli dari mana asalnya.

CARA JALANIN:
    pip install streamlit pandas numpy
    streamlit run dashboard_track5_v2.py
"""

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Predictive Maintenance - Motor Induksi", layout="wide")

# Batas ambang "normal" per parameter (nilai awal, disesuaikan lagi kalau sudah
# ada data asli dari Astra / hasil kalibrasi Track 3)
BATAS = {
    "vibration": {"normal_max": 0.020, "warning_max": 0.030},
    "current":   {"normal_range": (4.5, 5.5)},
    "temperature": {"normal_max": 42.0},
}
JUMLAH_WINDOW_PERSISTENCE = 3   # "N jendela berturut-turut" ala Regan bag. 6.4
FAILURE_THRESHOLD_HEALTH = 20   # health score di bawah ini dianggap "gagal" untuk hitung RUL

# ==========================================================
# STATE - menyimpan histori beberapa pembacaan terakhir
# (dibutuhkan untuk persistence rule & tren RUL)
# ==========================================================
if "history" not in st.session_state:
    st.session_state.history = []          # list of dict: {vib, cur, temp, health}
if "cooldown_single" not in st.session_state:
    st.session_state.cooldown_single = 0    # penekan alarm ulang untuk kejadian yang sama


# ==========================================================
# BAGIAN 1: Health Score (placeholder heuristik - lihat catatan di atas)
# TODO: ganti isi fungsi ini dengan output asli model Marsha begitu tersedia
# ==========================================================
def hitung_health_score(vibration, current, temperature):
    penalti_vib = max(0, vibration - BATAS["vibration"]["normal_max"]) * 2000
    penalti_cur = max(0, abs(current - 5.0) - 0.5) * 20
    penalti_temp = max(0, temperature - BATAS["temperature"]["normal_max"]) * 5
    skor = 100 - penalti_vib - penalti_cur - penalti_temp
    return float(np.clip(skor, 0, 100))


# ==========================================================
# BAGIAN 2: Status abnormal per parameter (dipakai voting/multi-condition)
# ==========================================================
def cek_parameter_abnormal(vibration, current, temperature):
    abnormal = {
        "vibrasi": vibration > BATAS["vibration"]["warning_max"],
        "arus": not (BATAS["current"]["normal_range"][0] <= current <= BATAS["current"]["normal_range"][1]),
        "suhu": temperature > BATAS["temperature"]["normal_max"],
    }
    jumlah_abnormal = sum(abnormal.values())
    return abnormal, jumlah_abnormal


# ==========================================================
# BAGIAN 2b: Root Cause Hint - kemungkinan jenis kegagalan
# Mengacu Laporan Regan bag. 5 (pemetaan sensor -> fault) & bag. 4 (fisika 4 fault):
#   Vibrasi saja      -> Bearing / unbalance / kelonggaran mekanis
#   Arus saja         -> Broken Rotor Bar / masalah suplai
#   Suhu saja         -> Overload / masalah pendinginan
#   Vibrasi + Arus    -> Eccentricity (satu-satunya fault yg butuh 2 sensor ini bersamaan)
#   Arus + Suhu       -> Stator winding (isolasi memanas + arus tidak seimbang)
#   Ketiganya         -> Kondisi parah / lebih dari 1 mode kegagalan
# TODO: ganti dengan hasil analisis frekuensi asli (BPFO/BPFI/NSC) dari Track 3 bila tersedia
# ==========================================================
def diagnosis_kemungkinan_fault(abnormal):
    v, a, t = abnormal["vibrasi"], abnormal["arus"], abnormal["suhu"]
    if v and a and t:
        return "Kondisi parah — indikasi lebih dari satu mode kegagalan sekaligus", "danger"
    if v and a:
        return "Eccentricity — celah udara rotor-stator tidak merata (unbalanced magnetic pull)", "warning"
    if a and t:
        return "Stator Winding — indikasi isolasi memanas & arus 3 fasa tidak seimbang", "warning"
    if v:
        return "Bearing / kelonggaran mekanis — terdeteksi dari sinyal vibrasi", "warning"
    if a:
        return "Broken Rotor Bar / masalah suplai — terdeteksi dari sinyal arus", "warning"
    if t:
        return "Overload / masalah pendinginan — terdeteksi dari suhu", "warning"
    return "Tidak ada indikasi fault spesifik", "normal"


# ==========================================================
# BAGIAN 3: Logika alarm - Persistence (debounce) + Voting (multi-condition)
# Mengacu Laporan Regan bag. 6.4:
#   - persistence rule : alarm hanya jika N jendela berturut-turut abnormal (1 parameter)
#   - voting rule       : alarm langsung jika >= 2 parameter abnormal BERSAMAAN
# ==========================================================
def evaluasi_alarm(history, abnormal_dict, jumlah_abnormal):
    # Voting rule -> multi-condition, alarm langsung tanpa nunggu N window
    if jumlah_abnormal >= 2:
        parameter_terlibat = [k for k, v in abnormal_dict.items() if v]
        return "CRITICAL", f"Multi-condition: {', '.join(parameter_terlibat)} abnormal bersamaan"

    # Persistence rule -> debounce, hanya 1 parameter, cek N window terakhir
    if jumlah_abnormal == 1:
        window_terakhir = history[-(JUMLAH_WINDOW_PERSISTENCE - 1):] if len(history) >= 1 else []
        semua_history = window_terakhir + [abnormal_dict]
        jumlah_window_abnormal = sum(1 for h in semua_history if sum(h.values()) >= 1)

        if jumlah_window_abnormal >= JUMLAH_WINDOW_PERSISTENCE and st.session_state.cooldown_single == 0:
            st.session_state.cooldown_single = JUMLAH_WINDOW_PERSISTENCE  # tekan alarm ulang selama event yg sama
            parameter_terlibat = [k for k, v in abnormal_dict.items() if v]
            return "WARNING", f"Persistence: {parameter_terlibat[0]} abnormal {JUMLAH_WINDOW_PERSISTENCE}x berturut-turut"
        elif st.session_state.cooldown_single > 0:
            return "WARNING", "Kondisi sama masih berlangsung (alarm sudah dibunyikan, tidak diulang / debounce aktif)"

    # Kalau normal, turunkan cooldown & reset
    if st.session_state.cooldown_single > 0:
        st.session_state.cooldown_single -= 1
    return "NORMAL", "Semua parameter dalam rentang wajar"


# ==========================================================
# BAGIAN 4: Estimasi RUL - tren degradasi sederhana
# Mengacu Laporan Regan bag. 6.3: fit tren Health Score, proyeksikan ke depan
# sampai menyentuh failure threshold. Versi ini pakai regresi linear sebagai
# penyederhanaan dari model eksponensial f(t) = p1*e^(p2*t)+p3 di laporan asli.
# TODO: ganti dengan model degradasi asli dari Yose begitu tersedia.
# ==========================================================
def estimasi_rul(history, health_sekarang):
    riwayat_health = [h["health"] for h in history[-10:]] + [health_sekarang]
    if len(riwayat_health) < 3:
        return None, None  # belum cukup data untuk hitung tren

    x = np.arange(len(riwayat_health))
    slope, intercept = np.polyfit(x, riwayat_health, 1)

    if slope >= 0:
        return None, "Tren stabil/membaik, RUL belum dapat diestimasi"

    langkah_ke_gagal = (FAILURE_THRESHOLD_HEALTH - intercept) / slope - x[-1]
    langkah_ke_gagal = max(0, langkah_ke_gagal)
    probabilitas_gagal = round(100 - health_sekarang, 1)
    return round(langkah_ke_gagal), probabilitas_gagal


# ==========================================================
# BAGIAN 5: Sidebar - input sensor (mode manual atau replay CSV)
# ==========================================================
st.sidebar.header("Input Sensor")
mode = st.sidebar.radio("Mode simulasi", ["Manual (slider)", "Replay CSV"])

if mode == "Manual (slider)":
    vibration = st.sidebar.slider("Vibrasi (g)", 0.0, 0.05, 0.015, 0.001)
    current = st.sidebar.slider("Arus (A)", 3.0, 7.0, 5.0, 0.1)
    temperature = st.sidebar.slider("Suhu (°C)", 30.0, 50.0, 40.0, 0.5)
else:
    file = st.sidebar.file_uploader("Upload CSV (kolom: vibration, current, temperature)", type="csv")
    if file is not None:
        df_csv = pd.read_csv(file)
        idx = st.sidebar.slider("Baris data ke-", 0, len(df_csv) - 1, 0)
        vibration = float(df_csv.loc[idx, "vibration"])
        current = float(df_csv.loc[idx, "current"])
        temperature = float(df_csv.loc[idx, "temperature"])
    else:
        st.sidebar.info("Upload CSV dulu, atau pindah ke mode Manual.")
        vibration, current, temperature = 0.015, 5.0, 40.0

if st.sidebar.button("Reset histori simulasi"):
    st.session_state.history = []
    st.session_state.cooldown_single = 0

# ==========================================================
# BAGIAN 6: Jalankan pipeline & simpan ke histori
# ==========================================================
health_score = hitung_health_score(vibration, current, temperature)
abnormal_dict, jumlah_abnormal = cek_parameter_abnormal(vibration, current, temperature)
status_alarm, alasan_alarm = evaluasi_alarm(st.session_state.history, abnormal_dict, jumlah_abnormal)
langkah_rul, prob_gagal = estimasi_rul(st.session_state.history, health_score)
kemungkinan_fault, level_fault = diagnosis_kemungkinan_fault(abnormal_dict)

st.session_state.history.append({
    "vib": vibration, "cur": current, "temp": temperature,
    "health": health_score, **abnormal_dict,
})

# ==========================================================
# BAGIAN 7: Tampilan dashboard
# ==========================================================
st.title("Dashboard Predictive Maintenance - Motor Induksi")
st.caption("Prototipe Track 5 — logika alarm & RUL mengacu metodologi terkunci Track 2/3/4")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Health Score", f"{health_score:.1f}%")
    st.progress(int(health_score))

with col2:
    warna = {"NORMAL": "🟢", "WARNING": "🟡", "CRITICAL": "🔴"}[status_alarm]
    st.metric("Status Alarm", f"{warna} {status_alarm}")
    st.caption(alasan_alarm)

with col3:
    if langkah_rul is not None:
        st.metric("Estimasi RUL", f"{langkah_rul} langkah lagi")
        st.caption(f"Probabilitas gagal: {prob_gagal}%")
    else:
        st.metric("Estimasi RUL", "—")
        st.caption(prob_gagal or "Butuh lebih banyak data histori")

st.divider()
st.subheader("Root Cause Analysis — Kemungkinan Penyebab")
ikon = {"normal": "🟢", "warning": "🟡", "danger": "🔴"}[level_fault]
st.markdown(f"### {ikon} {kemungkinan_fault}")
st.caption("Diagnosis berbasis pemetaan sensor→fault (Laporan Progres Case 2, bagian 5 & 4)")

st.divider()
st.subheader("Tren Health Score")
if len(st.session_state.history) > 1:
    df_hist = pd.DataFrame(st.session_state.history)
    st.line_chart(df_hist["health"])
else:
    st.caption("Gerakkan slider / ganti baris CSV untuk mulai membangun histori tren.")

st.info(
    "Health Score saat ini masih heuristik sederhana (belum model asli Marsha). "
    "Logika alarm (persistence + voting) dan estimasi RUL sudah mengikuti "
    "metodologi yang tercantum di Laporan Progres Case 2 bagian 6.3 & 6.4."
)
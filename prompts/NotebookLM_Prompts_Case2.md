# Prompt NotebookLM — Case 2: Predictive Maintenance Motor Induksi

> Cara pakai: buat **3 notebook terpisah** di NotebookLM, upload paper sesuai daftar per notebook, lalu tanyakan prompt-nya berurutan. NotebookLM hanya menjawab dari sumber yang di-upload — kualitas jawaban = kualitas paper yang kamu masukkan.

---

## Notebook A — Fisika Kegagalan & Fitur Sinyal (fondasi, Track 3)

**Paper yang di-upload (cari di Google Scholar):**
- "Advancements in Induction Motor Fault Diagnosis and Condition Monitoring: A Comprehensive Review" (Sensors/MDPI, 2025)
- 1 paper survey MCSA (mis. Thomson & Fenger, "Current signature analysis to detect induction motor faults", IEEE IAS Magazine)
- 1 paper envelope analysis / bearing fault diagnosis (mis. Randall & Antoni, "Rolling element bearing diagnostics — a tutorial")
- 1 paper stator inter-turn fault / negative-sequence detection

**Prompt:**
1. "Buatkan tabel perbandingan 4 fault utama motor induksi (bearing, broken rotor bar, stator winding, eccentricity): mekanisme fisik, frekuensi/sinyal karakteristik, sensor yang paling sensitif, dan seberapa awal fault bisa terdeteksi sebelum kegagalan — sertakan kutipan dari sumber."
2. "Dari sumber-sumber ini, fitur sinyal apa saja (time-domain, frequency-domain, envelope) yang paling sering dipakai untuk mendeteksi bearing fault, dan bagaimana cara menghitungnya dari sinyal vibrasi mentah?"
3. "Jelaskan langkah-demi-langkah envelope analysis untuk bearing fault: kenapa perlu demodulasi, band frekuensi mana yang dipilih, dan bagaimana BPFO/BPFI muncul di spektrum envelope."
4. "Apa keterbatasan MCSA menurut sumber-sumber ini — pada kondisi beban atau motor seperti apa MCSA tidak andal, dan apa mitigasinya?"
5. "Kalau saya hanya boleh memakai 3 jenis sensor (vibrasi, arus, suhu), fitur apa dari masing-masing yang memberi cakupan deteksi terluas untuk keempat fault? Jawab sebagai tabel sensor → fitur → fault yang tercakup."

---

## Notebook B — Anomaly Detection & Health Index (Minggu 2)

**Paper yang di-upload:**
- 1 survey anomaly detection untuk machine condition monitoring / PHM
- Paper Isolation Forest asli (Liu, Ting, Zhou, 2008) atau survey yang membahasnya
- 1 paper autoencoder untuk fault/anomaly detection pada rotating machinery
- 1 paper health index construction / sensor fusion untuk PHM (mis. dari IEEE PHM conference)

**Prompt:**
6. "Bandingkan Isolation Forest vs Autoencoder untuk deteksi anomali pada data sensor mesin: asumsi data, kebutuhan data latih, cara menentukan threshold skor anomali, dan kelemahan masing-masing menurut sumber."
7. "Bagaimana cara yang benar melatih model anomaly detection hanya dengan data kondisi sehat (tanpa label fault)? Apa jebakan umum (data leakage, threshold arbitrer) yang disebut sumber?"
8. "Rangkum metode membangun satu health index gabungan dari banyak sensor/fitur: pendekatan weighted aggregation, PCA-based, dan model-based. Mana yang paling sederhana tapi defensible untuk prototipe?"
9. "Teknik apa saja yang disebut sumber untuk mengurangi false alarm pada sistem monitoring — persistence rules, voting antar parameter, adaptive threshold? Bagaimana efektivitasnya diukur?"
10. "Metrik evaluasi apa yang tepat untuk sistem anomaly detection tanpa banyak label kegagalan nyata: bagaimana sumber-sumber ini mengevaluasi (precision/recall event, lead time deteksi, false alarm rate per jam operasi)?"

---

## Notebook C — RUL & Degradation Modeling (Minggu 3)

**Paper yang di-upload:**
- 1 survey RUL estimation / prognostics (mis. Lei et al., "Machinery health prognostics: A systematic review")
- 1 paper yang memakai NASA IMS bearing dataset (run-to-failure)
- 1 paper LSTM untuk RUL pada C-MAPSS (untuk pembanding, sinkron dengan track Yose)
- 1 paper degradation curve fitting / exponential degradation model

**Prompt:**
11. "Jelaskan taksonomi pendekatan RUL menurut sumber: physics-based, statistical/degradation-model, dan data-driven (ML). Untuk dataset run-to-failure kecil seperti NASA IMS, pendekatan mana yang paling realistis dan kenapa?"
12. "Bagaimana langkah konkret membangun RUL sederhana dari data IMS: fitur kesehatan apa yang dipakai sebagai degradation indicator, bagaimana menentukan failure threshold, dan bagaimana ekstrapolasi kurvanya? Sertakan formula bila ada di sumber."
13. "Apa kelemahan utama LSTM untuk RUL yang disebut sumber (kebutuhan data, overfitting, ketidakpastian prediksi), dan dalam kondisi apa metode degradasi statistik justru lebih akurat?"
14. "Bagaimana sumber-sumber ini mengukur akurasi prediksi RUL (RMSE, scoring function C-MAPSS, prognostic horizon)? Metrik mana yang paling jujur untuk dilaporkan di proposal?"
15. "Berdasarkan semua sumber, susun arsitektur pipeline end-to-end yang menyatukan: ekstraksi fitur → anomaly detection → health index → RUL → alert. Di titik mana tiap komponen bisa gagal, dan apa mitigasinya?"

---

## Rencana 4 Minggu (ringkas)

| Minggu | Fokus | Output demoable |
|---|---|---|
| 1 | Dataset (NASA IMS + MAFAULDA), EDA, ekstraksi fitur per fault | Notebook fitur + baseline data sehat |
| 2 | Isolation Forest + Autoencoder (latih di data sehat), health index gabungan | Health score 0–100 per mesin |
| 3 | RUL (degradation curve + ekstrapolasi), aturan false alarm (persistence + voting), dashboard Streamlit | Demo tiap komponen |
| 4 | Integrasi replay-stream (simulasi real-time), metrik evaluasi, proposal & slide | Demo end-to-end + proposal |

**Prinsip:** tiap akhir minggu harus ada yang bisa didemokan. RUL versi sederhana yang bisa dijelaskan > LSTM yang tidak selesai. Streaming cukup disimulasikan dengan replay data.

## Stack yang disarankan
Python + pandas/numpy/scipy (fitur sinyal), scikit-learn (Isolation Forest), PyTorch/Keras opsional (autoencoder), Streamlit (dashboard + alert). Dataset: NASA IMS (run-to-failure, untuk RUL & anomaly), MAFAULDA (multi-fault, untuk klasifikasi & demo multi-sensor).

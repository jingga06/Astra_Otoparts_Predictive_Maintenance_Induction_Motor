"""
Track 5 - Analisis Kebutuhan Akuisisi Data & Arsitektur Deployment
Case 2: Predictive Maintenance Motor Induksi - Bootcamp AOP Winteq
Jingga

Script ini punya 2 bagian:
1. Inspeksi 1 file sample dari dataset NASA IMS Bearing (setelah kamu download manual)
2. Kalkulasi perbandingan volume data: kirim mentah terus-menerus VS snapshot
   berkala (edge processing) - ini bukti konkret kenapa arsitektur harus
   punya strategi akuisisi data yang pintar, bukan streaming semua mentah.

CARA PAKAI:
1. Download dataset dari: https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip
   (atau mirror Kaggle: kaggle.com/datasets/vinayak123tyagi/bearing-dataset)
2. Extract, taruh folder-nya di sebelah script ini (misal folder "data/")
3. Install pandas dulu kalau belum ada: pip install pandas
4. Jalankan: python track5_analisis_arsitektur.py
"""

import os
import pandas as pd


# ==========================================================
# BAGIAN 1: Inspeksi sample data IMS Bearing
# ==========================================================
# Struktur folder dataset setelah di-extract:
#   data/1st_test/...   -> tiap bearing 2 channel (x & y axis)
#   data/2nd_test/...   -> tiap bearing 1 channel
#   data/3rd_test/...   -> tiap bearing 1 channel
# Tiap file = snapshot getaran 1 detik, format teks tab-separated,
# nama file = timestamp perekaman (contoh: "2004.02.12.10.32.39")

def inspect_sample(filepath):
    """Baca 1 file sample dan tampilkan info dasarnya."""
    df = pd.read_csv(filepath, sep="\t", header=None)
    ukuran_kb = os.path.getsize(filepath) / 1024

    print("=== Inspeksi Sample Data ===")
    print(f"File            : {filepath}")
    print(f"Jumlah baris    : {len(df)}  (titik data dalam 1 snapshot)")
    print(f"Jumlah kolom    : {df.shape[1]}  (channel sensor bearing)")
    print(f"Ukuran di disk  : {ukuran_kb:.1f} KB")
    print(f"5 baris pertama :\n{df.head()}\n")
    return df


# ==========================================================
# BAGIAN 2: Kalkulasi kebutuhan bandwidth (INI BUKTI UTAMA TRACK 5)
# Membandingkan: kirim data mentah terus-menerus VS snapshot berkala
# ==========================================================

def hitung_kebutuhan_bandwidth(
    sampling_rate_hz=20000,      # 20 kHz - sesuai spesifikasi dataset IMS
    bytes_per_sample=2,          # umum: sensor ADC 16-bit = 2 byte per sampel
    jumlah_channel=4,            # 4 bearing dipantau bersamaan
    durasi_snapshot_detik=1,     # tiap snapshot 1 detik
    interval_snapshot_menit=10,  # snapshot diambil tiap 10 menit (sesuai dataset asli)
):
    """
    Bandingkan volume data per motor per hari:
    - Skenario 1: semua data getaran dikirim MENTAH, terus-menerus (naive)
    - Skenario 2: data diambil berkala (snapshot), gaya edge/duty-cycle
      -> ini strategi yang dipakai dataset IMS itu sendiri
    """
    detik_per_hari = 24 * 60 * 60

    # --- Skenario 1: streaming mentah 24 jam nonstop ---
    bytes_per_detik_per_channel = sampling_rate_hz * bytes_per_sample
    total_kontinu_per_hari = bytes_per_detik_per_channel * detik_per_hari * jumlah_channel

    # --- Skenario 2: snapshot berkala (edge/duty-cycle) ---
    snapshot_per_hari = detik_per_hari / (interval_snapshot_menit * 60)
    bytes_per_snapshot_per_channel = sampling_rate_hz * durasi_snapshot_detik * bytes_per_sample
    total_snapshot_per_hari = bytes_per_snapshot_per_channel * snapshot_per_hari * jumlah_channel

    reduksi_persen = (1 - total_snapshot_per_hari / total_kontinu_per_hari) * 100

    print("=== Perbandingan Kebutuhan Bandwidth per Motor per Hari ===")
    print(f"Skenario 1 (kirim mentah terus-menerus) : {total_kontinu_per_hari/1e9:.2f} GB/hari")
    print(f"Skenario 2 (snapshot tiap {interval_snapshot_menit} menit)         : {total_snapshot_per_hari/1e6:.2f} MB/hari")
    print(f"Reduksi volume data                     : {reduksi_persen:.2f}%")
    print()
    print("Kesimpulan: strategi snapshot/edge processing bukan cuma teori,")
    print("tapi bisa dihitung konkret hasilnya - dan ini persis strategi")
    print("yang dipakai dataset NASA IMS yang dipakai tim untuk model AI.")

    return {
        "kontinu_gb_per_hari": total_kontinu_per_hari / 1e9,
        "snapshot_mb_per_hari": total_snapshot_per_hari / 1e6,
        "reduksi_persen": reduksi_persen,
    }


if __name__ == "__main__":
    # --- Jalankan kalkulasi bandwidth (tidak butuh dataset, bisa langsung jalan) ---
    hitung_kebutuhan_bandwidth()

    # --- Kalau dataset sudah didownload & di-extract, uncomment baris di bawah ---
    # inspect_sample("data/2nd_test/2004.02.12.10.32.39")

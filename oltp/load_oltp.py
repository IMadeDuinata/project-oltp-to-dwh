"""
Script untuk load dataset Olist dari CSV ke MySQL (OLTP).
- Baca CSV dengan separator ';'
- Buat tabel otomatis di database oltp_olist
- Insert data dalam chunk agar efisien
"""

import os
import sys
import time
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# ============================================================
# 1. LOAD KONFIGURASI DARI .env
# ============================================================
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "oltp_olist")
CSV_PATH = os.getenv("CSV_PATH", "data/Olist.csv")
TABLE_NAME = os.getenv("TABLE_NAME", "olist_raw")

if not DB_PASSWORD:
    print("❌ ERROR: DB_PASSWORD belum diisi di file .env")
    sys.exit(1)

# ============================================================
# 2. BIKIN KONEKSI KE MYSQL
# ============================================================
connection_url = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)
engine = create_engine(connection_url, pool_pre_ping=True)

print("=" * 60)
print("🚀 LOAD CSV OLIST KE MYSQL (OLTP)")
print("=" * 60)
print(f"📁 CSV        : {CSV_PATH}")
print(f"🗄️  Database   : {DB_NAME}")
print(f"📊 Tabel      : {TABLE_NAME}")
print(f"🔌 Host       : {DB_HOST}:{DB_PORT}")
print(f"👤 User       : {DB_USER}")
print("=" * 60)

# ============================================================
# 3. BACA CSV
# ============================================================
print("\n[1/4] 📖 Membaca file CSV...")
t0 = time.time()

# CSV punya ';' di awal & akhir, jadi kita:
#   - sep=';'          → separator titik koma
#   - index_col=False  → jangan pakai kolom pertama sebagai index
#   - skipinitialspace → buang spasi setelah separator
df = pd.read_csv(
    CSV_PATH,
    sep=";",
    index_col=False,
    skipinitialspace=True,
    encoding="utf-8",
    low_memory=False,
)

# Buang kolom yang tidak bernama (kolom kosong di awal & akhir)
df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

# Bersihkan nama kolom: ganti '/' jadi '_' (biar aman untuk MySQL)
df.columns = [c.strip().replace("/", "_").replace(" ", "_") for c in df.columns]

t1 = time.time()
print(f"   ✅ Selesai. {len(df):,} baris × {len(df.columns)} kolom")
print(f"   ⏱️  Waktu: {t1 - t0:.2f} detik")
print(f"\n   📋 Preview 5 baris pertama:")
print(df.head().to_string(max_colwidth=20))
print(f"\n   📋 Daftar kolom:")
for i, col in enumerate(df.columns, 1):
    print(f"      {i:2d}. {col}  ({df[col].dtype})")

# ============================================================
# 4. INSERT KE MYSQL
# ============================================================
print(f"\n[2/4] 🔌 Koneksi ke MySQL...")
with engine.connect() as conn:
    result = conn.execute(text("SELECT VERSION()"))
    version = result.scalar()
    print(f"   ✅ Terhubung. MySQL version: {version}")

print(f"\n[3/4] 📤 Insert data ke tabel `{TABLE_NAME}`...")
print(f"   (Ini mungkin butuh 1-3 menit untuk 51 MB CSV, sabar ya...)")
t2 = time.time()

# chunksize = 5000 → insert per 5000 baris agar tidak memory-error
# if_exists='replace' → kalau tabel sudah ada, drop & buat ulang
# method='multi' → insert banyak baris sekaligus (lebih cepat)
df.to_sql(
    name=TABLE_NAME,
    con=engine,
    if_exists="replace",
    index=False,
    chunksize=5000,
    method="multi",
)

t3 = time.time()
print(f"   ✅ Selesai insert!")
print(f"   ⏱️  Waktu: {t3 - t2:.2f} detik")

# ============================================================
# 5. VERIFIKASI
# ============================================================
print(f"\n[4/4] 🔍 Verifikasi data di MySQL...")
with engine.connect() as conn:
    # Hitung jumlah baris
    result = conn.execute(text(f"SELECT COUNT(*) FROM `{TABLE_NAME}`"))
    count = result.scalar()
    print(f"   📊 Jumlah baris di tabel `{TABLE_NAME}`: {count:,}")

    # Preview 3 baris pertama
    result = conn.execute(text(f"SELECT * FROM `{TABLE_NAME}` LIMIT 3"))
    rows = result.fetchall()
    print(f"\n   📋 Preview 3 baris pertama (kolom pertama saja):")
    for row in rows:
        print(f"      {row[0]}")

# ============================================================
# SELESAI
# ============================================================
print("\n" + "=" * 60)
print("🎉 SELESAI! Data Olist berhasil di-load ke MySQL.")
print("=" * 60)
print(f"\n📌 Langkah selanjutnya:")
print(f"   1. Buka MySQL Workbench / CLI, cek: SELECT * FROM {DB_NAME}.{TABLE_NAME} LIMIT 10;")
print(f"   2. Lanjut buat script ETL: etl/transform_oltp_to_dwh.py")
print(f"   3. Atau buat script DWH: dwh/create_star_schema.py")
print()
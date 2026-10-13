"""
ETL Pipeline: OLTP (olist_raw) → DWH (Star Schema)

Proses:
1. EXTRACT  : Baca dari oltp_olist.olist_raw
2. TRANSFORM: Bersihkan + pisah jadi 5 dimensi & 1 fakta
3. LOAD     : Insert ke dwh_olist
"""

import os
import sys
import time
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# ============================================================
# 1. KONFIGURASI
# ============================================================
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME_OLTP = os.getenv("DB_NAME", "oltp_olist")
DB_NAME_DWH  = "dwh_olist"

if not DB_PASSWORD:
    print("❌ ERROR: DB_PASSWORD belum diisi di .env")
    sys.exit(1)

# Engine OLTP
engine_oltp = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_OLTP}?charset=utf8mb4",
    pool_pre_ping=True
)
# Engine DWH
engine_dwh = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_DWH}?charset=utf8mb4",
    pool_pre_ping=True
)

print("=" * 60)
print("🔄 ETL: OLTP → DWH")
print("=" * 60)
print(f"📥 Sumber : {DB_NAME_OLTP}.olist_raw")
print(f"📤 Target : {DB_NAME_DWH}")
print("=" * 60)


# ============================================================
# 2. EXTRACT
# ============================================================
print("\n[1/4] 📥 EXTRACT: Baca data dari OLTP...")
t0 = time.time()

df = pd.read_sql("SELECT * FROM olist_raw", engine_oltp)
print(f"   ✅ {len(df):,} baris × {len(df.columns)} kolom dibaca")
print(f"   ⏱️  Waktu: {time.time() - t0:.2f} detik")


# ============================================================
# 3. TRANSFORM
# ============================================================
print("\n[2/4] 🔧 TRANSFORM: Bersihkan & pisah jadi tabel-tabel...")
t1 = time.time()

# --- 3a. Bersihkan data kotor ---
before = len(df)
# Buang baris dengan order_status tidak valid (angka '2018')
valid_status = ['delivered', 'canceled', 'shipped', 'processing',
                'invoiced', 'approved', 'unavailable', 'created']
df = df[df['order_status'].isin(valid_status)].copy()

# Buang baris dengan payment_type tidak valid (kode state: RJ, RS, dll — 2 huruf kapital)
valid_payment = ['credit_card', 'boleto', 'voucher', 'debit_card', 'not_defined']
df = df[df['payment_type'].isin(valid_payment)].copy()

after = len(df)
print(f"   🧹 Dibuang: {before - after} baris kotor")
print(f"   ✅ Data bersih: {after:,} baris")

# --- 3b. Konversi tipe data ---
# Konversi kolom tanggal (string → datetime)
date_cols = [
    'order_purchase_timestamp',
    'order_approved_at',
    'order_delivered_carrier_date',
    'order_delivered_customer_date',
    'order_estimated_delivery_date',
    'shipping_limit_date',
]
for col in date_cols:
    df[col] = pd.to_datetime(df[col], format='%d/%m/%Y %H:%M', errors='coerce')

# Konversi numerik
df['price'] = pd.to_numeric(df['price'], errors='coerce')
df['freight_value'] = pd.to_numeric(df['freight_value'], errors='coerce')
df['payment_value'] = pd.to_numeric(df['payment_value'], errors='coerce')

# --- 3c. Buat dim_customer ---
dim_customer = (
    df[['customer_id', 'customer_unique_id', 'customer_zip_code_prefix',
        'customer_city', 'customer_state']]
    .drop_duplicates(subset=['customer_id'])
    .rename(columns={'customer_zip_code_prefix': 'customer_zip_code'})
    .reset_index(drop=True)
)
print(f"   📊 dim_customer: {len(dim_customer):,} baris")

# --- 3d. Buat dim_product ---
dim_product = (
    df[['product_id', 'product_category_name', 'product_name_lenght',
        'product_description_lenght', 'product_photos_qty',
        'product_weight_g', 'product_length_cm', 'product_height_cm',
        'product_width_cm']]
    .drop_duplicates(subset=['product_id'])
    .rename(columns={
        'product_name_lenght': 'product_name_length',
        'product_description_lenght': 'product_description_length'
    })
    .reset_index(drop=True)
)
print(f"   📊 dim_product: {len(dim_product):,} baris")

# --- 3e. Buat dim_seller ---
dim_seller = (
    df[['seller_id', 'seller_zip_code_prefix', 'seller_city', 'seller_state']]
    .drop_duplicates(subset=['seller_id'])
    .rename(columns={'seller_zip_code_prefix': 'seller_zip_code'})
    .reset_index(drop=True)
)
print(f"   📊 dim_seller: {len(dim_seller):,} baris")

# --- 3f. Buat dim_payment ---
dim_payment = (
    df[['payment_type', 'payment_installments']]
    .drop_duplicates()
    .reset_index(drop=True)
)
print(f"   📊 dim_payment: {len(dim_payment):,} baris")

# --- 3g. Buat dim_date (generate kalender) ---
date_range = pd.date_range(
    start=df['order_purchase_timestamp'].min().normalize(),
    end=df['order_purchase_timestamp'].max().normalize(),
    freq='D'
)
dim_date = pd.DataFrame({'full_date': date_range})
dim_date['day']         = dim_date['full_date'].dt.day
dim_date['month']       = dim_date['full_date'].dt.month
dim_date['month_name']  = dim_date['full_date'].dt.strftime('%B')
dim_date['quarter']     = dim_date['full_date'].dt.quarter
dim_date['year']        = dim_date['full_date'].dt.year
dim_date['day_of_week'] = dim_date['full_date'].dt.strftime('%A')
dim_date['is_weekend']  = dim_date['full_date'].dt.dayofweek.isin([5, 6]).astype(int)
print(f"   📊 dim_date: {len(dim_date):,} baris")

print(f"   ⏱️  Waktu transform: {time.time() - t1:.2f} detik")


# ============================================================
# 4. LOAD — Insert dimensi dulu (biar dapat surrogate key)
# ============================================================
print("\n[3/4] 📤 LOAD: Insert ke DWH...")
t2 = time.time()

# Truncate dulu (biar idempotent — bisa dijalankan ulang)
with engine_dwh.begin() as conn:
    for t in ['fact_sales', 'dim_customer', 'dim_product', 'dim_seller', 'dim_payment', 'dim_date']:
        conn.execute(text(f"SET FOREIGN_KEY_CHECKS=0;"))
        conn.execute(text(f"TRUNCATE TABLE `{t}`;"))
    conn.execute(text("SET FOREIGN_KEY_CHECKS=1;"))
print("   🧹 Tabel DWH di-truncate dulu")

# Insert dimensi
dim_customer.to_sql('dim_customer', engine_dwh, if_exists='append', index=False, chunksize=5000)
print(f"   ✅ dim_customer  : {len(dim_customer):,} baris")

dim_product.to_sql('dim_product', engine_dwh, if_exists='append', index=False, chunksize=5000)
print(f"   ✅ dim_product   : {len(dim_product):,} baris")

dim_seller.to_sql('dim_seller', engine_dwh, if_exists='append', index=False, chunksize=5000)
print(f"   ✅ dim_seller    : {len(dim_seller):,} baris")

dim_payment.to_sql('dim_payment', engine_dwh, if_exists='append', index=False, chunksize=5000)
print(f"   ✅ dim_payment   : {len(dim_payment):,} baris")

dim_date.to_sql('dim_date', engine_dwh, if_exists='append', index=False, chunksize=5000)
print(f"   ✅ dim_date      : {len(dim_date):,} baris")

# ============================================================
# 5. BUILD FACT TABLE (lookup surrogate keys)
# ============================================================
print("\n   🔗 Membangun fact_sales (lookup surrogate keys)...")

# Baca kembali dimensi (untuk dapat surrogate key)
cust_map = pd.read_sql("SELECT customer_sk, customer_id FROM dim_customer", engine_dwh)
prod_map = pd.read_sql("SELECT product_sk, product_id FROM dim_product", engine_dwh)
sell_map = pd.read_sql("SELECT seller_sk, seller_id FROM dim_seller", engine_dwh)
paym_map = pd.read_sql("SELECT payment_sk, payment_type, payment_installments FROM dim_payment", engine_dwh)
date_map = pd.read_sql("SELECT date_sk, full_date FROM dim_date", engine_dwh)
date_map['full_date'] = pd.to_datetime(date_map['full_date'])

# Join untuk dapat surrogate key
fact = df.merge(cust_map, on='customer_id', how='left')
fact = fact.merge(prod_map, on='product_id', how='left')
fact = fact.merge(sell_map, on='seller_id', how='left')
fact = fact.merge(paym_map, on=['payment_type', 'payment_installments'], how='left')

# Untuk date, cocokkan dengan tanggal (tanpa jam)
fact['order_date_only'] = fact['order_purchase_timestamp'].dt.normalize()
fact = fact.merge(date_map, left_on='order_date_only', right_on='full_date', how='left')

# Pilih kolom untuk fact_sales
fact_sales = fact[[
    'order_id', 'order_item_id',
    'customer_sk', 'product_sk', 'seller_sk', 'payment_sk', 'date_sk',
    'order_status', 'price', 'freight_value', 'payment_value',
    'order_purchase_timestamp', 'order_delivered_customer_date',
    'order_estimated_delivery_date'
]].copy()

# Cek missing FK
missing = fact_sales[['customer_sk', 'product_sk', 'seller_sk', 'payment_sk', 'date_sk']].isnull().sum()
if missing.sum() > 0:
    print(f"   ⚠️  Ada {missing.sum()} FK yang NULL:")
    print(missing[missing > 0])
    fact_sales = fact_sales.dropna(subset=['customer_sk', 'product_sk', 'seller_sk', 'payment_sk', 'date_sk'])

# Konversi tipe
for col in ['customer_sk', 'product_sk', 'seller_sk', 'payment_sk', 'date_sk', 'order_item_id']:
    fact_sales[col] = fact_sales[col].astype(int)

fact_sales.to_sql('fact_sales', engine_dwh, if_exists='append', index=False, chunksize=5000)
print(f"   ✅ fact_sales    : {len(fact_sales):,} baris")
print(f"   ⏱️  Waktu load: {time.time() - t2:.2f} detik")


# ============================================================
# 6. VERIFIKASI
# ============================================================
print("\n[4/4] 🔍 VERIFIKASI hasil ETL...")

with engine_dwh.connect() as conn:
    tables = ['dim_customer', 'dim_product', 'dim_seller', 'dim_payment', 'dim_date', 'fact_sales']
    for t in tables:
        count = conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
        print(f"   📊 {t:15s} : {count:>7,} baris")

    # Sample query: total sales
    total = conn.execute(text("SELECT SUM(price) FROM fact_sales")).scalar()
    print(f"\n   💰 Total penjualan (SUM price): R$ {total:,.2f}")

    # Sample: Top 5 kategori
    print(f"\n   🏆 Top 5 kategori produk terlaris:")
    result = conn.execute(text("""
        SELECT dp.product_category_name, COUNT(*) as jumlah
        FROM fact_sales f
        JOIN dim_product dp ON f.product_sk = dp.product_sk
        GROUP BY dp.product_category_name
        ORDER BY jumlah DESC
        LIMIT 5
    """))
    for row in result:
        print(f"      • {row[0]:30s} : {row[1]:>6,}")


# ============================================================
# SELESAI
# ============================================================
print("\n" + "=" * 60)
print("🎉 ETL SELESAI! Data sudah ada di DWH.")
print("=" * 60)
print("\n📌 Langkah selanjutnya:")
print("   1. Analisis data: python etl/analytics.py")
print("   2. Atau query manual di MySQL:")
print("      USE dwh_olist;")
print("      SELECT * FROM fact_sales LIMIT 5;")
print()
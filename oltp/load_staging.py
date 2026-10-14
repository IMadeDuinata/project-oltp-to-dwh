"""
Script untuk memuat data mentah ke tabel staging `olist_raw` di database `oltp_olist`.
Mendukung:
1. Membaca langsung file CSV flat jika ada (`data/Olist.csv`), ATAU
2. Menggabungkan file dataset Kaggle mentah dari `data/raw/*.csv` menjadi flat staging table
3. Menginjeksi data kotor pengujian secara otomatis jika diinginkan.
"""

import os
import sys
import time
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

from inject_dirty_data import inject_dirty_data

# ============================================================
# 1. KONFIGURASI DARI .env
# ============================================================
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secret")
DB_NAME_OLTP = os.getenv("DB_NAME_OLTP", os.getenv("DB_NAME", "oltp_olist"))
CSV_PATH = os.getenv("CSV_PATH", "data/Olist.csv")
TABLE_NAME = os.getenv("TABLE_NAME", "olist_raw")

# Koneksi aman menggunakan URL.create
url = URL.create(
    drivername="mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME_OLTP,
    query={"charset": "utf8mb4"},
)
engine = create_engine(url, pool_pre_ping=True)


def build_staging_from_raw_csvs(data_raw_dir="data/raw"):
    """
    Jika file data/Olist.csv tidak ada, fungsi ini menggabungkan
    dataset mentah dari data/raw/ menjadi flat dataframe persis seperti format staging.
    """
    print(f"📖 Membaca dan menggabungkan raw CSVs dari `{data_raw_dir}`...")
    t0 = time.time()

    orders_file = os.path.join(data_raw_dir, "olist_orders_dataset.csv")
    items_file = os.path.join(data_raw_dir, "olist_order_items_dataset.csv")
    payments_file = os.path.join(data_raw_dir, "olist_order_payments_dataset.csv")
    customers_file = os.path.join(data_raw_dir, "olist_customers_dataset.csv")
    products_file = os.path.join(data_raw_dir, "olist_products_dataset.csv")
    sellers_file = os.path.join(data_raw_dir, "olist_sellers_dataset.csv")

    df_orders = pd.read_csv(orders_file)
    df_items = pd.read_csv(items_file)
    df_payments = pd.read_csv(payments_file)
    df_customers = pd.read_csv(customers_file)
    df_products = pd.read_csv(products_file)
    df_sellers = pd.read_csv(sellers_file)

    # Lakukan join untuk membentuk flat staging table
    # Urutan: items -> orders -> customers -> products -> sellers -> payments
    df = df_items.merge(df_orders, on="order_id", how="left")
    df = df.merge(df_customers, on="customer_id", how="left")
    df = df.merge(df_products, on="product_id", how="left")
    df = df.merge(df_sellers, on="seller_id", how="left")
    df = df.merge(df_payments, on="order_id", how="left")

    print(f"   ✅ Selesai digabungkan: {len(df):,} baris dalam {time.time() - t0:.2f} detik")
    return df


def load_staging_data(csv_path=CSV_PATH, table_name=TABLE_NAME, inject_dirty=True):
    """Membaca CSV dan memuat ke database OLTP staging olist_raw."""
    print("=" * 60)
    print("🚀 LOAD DATA STAGING (olist_raw)")
    print("=" * 60)
    print(f"🗄️  Database : {DB_NAME_OLTP}")
    print(f"📊 Tabel    : {table_name}")

    if os.path.exists(csv_path):
        print(f"📁 Membaca dari CSV flat: {csv_path}")
        # Coba baca dengan sep ';' atau ','
        try:
            df = pd.read_csv(
                csv_path,
                sep=";",
                index_col=False,
                skipinitialspace=True,
                encoding="utf-8",
                low_memory=False,
            )
            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
            if len(df.columns) <= 2:
                # Delimiter mungkin koma
                df = pd.read_csv(csv_path, sep=",", low_memory=False)
        except Exception:
            df = pd.read_csv(csv_path, sep=",", low_memory=False)
    else:
        print(f"⚠️  File `{csv_path}` tidak ditemukan.")
        df = build_staging_from_raw_csvs()

    # Bersihkan nama kolom
    df.columns = [c.strip().replace("/", "_").replace(" ", "_") for c in df.columns]

    print(f"📥 Memuat {len(df):,} baris ke tabel `{table_name}`...")
    t0 = time.time()

    # Pastikan tipe data dikonversi ke string agar dapat menampung nilai anomali apa adanya
    df = df.astype(str).replace({"nan": None, "None": None})

    # Drop & recreate olist_raw
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
        # Baca DDL dari sql/01_oltp_ddl.sql jika tabel belum ada
        with open("sql/01_oltp_ddl.sql") as f:
            ddl_content = f.read()
        # Eksekusi blok DDL olist_raw
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS olist_raw (
                raw_id                         BIGINT AUTO_INCREMENT PRIMARY KEY,
                order_id                       VARCHAR(100),
                order_item_id                  VARCHAR(50),
                product_id                     VARCHAR(100),
                seller_id                      VARCHAR(100),
                seller_zip_code_prefix         VARCHAR(50),
                seller_city                    VARCHAR(100),
                seller_state                   VARCHAR(50),
                shipping_limit_date            VARCHAR(50),
                price                          VARCHAR(50),
                freight_value                  VARCHAR(50),
                payment_sequential             VARCHAR(50),
                payment_type                   VARCHAR(50),
                payment_installments           VARCHAR(50),
                payment_value                  VARCHAR(50),
                customer_id                    VARCHAR(100),
                customer_unique_id             VARCHAR(100),
                customer_zip_code_prefix       VARCHAR(50),
                customer_city                  VARCHAR(100),
                customer_state                 VARCHAR(50),
                order_status                   VARCHAR(50),
                order_purchase_timestamp       VARCHAR(50),
                order_approved_at              VARCHAR(50),
                order_delivered_carrier_date   VARCHAR(50),
                order_delivered_customer_date  VARCHAR(50),
                order_estimated_delivery_date  VARCHAR(50),
                product_category_name          VARCHAR(100),
                product_name_lenght            VARCHAR(50),
                product_description_lenght     VARCHAR(50),
                product_photos_qty             VARCHAR(50),
                product_weight_g               VARCHAR(50),
                product_length_cm              VARCHAR(50),
                product_height_cm              VARCHAR(50),
                product_width_cm               VARCHAR(50),
                INDEX idx_raw_order_id (order_id),
                INDEX idx_raw_customer_id (customer_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """))

    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="append",
        index=False,
        chunksize=5000,
        method="multi",
    )
    print(f"✅ Selesai memuat staging dalam {time.time() - t0:.2f} detik.")

    if inject_dirty:
        inject_dirty_data(table_name=table_name)

    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar()
        print(f"📊 Total baris akhir di `{table_name}`: {count:,}")


def main():
    parser = argparse.ArgumentParser(description="Load data ke staging table olist_raw")
    parser.add_argument("--no-inject", action="store_true", help="Jangan injeksi baris kotor tambahan")
    args = parser.parse_args()

    load_staging_data(inject_dirty=not args.no_inject)


if __name__ == "__main__":
    main()

"""
Script Loader CSV Olist Brazil ke MySQL Database `oltp_olist`.
Alur:
1. Inisialisasi schema sql/01_oltp_ddl.sql jika belum ada
2. Truncate tabel-tabel 3NF untuk menjaga idempotensi
3. Load data dari data/raw/ ke MySQL (port 3306)
"""

import os
import sys
import time
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

# 1. Konfigurasi
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT_OLTP_BR", os.getenv("DB_PORT", "3306")))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME_OLTP_BR", "oltp_olist")
CSV_DIR = BASE_DIR / "data" / "raw"

CSV_MAP = {
    "customers":            "olist_customers_dataset.csv",
    "sellers":              "olist_sellers_dataset.csv",
    "products":             "olist_products_dataset.csv",
    "orders":               "olist_orders_dataset.csv",
    "order_items":          "olist_order_items_dataset.csv",
    "order_payments":       "olist_order_payments_dataset.csv",
    "order_reviews":        "olist_order_reviews_dataset.csv",
    "geolocation":          "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

LOAD_ORDER = [
    "customers",
    "sellers",
    "products",
    "orders",
    "order_items",
    "order_payments",
    "order_reviews",
    "geolocation",
    "category_translation",
]

def get_server_engine():
    """Engine tanpa default database untuk memastikan database ada/dibuat."""
    url = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)

def get_db_engine():
    """Engine ke database oltp_olist."""
    url = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)

def init_schema():
    print(f"\n[1/2] 🔨 Memeriksa / mengeksekusi DDL sql/01_oltp_ddl.sql pada {DB_NAME}...")
    server_engine = get_server_engine()
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4;"))
        conn.commit()

    db_engine = get_db_engine()
    schema_path = BASE_DIR / "sql" / "01_oltp_ddl.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]
    with db_engine.begin() as conn:
        for stmt in statements:
            if stmt.upper().startswith("CREATE DATABASE") or stmt.upper().startswith("USE"):
                continue
            conn.execute(text(stmt))
    print(" -> Schema DDL berhasil dipersiapkan.")

def load_data(db_engine):
    print("\n[2/2] 🗄️ Memuat data CSV Brazil ke tabel 3NF OLTP...")

    # Truncate tables first to ensure idempotency
    with db_engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        for tbl in LOAD_ORDER:
            conn.execute(text(f"TRUNCATE TABLE `{tbl}`;"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

    for tbl in LOAD_ORDER:
        filename = CSV_MAP[tbl]
        file_path = CSV_DIR / filename
        if not file_path.exists():
            print(f" ⚠️ File tidak ditemukan: {file_path}, lewati tabel `{tbl}`.")
            continue

        df = pd.read_csv(file_path)

        # Penyesuaian spesifik per tabel
        if tbl == "geolocation":
            # Rename kolom geolocation_zip_code_prefix->zip_code_prefix, geolocation_city->city, geolocation_state->state
            df = df.rename(columns={
                "geolocation_zip_code_prefix": "zip_code_prefix",
                "geolocation_city": "city",
                "geolocation_state": "state",
            })
        elif tbl == "products":
            # Rename product_name_lenght->product_name_length, product_description_lenght->product_description_length
            df = df.rename(columns={
                "product_name_lenght": "product_name_length",
                "product_description_lenght": "product_description_length",
            })

        df.to_sql(tbl, db_engine, if_exists="append", index=False, chunksize=1000)

        with db_engine.connect() as conn:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM `{tbl}`;")).scalar()
            print(f" -> `{tbl}`: {cnt:,} baris terisi.")

def main():
    start_time = time.time()
    print("=" * 60)
    print(f"🚀 LOAD DATASET OLIST BRAZIL KE MYSQL ({DB_NAME})")
    print("=" * 60)
    print(f"Host     : {DB_HOST}:{DB_PORT}")
    print(f"User     : {DB_USER}")
    print(f"Database : {DB_NAME}")
    print(f"Data Dir : {CSV_DIR}")
    print("=" * 60)

    try:
        init_schema()
        db_engine = get_db_engine()
        load_data(db_engine)
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"✨ BERHASIL MEMUAT SELURUH DATA OLTP BRAZIL ({elapsed:.2f} detik) ✨")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ TERJADI KESALAHAN: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

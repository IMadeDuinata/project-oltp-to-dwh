"""
Script Loader CSV Olist Indonesia ke MySQL Database `olist_oltp_id`.
Alur:
1. Jalankan schema_indo.sql (CREATE DATABASE & CREATE TABLES)
2. Load data staging ke olist_raw
3. Load data ke tabel 3NF normalisasi (JANGAN clean — pertahankan data karakteristik apa adanya)
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
DB_PORT = int(os.getenv("DB_PORT_OLTP_ID", "3307"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = "olist_oltp_id"
CSV_DIR = BASE_DIR / "data" / "olist_id"

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
    """Engine ke database olist_oltp_id."""
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
    print("\n[1/3] 🔨 Menjalankan DDL schema_indo.sql...")
    server_engine = get_server_engine()
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4;"))
        conn.commit()

    db_engine = get_db_engine()
    schema_path = BASE_DIR / "oltp_id" / "schema_indo.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split statements
    statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]
    with db_engine.begin() as conn:
        for stmt in statements:
            if stmt.upper().startswith("CREATE DATABASE") or stmt.upper().startswith("USE"):
                continue
            conn.execute(text(stmt))
    print(" -> Schema DDL berhasil dieksekusi.")

def load_staging(db_engine):
    print("\n[2/3] 📥 Memuat data flat ke tabel staging `olist_raw`...")
    # Truncate staging table
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE olist_raw;"))

    df_orders = pd.read_csv(CSV_DIR / "orders.csv")
    df_items = pd.read_csv(CSV_DIR / "order_items.csv")
    df_cust = pd.read_csv(CSV_DIR / "customers.csv").drop_duplicates(subset=["customer_id"])
    df_prod = pd.read_csv(CSV_DIR / "products.csv")
    df_sellers = pd.read_csv(CSV_DIR / "sellers.csv")
    df_payments = pd.read_csv(CSV_DIR / "order_payments.csv")

    # Merge flat representation
    df_flat = df_items.merge(df_orders, on="order_id", how="left")
    df_flat = df_flat.merge(df_cust, on="customer_id", how="left")
    df_flat = df_flat.merge(df_prod, on="product_id", how="left")
    df_flat = df_flat.merge(df_sellers, on="seller_id", how="left")
    df_flat = df_flat.merge(df_payments, on="order_id", how="left")

    staging_cols = [
        "order_id", "order_item_id", "product_id", "seller_id",
        "seller_zip_code_prefix", "seller_city", "seller_state",
        "shipping_limit_date", "price", "freight_value",
        "payment_sequential", "payment_type", "payment_installments", "payment_value",
        "customer_id", "customer_unique_id", "customer_zip_code_prefix",
        "customer_city", "customer_state", "order_status",
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date", "product_category_name",
        "product_category_name_original", "product_name_lenght",
        "product_description_lenght", "product_photos_qty",
        "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"
    ]
    
    # Keep only available columns
    available_cols = [c for c in staging_cols if c in df_flat.columns]
    df_staging = df_flat[available_cols].copy()

    # Load in chunks
    df_staging.to_sql("olist_raw", db_engine, if_exists="append", index=False, chunksize=1000)
    print(f" -> Berhasil memuat {len(df_staging):,} baris ke `olist_raw`.")

def load_3nf(db_engine):
    print("\n[3/3] 🗄️ Memuat data ke tabel-tabel 3NF OLTP...")
    
    # Truncate tables first to make it idempotent
    tables = [
        ("category_translation", "category_translation.csv"),
        ("customers", "customers.csv"),
        ("sellers", "sellers.csv"),
        ("products", "products.csv"),
        ("orders", "orders.csv"),
        ("order_items", "order_items.csv"),
        ("order_payments", "order_payments.csv"),
        ("order_reviews", "order_reviews.csv"),
        ("geolocation", "geolocation.csv"),
    ]

    # Disable FK checks temporarily for truncate
    with db_engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        for tbl, _ in tables:
            conn.execute(text(f"TRUNCATE TABLE `{tbl}`;"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

    for tbl, filename in tables:
        file_path = CSV_DIR / filename
        df = pd.read_csv(file_path)

        # Handling specific tables
        if tbl == "customers":
            # If duplicates cause PK conflict, we keep first for PK table or let ignore
            # Spec states: customers has duplicate rows intentionally. We use INSERT IGNORE
            df.to_sql("temp_customers", db_engine, if_exists="replace", index=False)
            with db_engine.begin() as conn:
                conn.execute(text("""
                    INSERT IGNORE INTO customers (customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state)
                    SELECT customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state
                    FROM temp_customers;
                """))
                conn.execute(text("DROP TABLE temp_customers;"))
        elif tbl == "geolocation":
            # Rename columns to match schema
            df_geo = df.rename(columns={
                "geolocation_zip_code_prefix": "zip_code_prefix",
                "geolocation_city": "city",
                "geolocation_state": "state"
            })
            df_geo.to_sql(tbl, db_engine, if_exists="append", index=False, chunksize=1000)
        elif tbl == "products":
            # Product lengths name mapping
            df_p = df.rename(columns={
                "product_name_lenght": "product_name_length",
                "product_description_lenght": "product_description_length"
            })
            df_p.to_sql(tbl, db_engine, if_exists="append", index=False, chunksize=1000)
        else:
            df.to_sql(tbl, db_engine, if_exists="append", index=False, chunksize=1000)

        with db_engine.connect() as conn:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM `{tbl}`;")).scalar()
            print(f" -> `{tbl}`: {cnt:,} baris terisi.")

def main():
    start_time = time.time()
    print("=" * 60)
    print(f"🚀 LOAD DATASET OLIST INDONESIA KE MYSQL ({DB_NAME})")
    print("=" * 60)
    print(f"Host     : {DB_HOST}:{DB_PORT}")
    print(f"User     : {DB_USER}")
    print(f"Database : {DB_NAME}")
    print(f"Data Dir : {CSV_DIR}")
    print("=" * 60)

    try:
        init_schema()
        db_engine = get_db_engine()
        load_staging(db_engine)
        load_3nf(db_engine)
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"✨ BERHASIL MEMUAT SELURUH DATA OLTP INDONESIA ({elapsed:.2f} detik) ✨")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ TERJADI KESALAHAN: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

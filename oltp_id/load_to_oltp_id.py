"""
Loader CSV Olist Indonesia ke MySQL OLTP (olist_oltp_id).
"""

import os
import sys
import time
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT_OLTP_ID", "3307"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = "olist_oltp_id"
CSV_DIR = BASE_DIR / "data" / "olist_id"

TABLES_3NF = [
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

COLUMN_RENAMES = {
    "geolocation": {
        "geolocation_zip_code_prefix": "zip_code_prefix",
        "geolocation_city": "city",
        "geolocation_state": "state",
    },
    "products": {
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    },
}


def get_engine(database: str | None = None):
    url = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=database,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)


def init_schema():
    print("\n[1/3] Menjalankan DDL schema_indo.sql...")
    server_engine = get_engine()
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4;"))
        conn.commit()

    db_engine = get_engine(database=DB_NAME)
    schema_path = BASE_DIR / "oltp_id" / "schema_indo.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    statements = [s.strip() for s in sql_content.split(";") if s.strip()]
    with db_engine.begin() as conn:
        for stmt in statements:
            if stmt.upper().startswith("CREATE DATABASE") or stmt.upper().startswith("USE"):
                continue
            conn.execute(text(stmt))
    print(" -> Schema DDL berhasil dieksekusi.")


def load_staging(db_engine):
    print("\n[2/3] Memuat data flat ke tabel staging `olist_raw`...")
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE olist_raw;"))

    df_orders = pd.read_csv(CSV_DIR / "orders.csv")
    df_items = pd.read_csv(CSV_DIR / "order_items.csv")
    df_cust = pd.read_csv(CSV_DIR / "customers.csv").drop_duplicates(subset=["customer_id"])
    df_prod = pd.read_csv(CSV_DIR / "products.csv")
    df_sellers = pd.read_csv(CSV_DIR / "sellers.csv")
    df_payments = pd.read_csv(CSV_DIR / "order_payments.csv")

    df_flat = (
        df_items.merge(df_orders, on="order_id", how="left")
        .merge(df_cust, on="customer_id", how="left")
        .merge(df_prod, on="product_id", how="left")
        .merge(df_sellers, on="seller_id", how="left")
        .merge(df_payments, on="order_id", how="left")
    )

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
        "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm",
    ]
    available_cols = [c for c in staging_cols if c in df_flat.columns]
    df_flat[available_cols].to_sql("olist_raw", db_engine, if_exists="append", index=False, chunksize=1000)
    print(f" -> Berhasil memuat {len(df_flat):,} baris ke `olist_raw`.")


def load_3nf(db_engine):
    print("\n[3/3] Memuat data ke tabel-tabel 3NF OLTP...")
    with db_engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        for tbl, _ in TABLES_3NF:
            conn.execute(text(f"TRUNCATE TABLE `{tbl}`;"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

    for tbl, filename in TABLES_3NF:
        file_path = CSV_DIR / filename
        df = pd.read_csv(file_path)

        if tbl in COLUMN_RENAMES:
            df = df.rename(columns=COLUMN_RENAMES[tbl])

        if tbl == "customers":
            df.to_sql("temp_customers", db_engine, if_exists="replace", index=False)
            with db_engine.begin() as conn:
                conn.execute(text("""
                    INSERT IGNORE INTO customers (customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state)
                    SELECT customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state
                    FROM temp_customers;
                """))
                conn.execute(text("DROP TABLE temp_customers;"))
        else:
            df.to_sql(tbl, db_engine, if_exists="append", index=False, chunksize=1000)

        with db_engine.connect() as conn:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM `{tbl}`;")).scalar()
            print(f" -> `{tbl}`: {cnt:,} baris terisi.")


def main():
    start_time = time.time()
    print("=" * 60)
    print(f"LOAD DATASET OLIST INDONESIA KE MYSQL ({DB_NAME})")
    print("=" * 60)
    print(f"Host     : {DB_HOST}:{DB_PORT}")
    print(f"Database : {DB_NAME}")
    print("=" * 60)

    try:
        init_schema()
        db_engine = get_engine(database=DB_NAME)
        load_staging(db_engine)
        load_3nf(db_engine)
        elapsed = time.time() - start_time
        print(f"\nBerhasil memuat seluruh data OLTP Indonesia ({elapsed:.2f} detik).")
    except Exception as e:
        print(f"\nTerjadi kesalahan: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

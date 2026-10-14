"""
Script untuk membuat Star Schema di database dwh_olist.
- Membuat 5 tabel dimensi:
    dim_customer (SCD Type 2), dim_product, dim_seller, dim_payment_type, dim_date
- Membuat 2 tabel fakta:
    fact_order_items (grain: order_id + order_item_id)
    fact_order_delivery (grain: order_id)
- Membuat tabel pendukung (Support Tables):
    etl_log, rejected_rows, etl_watermark
- Memastikan record Unknown (-1) terpasang di setiap dimensi
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secret")
DB_NAME_DWH = os.getenv("DB_NAME_DWH", "dwh_olist")

url = URL.create(
    drivername="mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME_DWH,
    query={"charset": "utf8mb4"},
)
engine = create_engine(url, pool_pre_ping=True)


def execute_sql_file(file_path: str):
    print(f"📄 Menjalankan file DDL: `{file_path}`...")
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        clean_lines.append(line)

    sql = "".join(clean_lines)
    queries = sql.split(";")
    with engine.begin() as conn:
        for q in queries:
            q = q.strip()
            if q and not q.upper().startswith("CREATE DATABASE") and not q.upper().startswith("USE"):
                conn.execute(text(q))


def setup_unknown_records():
    """Memasang record Unknown (-1) pada semua dimensi agar FK orphan tidak dibuang."""
    print("🛡️  Memverifikasi record Unknown (sk = -1) di tabel dimensi...")
    
    statements = [
        """
        INSERT IGNORE INTO dim_customer (
            customer_sk, customer_id, customer_unique_id, customer_zip_code, customer_city, customer_state, valid_from, is_current
        ) VALUES (
            -1, 'UNKNOWN', 'UNKNOWN', '00000', 'unknown', 'NA', '1970-01-01 00:00:00', 1
        )
        """,
        """
        INSERT IGNORE INTO dim_product (
            product_sk, product_id, product_category_name, product_name_length, product_description_length,
            product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm
        ) VALUES (
            -1, 'UNKNOWN', 'unknown', 0, 0, 0, 0, 0, 0, 0
        )
        """,
        """
        INSERT IGNORE INTO dim_seller (
            seller_sk, seller_id, seller_zip_code, seller_city, seller_state
        ) VALUES (
            -1, 'UNKNOWN', '00000', 'unknown', 'NA'
        )
        """,
        """
        INSERT IGNORE INTO dim_payment_type (
            payment_type_sk, payment_type
        ) VALUES (
            -1, 'unknown'
        )
        """,
        """
        INSERT IGNORE INTO dim_date (
            date_sk, full_date, day, month, month_name, quarter, year, day_of_week, is_weekend
        ) VALUES (
            -1, '1970-01-01', 1, 1, 'January', 1, 1970, 'Thursday', 0
        )
        """
    ]

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    print("   ✅ Record Unknown (-1) terpasang di semua dimensi.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Create Star Schema in DWH")
    parser.add_argument("--recreate", action="store_true", help="Drop existing tables before creating")
    args = parser.parse_args()

    print("=" * 60)
    print("🏗️  MEMBUAT STAR SCHEMA DAN SUPPORT TABLES DI DWH")
    print("=" * 60)
    
    if args.recreate:
        print("🧹 Menghapus tabel lama di DWH...")
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=0;"))
            drop_tables = [
                "fact_order_items", "fact_order_delivery", "fact_order_payments",
                "dim_customer", "dim_product", "dim_seller",
                "dim_payment_type", "dim_date",
                "etl_log", "rejected_rows", "etl_watermark"
            ]
            for t in drop_tables:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`;"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1;"))
        print("   ✅ Tabel lama telah dibersihkan.")

    # 1. Jalankan 02_dwh_ddl.sql
    execute_sql_file("sql/02_dwh_ddl.sql")
    
    # 2. Jalankan 03_support_tables.sql
    execute_sql_file("sql/03_support_tables.sql")
    
    # 3. Setup unknown records
    setup_unknown_records()
    
    print("\n🔍 Verifikasi tabel di dwh_olist:")
    with engine.connect() as conn:
        res = conn.execute(text("SHOW TABLES"))
        tables = [r[0] for r in res]
        for t in sorted(tables):
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
            print(f"   • {t:22s} : {cnt:>6,} baris")

    print("\n" + "=" * 60)
    print("🎉 STAR SCHEMA & SUPPORT TABLES BERHASIL DIBUAT!")
    print("=" * 60)


if __name__ == "__main__":
    main()
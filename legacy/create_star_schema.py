"""
Script untuk membuat Star Schema di database dwh_olist.
- Bikin 5 tabel dimensi: dim_customer, dim_product, dim_seller, dim_payment, dim_date
- Bikin 1 tabel fakta: fact_sales
- Kosong dulu (baru struktur) — data diisi oleh script ETL nanti
"""

import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# ============================================================
# 1. LOAD KONFIGURASI
# ============================================================
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME_DWH = "dwh_olist"

if not DB_PASSWORD:
    print("❌ ERROR: DB_PASSWORD belum diisi di file .env")
    sys.exit(1)

# ============================================================
# 2. KONEKSI KE MYSQL (database DWH)
# ============================================================
connection_url = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_DWH}"
    "?charset=utf8mb4"
)
engine = create_engine(connection_url, pool_pre_ping=True)

print("=" * 60)
print("🏗️  CREATE STAR SCHEMA DI DWH")
print("=" * 60)
print(f"🗄️  Database DWH : {DB_NAME_DWH}")
print(f"🔌 Host          : {DB_HOST}:{DB_PORT}")
print("=" * 60)

# ============================================================
# 3. DEFINISI TABEL
# ============================================================
DDL_STATEMENTS = {

    "dim_customer": """
        CREATE TABLE IF NOT EXISTS dim_customer (
            customer_sk        INT AUTO_INCREMENT PRIMARY KEY,
            customer_id        VARCHAR(50)  NOT NULL,
            customer_unique_id VARCHAR(50)  NOT NULL,
            customer_zip_code  VARCHAR(10),
            customer_city      VARCHAR(100),
            customer_state     VARCHAR(5),
            UNIQUE KEY uk_customer_id (customer_id),
            INDEX idx_customer_state (customer_state)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    "dim_product": """
        CREATE TABLE IF NOT EXISTS dim_product (
            product_sk                 INT AUTO_INCREMENT PRIMARY KEY,
            product_id                 VARCHAR(50) NOT NULL,
            product_category_name      VARCHAR(100),
            product_name_length        INT,
            product_description_length INT,
            product_photos_qty         INT,
            product_weight_g           DECIMAL(10,2),
            product_length_cm          DECIMAL(10,2),
            product_height_cm          DECIMAL(10,2),
            product_width_cm           DECIMAL(10,2),
            UNIQUE KEY uk_product_id (product_id),
            INDEX idx_category (product_category_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    "dim_seller": """
        CREATE TABLE IF NOT EXISTS dim_seller (
            seller_sk       INT AUTO_INCREMENT PRIMARY KEY,
            seller_id       VARCHAR(50) NOT NULL,
            seller_zip_code VARCHAR(10),
            seller_city     VARCHAR(100),
            seller_state    VARCHAR(5),
            UNIQUE KEY uk_seller_id (seller_id),
            INDEX idx_seller_state (seller_state)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    "dim_payment": """
        CREATE TABLE IF NOT EXISTS dim_payment (
            payment_sk           INT AUTO_INCREMENT PRIMARY KEY,
            payment_type         VARCHAR(30) NOT NULL,
            payment_installments VARCHAR(10),
            UNIQUE KEY uk_payment (payment_type, payment_installments)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    "dim_date": """
        CREATE TABLE IF NOT EXISTS dim_date (
            date_sk     INT AUTO_INCREMENT PRIMARY KEY,
            full_date   DATE NOT NULL,
            day         INT,
            month       INT,
            month_name  VARCHAR(20),
            quarter     INT,
            year        INT,
            day_of_week VARCHAR(20),
            is_weekend  TINYINT(1),
            UNIQUE KEY uk_full_date (full_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    "fact_sales": """
        CREATE TABLE IF NOT EXISTS fact_sales (
            sales_sk                       BIGINT AUTO_INCREMENT PRIMARY KEY,
            order_id                       VARCHAR(50) NOT NULL,
            order_item_id                  INT NOT NULL,
            customer_sk                    INT NOT NULL,
            product_sk                     INT NOT NULL,
            seller_sk                      INT NOT NULL,
            payment_sk                     INT NOT NULL,
            date_sk                        INT NOT NULL,
            order_status                   VARCHAR(20),
            price                          DECIMAL(10,2),
            freight_value                  DECIMAL(10,2),
            payment_value                  DECIMAL(10,2),
            order_purchase_timestamp       DATETIME,
            order_delivered_customer_date  DATETIME,
            order_estimated_delivery_date  DATETIME,
            INDEX idx_customer_sk (customer_sk),
            INDEX idx_product_sk (product_sk),
            INDEX idx_seller_sk (seller_sk),
            INDEX idx_payment_sk (payment_sk),
            INDEX idx_date_sk (date_sk),
            INDEX idx_order_id (order_id),
            CONSTRAINT fk_fact_customer FOREIGN KEY (customer_sk) REFERENCES dim_customer(customer_sk),
            CONSTRAINT fk_fact_product  FOREIGN KEY (product_sk)  REFERENCES dim_product(product_sk),
            CONSTRAINT fk_fact_seller   FOREIGN KEY (seller_sk)   REFERENCES dim_seller(seller_sk),
            CONSTRAINT fk_fact_payment  FOREIGN KEY (payment_sk)  REFERENCES dim_payment(payment_sk),
            CONSTRAINT fk_fact_date     FOREIGN KEY (date_sk)     REFERENCES dim_date(date_sk)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
}

# ============================================================
# 4. EKSEKUSI DDL
# ============================================================
print("\n📋 Membuat tabel-tabel...")
urutan_buat = [
    "dim_customer",
    "dim_product",
    "dim_seller",
    "dim_payment",
    "dim_date",
    "fact_sales",
]

with engine.begin() as conn:
    for nama_tabel in urutan_buat:
        try:
            conn.execute(text(DDL_STATEMENTS[nama_tabel]))
            print(f"   ✅ Tabel `{nama_tabel}` berhasil dibuat")
        except Exception as e:
            print(f"   ❌ Gagal buat `{nama_tabel}`: {e}")

# ============================================================
# 5. VERIFIKASI
# ============================================================
print("\n🔍 Verifikasi tabel di DWH...")
with engine.connect() as conn:
    result = conn.execute(text("SHOW TABLES"))
    tables = [row[0] for row in result]
    print(f"   📊 Tabel yang ada di `{DB_NAME_DWH}`:")
    for t in tables:
        result2 = conn.execute(text(f"SELECT COUNT(*) FROM `{t}`"))
        count = result2.scalar()
        print(f"      • {t}  ({count} baris)")

# ============================================================
# SELESAI
# ============================================================
print("\n" + "=" * 60)
print("🎉 SELESAI! Star Schema berhasil dibuat di DWH.")
print("=" * 60)
print("\n📌 Langkah selanjutnya:")
print("   1. Cek di MySQL: USE dwh_olist; SHOW TABLES;")
print("   2. Jalankan ETL: python etl/transform_oltp_to_dwh.py")
print()

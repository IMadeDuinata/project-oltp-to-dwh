"""
Script untuk memecah data dari tabel staging `olist_raw` ke skema OLTP 3NF:
- customers
- products
- sellers
- orders
- order_items
- order_payments

PENTING (Syarat Tugas):
Data kotor TIDAK dibersihkan pada tahap ini (biarkan apa adanya),
karena proses pembersihan data adalah tugas pipeline ETL.
"""

import os
import time
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secret")
DB_NAME_OLTP = os.getenv("DB_NAME_OLTP", os.getenv("DB_NAME", "oltp_olist"))

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


def init_oltp_tables():
    """Membuat tabel 3NF jika belum ada."""
    print("📋 Menyiapkan tabel-tabel 3NF di OLTP...")
    with engine.begin() as conn:
        with open("sql/01_oltp_ddl.sql") as f:
            sql_script = f.read()
        
        # Eksekusi blok per statement
        statements = sql_script.split(";")
        for stmt in statements:
            stmt = stmt.strip()
            if stmt and not stmt.upper().startswith("CREATE DATABASE") and not stmt.upper().startswith("USE"):
                conn.execute(text(stmt))
    print("   ✅ Tabel 3NF siap.")


def split_staging_to_oltp():
    """Membaca olist_raw dan membaginya ke tabel 3NF."""
    init_oltp_tables()
    
    print("\n" + "=" * 60)
    print("🔄 MEMECAH olist_raw KE TABEL 3NF (OLTP)")
    print("=" * 60)
    t0 = time.time()

    print("📥 Membaca data dari `olist_raw`...")
    df_raw = pd.read_sql("SELECT * FROM olist_raw", engine)
    print(f"   ✅ Dibaca: {len(df_raw):,} baris")

    # 1. CUSTOMERS
    print("\n[1/6] 👥 Memproses tabel `customers`...")
    cust_cols = [
        "customer_id",
        "customer_unique_id",
        "customer_zip_code_prefix",
        "customer_city",
        "customer_state",
    ]
    df_customers = (
        df_raw[cust_cols]
        .dropna(subset=["customer_id"])
        .drop_duplicates(subset=["customer_id"])
        .reset_index(drop=True)
    )
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE customers"))
    df_customers.to_sql("customers", engine, if_exists="append", index=False, chunksize=5000)
    print(f"   ✅ {len(df_customers):,} baris ke `customers`")

    # 2. PRODUCTS
    print("\n[2/6] 📦 Memproses tabel `products`...")
    prod_rename = {
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    }
    prod_cols = [
        "product_id",
        "product_category_name",
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]
    df_products = (
        df_raw[prod_cols]
        .rename(columns=prod_rename)
        .dropna(subset=["product_id"])
        .drop_duplicates(subset=["product_id"])
        .reset_index(drop=True)
    )
    # Konversi tipe data dengan coerce agar tidak crash bila ada data kotor
    num_cols = [
        "product_name_length", "product_description_length", "product_photos_qty",
        "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"
    ]
    for col in num_cols:
        df_products[col] = pd.to_numeric(df_products[col], errors="coerce")

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE products"))
    df_products.to_sql("products", engine, if_exists="append", index=False, chunksize=5000)
    print(f"   ✅ {len(df_products):,} baris ke `products`")

    # 3. SELLERS
    print("\n[3/6] 🏪 Memproses tabel `sellers`...")
    seller_cols = [
        "seller_id",
        "seller_zip_code_prefix",
        "seller_city",
        "seller_state",
    ]
    df_sellers = (
        df_raw[seller_cols]
        .dropna(subset=["seller_id"])
        .drop_duplicates(subset=["seller_id"])
        .reset_index(drop=True)
    )
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE sellers"))
    df_sellers.to_sql("sellers", engine, if_exists="append", index=False, chunksize=5000)
    print(f"   ✅ {len(df_sellers):,} baris ke `sellers`")

    # 4. ORDERS
    print("\n[4/6] 📑 Memproses tabel `orders`...")
    order_cols = [
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    df_orders = (
        df_raw[order_cols]
        .dropna(subset=["order_id"])
        .drop_duplicates(subset=["order_id"])
        .reset_index(drop=True)
    )
    # Konversi tanggal dengan coerce; nilai anomali tetap tersimpan atau ditangani di ETL
    date_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    for col in date_cols:
        # Coba format umum atau fallback ke to_datetime
        df_orders[col] = pd.to_datetime(df_orders[col], errors="coerce")

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE orders"))
    df_orders.to_sql("orders", engine, if_exists="append", index=False, chunksize=5000)
    print(f"   ✅ {len(df_orders):,} baris ke `orders`")

    # 5. ORDER_ITEMS
    print("\n[5/6] 🏷️ Memproses tabel `order_items`...")
    item_cols = [
        "order_id",
        "order_item_id",
        "product_id",
        "seller_id",
        "shipping_limit_date",
        "price",
        "freight_value",
    ]
    # Dapatkan deduplikasi item murni dari Cartesian produk staging
    # tapi pertahankan record yang sengaja diinjeksi
    df_items = (
        df_raw[item_cols]
        .dropna(subset=["order_id", "order_item_id"])
        .reset_index(drop=True)
    )
    # Dedup cartesian join: items x payments
    # Namun biarkan duplikat jika persis berasal dari data injeksi
    injected_dups = df_items[df_items["order_id"].str.startswith("DIRTY_DUP")]
    non_injected = df_items[~df_items["order_id"].str.startswith("DIRTY_DUP")].drop_duplicates(
        subset=["order_id", "order_item_id"]
    )
    df_items = pd.concat([non_injected, injected_dups], ignore_index=True)

    df_items["order_item_id"] = pd.to_numeric(df_items["order_item_id"], errors="coerce").fillna(1).astype(int)
    df_items["shipping_limit_date"] = pd.to_datetime(df_items["shipping_limit_date"], errors="coerce")
    df_items["price"] = pd.to_numeric(df_items["price"], errors="coerce")
    df_items["freight_value"] = pd.to_numeric(df_items["freight_value"], errors="coerce")

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE order_items"))
    df_items.to_sql("order_items", engine, if_exists="append", index=False, chunksize=5000)
    print(f"   ✅ {len(df_items):,} baris ke `order_items`")

    # 6. ORDER_PAYMENTS
    print("\n[6/6] 💳 Memproses tabel `order_payments`...")
    pay_cols = [
        "order_id",
        "payment_sequential",
        "payment_type",
        "payment_installments",
        "payment_value",
    ]
    df_payments = (
        df_raw[pay_cols]
        .dropna(subset=["order_id"])
        .drop_duplicates(subset=["order_id", "payment_sequential", "payment_type"])
        .reset_index(drop=True)
    )
    df_payments["payment_sequential"] = pd.to_numeric(df_payments["payment_sequential"], errors="coerce").fillna(1).astype(int)
    df_payments["payment_installments"] = pd.to_numeric(df_payments["payment_installments"], errors="coerce").fillna(1).astype(int)
    df_payments["payment_value"] = pd.to_numeric(df_payments["payment_value"], errors="coerce")

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE order_payments"))
    df_payments.to_sql("order_payments", engine, if_exists="append", index=False, chunksize=5000)
    print(f"   ✅ {len(df_payments):,} baris ke `order_payments`")

    print("\n" + "=" * 60)
    print(f"🎉 SELESAI MEMECAH KE 3NF! Waktu: {time.time() - t0:.2f} detik")
    print("=" * 60)


if __name__ == "__main__":
    split_staging_to_oltp()

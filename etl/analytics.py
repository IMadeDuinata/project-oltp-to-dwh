"""
Analytics: Query analitik dari DWH (star schema).
Menjawab pertanyaan bisnis dari data Olist.
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# ============================================================
# 1. KONEKSI
# ============================================================
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME_DWH = "dwh_olist"

engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME_DWH}?charset=utf8mb4",
    pool_pre_ping=True
)


def run_query(title, sql):
    """Helper: jalankan query & tampilkan hasilnya."""
    print("\n" + "=" * 70)
    print(f"📊 {title}")
    print("=" * 70)
    df = pd.read_sql(sql, engine)
    print(df.to_string(index=False))
    return df


print("=" * 70)
print("📈 ANALISIS DATA OLIST — BUSINESS INSIGHTS")
print("=" * 70)


# ============================================================
# 1. TOTAL REVENUE PER TAHUN
# ============================================================
run_query("1. TOTAL REVENUE PER TAHUN", """
    SELECT 
        dd.year,
        COUNT(*) AS jumlah_transaksi,
        ROUND(SUM(fs.price), 2) AS total_revenue,
        ROUND(AVG(fs.price), 2) AS rata_rata_harga
    FROM fact_sales fs
    JOIN dim_date dd ON fs.date_sk = dd.date_sk
    GROUP BY dd.year
    ORDER BY dd.year
""")


# ============================================================
# 2. TOP 10 KATEGORI PRODUK (BY REVENUE)
# ============================================================
run_query("2. TOP 10 KATEGORI PRODUK — BY REVENUE", """
    SELECT 
        dp.product_category_name AS kategori,
        COUNT(*) AS jumlah_terjual,
        ROUND(SUM(fs.price), 2) AS total_revenue
    FROM fact_sales fs
    JOIN dim_product dp ON fs.product_sk = dp.product_sk
    WHERE dp.product_category_name IS NOT NULL
    GROUP BY dp.product_category_name
    ORDER BY total_revenue DESC
    LIMIT 10
""")


# ============================================================
# 3. TOP 10 STATE (PROVINSI) PELANGGAN
# ============================================================
run_query("3. TOP 10 STATE PELANGGAN — BY JUMLAH ORDER", """
    SELECT 
        dc.customer_state AS state,
        COUNT(DISTINCT fs.order_id) AS jumlah_order,
        ROUND(SUM(fs.price), 2) AS total_revenue
    FROM fact_sales fs
    JOIN dim_customer dc ON fs.customer_sk = dc.customer_sk
    GROUP BY dc.customer_state
    ORDER BY jumlah_order DESC
    LIMIT 10
""")


# ============================================================
# 4. DISTRIBUSI PAYMENT TYPE
# ============================================================
run_query("4. DISTRIBUSI METODE PEMBAYARAN", """
    SELECT 
        dpm.payment_type AS metode,
        COUNT(*) AS jumlah_transaksi,
        ROUND(SUM(fs.payment_value), 2) AS total_value,
        ROUND(AVG(fs.payment_value), 2) AS rata_rata
    FROM fact_sales fs
    JOIN dim_payment dpm ON fs.payment_sk = dpm.payment_sk
    GROUP BY dpm.payment_type
    ORDER BY total_value DESC
""")


# ============================================================
# 5. REVENUE PER BULAN (TIME SERIES)
# ============================================================
run_query("5. TREN REVENUE PER BULAN (2017-2018)", """
    SELECT 
        dd.year,
        dd.month,
        dd.month_name,
        COUNT(*) AS jumlah_order,
        ROUND(SUM(fs.price), 2) AS revenue
    FROM fact_sales fs
    JOIN dim_date dd ON fs.date_sk = dd.date_sk
    WHERE dd.year IN (2017, 2018)
    GROUP BY dd.year, dd.month, dd.month_name
    ORDER BY dd.year, dd.month
""")


# ============================================================
# 6. TOP 10 SELLER
# ============================================================
run_query("6. TOP 10 SELLER — BY REVENUE", """
    SELECT 
        ds.seller_id,
        ds.seller_state AS state,
        COUNT(*) AS jumlah_terjual,
        ROUND(SUM(fs.price), 2) AS total_revenue
    FROM fact_sales fs
    JOIN dim_seller ds ON fs.seller_sk = ds.seller_sk
    GROUP BY ds.seller_id, ds.seller_state
    ORDER BY total_revenue DESC
    LIMIT 10
""")


# ============================================================
# 7. RATA-RATA WAKTU PENGIRIMAN
# ============================================================
run_query("7. RATA-RATA WAKTU PENGIRIMAN (HARI)", """
    SELECT 
        dd.year,
        dd.month,
        ROUND(AVG(DATEDIFF(fs.order_delivered_customer_date, fs.order_purchase_timestamp)), 2) AS rata_rata_hari,
        COUNT(*) AS jumlah_order
    FROM fact_sales fs
    JOIN dim_date dd ON fs.date_sk = dd.date_sk
    WHERE fs.order_delivered_customer_date IS NOT NULL
      AND dd.year IN (2017, 2018)
    GROUP BY dd.year, dd.month
    ORDER BY dd.year, dd.month
""")


# ============================================================
# 8. STATUS ORDER BREAKDOWN
# ============================================================
run_query("8. BREAKDOWN STATUS ORDER", """
    SELECT 
        order_status,
        COUNT(*) AS jumlah,
        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM fact_sales), 2) AS persentase
    FROM fact_sales
    GROUP BY order_status
    ORDER BY jumlah DESC
""")


print("\n" + "=" * 70)
print("🎉 ANALISIS SELESAI!")
print("=" * 70)
print("\n💡 Insight yang bisa diambil dari query di atas:")
print("   • Revenue tertinggi terjadi di tahun berapa?")
print("   • Kategori produk apa yang paling menguntungkan?")
print("   • State mana yang paling banyak order?")
print("   • Metode pembayaran favorit customer?")
print("   • Bulan apa penjualan tertinggi?")
print()
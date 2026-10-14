"""
Script Analitik Data Warehouse Olist (Star Schema).
Query bisnis yang telah disesuaikan dengan grain skema baru:
- Menghitung order menggunakan COUNT(DISTINCT order_id)
- Tidak menduplikasi nilai pembayaran atau menggabungkan metrik item dan order secara keliru
- Menggunakan role-playing dimensions (dim_date)
- Menyertakan minimal 2 query analitik canggih yang menggabungkan kedua tabel fakta:
  (fact_order_items dan fact_order_delivery)
"""

import os
import sys
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from etl.config import get_dwh_engine

engine = get_dwh_engine()


def run_query(title: str, sql: str) -> pd.DataFrame:
    """Helper untuk menjalankan dan mencetak hasil query dengan rapi."""
    print("\n" + "=" * 75)
    print(f"📊 {title}")
    print("=" * 75)
    df = pd.read_sql(sql, engine)
    print(df.to_string(index=False))
    return df


def main():
    print("=" * 75)
    print("📈 ANALISIS DATA WAREHOUSE OLIST — BUSINESS INSIGHTS")
    print("=" * 75)

    # 1. TOTAL REVENUE & ORDER PER TAHUN (Grain: fact_order_items)
    run_query(
        "1. TOTAL REVENUE DAN JUMLAH ORDER PER TAHUN",
        """
        SELECT 
            dd.year,
            COUNT(DISTINCT foi.order_id) AS jumlah_order,
            COUNT(foi.order_item_sk) AS jumlah_item_terjual,
            ROUND(SUM(foi.price), 2) AS total_revenue_rp,
            ROUND(SUM(foi.freight_value), 2) AS total_ongkir_rp,
            ROUND(AVG(foi.price), 2) AS avg_harga_item
        FROM fact_order_items foi
        JOIN dim_date dd ON foi.purchase_date_sk = dd.date_sk
        GROUP BY dd.year
        ORDER BY dd.year
        """
    )

    # 2. TOP 10 KATEGORI PRODUK (BY REVENUE)
    run_query(
        "2. TOP 10 KATEGORI PRODUK DENGAN REVENUE TERTINGGI",
        """
        SELECT 
            dp.product_category_name AS kategori,
            COUNT(DISTINCT foi.order_id) AS jumlah_order,
            COUNT(foi.order_item_sk) AS jumlah_item,
            ROUND(SUM(foi.price), 2) AS total_revenue
        FROM fact_order_items foi
        JOIN dim_product dp ON foi.product_sk = dp.product_sk
        GROUP BY dp.product_category_name
        ORDER BY total_revenue DESC
        LIMIT 10
        """
    )

    # 3. TOP 10 PROVINSI PELANGGAN (BY ORDER & REVENUE)
    run_query(
        "3. TOP 10 STATE PELANGGAN — BERDASARKAN JUMLAH ORDER",
        """
        SELECT 
            dc.customer_state AS state,
            COUNT(DISTINCT foi.order_id) AS jumlah_order,
            ROUND(SUM(foi.price), 2) AS total_revenue,
            ROUND(AVG(foi.price), 2) AS avg_belanja_per_item
        FROM fact_order_items foi
        JOIN dim_customer dc ON foi.customer_sk = dc.customer_sk
        GROUP BY dc.customer_state
        ORDER BY jumlah_order DESC
        LIMIT 10
        """
    )

    # 4. TREN PENJUALAN BULANAN (TIME SERIES 2017-2018)
    run_query(
        "4. TREN PENJUALAN BULANAN (2017 - 2018)",
        """
        SELECT 
            dd.year,
            dd.month,
            dd.month_name,
            COUNT(DISTINCT foi.order_id) AS jumlah_order,
            ROUND(SUM(foi.price), 2) AS total_revenue
        FROM fact_order_items foi
        JOIN dim_date dd ON foi.purchase_date_sk = dd.date_sk
        WHERE dd.year IN (2017, 2018)
        GROUP BY dd.year, dd.month, dd.month_name
        ORDER BY dd.year, dd.month
        LIMIT 12
        """
    )

    # 5. TOP 10 SELLER DENGAN PENJUALAN TERTINGGI
    run_query(
        "5. TOP 10 SELLER — BERDASARKAN TOTAL REVENUE",
        """
        SELECT 
            ds.seller_id,
            ds.seller_state,
            COUNT(DISTINCT foi.order_id) AS jumlah_order,
            ROUND(SUM(foi.price), 2) AS total_revenue
        FROM fact_order_items foi
        JOIN dim_seller ds ON foi.seller_sk = ds.seller_sk
        GROUP BY ds.seller_id, ds.seller_state
        ORDER BY total_revenue DESC
        LIMIT 10
        """
    )

    # 6. PERFORMA LOGISTIK: RATA-RATA WAKTU PENGIRIMAN (Grain: fact_order_delivery)
    run_query(
        "6. RATA-RATA WAKTU PENGIRIMAN & ESTIMASI PER BULAN (HARI)",
        """
        SELECT 
            dd.year,
            dd.month,
            dd.month_name,
            COUNT(fod.order_delivery_sk) AS total_pengiriman,
            ROUND(AVG(fod.actual_delivery_days), 2) AS avg_hari_aktual,
            ROUND(AVG(fod.estimated_delivery_days), 2) AS avg_hari_estimasi,
            ROUND(AVG(fod.delivery_delay_days), 2) AS avg_selisih_estimasi
        FROM fact_order_delivery fod
        JOIN dim_date dd ON fod.purchase_date_sk = dd.date_sk
        WHERE dd.year IN (2017, 2018) AND fod.actual_delivery_days IS NOT NULL
        GROUP BY dd.year, dd.month, dd.month_name
        ORDER BY dd.year, dd.month
        LIMIT 10
        """
    )

    # 7. TINGKAT KETERLAMBATAN PENGIRIMAN PER PROVINSI (Grain: fact_order_delivery)
    run_query(
        "7. TINGKAT KETERLAMBATAN PENGIRIMAN (DELAY RATE) PER PROVINSI",
        """
        SELECT 
            dc.customer_state AS state,
            COUNT(fod.order_delivery_sk) AS total_order,
            SUM(fod.is_delayed) AS order_terlambat,
            ROUND(100.0 * SUM(fod.is_delayed) / COUNT(fod.order_delivery_sk), 2) AS persentase_telat_pct,
            ROUND(AVG(fod.actual_delivery_days), 2) AS avg_hari_sampai
        FROM fact_order_delivery fod
        JOIN dim_customer dc ON fod.customer_sk = dc.customer_sk
        WHERE fod.actual_delivery_days IS NOT NULL
        GROUP BY dc.customer_state
        HAVING total_order > 100
        ORDER BY persentase_telat_pct DESC
        LIMIT 10
        """
    )

    # 8. QUERY GABUNGAN FAKTA 1 & FAKTA 2 (Query Multi-Fact A)
    # Analisis: Apakah order bernilai tinggi (high ticket) memiliki kecenderungan telat yang lebih rendah?
    run_query(
        "8. [MULTI-FACT QUERY 1] KORELASI NILAI ORDER DENGAN TINGKAT KETERLAMBATAN",
        """
        WITH order_revenues AS (
            SELECT 
                order_id,
                SUM(price) AS order_total_price
            FROM fact_order_items
            GROUP BY order_id
        )
        SELECT 
            CASE 
                WHEN r.order_total_price < 50 THEN '1. Low Value (< R$ 50)'
                WHEN r.order_total_price BETWEEN 50 AND 200 THEN '2. Medium Value (R$ 50 - 200)'
                WHEN r.order_total_price BETWEEN 200 AND 500 THEN '3. High Value (R$ 200 - 500)'
                ELSE '4. Premium (> R$ 500)'
            END AS tier_nilai_order,
            COUNT(d.order_delivery_sk) AS total_order,
            SUM(d.is_delayed) AS total_terlambat,
            ROUND(100.0 * SUM(d.is_delayed) / COUNT(d.order_delivery_sk), 2) AS delay_rate_pct,
            ROUND(AVG(d.actual_delivery_days), 2) AS avg_hari_pengiriman
        FROM fact_order_delivery d
        JOIN order_revenues r ON d.order_id = r.order_id
        WHERE d.actual_delivery_days IS NOT NULL
        GROUP BY tier_nilai_order
        ORDER BY tier_nilai_order
        """
    )

    # 9. QUERY GABUNGAN FAKTA 1 & FAKTA 2 (Query Multi-Fact B)
    # Analisis: Performa pengiriman dan ketepatan waktu untuk Top 10 Kategori Produk Terlaris
    run_query(
        "9. [MULTI-FACT QUERY 2] PERFORMA LOGISTIK PADA TOP 10 KATEGORI PRODUK TERLARIS",
        """
        SELECT 
            dp.product_category_name AS kategori_produk,
            COUNT(DISTINCT foi.order_id) AS total_order,
            ROUND(SUM(foi.price), 2) AS total_revenue,
            ROUND(AVG(fod.actual_delivery_days), 2) AS avg_hari_pengiriman,
            ROUND(100.0 * SUM(fod.is_delayed) / COUNT(DISTINCT foi.order_id), 2) AS delay_rate_pct
        FROM fact_order_items foi
        JOIN dim_product dp ON foi.product_sk = dp.product_sk
        JOIN fact_order_delivery fod ON foi.order_id = fod.order_id
        WHERE fod.actual_delivery_days IS NOT NULL
        GROUP BY dp.product_category_name
        ORDER BY total_revenue DESC
        LIMIT 10
        """
    )

    # 10. DISTRIBUSI METODE PEMBAYARAN (fact_order_payments)
    run_query(
        "10. DISTRIBUSI METODE PEMBAYARAN — REVENUE & ORDER COUNT (fact_order_payments)",
        """
        SELECT
            dpt.payment_type                           AS metode_pembayaran,
            COUNT(DISTINCT fop.order_id)               AS jumlah_order,
            COUNT(fop.payment_fact_sk)                 AS jumlah_transaksi,
            ROUND(SUM(fop.payment_value), 2)           AS total_nilai_pembayaran,
            ROUND(AVG(fop.payment_value), 2)           AS rata_rata_per_transaksi,
            ROUND(AVG(fop.payment_installments), 2)    AS rata_rata_cicilan
        FROM fact_order_payments fop
        JOIN dim_payment_type dpt ON fop.payment_type_sk = dpt.payment_type_sk
        WHERE dpt.payment_type != 'unknown'
        GROUP BY dpt.payment_type
        ORDER BY total_nilai_pembayaran DESC
        """
    )

    # 11. ANALISIS CICILAN PER TIPE PEMBAYARAN DAN SEGMEN NILAI ORDER
    run_query(
        "11. ANALISIS CICILAN PER METODE PEMBAYARAN & SEGMEN NILAI (fact_order_payments)",
        """
        SELECT
            dpt.payment_type                        AS metode_pembayaran,
            CASE
                WHEN fop.payment_value < 50   THEN '1. Kecil (< R$ 50)'
                WHEN fop.payment_value < 200  THEN '2. Sedang (R$ 50-200)'
                WHEN fop.payment_value < 500  THEN '3. Tinggi (R$ 200-500)'
                ELSE '4. Premium (> R$ 500)'
            END                                     AS segmen_nilai,
            COUNT(fop.payment_fact_sk)              AS jumlah_transaksi,
            ROUND(AVG(fop.payment_installments), 2) AS avg_cicilan,
            ROUND(SUM(fop.payment_value), 2)        AS total_nilai
        FROM fact_order_payments fop
        JOIN dim_payment_type dpt ON fop.payment_type_sk = dpt.payment_type_sk
        WHERE dpt.payment_type != 'unknown'
        GROUP BY dpt.payment_type, segmen_nilai
        ORDER BY dpt.payment_type, segmen_nilai
        """
    )

    print("\n" + "=" * 75)
    print("🎉 SEMUA QUERY ANALITIK SELESAI DIEKSEKUSI!")
    print("=" * 75)


if __name__ == "__main__":
    main()
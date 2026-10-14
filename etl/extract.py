"""
Modul Extract: Membaca data dari database OLTP (oltp_olist).
Mendukung:
1. Full Extract
2. Incremental Extract menggunakan watermark (order_purchase_timestamp)
"""

import os
import sys
import logging
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from sqlalchemy import text

from etl.config import get_oltp_engine, get_dwh_engine

logger = logging.getLogger(__name__)


def get_last_watermark(pipeline_name="olist_pipeline") -> datetime | None:
    """Mengambil nilai watermark terakhir dari tabel dwh_olist.etl_watermark."""
    dwh_engine = get_dwh_engine()
    query = text("""
        SELECT last_watermark_value 
        FROM etl_watermark 
        WHERE pipeline_name = :pname
    """)
    try:
        with dwh_engine.connect() as conn:
            res = conn.execute(query, {"pname": pipeline_name}).scalar()
            if res:
                return pd.to_datetime(res)
    except Exception as e:
        logger.warning(f"Tidak dapat membaca watermark: {e}")
    return None


def update_watermark(new_watermark_value: str, pipeline_name="olist_pipeline"):
    """Menyimpan nilai watermark baru ke dwh_olist.etl_watermark."""
    dwh_engine = get_dwh_engine()
    query = text("""
        INSERT INTO etl_watermark (pipeline_name, watermark_column, last_watermark_value, updated_at)
        VALUES (:pname, 'order_purchase_timestamp', :wval, NOW())
        ON DUPLICATE KEY UPDATE 
            last_watermark_value = VALUES(last_watermark_value),
            updated_at = NOW()
    """)
    with dwh_engine.begin() as conn:
        conn.execute(query, {"pname": pipeline_name, "wval": str(new_watermark_value)})


def extract_oltp_data(incremental: bool = False, pipeline_name="olist_pipeline") -> dict[str, pd.DataFrame]:
    """
    Mengekstrak data dari semua tabel 3NF OLTP.
    Jika incremental=True, orders dan order_items/payments difilter berdasarkan watermark.
    """
    oltp_engine = get_oltp_engine()
    data = {}
    
    logger.info(f"Memulai extract dari OLTP (incremental={incremental})...")

    # Tabel Master selalu diekstrak penuh untuk sinkronisasi dimensi
    master_tables = ["customers", "products", "sellers"]
    for tbl in master_tables:
        logger.info(f"Extract tabel `{tbl}`...")
        df = pd.read_sql(f"SELECT * FROM `{tbl}`", oltp_engine)
        data[tbl] = df
        logger.info(f"  -> {len(df):,} baris diekstrak dari `{tbl}`")

    watermark = get_last_watermark(pipeline_name) if incremental else None

    if incremental and watermark:
        logger.info(f"Extract incremental dengan watermark order_purchase_timestamp > '{watermark}'")
        order_query = text("SELECT * FROM orders WHERE order_purchase_timestamp > :wm")
        df_orders = pd.read_sql(order_query, oltp_engine, params={"wm": watermark})
        data["orders"] = df_orders

        # Extract items dan payments untuk orders yang masuk
        if not df_orders.empty:
            order_ids = tuple(df_orders["order_id"].tolist())
            # Potong ke chunk jika order_id sangat banyak
            items_query = text(f"SELECT * FROM order_items WHERE order_id IN :oids")
            pay_query = text(f"SELECT * FROM order_payments WHERE order_id IN :oids")
            data["order_items"] = pd.read_sql(items_query, oltp_engine, params={"oids": order_ids})
            data["order_payments"] = pd.read_sql(pay_query, oltp_engine, params={"oids": order_ids})
        else:
            data["order_items"] = pd.DataFrame()
            data["order_payments"] = pd.DataFrame()
    else:
        logger.info("Extract full load untuk orders, items, dan payments...")
        data["orders"] = pd.read_sql("SELECT * FROM orders", oltp_engine)
        data["order_items"] = pd.read_sql("SELECT * FROM order_items", oltp_engine)
        data["order_payments"] = pd.read_sql("SELECT * FROM order_payments", oltp_engine)

    logger.info(f"  -> {len(data['orders']):,} baris dari `orders`")
    logger.info(f"  -> {len(data['order_items']):,} baris dari `order_items`")
    logger.info(f"  -> {len(data['order_payments']):,} baris dari `order_payments`")
    
    return data


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    data = extract_oltp_data(incremental=False)
    print("\nRingkasan Ekstraksi:")
    for k, v in data.items():
        print(f"  - {k:15s}: {len(v):,} baris")


if __name__ == "__main__":
    main()

"""
Modul Extract: Membaca data dari dual-source database OLTP (Brazil dan Indonesia).
Mendukung:
1. Full Extract (kedua source)
2. Incremental Extract menggunakan watermark (hanya untuk Brazil saat ini)
3. Source tagging kolom `source_country` ('BR' / 'ID')
"""

import os
import sys
import logging
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from sqlalchemy import text

from etl.config import (
    get_oltp_engine,
    get_oltp_br_engine,
    get_oltp_id_engine,
    get_dwh_engine,
)

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


def extract_from_source(
    engine,
    source_country: str,
    incremental: bool = False,
    watermark: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Ekstrak data dari satu source database OLTP dan beri tag kolom `source_country`.
    Tabel yang diekstrak: customers, products, sellers, orders, order_items, order_payments.
    """
    prefix = f"[{source_country}]"
    data: dict[str, pd.DataFrame] = {}
    logger.info(f"{prefix} Memulai extract (incremental={incremental})...")

    # Tabel Master selalu diekstrak penuh
    master_tables = ["customers", "products", "sellers"]
    for tbl in master_tables:
        logger.info(f"{prefix} Extract tabel `{tbl}`...")
        df = pd.read_sql(f"SELECT * FROM `{tbl}`", engine)
        data[tbl] = df
        logger.info(f"{prefix}   -> {len(df):,} baris diekstrak dari `{tbl}`")

    # Ekstrak orders, items, payments
    if incremental and watermark:
        logger.info(f"{prefix} Extract incremental dengan watermark order_purchase_timestamp > '{watermark}'")
        order_query = text("SELECT * FROM orders WHERE order_purchase_timestamp > :wm")
        df_orders = pd.read_sql(order_query, engine, params={"wm": watermark})
        data["orders"] = df_orders

        if not df_orders.empty:
            order_ids = tuple(df_orders["order_id"].tolist())
            items_query = text("SELECT * FROM order_items WHERE order_id IN :oids")
            pay_query = text("SELECT * FROM order_payments WHERE order_id IN :oids")
            data["order_items"] = pd.read_sql(items_query, engine, params={"oids": order_ids})
            data["order_payments"] = pd.read_sql(pay_query, engine, params={"oids": order_ids})
        else:
            data["order_items"] = pd.DataFrame()
            data["order_payments"] = pd.DataFrame()
    else:
        logger.info(f"{prefix} Extract full load untuk orders, items, dan payments...")
        data["orders"] = pd.read_sql("SELECT * FROM orders", engine)
        data["order_items"] = pd.read_sql("SELECT * FROM order_items", engine)
        data["order_payments"] = pd.read_sql("SELECT * FROM order_payments", engine)

    logger.info(f"{prefix}   -> {len(data['orders']):,} baris dari `orders`")
    logger.info(f"{prefix}   -> {len(data['order_items']):,} baris dari `order_items`")
    logger.info(f"{prefix}   -> {len(data['order_payments']):,} baris dari `order_payments`")

    # Tagging source_country pada setiap tabel
    for tbl in ["customers", "products", "sellers", "orders", "order_items", "order_payments"]:
        if tbl in data and not data[tbl].empty:
            data[tbl]["source_country"] = source_country
        elif tbl in data:
            data[tbl]["source_country"] = pd.Series(dtype="object")

    return data


def extract_oltp_data(incremental: bool = False, pipeline_name="olist_pipeline") -> dict[str, pd.DataFrame]:
    """
    Orchestrator dual-source extract:
    - Mengekstrak data dari Brazil (BR) menggunakan engine BR (incremental didukung).
    - Mengekstrak data dari Indonesia (ID) menggunakan engine ID (selalu full load untuk saat ini).
    - Menggabungkan data per tabel dan menghasilkan dict gabungan dengan tag source_country.
    """
    logger.info(f"Memulai dual-source extract (incremental={incremental}, pipeline={pipeline_name})...")

    # 1. Source Brazil
    engine_br = get_oltp_br_engine()
    watermark_br = get_last_watermark(pipeline_name) if incremental else None
    data_br = extract_from_source(
        engine=engine_br,
        source_country="BR",
        incremental=incremental,
        watermark=watermark_br,
    )

    # 2. Source Indonesia
    # Catatan: ID selalu full extract pada fase ini karena timestamp formatnya campur / VARCHAR
    engine_id = get_oltp_id_engine()
    data_id = extract_from_source(
        engine=engine_id,
        source_country="ID",
        incremental=False,
        watermark=None,
    )

    # 3. Penggabungan per tabel
    combined_data: dict[str, pd.DataFrame] = {}
    tables = ["customers", "products", "sellers", "orders", "order_items", "order_payments"]

    for tbl in tables:
        df_br = data_br.get(tbl, pd.DataFrame())
        df_id = data_id.get(tbl, pd.DataFrame())

        # Deteksi tipe kolom yang tidak cocok antar source untuk logging warning
        common_cols = set(df_br.columns).intersection(set(df_id.columns))
        for col in common_cols:
            dtype_br = df_br[col].dtype
            dtype_id = df_id[col].dtype
            if dtype_br != dtype_id:
                logger.warning(
                    f"Schema mismatch terdeteksi pada tabel `{tbl}`, kolom `{col}`: "
                    f"BR ({dtype_br}) vs ID ({dtype_id}). Akan diserahkan ke reconcile/clean phase."
                )

        combined_df = pd.concat([df_br, df_id], ignore_index=True)
        combined_data[tbl] = combined_df
        logger.info(f"[COMBINED] `{tbl}`: total {len(combined_df):,} baris ({len(df_br):,} BR + {len(df_id):,} ID)")

    return combined_data


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    data = extract_oltp_data(incremental=False)
    print("\nRingkasan Ekstraksi Dual-Source:")
    for k, v in data.items():
        br_cnt = len(v[v["source_country"] == "BR"]) if "source_country" in v.columns else 0
        id_cnt = len(v[v["source_country"] == "ID"]) if "source_country" in v.columns else 0
        print(f"  - {k:15s}: {len(v):,} total baris ({br_cnt:,} BR, {id_cnt:,} ID)")


if __name__ == "__main__":
    main()

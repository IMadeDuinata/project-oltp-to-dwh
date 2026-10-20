"""
Modul Extract: Ekstraksi data dari dual-source OLTP (Brazil & Indonesia) serta Physical Staging Area.
"""

import os
import sys
import logging
from datetime import datetime
from typing import Callable, Optional
import pandas as pd
from sqlalchemy import text

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from etl.config import (
    get_oltp_br_engine,
    get_oltp_id_engine,
    get_dwh_engine,
    get_staging_engine,
)

logger = logging.getLogger(__name__)

STAGING_MAP = {
    "customers": "stg_customers",
    "products": "stg_products",
    "sellers": "stg_sellers",
    "orders": "stg_orders",
    "order_items": "stg_order_items",
    "order_payments": "stg_order_payments",
}


def get_last_watermark(pipeline_name: str = "olist_pipeline") -> datetime | None:
    """Mengambil nilai watermark terakhir dari tabel dwh_olist.etl_watermark."""
    query = text("SELECT last_watermark_value FROM etl_watermark WHERE pipeline_name = :pname")
    try:
        with get_dwh_engine().connect() as conn:
            res = conn.execute(query, {"pname": pipeline_name}).scalar()
            return pd.to_datetime(res) if res else None
    except Exception as e:
        logger.warning(f"Tidak dapat membaca watermark: {e}")
        return None


def update_watermark(new_watermark_value: str, pipeline_name: str = "olist_pipeline") -> None:
    """Menyimpan nilai watermark baru ke dwh_olist.etl_watermark."""
    query = text("""
        INSERT INTO etl_watermark (pipeline_name, watermark_column, last_watermark_value, updated_at)
        VALUES (:pname, 'order_purchase_timestamp', :wval, NOW())
        ON DUPLICATE KEY UPDATE 
            last_watermark_value = VALUES(last_watermark_value),
            updated_at = NOW()
    """)
    with get_dwh_engine().begin() as conn:
        conn.execute(query, {"pname": pipeline_name, "wval": str(new_watermark_value)})


def extract_from_source(
    engine,
    source_country: str,
    incremental: bool = False,
    watermark: datetime | None = None,
    on_progress: Optional[Callable[[str, int, int], None]] = None,
) -> dict[str, pd.DataFrame]:
    """Ekstrak tabel-tabel OLTP dari satu source engine dan beri tag kolom `source_country`."""
    prefix = f"[{source_country}]"
    data: dict[str, pd.DataFrame] = {}
    logger.info(f"{prefix} Memulai extract (incremental={incremental})...")

    # 1. Master Tables (Selalu diekstrak penuh)
    master_tables = ["customers", "products", "sellers"]
    for idx, tbl in enumerate(master_tables, start=1):
        df = pd.read_sql(f"SELECT * FROM `{tbl}`", engine)
        data[tbl] = df
        logger.info(f"{prefix} `{tbl}`: {len(df):,} baris")
        if on_progress:
            on_progress(f"{prefix} {tbl}", idx, 6)

    # 2. Transaction Tables
    if incremental and watermark:
        logger.info(f"{prefix} Incremental extract > '{watermark}'")
        order_query = text("SELECT * FROM orders WHERE order_purchase_timestamp > :wm")
        df_orders = pd.read_sql(order_query, engine, params={"wm": watermark})
        data["orders"] = df_orders

        if not df_orders.empty:
            order_ids = tuple(df_orders["order_id"].tolist())
            data["order_items"] = pd.read_sql(text("SELECT * FROM order_items WHERE order_id IN :oids"), engine, params={"oids": order_ids})
            data["order_payments"] = pd.read_sql(text("SELECT * FROM order_payments WHERE order_id IN :oids"), engine, params={"oids": order_ids})
        else:
            data["order_items"] = pd.DataFrame()
            data["order_payments"] = pd.DataFrame()
    else:
        for tbl in ["orders", "order_items", "order_payments"]:
            data[tbl] = pd.read_sql(f"SELECT * FROM `{tbl}`", engine)

    for idx, tbl in enumerate(["orders", "order_items", "order_payments"], start=4):
        logger.info(f"{prefix} `{tbl}`: {len(data[tbl]):,} baris")
        if on_progress:
            on_progress(f"{prefix} {tbl}", idx, 6)

    # Tagging source_country
    for tbl in list(STAGING_MAP.keys()):
        if tbl in data:
            data[tbl]["source_country"] = source_country if not data[tbl].empty else pd.Series(dtype="object")

    return data


def extract_oltp_data(
    incremental: bool = False,
    pipeline_name: str = "olist_pipeline",
    on_progress: Optional[Callable[[str, int, int], None]] = None,
) -> dict[str, pd.DataFrame]:
    """Orkestrator ekstraksi gabungan dari OLTP Brazil dan Indonesia."""
    logger.info(f"Memulai dual-source extract (incremental={incremental}, pipeline={pipeline_name})...")

    data_br = extract_from_source(
        engine=get_oltp_br_engine(),
        source_country="BR",
        incremental=incremental,
        watermark=get_last_watermark(pipeline_name) if incremental else None,
        on_progress=on_progress,
    )

    data_id = extract_from_source(
        engine=get_oltp_id_engine(),
        source_country="ID",
        incremental=False,
        watermark=None,
        on_progress=on_progress,
    )

    combined_data: dict[str, pd.DataFrame] = {}
    for tbl in STAGING_MAP.keys():
        df_br = data_br.get(tbl, pd.DataFrame())
        df_id = data_id.get(tbl, pd.DataFrame())
        combined_df = pd.concat([df_br, df_id], ignore_index=True)
        combined_data[tbl] = combined_df
        logger.info(f"[COMBINED] `{tbl}`: {len(combined_df):,} baris ({len(df_br):,} BR + {len(df_id):,} ID)")

    return combined_data


def load_oltp_to_staging(
    raw_data: dict[str, pd.DataFrame] | None = None,
    incremental: bool = False,
    pipeline_name: str = "olist_pipeline",
    on_progress: Optional[Callable[[str, int, int], None]] = None,
) -> dict[str, int]:
    """Memuat data hasil extract OLTP ke tabel staging fisik di database dwh_staging."""
    if raw_data is None:
        raw_data = extract_oltp_data(incremental=incremental, pipeline_name=pipeline_name, on_progress=on_progress)

    stg_engine = get_staging_engine()
    counts = {}

    with stg_engine.begin() as conn:
        for entity, stg_table in STAGING_MAP.items():
            if entity not in raw_data or raw_data[entity].empty:
                continue

            df = raw_data[entity].copy()
            df["_source_country"] = df["source_country"]
            df["_extracted_at"] = datetime.now()
            df_stg = df.drop(columns=[c for c in ["source_country"] if c in df.columns])

            if not incremental:
                conn.execute(text(f"TRUNCATE TABLE `{stg_table}`"))

            df_stg.to_sql(stg_table, conn, if_exists="append", index=False, chunksize=2000)
            counts[stg_table] = len(df_stg)
            logger.info(f"Staging `{stg_table}`: {len(df_stg):,} baris termuat.")

    return counts


def extract_from_staging() -> dict[str, pd.DataFrame]:
    """Mengekstrak data mentah dari database staging fisik dwh_staging."""
    stg_engine = get_staging_engine()
    data: dict[str, pd.DataFrame] = {}

    with stg_engine.connect() as conn:
        for entity, stg_table in STAGING_MAP.items():
            df = pd.read_sql(f"SELECT * FROM `{stg_table}`", conn)
            if "_source_country" in df.columns:
                df["source_country"] = df["_source_country"]
                df = df.drop(columns=["_source_country"])
            drop_cols = [c for c in ["_stg_id", "_extracted_at"] if c in df.columns]
            if drop_cols:
                df = df.drop(columns=drop_cols)
            data[entity] = df
            logger.info(f"Extract staging `{stg_table}`: {len(df):,} baris.")

    return data


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

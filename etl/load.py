"""
Modul Load: Memuat tabel dimensi (Upsert / SCD2) dan fakta ke Data Warehouse (dwh_olist).
"""

import json
import logging
from datetime import datetime
from typing import Callable, Optional
import pandas as pd
from sqlalchemy import text

from etl.config import get_dwh_engine

logger = logging.getLogger(__name__)


def upsert_dimension(table_name: str, df: pd.DataFrame, key_col: str, sk_col: str) -> None:
    """Melakukan upsert (INSERT ... ON DUPLICATE KEY UPDATE) ke tabel dimensi secara batch."""
    if df.empty:
        return

    engine = get_dwh_engine()
    unknown_rows = df[df.get(sk_col) == -1] if sk_col in df.columns else pd.DataFrame()
    normal_rows = df[df.get(sk_col) != -1] if sk_col in df.columns else df

    # Pastikan record UNKNOWN (-1) terpasang via INSERT IGNORE
    if not unknown_rows.empty:
        with engine.begin() as conn:
            cols = [f"`{c}`" for c in unknown_rows.columns]
            placeholders = [f":{c}" for c in unknown_rows.columns]
            sql_unk = f"INSERT IGNORE INTO `{table_name}` ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
            for _, r in unknown_rows.iterrows():
                conn.execute(text(sql_unk), r.to_dict())

    if normal_rows.empty:
        return

    # Normalisasi missing values ke None untuk MySQL NULL
    normal_rows = normal_rows.copy().astype(object).where(pd.notna(normal_rows), None)
    insert_cols = [c for c in normal_rows.columns if c != sk_col]
    update_cols = [c for c in insert_cols if c != key_col and c != "valid_from"]

    col_str = ", ".join([f"`{c}`" for c in insert_cols])
    val_placeholders = ", ".join([f":{c}" for c in insert_cols])

    if update_cols:
        update_str = ", ".join([f"`{c}` = VALUES(`{c}`)" for c in update_cols])
        sql = f"INSERT INTO `{table_name}` ({col_str}) VALUES ({val_placeholders}) ON DUPLICATE KEY UPDATE {update_str}"
    else:
        sql = f"INSERT IGNORE INTO `{table_name}` ({col_str}) VALUES ({val_placeholders})"

    records = normal_rows[insert_cols].to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if pd.isna(v) or v is pd.NaT:
                r[k] = None

    chunk_size = 3000
    with engine.begin() as conn:
        for i in range(0, len(records), chunk_size):
            conn.execute(text(sql), records[i:i + chunk_size])
    logger.info(f"Upsert {len(normal_rows):,} baris ke `{table_name}` selesai.")


def upsert_dim_customer_scd2(df_incoming: pd.DataFrame) -> None:
    """Implementasi SCD Type 2 untuk dim_customer (menutup versi lama, membuka versi baru)."""
    if df_incoming.empty:
        return

    engine = get_dwh_engine()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Pastikan row UNKNOWN terdaftar
    unknown_rows = df_incoming[df_incoming.get("customer_sk") == -1] if "customer_sk" in df_incoming.columns else pd.DataFrame()
    normal_df = df_incoming[df_incoming.get("customer_sk") != -1].copy() if "customer_sk" in df_incoming.columns else df_incoming.copy()

    if not unknown_rows.empty:
        with engine.begin() as conn:
            for _, r in unknown_rows.iterrows():
                conn.execute(text("""
                    INSERT IGNORE INTO dim_customer
                    (customer_sk, customer_id, customer_unique_id, customer_zip_code, customer_city, customer_state, valid_from, is_current)
                    VALUES (:sk, :cid, :cuid, :zip, :city, :state, :vf, 1)
                """), {
                    "sk": int(r.get("customer_sk", -1)),
                    "cid": r.get("customer_id", "UNKNOWN"),
                    "cuid": r.get("customer_unique_id", "UNKNOWN"),
                    "zip": r.get("customer_zip_code", "00000"),
                    "city": r.get("customer_city", "unknown"),
                    "state": r.get("customer_state", "NA"),
                    "vf": r.get("valid_from", "1970-01-01 00:00:00"),
                })

    if normal_df.empty:
        return

    # 2. Ambil snapshot versi aktif (is_current = 1)
    with engine.connect() as conn:
        existing_df = pd.read_sql(
            "SELECT customer_sk, customer_unique_id, customer_city, customer_state, customer_zip_code "
            "FROM dim_customer WHERE is_current = 1 AND customer_sk != -1",
            conn,
        )

    existing_map = {
        row["customer_unique_id"]: {
            "customer_sk": int(row["customer_sk"]),
            "customer_city": str(row["customer_city"] or "").lower().strip(),
            "customer_state": str(row["customer_state"] or "").lower().strip(),
            "customer_zip_code": str(row["customer_zip_code"] or "").strip(),
        }
        for _, row in existing_df.iterrows()
    }

    # 3. Klasifikasi insert baru vs update versi SCD2
    to_close_sks = []
    to_insert = []
    scd_attrs = ["customer_city", "customer_state", "customer_zip_code"]

    for _, row in normal_df.iterrows():
        cuid = row.get("customer_unique_id")
        if not cuid or cuid == "UNKNOWN" or pd.isna(cuid):
            continue

        incoming_vals = {
            "customer_city": str(row.get("customer_city", "") or "").lower().strip(),
            "customer_state": str(row.get("customer_state", "") or "").lower().strip(),
            "customer_zip_code": str(row.get("customer_zip_code", "") or "").strip(),
        }

        new_record = {
            "customer_id": row.get("customer_id", ""),
            "customer_unique_id": cuid,
            "customer_zip_code": incoming_vals["customer_zip_code"],
            "customer_city": incoming_vals["customer_city"],
            "customer_state": incoming_vals["customer_state"],
            "valid_from": now,
            "valid_to": None,
            "is_current": 1,
        }

        if cuid not in existing_map:
            to_insert.append(new_record)
        else:
            ex = existing_map[cuid]
            if any(incoming_vals[attr] != ex[attr] for attr in scd_attrs):
                to_close_sks.append(ex["customer_sk"])
                to_insert.append(new_record)

    # 4. Terapkan perubahan ke database
    with engine.begin() as conn:
        if to_close_sks:
            for i in range(0, len(to_close_sks), 1000):
                conn.execute(text("""
                    UPDATE dim_customer
                    SET is_current = 0, valid_to = :vt
                    WHERE customer_sk IN :sks AND is_current = 1
                """), {"vt": now, "sks": tuple(to_close_sks[i:i + 1000])})

        if to_insert:
            df_new = pd.DataFrame(to_insert).where(pd.notna(pd.DataFrame(to_insert)), None)
            records = df_new.to_dict(orient="records")
            insert_sql = text("""
                INSERT INTO dim_customer
                (customer_id, customer_unique_id, customer_zip_code, customer_city, customer_state, valid_from, valid_to, is_current)
                VALUES
                (:customer_id, :customer_unique_id, :customer_zip_code, :customer_city, :customer_state, :valid_from, :valid_to, :is_current)
            """)
            for i in range(0, len(records), 3000):
                conn.execute(insert_sql, records[i:i + 3000])

    logger.info(f"SCD2 dim_customer: {len(to_close_sks)} ditutup, {len(to_insert)} dibuka/baru.")


def load_all_dimensions(dimensions: dict, on_progress: Optional[Callable[[str, int, int], None]] = None) -> dict:
    """Memuat seluruh tabel dimensi dan mengembalikan map Business Key -> Surrogate Key."""
    engine = get_dwh_engine()
    total_dims = 5

    # 1. Dim Date
    if "dim_date" in dimensions:
        if on_progress:
            on_progress("dim_date", 1, total_dims)
        df_date = dimensions["dim_date"]
        with engine.begin() as conn:
            cols = ", ".join([f"`{c}`" for c in df_date.columns])
            vals = ", ".join([f":{c}" for c in df_date.columns])
            conn.execute(text(f"INSERT IGNORE INTO dim_date ({cols}) VALUES ({vals})"), df_date.to_dict(orient="records"))

    # 2. Dim Customer (SCD Type 2)
    if "dim_customer" in dimensions:
        if on_progress:
            on_progress("dim_customer", 2, total_dims)
        upsert_dim_customer_scd2(dimensions["dim_customer"])

    # 3. Dimensi Standar
    standard_dims = [
        ("dim_product", "product_id", "product_sk", 3),
        ("dim_seller", "seller_id", "seller_sk", 4),
        ("dim_payment_type", "payment_type", "payment_type_sk", 5),
    ]
    for tbl, key_col, sk_col, step_idx in standard_dims:
        if tbl in dimensions:
            if on_progress:
                on_progress(tbl, step_idx, total_dims)
            upsert_dimension(tbl, dimensions[tbl], key_col=key_col, sk_col=sk_col)

    # Baca kembali SK mappings untuk pembuatan fakta
    with engine.connect() as conn:
        cust_df = pd.read_sql("SELECT customer_id, customer_sk FROM dim_customer WHERE is_current = 1", conn)
        prod_df = pd.read_sql("SELECT product_id, product_sk FROM dim_product", conn)
        sell_df = pd.read_sql("SELECT seller_id, seller_sk FROM dim_seller", conn)
        pay_df = pd.read_sql("SELECT payment_type, payment_type_sk FROM dim_payment_type", conn)

    return {
        "cust_sk_map": dict(zip(cust_df["customer_id"], cust_df["customer_sk"])),
        "prod_sk_map": dict(zip(prod_df["product_id"], prod_df["product_sk"])),
        "seller_sk_map": dict(zip(sell_df["seller_id"], sell_df["seller_sk"])),
        "pay_sk_map": dict(zip(pay_df["payment_type"], pay_df["payment_type_sk"])),
    }


def load_facts_transactional(
    fact_order_items: pd.DataFrame,
    fact_order_delivery: pd.DataFrame,
    fact_order_payments: pd.DataFrame,
    incremental: bool = False,
    order_ids: list | None = None,
    on_progress: Optional[Callable[[str, int, int], None]] = None,
) -> int:
    """Memuat tabel fakta secara transaksional dan idempotent."""
    engine = get_dwh_engine()
    total_loaded = 0
    fact_tables = [
        ("fact_order_items", fact_order_items),
        ("fact_order_delivery", fact_order_delivery),
        ("fact_order_payments", fact_order_payments),
    ]

    with engine.begin() as conn:
        if incremental and order_ids:
            chunk_size = 2000
            for i in range(0, len(order_ids), chunk_size):
                sub_ids = tuple(order_ids[i:i + chunk_size])
                for tbl, _ in fact_tables:
                    conn.execute(text(f"DELETE FROM `{tbl}` WHERE order_id IN :oids"), {"oids": sub_ids})
        elif not incremental:
            for tbl, _ in reversed(fact_tables):
                conn.execute(text(f"DELETE FROM `{tbl}`"))

        for idx, (tbl, df) in enumerate(fact_tables, start=1):
            df.to_sql(tbl, con=conn, if_exists="append", index=False, chunksize=5000, method="multi")
            total_loaded += len(df)
            if on_progress:
                on_progress(tbl, idx, len(fact_tables))

    logger.info(f"Berhasil memuat total {total_loaded:,} baris fakta.")
    return total_loaded


def load_rejected_rows(rejections: list, run_id: str) -> None:
    """Menyimpan seluruh baris kotor yang ditolak ke tabel rejected_rows."""
    if not rejections:
        return

    engine = get_dwh_engine()
    for r in rejections:
        r["run_id"] = run_id

    df_rej = pd.DataFrame(rejections)
    with engine.begin() as conn:
        df_rej.to_sql("rejected_rows", con=conn, if_exists="append", index=False, chunksize=2000)
    logger.info(f"Tersimpan {len(rejections):,} baris karantina (run_id={run_id}).")


def log_etl_execution(
    run_id: str,
    pipeline_name: str,
    start_time: datetime,
    end_time: datetime,
    status: str,
    rows_in: int,
    rows_clean: int,
    rows_rejected: int,
    rows_loaded: int,
    error_message: str | None = None,
    table_stats: dict | None = None,
) -> None:
    """Mencatat metrik run ETL ke tabel etl_log."""
    engine = get_dwh_engine()
    table_stats_json = json.dumps(table_stats, ensure_ascii=False) if table_stats else None

    query = text("""
        INSERT INTO etl_log (
            run_id, pipeline_name, start_time, end_time, status,
            rows_in, rows_clean, rows_rejected, rows_loaded, error_message,
            table_stats_json, created_at
        ) VALUES (
            :run_id, :pipeline_name, :start_time, :end_time, :status,
            :rows_in, :rows_clean, :rows_rejected, :rows_loaded, :error_message,
            :table_stats_json, NOW()
        )
    """)
    with engine.begin() as conn:
        conn.execute(query, {
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "start_time": start_time,
            "end_time": end_time,
            "status": status,
            "rows_in": rows_in,
            "rows_clean": rows_clean,
            "rows_rejected": rows_rejected,
            "rows_loaded": rows_loaded,
            "error_message": error_message[:250] if error_message else None,
            "table_stats_json": table_stats_json,
        })
    logger.info(f"Audit log ETL dicatat ke etl_log (status={status}).")

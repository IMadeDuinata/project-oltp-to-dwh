"""
Modul Load: Memuat data dimensi dan fakta ke Data Warehouse (dwh_olist).
Prinsip:
1. Dimensi menggunakan pola Upsert (INSERT ... ON DUPLICATE KEY UPDATE).
2. Fakta dimuat di dalam transaksi database yang aman dan idempotent (tanpa TRUNCATE tanpa pengaman).
3. Baris rejected disimpan ke tabel rejected_rows.
4. Riwayat eksekusi dicatat ke tabel etl_log.
"""

import logging
import pandas as pd
from sqlalchemy import text
from datetime import datetime

from etl.config import get_dwh_engine

logger = logging.getLogger(__name__)


# ============================================================
# 1. LOAD DIMENSI (UPSERT)
# ============================================================
def upsert_dimension(table_name: str, df: pd.DataFrame, key_col: str, sk_col: str):
    """
    Melakukan upsert ke tabel dimensi secara batch.
    Jika key_col sudah ada, update atribut; jika belum, insert baru.
    """
    if df.empty:
        return

    engine = get_dwh_engine()
    cols = [c for c in df.columns if c != sk_col or c == sk_col and -1 in df[c].values]
    
    # Handle unknown row explicitly (-1)
    unknown_rows = df[df.get(sk_col) == -1] if sk_col in df.columns else pd.DataFrame()
    normal_rows = df[df.get(sk_col) != -1] if sk_col in df.columns else df

    # Pastikan row Unknown (-1) terpasang
    if not unknown_rows.empty:
        with engine.begin() as conn:
            # Gunakan REPLACE atau INSERT IGNORE untuk sk = -1
            u_cols = list(unknown_rows.columns)
            col_str = ", ".join([f"`{c}`" for c in u_cols])
            val_placeholders = ", ".join([f":{c}" for c in u_cols])
            sql_unk = f"INSERT IGNORE INTO `{table_name}` ({col_str}) VALUES ({val_placeholders})"
            for _, r in unknown_rows.iterrows():
                conn.execute(text(sql_unk), r.to_dict())

    # Upsert baris normal
    if normal_rows.empty:
        return

    # Ganti NaT dan NaN menjadi None agar dikirim sebagai NULL di MySQL
    normal_rows = normal_rows.copy().astype(object)
    normal_rows = normal_rows.where(pd.notna(normal_rows), None)

    # Buat query INSERT ... ON DUPLICATE KEY UPDATE
    insert_cols = [c for c in normal_rows.columns if c != sk_col]
    update_cols = [c for c in insert_cols if c != key_col and c not in ["valid_from"]]
    
    col_str = ", ".join([f"`{c}`" for c in insert_cols])
    val_placeholders = ", ".join([f":{c}" for c in insert_cols])
    
    if update_cols:
        update_str = ", ".join([f"`{c}` = VALUES(`{c}`)" for c in update_cols])
        sql = f"INSERT INTO `{table_name}` ({col_str}) VALUES ({val_placeholders}) ON DUPLICATE KEY UPDATE {update_str}"
    else:
        sql = f"INSERT IGNORE INTO `{table_name}` ({col_str}) VALUES ({val_placeholders})"

    logger.info(f"Upsert {len(normal_rows):,} baris ke `{table_name}`...")
    records = normal_rows[insert_cols].to_dict(orient="records")
    # Pastikan kembali setiap nilai NaT/NaN di dictionary menjadi None murni
    for r in records:
        for k, v in r.items():
            if pd.isna(v) or v is pd.NaT:
                r[k] = None
    
    chunk_size = 3000
    with engine.begin() as conn:
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            conn.execute(text(sql), chunk)
    logger.info(f"  -> Selesai upsert `{table_name}`")


def load_all_dimensions(dimensions: dict[str, pd.DataFrame]) -> dict[str, dict]:
    """Memuat seluruh tabel dimensi dan mengembalikan map Business Key -> Surrogate Key."""
    logger.info("Memuat seluruh tabel dimensi ke DWH...")
    engine = get_dwh_engine()

    # 1. Dim Date
    if "dim_date" in dimensions:
        df_date = dimensions["dim_date"]
        # dim_date date_sk bukan auto_increment, insert ignore
        with engine.begin() as conn:
            date_cols = list(df_date.columns)
            col_str = ", ".join([f"`{c}`" for c in date_cols])
            val_str = ", ".join([f":{c}" for c in date_cols])
            sql_date = f"INSERT IGNORE INTO dim_date ({col_str}) VALUES ({val_str})"
            records = df_date.to_dict(orient="records")
            conn.execute(text(sql_date), records)
        logger.info(f"  -> dim_date siap ({len(df_date):,} baris)")

    # 2. Dim Customer (SCD Type 2)
    if "dim_customer" in dimensions:
        upsert_dimension("dim_customer", dimensions["dim_customer"], key_col="customer_unique_id", sk_col="customer_sk")

    # 3. Dim Product
    if "dim_product" in dimensions:
        upsert_dimension("dim_product", dimensions["dim_product"], key_col="product_id", sk_col="product_sk")

    # 4. Dim Seller
    if "dim_seller" in dimensions:
        upsert_dimension("dim_seller", dimensions["dim_seller"], key_col="seller_id", sk_col="seller_sk")

    # 5. Dim Payment Type
    if "dim_payment_type" in dimensions:
        upsert_dimension("dim_payment_type", dimensions["dim_payment_type"], key_col="payment_type", sk_col="payment_type_sk")

    # Ambil kembali mapping BK -> SK
    logger.info("Membaca kembali Surrogate Key mappings...")
    with engine.connect() as conn:
        cust_df = pd.read_sql("SELECT customer_unique_id, customer_id, customer_sk FROM dim_customer WHERE is_current = 1", conn)
        # Bisa dipetakan baik via customer_unique_id maupun customer_id
        cust_sk_map = dict(zip(cust_df["customer_id"], cust_df["customer_sk"]))
        
        prod_df = pd.read_sql("SELECT product_id, product_sk FROM dim_product", conn)
        prod_sk_map = dict(zip(prod_df["product_id"], prod_df["product_sk"]))
        
        sell_df = pd.read_sql("SELECT seller_id, seller_sk FROM dim_seller", conn)
        seller_sk_map = dict(zip(sell_df["seller_id"], sell_df["seller_sk"]))
        
        pay_df = pd.read_sql("SELECT payment_type, payment_type_sk FROM dim_payment_type", conn)
        pay_sk_map = dict(zip(pay_df["payment_type"], pay_df["payment_type_sk"]))

    return {
        "cust_sk_map": cust_sk_map,
        "prod_sk_map": prod_sk_map,
        "seller_sk_map": seller_sk_map,
        "pay_sk_map": pay_sk_map,
    }


# ============================================================
# 2. LOAD TABEL FAKTA (TRANSAKSIONAL & IDEMPOTENT)
# ============================================================
def load_facts_transactional(
    fact_order_items: pd.DataFrame,
    fact_order_delivery: pd.DataFrame,
    incremental: bool = False,
    order_ids: list[str] | None = None
) -> int:
    """
    Memuat tabel fakta secara transaksional:
    - Jika incremental: hapus baris dengan order_id yang sedang diproses agar idempotent.
    - Jika full load: bersihkan data fakta secara transaksional dengan aman.
    - Insert data fakta dalam chunk di dalam transaksi yang sama.
    """
    engine = get_dwh_engine()
    total_loaded = 0

    logger.info(f"Memuat tabel fakta (incremental={incremental})...")
    with engine.begin() as conn:
        if incremental and order_ids:
            # Idempotent delete hanya untuk batch order_id yang masuk
            logger.info(f"Menghapus {len(order_ids):,} existing order_id dari fakta untuk idempotent reload...")
            chunk_size = 2000
            for i in range(0, len(order_ids), chunk_size):
                sub_ids = tuple(order_ids[i:i + chunk_size])
                conn.execute(text("DELETE FROM fact_order_items WHERE order_id IN :oids"), {"oids": sub_ids})
                conn.execute(text("DELETE FROM fact_order_delivery WHERE order_id IN :oids"), {"oids": sub_ids})
        elif not incremental:
            # Full load: bersihkan fakta secara aman dalam transaksi
            logger.info("Full load: mengosongkan tabel fakta...")
            conn.execute(text("DELETE FROM fact_order_items"))
            conn.execute(text("DELETE FROM fact_order_delivery"))

        # Insert fact_order_items
        logger.info(f"Insert {len(fact_order_items):,} baris ke fact_order_items...")
        fact_order_items.to_sql(
            "fact_order_items",
            con=conn,
            if_exists="append",
            index=False,
            chunksize=5000,
            method="multi"
        )
        total_loaded += len(fact_order_items)

        # Insert fact_order_delivery
        logger.info(f"Insert {len(fact_order_delivery):,} baris ke fact_order_delivery...")
        fact_order_delivery.to_sql(
            "fact_order_delivery",
            con=conn,
            if_exists="append",
            index=False,
            chunksize=5000,
            method="multi"
        )
        total_loaded += len(fact_order_delivery)

    logger.info(f"✅ Berhasil memuat total {total_loaded:,} baris fakta.")
    return total_loaded


# ============================================================
# 3. LOAD REJECTED ROWS (QUARANTINE)
# ============================================================
def load_rejected_rows(rejections: list[dict], run_id: str):
    """Menyimpan seluruh baris yang ditolak ke tabel rejected_rows."""
    if not rejections:
        return

    engine = get_dwh_engine()
    logger.info(f"Menyimpan {len(rejections):,} baris karantina ke `rejected_rows` (run_id={run_id})...")
    
    # Tambahkan run_id ke tiap record
    for r in rejections:
        r["run_id"] = run_id

    df_rej = pd.DataFrame(rejections)
    with engine.begin() as conn:
        df_rej.to_sql(
            "rejected_rows",
            con=conn,
            if_exists="append",
            index=False,
            chunksize=2000
        )
    logger.info("  -> Karantina tersimpan.")


# ============================================================
# 4. LOGGING ETL AUDIT
# ============================================================
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
    error_message: str | None = None
):
    """Mencatat metrik run ETL ke tabel etl_log."""
    engine = get_dwh_engine()
    query = text("""
        INSERT INTO etl_log (
            run_id, pipeline_name, start_time, end_time, status,
            rows_in, rows_clean, rows_rejected, rows_loaded, error_message, created_at
        ) VALUES (
            :run_id, :pipeline_name, :start_time, :end_time, :status,
            :rows_in, :rows_clean, :rows_rejected, :rows_loaded, :error_message, NOW()
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
            "error_message": error_message,
        })
    logger.info(f"Audit log ETL dicatat ke etl_log (status={status}).")

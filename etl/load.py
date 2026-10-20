"""
Modul Load: Memuat data dimensi dan fakta ke Data Warehouse (dwh_olist).
Prinsip:
1. Dimensi menggunakan pola Upsert (INSERT ... ON DUPLICATE KEY UPDATE).
   - dim_customer menggunakan SCD Type 2 yang sesungguhnya (deteksi perubahan atribut,
     tutup versi lama, insert versi baru dengan surrogate key baru).
2. Fakta dimuat di dalam transaksi database yang aman dan idempotent (tanpa TRUNCATE tanpa pengaman).
3. Baris rejected disimpan ke tabel rejected_rows.
4. Riwayat eksekusi dicatat ke tabel etl_log dengan rincian per-tabel di kolom table_stats_json.
"""

import json
import logging
import pandas as pd
from sqlalchemy import text
from datetime import datetime
from typing import Callable, Optional

from etl.config import get_dwh_engine

logger = logging.getLogger(__name__)


# ============================================================
# 1. LOAD DIMENSI (UPSERT)
# ============================================================
def upsert_dimension(table_name: str, df: pd.DataFrame, key_col: str, sk_col: str):
    """
    Melakukan upsert ke tabel dimensi secara batch.
    Jika key_col sudah ada, update atribut; jika belum, insert baru.
    CATATAN: Tidak digunakan untuk dim_customer — gunakan upsert_dim_customer_scd2().
    """
    if df.empty:
        return

    engine = get_dwh_engine()

    # Handle unknown row explicitly (-1)
    unknown_rows = df[df.get(sk_col) == -1] if sk_col in df.columns else pd.DataFrame()
    normal_rows = df[df.get(sk_col) != -1] if sk_col in df.columns else df

    # Pastikan row Unknown (-1) terpasang
    if not unknown_rows.empty:
        with engine.begin() as conn:
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


def upsert_dim_customer_scd2(df_incoming: pd.DataFrame) -> None:
    """
    SCD Type 2 untuk dim_customer:
    1. Ambil semua record IS_CURRENT=1 dari DWH.
    2. Bandingkan atribut (city, state, zip_code) dengan data masuk.
    3. Jika berubah: tutup versi lama (valid_to=NOW(), is_current=0),
       INSERT versi baru dengan is_current=1, valid_from=NOW().
    4. Jika baru (belum ada): INSERT langsung dengan is_current=1.
    5. Baris Unknown (-1) diinsert dengan INSERT IGNORE.

    Surrogate key (customer_sk) adalah AUTO_INCREMENT — versi baru mendapat SK baru otomatis.
    Fakta lama tetap menunjuk SK versi lama (point-in-time integrity terjaga).
    """
    if df_incoming.empty:
        return

    engine = get_dwh_engine()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- Pisahkan row UNKNOWN ---
    unknown_rows = df_incoming[df_incoming.get("customer_sk") == -1] if "customer_sk" in df_incoming.columns else pd.DataFrame()
    normal_df = df_incoming[df_incoming.get("customer_sk") != -1].copy() if "customer_sk" in df_incoming.columns else df_incoming.copy()

    # Pastikan row UNKNOWN (-1) terpasang
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

    # --- Baca semua record IS_CURRENT=1 dari DWH ---
    with engine.connect() as conn:
        existing_df = pd.read_sql(
            "SELECT customer_sk, customer_unique_id, customer_city, customer_state, customer_zip_code "
            "FROM dim_customer WHERE is_current = 1 AND customer_sk != -1",
            conn
        )

    existing_map = {}
    for _, row in existing_df.iterrows():
        existing_map[row["customer_unique_id"]] = {
            "customer_sk": int(row["customer_sk"]),
            "customer_city": str(row["customer_city"] or "").lower().strip(),
            "customer_state": str(row["customer_state"] or "").lower().strip(),
            "customer_zip_code": str(row["customer_zip_code"] or "").strip(),
        }

    # --- Kategorikan: new, unchanged, changed ---
    to_close_sks = []      # SK lama yang perlu ditutup
    to_insert = []         # Baris yang perlu di-insert (baru atau versi baru)

    SCD2_ATTRS = ["customer_city", "customer_state", "customer_zip_code"]

    for _, row in normal_df.iterrows():
        cuid = row.get("customer_unique_id", "")
        # Skip baris dengan customer_unique_id null/None/NaN/kosong/UNKNOWN
        if not cuid or cuid == "UNKNOWN" or (hasattr(cuid, '__class__') and pd.isna(cuid)):
            continue

        incoming_vals = {
            "customer_city": str(row.get("customer_city", "") or "").lower().strip(),
            "customer_state": str(row.get("customer_state", "") or "").lower().strip(),
            "customer_zip_code": str(row.get("customer_zip_code", "") or "").strip(),
        }

        if cuid not in existing_map:
            # Baru: insert langsung
            to_insert.append({
                "customer_id": row.get("customer_id", ""),
                "customer_unique_id": cuid,
                "customer_zip_code": incoming_vals["customer_zip_code"],
                "customer_city": incoming_vals["customer_city"],
                "customer_state": incoming_vals["customer_state"],
                "valid_from": now,
                "valid_to": None,
                "is_current": 1,
            })
        else:
            ex = existing_map[cuid]
            changed = any(
                incoming_vals[attr] != ex[attr]
                for attr in SCD2_ATTRS
            )
            if changed:
                # Tutup versi lama, insert versi baru
                to_close_sks.append(ex["customer_sk"])
                to_insert.append({
                    "customer_id": row.get("customer_id", ""),
                    "customer_unique_id": cuid,
                    "customer_zip_code": incoming_vals["customer_zip_code"],
                    "customer_city": incoming_vals["customer_city"],
                    "customer_state": incoming_vals["customer_state"],
                    "valid_from": now,
                    "valid_to": None,
                    "is_current": 1,
                })
            # else: tidak ada perubahan, tidak perlu action

    logger.info(f"  SCD2 dim_customer: {len(to_close_sks)} versi lama ditutup, {len(to_insert)} baris baru/berubah.")

    with engine.begin() as conn:
        # Tutup versi lama
        if to_close_sks:
            chunk_size = 1000
            for i in range(0, len(to_close_sks), chunk_size):
                sub = to_close_sks[i:i + chunk_size]
                for sk in sub:
                    conn.execute(text("""
                        UPDATE dim_customer
                        SET is_current = 0, valid_to = :vt
                        WHERE customer_sk = :sk AND is_current = 1
                    """), {"vt": now, "sk": sk})

        # Insert baris baru
        if to_insert:
            df_new = pd.DataFrame(to_insert)
            to_insert_records = [
                {k: (None if (v is not None and pd.isna(v)) else v) for k, v in row.items()}
                for row in df_new.to_dict(orient="records")
            ]

            chunk_size = 3000
            for i in range(0, len(to_insert_records), chunk_size):
                chunk = to_insert_records[i:i + chunk_size]
                conn.execute(text("""
                    INSERT INTO dim_customer
                    (customer_id, customer_unique_id, customer_zip_code, customer_city, customer_state,
                     valid_from, valid_to, is_current)
                    VALUES
                    (:customer_id, :customer_unique_id, :customer_zip_code, :customer_city, :customer_state,
                     :valid_from, :valid_to, :is_current)
                """), chunk)

    logger.info(f"  -> Selesai SCD2 upsert `dim_customer`")


def load_all_dimensions(dimensions: dict, on_progress=None) -> dict:
    """Memuat seluruh tabel dimensi dan mengembalikan map Business Key -> Surrogate Key."""
    logger.info("Memuat seluruh tabel dimensi ke DWH...")
    engine = get_dwh_engine()
    total_dims = 5

    # 1. Dim Date
    if on_progress:
        on_progress("dim_date", 1, total_dims)
    if "dim_date" in dimensions:
        df_date = dimensions["dim_date"]
        with engine.begin() as conn:
            date_cols = list(df_date.columns)
            col_str = ", ".join([f"`{c}`" for c in date_cols])
            val_str = ", ".join([f":{c}" for c in date_cols])
            sql_date = f"INSERT IGNORE INTO dim_date ({col_str}) VALUES ({val_str})"
            records = df_date.to_dict(orient="records")
            conn.execute(text(sql_date), records)
        logger.info(f"  -> dim_date siap ({len(df_date):,} baris)")

    # 2. Dim Customer (SCD Type 2 — versi nyata)
    if on_progress:
        on_progress("dim_customer", 2, total_dims)
    if "dim_customer" in dimensions:
        upsert_dim_customer_scd2(dimensions["dim_customer"])

    # 3. Dim Product
    if on_progress:
        on_progress("dim_product", 3, total_dims)
    if "dim_product" in dimensions:
        upsert_dimension("dim_product", dimensions["dim_product"], key_col="product_id", sk_col="product_sk")

    # 4. Dim Seller
    if on_progress:
        on_progress("dim_seller", 4, total_dims)
    if "dim_seller" in dimensions:
        upsert_dimension("dim_seller", dimensions["dim_seller"], key_col="seller_id", sk_col="seller_sk")

    # 5. Dim Payment Type
    if on_progress:
        on_progress("dim_payment_type", 5, total_dims)
    if "dim_payment_type" in dimensions:
        upsert_dimension("dim_payment_type", dimensions["dim_payment_type"], key_col="payment_type", sk_col="payment_type_sk")

    # Ambil kembali mapping BK -> SK
    logger.info("Membaca kembali Surrogate Key mappings...")
    with engine.connect() as conn:
        # Untuk dim_customer: gunakan customer_id (bukan unique_id) karena fakta join via customer_id
        # dan hanya ambil is_current=1 agar memetakan ke versi terbaru
        cust_df = pd.read_sql(
            "SELECT customer_unique_id, customer_id, customer_sk FROM dim_customer WHERE is_current = 1",
            conn
        )
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
    fact_order_payments: pd.DataFrame,
    incremental: bool = False,
    order_ids: list | None = None,
    on_progress: Optional[Callable[[str, int, int], None]] = None,
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
            logger.info(f"Menghapus {len(order_ids):,} existing order_id dari fakta untuk idempotent reload...")
            chunk_size = 2000
            for i in range(0, len(order_ids), chunk_size):
                sub_ids = tuple(order_ids[i:i + chunk_size])
                conn.execute(text("DELETE FROM fact_order_items WHERE order_id IN :oids"), {"oids": sub_ids})
                conn.execute(text("DELETE FROM fact_order_delivery WHERE order_id IN :oids"), {"oids": sub_ids})
                conn.execute(text("DELETE FROM fact_order_payments WHERE order_id IN :oids"), {"oids": sub_ids})
        elif not incremental:
            logger.info("Full load: mengosongkan tabel fakta...")
            conn.execute(text("DELETE FROM fact_order_payments"))
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
        if on_progress:
            on_progress("fact_order_items", 1, 3)

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
        if on_progress:
            on_progress("fact_order_delivery", 2, 3)

        # Insert fact_order_payments
        logger.info(f"Insert {len(fact_order_payments):,} baris ke fact_order_payments...")
        fact_order_payments.to_sql(
            "fact_order_payments",
            con=conn,
            if_exists="append",
            index=False,
            chunksize=5000,
            method="multi"
        )
        total_loaded += len(fact_order_payments)
        if on_progress:
            on_progress("fact_order_payments", 3, 3)

    logger.info(f"✅ Berhasil memuat total {total_loaded:,} baris fakta.")
    return total_loaded


# ============================================================
# 3. LOAD REJECTED ROWS (QUARANTINE)
# ============================================================
def load_rejected_rows(rejections: list, run_id: str):
    """Menyimpan seluruh baris yang ditolak ke tabel rejected_rows."""
    if not rejections:
        return

    engine = get_dwh_engine()
    logger.info(f"Menyimpan {len(rejections):,} baris karantina ke `rejected_rows` (run_id={run_id})...")

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
    error_message: str | None = None,
    table_stats: dict | None = None,
):
    """
    Mencatat metrik run ETL ke tabel etl_log.
    table_stats: dict dengan format {table_name: {rows_in, rows_clean, rows_rejected}}
                 disimpan sebagai JSON di kolom table_stats_json.
    """
    engine = get_dwh_engine()

    # Cek apakah kolom table_stats_json sudah ada; jika belum, tambahkan (one-time migration)
    with engine.begin() as conn:
        try:
            conn.execute(text("SELECT table_stats_json FROM etl_log LIMIT 1"))
        except Exception:
            conn.execute(text("ALTER TABLE etl_log ADD COLUMN table_stats_json JSON DEFAULT NULL"))
            logger.info("Kolom `table_stats_json` ditambahkan ke etl_log.")

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

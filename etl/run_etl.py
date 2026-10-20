"""
Orkestrator Utama Pipeline ETL:
Extract -> Clean -> Transform -> Load

Fitur:
- Logging terstruktur menggunakan modul logging
- Pencatatan status, baris in/clean/rejected/loaded ke tabel dwh_olist.etl_log
- Penyimpanan baris invalid/kotor ke dwh_olist.rejected_rows
- Pembuatan laporan kualitas data 'Before vs After' di direktori reports/
- Manajemen watermark untuk full & incremental load
- Mengembalikan exit code non-zero bila terjadi kegagalan
"""

import os
import sys
import uuid
import time
import logging
import argparse
import pandas as pd
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("run_etl")

# Import modul ETL internal
from etl.config import REPORTS_DIR
from etl.extract import extract_oltp_data, update_watermark
from etl.reconcile import reconcile
from etl.clean import clean_all_data
from etl.transform import (
    build_dim_customer,
    build_dim_product,
    build_dim_seller,
    build_dim_payment_type,
    build_dim_date,
    build_fact_order_items,
    build_fact_order_delivery,
    build_fact_order_payments,
)
from etl.load import (
    load_all_dimensions,
    load_facts_transactional,
    load_rejected_rows,
    log_etl_execution,
)
from etl.progress import ETLProgress


def generate_data_quality_report(run_id: str, start_time: datetime, audit: dict, rejections: list[dict], reports_dir: Path):
    """Menghasilkan file Markdown laporan kualitas data Before vs After."""
    report_file = reports_dir / f"data_quality_report_{run_id}.md"
    latest_file = reports_dir / "data_quality_report_latest.md"

    # Kelompokkan rejections berdasarkan alasan
    reason_counts = {}
    for r in rejections:
        reason = r["rejection_reason"]
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    content = f"""# 📋 Laporan Kualitas Data ETL (Before vs After Cleansing)

- **Run ID**: `{run_id}`
- **Waktu Eksekusi**: `{start_time.strftime('%Y-%m-%d %H:%M:%S')}`
- **Total Baris Ditolak (Quarantine)**: `{len(rejections):,}`

---

## 1. Perbandingan Baris Data: Before vs After

| Nama Tabel / Entitas | Baris Sebelum Cleansing (Before) | Baris Lolos Cleansing (After) | Selisih (Ditolak / Didrop) |
|---|---|---|---|
| **Customers** | {audit.get('customers_rows_before', 0):,} | {audit.get('customers_rows_after', 0):,} | {audit.get('customers_rows_before', 0) - audit.get('customers_rows_after', 0):,} |
| **Products** | {audit.get('products_rows_before', 0):,} | {audit.get('products_rows_after', 0):,} | {audit.get('products_rows_before', 0) - audit.get('products_rows_after', 0):,} |
| **Sellers** | {audit.get('sellers_rows_before', 0):,} | {audit.get('sellers_rows_after', 0):,} | {audit.get('sellers_rows_before', 0) - audit.get('sellers_rows_after', 0):,} |
| **Orders** | {audit.get('orders_rows_before', 0):,} | {audit.get('orders_rows_after', 0):,} | {audit.get('orders_rows_before', 0) - audit.get('orders_rows_after', 0):,} |
| **Order Items** | {audit.get('order_items_rows_before', 0):,} | {audit.get('order_items_rows_after', 0):,} | {audit.get('order_items_rows_before', 0) - audit.get('order_items_rows_after', 0):,} |
| **Order Payments** | {audit.get('order_payments_rows_before', 0):,} | {audit.get('order_payments_rows_after', 0):,} | {audit.get('order_payments_rows_before', 0) - audit.get('order_payments_rows_after', 0):,} |

---

## 2. Rincian Pelanggaran Data & Alasan Karantina (Rejected Rows)

| No | Aturan / Masalah Validasi | Alasan Penolakan | Jumlah Baris Ditolak | Tindakan |
|---|---|---|---|---|
"""
    for idx, (reason, count) in enumerate(sorted(reason_counts.items(), key=lambda x: x[1], reverse=True), 1):
        content += f"| {idx} | Data Anomaly | `{reason}` | {count:,} | Karantina ke `rejected_rows` |\n"

    content += """
---

## 3. Catatan Keputusan Teknis Cleansing
1. **Null Handling**:
   - `product_category_name` NULL diimputasi dengan nilai `'unknown'` agar produk tetap dapat dianalisis pada Star Schema.
   - Ukuran fisik produk (berat, panjang, lebar, tinggi) NULL diimputasi dengan 0.
   - Transaksi dengan `order_approved_at` NULL pada status non-canceled ditolak (karena melanggar SOP pembayaran).
2. **Deduplikasi**:
   - Nama kota dan provinsi dinormalisasi (lowercase dan strip whitespace) sebelum pemeriksaan duplikasi.
   - Duplikat persis dan duplikat business key `(order_id, order_item_id)` dikarantina ke `rejected_rows`.
3. **Bad Business Logic**:
   - Tanggal pengiriman lebih awal dari tanggal pembelian (`delivered < purchase`) ditolak.
   - Tanggal estimasi lebih awal dari tanggal pembelian (`estimated < purchase`) ditolak.
   - Status `delivered` tanpa tanggal sampai ditolak.
   - Status `canceled` dengan tanggal pengiriman ditolak.
   - Harga produk `<= 0` atau ongkos kirim `< 0` ditolak.
   - Tanggal pembelian di masa depan (`future date`) ditolak.
4. **Validasi Domain & Column Shift**:
   - Nilai `order_status` yang bukan domain valid (misal angka tahun `'2018'`) atau `payment_type` berisi kode negara bagian (`'SP'`, `'RJ'`) dideteksi sebagai column shift / korupsi data dan dikarantina.
"""

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(content)
    with open(latest_file, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"📊 Laporan kualitas data berhasil disimpan ke `{report_file}`.")


def run_pipeline(incremental: bool = False, pipeline_name: str = "olist_pipeline"):
    """Fungsi orkestrasi end-to-end ETL."""
    run_id = f"RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info(f"🚀 MEMULAI ETL PIPELINE: {pipeline_name} (Run ID: {run_id})")
    logger.info(f"   Mode: {'Incremental' if incremental else 'Full Load'}")
    logger.info("=" * 60)

    rows_in = 0
    rows_clean = 0
    rows_rejected = 0
    rows_loaded = 0
    table_stats = None

    try:
        with ETLProgress(
            run_id=run_id,
            mode="Incremental" if incremental else "Full",
            pipeline_name=pipeline_name,
        ) as progress:
            # 1. EXTRACT
            logger.info("\n[Step 1/4] 📥 EXTRACT DARI OLTP...")
            progress.start_step("extract", message="Mengekstrak data dari database OLTP...")
            raw_data = extract_oltp_data(incremental=incremental, pipeline_name=pipeline_name)
            rows_in = sum(len(df) for df in raw_data.values())
            br_rows = sum(len(df[df["source_country"] == "BR"]) for df in raw_data.values() if "source_country" in df.columns)
            id_rows = sum(len(df[df["source_country"] == "ID"]) for df in raw_data.values() if "source_country" in df.columns)
            logger.info(f"Total baris diekstrak: {rows_in:,}")
            progress.complete_step(
                "extract",
                message=f"BR: [green]{br_rows:,}[/green] | ID: [green]{id_rows:,}[/green] | Combined: [green]{rows_in:,}[/green]",
                rows=rows_in,
            )

            # 1.5 RECONCILE (SCHEMA HARMONIZATION BR <-> ID)
            progress.start_step("reconcile", message="Menyelaraskan skema BR & ID...")
            raw_data = reconcile(raw_data)
            rows_reconciled = sum(len(df) for df in raw_data.values())
            progress.complete_step(
                "reconcile",
                message=f"[green]{rows_reconciled:,}[/green] baris diharmonisasi",
                rows=rows_reconciled,
            )

            # 2. CLEAN
            logger.info("\n[Step 2/4] 🧹 CLEANSING & VALIDASI DATA...")
            progress.start_step("clean", message="Cleansing dan validasi data...")
            clean_data, rejections, audit = clean_all_data(raw_data)
            rows_clean = sum(len(df) for df in clean_data.values())
            rows_rejected = len(rejections)
            logger.info(f"Total baris bersih: {rows_clean:,} | Ditolak: {rows_rejected:,}")
            progress.complete_step(
                "clean",
                message=f"[green]{rows_clean:,}[/green] clean | [green]{rows_rejected:,}[/green] rejected",
                rows=rows_clean,
            )

            # --- Per-table stats untuk etl_log ---
            TABLE_KEYS = ["customers", "products", "sellers", "orders", "order_items", "order_payments"]
            table_stats = {}
            for tbl in TABLE_KEYS:
                in_count = len(raw_data.get(tbl, []))
                clean_count = len(clean_data.get(tbl, []))
                rej_count = sum(1 for r in rejections if r.get("table_source", "") == tbl)
                table_stats[tbl] = {
                    "rows_in": in_count,
                    "rows_clean": clean_count,
                    "rows_rejected": rej_count,
                }

            # 3. TRANSFORM (Part 1 - Bangun Dimensi)
            logger.info("\n[Step 3/4] 🔄 TRANSFORM KE STAR SCHEMA...")
            progress.start_step("transform", message="Membangun dimensi...", total=8)
            # Bangun dimensi
            dim_cust = build_dim_customer(clean_data["customers"])
            dim_prod = build_dim_product(clean_data["products"])
            dim_sell = build_dim_seller(clean_data["sellers"])
            dim_pay = build_dim_payment_type(clean_data["order_payments"])
            dim_date = build_dim_date()

            dimensions = {
                "dim_date": dim_date,
                "dim_customer": dim_cust,
                "dim_product": dim_prod,
                "dim_seller": dim_sell,
                "dim_payment_type": dim_pay,
            }
            progress.update_step("transform", message="[green]5[/green] dimensi terbuild...", completed=5)

            # 4. LOAD DIMENSIONS & BUILD SURROGATE KEY MAPPINGS
            logger.info("\n[Step 4a/4] 📤 LOAD DIMENSI & SURROGATE KEY MAPPING...")
            progress.start_step("load_dims", message="Memuat dimensi ke DWH...", total=5)

            def on_dim_progress(dim_name: str, current: int, total: int):
                progress.update_step(
                    "load_dims",
                    message=f"{dim_name} [green]{current}/{total}[/green]...",
                    completed=current,
                    total=total,
                )

            sk_mappings = load_all_dimensions(dimensions, on_progress=on_dim_progress)
            progress.complete_step("load_dims", message="[green]5/5[/green] dimensi loaded", rows="5 dims")

            # Bangun fakta menggunakan surrogate key mappings yang sudah termuat
            logger.info("\n[Step 4b/4] 🔗 TRANSFORM TABEL FAKTA...")
            progress.update_step("transform", message="Membangun tabel fakta...", completed=6)
            fact_items = build_fact_order_items(
                clean_data["order_items"],
                clean_data["orders"],
                sk_mappings["cust_sk_map"],
                sk_mappings["prod_sk_map"],
                sk_mappings["seller_sk_map"],
            )

            progress.update_step("transform", completed=7)
            fact_delivery = build_fact_order_delivery(
                clean_data["orders"],
                sk_mappings["cust_sk_map"],
            )

            fact_payments = build_fact_order_payments(
                clean_data["order_payments"],
                clean_data["orders"],
                sk_mappings["cust_sk_map"],
                sk_mappings["pay_sk_map"],
            )

            logger.info(f"  fact_order_items    : {len(fact_items):,} baris")
            logger.info(f"  fact_order_delivery : {len(fact_delivery):,} baris")
            logger.info(f"  fact_order_payments : {len(fact_payments):,} baris")

            progress.complete_step(
                "transform",
                message="[green]5[/green] dimensi + [green]3[/green] fakta terbuild",
                rows="5 dims + 3 facts",
            )

            # 5. LOAD FACTS (TRANSACTIONAL)
            logger.info("\n[Step 4c/4] 📤 LOAD TABEL FAKTA (TRANSAKSIONAL)...")
            progress.start_step("load_facts", message="Memuat tabel fakta (transaksional)...", total=3)
            order_ids_batch = clean_data["orders"]["order_id"].tolist() if incremental else None
            rows_loaded = load_facts_transactional(
                fact_order_items=fact_items,
                fact_order_delivery=fact_delivery,
                fact_order_payments=fact_payments,
                incremental=incremental,
                order_ids=order_ids_batch,
            )
            progress.complete_step(
                "load_facts",
                message=f"total [green]{rows_loaded:,}[/green] baris loaded",
                rows=rows_loaded,
            )

            # 6. LOAD REJECTED ROWS (QUARANTINE)
            logger.info("\n[Step 4d/4] 🛡️ MENYIMPAN BARIS KARANTINA...")
            load_rejected_rows(rejections, run_id=run_id)

            # 7. UPDATE WATERMARK JIKA INCREMENTAL
            if not clean_data["orders"].empty:
                max_ts = clean_data["orders"]["order_purchase_timestamp"].max()
                if pd.notna(max_ts):
                    update_watermark(str(max_ts), pipeline_name=pipeline_name)
                    logger.info(f"Watermark diperbarui ke: {max_ts}")

            # 8. BUAT LAPORAN DATA QUALITY
            generate_data_quality_report(run_id, start_time, audit, rejections, REPORTS_DIR)

            # 9. CATAT STATUS LOG KE etl_log
            end_time = datetime.now()
            log_etl_execution(
                run_id=run_id,
                pipeline_name=pipeline_name,
                start_time=start_time,
                end_time=end_time,
                status="SUCCESS",
                rows_in=rows_in,
                rows_clean=rows_clean,
                rows_rejected=rows_rejected,
                rows_loaded=rows_loaded,
                table_stats=table_stats,
            )

            logger.info("=" * 60)
            logger.info(f"🎉 ETL PIPELINE BERHASIL DALAM {time.time() - start_time.timestamp():.2f} DETIK")
            logger.info("=" * 60)
            return 0

    except Exception as e:
        end_time = datetime.now()
        err_msg = str(e)
        logger.error(f"❌ ETL PIPELINE GAGAL: {err_msg}", exc_info=True)
        try:
            log_etl_execution(
                run_id=run_id,
                pipeline_name=pipeline_name,
                start_time=start_time,
                end_time=end_time,
                status="FAILED",
                rows_in=rows_in,
                rows_clean=rows_clean,
                rows_rejected=rows_rejected,
                rows_loaded=rows_loaded,
                error_message=err_msg,
            )
        except Exception as log_err:
            logger.error(f"Gagal mencatat log kegagalan: {log_err}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Orkestrator ETL Olist (OLTP to DWH)")
    parser.add_argument("--incremental", action="store_true", help="Jalankan ETL dalam mode incremental")
    parser.add_argument("--pipeline-name", type=str, default="olist_pipeline", help="Nama pipeline")
    args = parser.parse_args()

    exit_code = run_pipeline(incremental=args.incremental, pipeline_name=args.pipeline_name)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

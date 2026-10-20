"""
Orkestrator Utama Pipeline ETL:
Extract (OLTP -> Staging) -> Reconcile -> Clean -> Transform -> Load (Star Schema).
"""

import os
import sys
import uuid
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_etl")

from etl.config import REPORTS_DIR
from etl.extract import (
    update_watermark,
    load_oltp_to_staging,
    extract_from_staging,
)
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


def generate_data_quality_report(run_id: str, start_time: datetime, audit: dict, rejections: list[dict], reports_dir: Path) -> None:
    """Menghasilkan file Markdown ringkasan kualitas data Before vs After cleansing."""
    report_file = reports_dir / f"data_quality_report_{run_id}.md"
    latest_file = reports_dir / "data_quality_report_latest.md"

    reason_counts = {}
    for r in rejections:
        reason = r["rejection_reason"]
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    table_rows = "\n".join([
        f"| **{tbl.replace('_', ' ').title()}** | "
        f"{audit.get(f'{tbl}_rows_before', 0):,} | "
        f"{audit.get(f'{tbl}_rows_after', 0):,} | "
        f"{audit.get(f'{tbl}_rows_before', 0) - audit.get(f'{tbl}_rows_after', 0):,} |"
        for tbl in ["customers", "products", "sellers", "orders", "order_items", "order_payments"]
    ])

    rejection_rows = "\n".join([
        f"| {idx} | Anomali Data | `{reason}` | {count:,} | Karantina ke `rejected_rows` |"
        for idx, (reason, count) in enumerate(sorted(reason_counts.items(), key=lambda x: x[1], reverse=True), 1)
    ])

    content = f"""# Laporan Kualitas Data ETL (Before vs After Cleansing)

- **Run ID**: `{run_id}`
- **Waktu Eksekusi**: `{start_time.strftime('%Y-%m-%d %H:%M:%S')}`
- **Total Baris Ditolak (Quarantine)**: `{len(rejections):,}`

---

## 1. Perbandingan Baris Data: Before vs After

| Nama Tabel / Entitas | Baris Sebelum (Before) | Baris Lolos (After) | Selisih (Ditolak) |
|---|---|---|---|
{table_rows}

---

## 2. Rincian Pelanggaran Data & Alasan Karantina

| No | Kategori | Alasan Penolakan | Jumlah | Tindakan |
|---|---|---|---|---|
{rejection_rows}

---

## 3. Catatan Aturan Cleansing
1. Imputasi nilai NULL pada deskripsi produk dan penolakan pesanan aktif dengan approval date kosong.
2. Deduplikasi eksak dan natural key (order_id, order_item_id).
3. Penolakan logika anomali (delivered < purchase, estimated < purchase, harga <= 0, future dates).
4. Penolakan column shift / domain korup pada kolom status dan tipe pembayaran.
"""
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(content)
    with open(latest_file, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Laporan kualitas data disimpan ke `{report_file}`.")


def run_pipeline(incremental: bool = False, pipeline_name: str = "olist_pipeline") -> int:
    """Fungsi orkestrasi end-to-end pipeline ETL."""
    run_id = f"RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    start_time = datetime.now()

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
            logger.info(f"Memulai pipeline '{pipeline_name}' (Run ID: {run_id}, Mode: {'Incremental' if incremental else 'Full Load'})")

            # Helper callback untuk update progress bar secara konsisten
            def make_progress_cb(step_key: str, action_label: str):
                return lambda item, curr, tot: progress.update_step(
                    step_key,
                    message=f"{action_label}: `{item}` [green]{curr}/{tot}[/green]...",
                    completed=curr,
                    total=tot,
                )

            # 1. EXTRACT KE STAGING & BACA STAGING
            logger.info("\n[Step 1/4] EXTRACT OLTP KE STAGING AREA (dwh_staging)...")
            progress.start_step("extract", message="Memuat data dari OLTP ke staging...", total=6)
            load_oltp_to_staging(
                incremental=incremental,
                pipeline_name=pipeline_name,
                on_progress=make_progress_cb("extract", "Extract"),
            )
            raw_data = extract_from_staging()
            rows_in = sum(len(df) for df in raw_data.values())
            br_rows = sum(len(df[df["source_country"] == "BR"]) for df in raw_data.values() if "source_country" in df.columns)
            id_rows = sum(len(df[df["source_country"] == "ID"]) for df in raw_data.values() if "source_country" in df.columns)
            progress.complete_step(
                "extract",
                message=f"Staging BR: [green]{br_rows:,}[/green] | ID: [green]{id_rows:,}[/green] | Combined: [green]{rows_in:,}[/green]",
                rows=rows_in,
            )

            # 1.5 RECONCILE (SCHEMA HARMONIZATION BR <-> ID)
            progress.start_step("reconcile", message="Menyelaraskan skema BR & ID...", total=6)
            raw_data = reconcile(raw_data, on_progress=make_progress_cb("reconcile", "Harmonisasi"))
            rows_reconciled = sum(len(df) for df in raw_data.values())
            progress.complete_step("reconcile", message=f"[green]{rows_reconciled:,}[/green] baris diharmonisasi", rows=rows_reconciled)

            # 2. CLEAN & VALIDASI
            logger.info("\n[Step 2/4] CLEANSING & VALIDASI DATA...")
            progress.start_step("clean", message="Cleansing dan validasi data...", total=6)
            clean_data, rejections, audit = clean_all_data(raw_data, on_progress=make_progress_cb("clean", "Cleansing"))
            rows_clean = sum(len(df) for df in clean_data.values())
            rows_rejected = len(rejections)
            progress.complete_step("clean", message=f"[green]{rows_clean:,}[/green] clean | [green]{rows_rejected:,}[/green] rejected", rows=rows_clean)

            # Hitung statistik per tabel untuk etl_log
            table_stats = {
                tbl: {
                    "rows_in": len(raw_data.get(tbl, [])),
                    "rows_clean": len(clean_data.get(tbl, [])),
                    "rows_rejected": sum(1 for r in rejections if r.get("table_source") == tbl),
                }
                for tbl in ["customers", "products", "sellers", "orders", "order_items", "order_payments"]
            }

            # 3. TRANSFORM DIMENSI
            logger.info("\n[Step 3/4] TRANSFORM KE STAR SCHEMA...")
            progress.start_step("transform", message="Membangun dimensi...", total=8)
            dimensions = {
                "dim_date": build_dim_date(),
                "dim_customer": build_dim_customer(clean_data["customers"]),
                "dim_product": build_dim_product(clean_data["products"]),
                "dim_seller": build_dim_seller(clean_data["sellers"]),
                "dim_payment_type": build_dim_payment_type(clean_data["order_payments"]),
            }
            progress.update_step("transform", message="[green]5[/green] dimensi terbuild...", completed=5)

            # 4. LOAD DIMENSI & PEMETAAN SURROGATE KEY
            logger.info("\n[Step 4a/4] LOAD DIMENSI & SURROGATE KEY MAPPING...")
            progress.start_step("load_dims", message="Memuat dimensi ke DWH...", total=5)
            sk_mappings = load_all_dimensions(dimensions, on_progress=make_progress_cb("load_dims", "Load"))
            progress.complete_step("load_dims", message="[green]5/5[/green] dimensi loaded", rows="5 dims")

            # 5. TRANSFORM FAKTA
            progress.update_step("transform", message="Membangun tabel fakta...", completed=6)
            fact_items = build_fact_order_items(
                clean_data["order_items"],
                clean_data["orders"],
                sk_mappings["cust_sk_map"],
                sk_mappings["prod_sk_map"],
                sk_mappings["seller_sk_map"],
            )
            progress.update_step("transform", completed=7)
            fact_delivery = build_fact_order_delivery(clean_data["orders"], sk_mappings["cust_sk_map"])
            fact_payments = build_fact_order_payments(clean_data["order_payments"], clean_data["orders"], sk_mappings["cust_sk_map"], sk_mappings["pay_sk_map"])
            progress.complete_step("transform", message="[green]5[/green] dimensi + [green]3[/green] fakta terbuild", rows="5 dims + 3 facts")

            # 6. LOAD FAKTA (TRANSAKSIONAL)
            logger.info("\n[Step 4b/4] LOAD TABEL FAKTA (TRANSAKSIONAL)...")
            progress.start_step("load_facts", message="Memuat tabel fakta...", total=3)
            order_ids_batch = clean_data["orders"]["order_id"].tolist() if incremental else None
            rows_loaded = load_facts_transactional(
                fact_order_items=fact_items,
                fact_order_delivery=fact_delivery,
                fact_order_payments=fact_payments,
                incremental=incremental,
                order_ids=order_ids_batch,
                on_progress=make_progress_cb("load_facts", "Load"),
            )
            progress.complete_step("load_facts", message=f"total [green]{rows_loaded:,}[/green] baris loaded", rows=rows_loaded)

            # 7. LOAD REJECTED ROWS (QUARANTINE)
            logger.info("\n[Step 4c/4] MENYIMPAN BARIS KARANTINA...")
            load_rejected_rows(rejections, run_id=run_id)

            # 8. UPDATE WATERMARK JIKA INCREMENTAL
            if not clean_data["orders"].empty:
                max_ts = clean_data["orders"]["order_purchase_timestamp"].max()
                if pd.notna(max_ts):
                    update_watermark(str(max_ts), pipeline_name=pipeline_name)

            # 9. DOKUMENTASI DATA QUALITY & LOG AUDIT
            generate_data_quality_report(run_id, start_time, audit, rejections, REPORTS_DIR)
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

            logger.info(f"ETL pipeline selesai sukses dalam {time.time() - start_time.timestamp():.2f} detik.")
            return 0

    except Exception as e:
        end_time = datetime.now()
        err_msg = str(e)
        logger.error(f"ETL pipeline gagal: {err_msg}", exc_info=True)
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

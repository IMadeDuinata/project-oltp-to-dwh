"""
Scheduler Pipeline ETL DWH menggunakan APScheduler (BlockingScheduler).
Konfigurasi:
- Jadwal produksi: Cron harian setiap pukul 02:00 (malam)
- Mode demo/test: Interval per 1 menit atau eksekusi langsung sekali (manual trigger)
- Parameter: max_instances=1 untuk mencegah tumpang tindih eksekusi (concurrency control)
- Error handling & logging terintegrasi
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Add root dir to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from etl.run_etl import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Scheduler]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")


def execute_etl_job(incremental: bool = True):
    """Fungsi pembungkus eksekusi job ETL oleh scheduler."""
    logger.info("Trigger jadwal ETL dimulai...")
    t0 = time.time()
    try:
        # Menjalankan ETL
        exit_code = run_pipeline(incremental=incremental, pipeline_name="scheduler_olist_pipeline")
        if exit_code == 0:
            logger.info(f"Job ETL selesai dengan sukses dalam {time.time() - t0:.2f} detik.")
        else:
            logger.error(f"Job ETL selesai dengan kode kegagalan: {exit_code}")
    except Exception as e:
        logger.error(f"Terjadi kesalahan fatal saat eksekusi job ETL: {e}", exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="Scheduler ETL Data Warehouse Olist")
    parser.add_argument("--demo", action="store_true", help="Jalankan dalam mode demo (setiap 1 menit)")
    parser.add_argument("--now", action="store_true", help="Trigger eksekusi langsung sekali saat start")
    parser.add_argument("--full", action="store_true", help="Gunakan mode Full Load alih-alih Incremental")
    args = parser.parse_args()

    scheduler = BlockingScheduler()
    is_incremental = not args.full

    if args.now:
        logger.info("Eksekusi langsung (trigger manual saat start)...")
        execute_etl_job(incremental=is_incremental)

    if args.demo:
        logger.info("Mengaktifkan mode DEMO: jadwal interval setiap 1 menit.")
        trigger = IntervalTrigger(minutes=1)
    else:
        logger.info("Mengaktifkan mode PRODUKSI: jadwal cron setiap hari pukul 02:00.")
        trigger = CronTrigger(hour=2, minute=0)

    # Tambahkan job dengan max_instances=1 untuk mencegah tumpang tindih run
    scheduler.add_job(
        func=execute_etl_job,
        trigger=trigger,
        kwargs={"incremental": is_incremental},
        id="dwh_etl_job",
        name="Olist OLTP to DWH Daily Job",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    logger.info("Scheduler aktif. Tekan Ctrl+C untuk berhenti.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler dihentikan.")


if __name__ == "__main__":
    main()

Aku mengerjakan tugas Data Warehouse (OLTP -> ETL Python -> DWH star schema) dengan dataset Olist (CSV, separator ';'). Sudah ada script awal buatan temanku di folder legacy/:
- load_oltp.py (CSV -> MySQL tabel flat olist_raw)
- create_star_schema.py (DDL star schema: 5 dimensi + 1 fakta)
- transform_oltp_to_dwh.py (ETL: filter status/payment_type invalid, build dimensi & fakta)
- analytics.py (8 query analitik)

Tugasmu: PERBAIKI dan RESTRUKTURISASI project ini agar memenuhi syarat tugas di bawah. Pakai ulang kode lama yang masih bagus (koneksi .env, pola surrogate key lookup, idempotent load), jangan menulis dari nol tanpa alasan. Jangan ubah file di legacy/ dan data/raw/.

## Syarat tugas (wajib terpenuhi semua)
1. OLTP dengan data kotor (dataset ini sudah cukup kotor; jika jenis kotoran tertentu kurang, tambahkan lewat script injeksi terpisah)
2. ETL + desain DWH, bahasa Python
3. DWH minimal 2 tabel fakta dan 3 tabel dimensi
4. ETL wajib mengimplementasikan minimal 3 teknik cleansing: null handling, deduplikasi, bad business logic (tambahan: standardisasi format & validasi domain)
5. Ada scheduler

## Stack
Python, pandas, SQLAlchemy + pymysql, python-dotenv, MySQL. Kredensial dari .env (pakai sqlalchemy URL.create supaya password dengan karakter spesial aman). Scheduler: APScheduler, ditambah contoh unit systemd service+timer di folder scheduler/ sebagai alternatif.

## Perubahan yang harus dikerjakan

### A. OLTP ter-normalisasi
- Pertahankan olist_raw sebagai tabel staging/landing (load_oltp.py boleh diadaptasi).
- Buat skema OLTP 3NF dengan PK/FK/tipe data yang benar (INT, DECIMAL, DATETIME), minimal: customers, orders, order_items, products, sellers, order_payments.
- Buat script untuk memecah olist_raw ke tabel-tabel OLTP. Data kotor TIDAK dibersihkan di tahap ini (biarkan apa adanya, bila perlu longgarkan constraint) karena pembersihan adalah tugas ETL.

### B. Desain DWH (star schema), minimal:
- Dimensi: dim_customer, dim_product, dim_seller, dim_payment (atau dim_payment_type), dim_date
- Fakta 1: fact_order_items (grain: order + item; measure: price, freight_value)
- Fakta 2: fact_payments (grain: order + payment sequence; measure: payment_value, installments) ATAU fact_order_delivery (grain: order; measure: hari pengiriman, selisih vs estimasi, flag telat) — pilih yang paling masuk akal setelah kamu cek grain data, jelaskan alasannya.
- Perbaiki masalah grain: payment_value tidak boleh terduplikasi di baris item (cek dulu apakah CSV hasil join items x payments, buktikan dengan query).
- dim_customer: gunakan customer_unique_id sebagai business key; jadikan SCD Type 2 (valid_from, valid_to, is_current) bila data memungkinkan, jika tidak jelaskan alasannya.
- Tanggal pengiriman/estimasi juga sebagai FK ke dim_date (role-playing dimension).
- payment_installments bertipe INT.
- Sertakan satu baris "Unknown" (sk = -1 atau 0) di tiap dimensi untuk menangani FK yang tidak ketemu, agar fakta tidak dibuang diam-diam.
- Tulis semua DDL di sql/ dan/atau script create_star_schema.py yang sudah diperbaiki.

### C. ETL modular (folder etl/)
Struktur: config.py, extract.py, clean.py, transform.py, load.py, run_etl.py. Tidak ada kode yang jalan di level modul; semua dalam fungsi dengan main().
- extract: baca dari OLTP; dukung full load dan incremental (watermark berdasarkan order_purchase_timestamp atau tabel etl_watermark).
- clean.py: tiap teknik cleansing berupa fungsi terpisah, mengembalikan (df_bersih, df_rejected) dengan kolom alasan:
  1. Null handling: contoh product_category_name null -> 'unknown'; order_approved_at null pada order non-canceled -> reject/flag; jelaskan keputusan per kolom
  2. Deduplikasi: duplikat persis dan duplikat business key (order_id, order_item_id); normalisasi teks (trim, lowercase, kota) sebelum cek duplikat
  3. Bad business logic: delivered < purchase, price <= 0, freight < 0, status delivered tapi tanggal delivered kosong, status canceled tapi ada tanggal delivered, estimated < purchase, tanggal di masa depan
  4. Validasi domain: order_status dan payment_type valid. Investigasi dulu baris yang payment_type berisi kode state dan order_status berisi tahun: kemungkinan kolom bergeser (column shift); jika bisa diperbaiki, perbaiki, jika tidak, quarantine.
- Baris yang ditolak TIDAK didrop diam-diam: simpan ke tabel rejected_rows (run_id, sumber, kolom, alasan, data mentah JSON).
- load.py: dimensi dengan upsert (INSERT ... ON DUPLICATE KEY UPDATE), fakta dalam transaksi, idempotent, tidak pakai TRUNCATE di tengah proses tanpa pengaman.
- run_etl.py: orkestrasi extract -> clean -> transform -> load, menulis ke tabel etl_log (run_id, start, end, status, rows_in, rows_clean, rows_rejected, rows_loaded per tabel, error_message). Gunakan modul logging, bukan print saja. Exit code non-zero bila gagal.
- Buat laporan kualitas data "before vs after cleansing" (jumlah null, duplikat, pelanggaran per aturan) dan simpan ke reports/.

### D. Scheduler
- scheduler/run_scheduler.py (APScheduler, cron harian jam 02:00, max_instances=1 supaya run tidak tumpang tindih, log error).
- scheduler/dwh-etl.service dan dwh-etl.timer (systemd) sebagai alternatif.
- Jelaskan cara menjalankan dan menguji (misal trigger manual + jadwal tiap 1 menit untuk demo).

### E. Analytics
- Perbaiki analytics.py agar sesuai skema baru dan grain yang benar (jangan menjumlah payment_value dari baris item; hitung order dengan COUNT(DISTINCT order_id)).
- Pertahankan query yang masih relevan, tambahkan minimal 2 query yang memakai kedua tabel fakta.

### F. Tes
- tests/: pytest sederhana untuk fungsi cleansing (input kotor -> output sesuai), cek integritas DWH (tidak ada FK orphan, tidak ada duplikat grain di fakta, SUM measure DWH konsisten dengan OLTP setelah dikurangi baris rejected).

## Cara kerja
1. Kerjakan bertahap sesuai urutan A -> F. Setelah tiap bagian, jalankan dan verifikasi, lalu beri ringkasan singkat.
2. Sebelum mengubah desain (terutama grain fakta dan SCD), tampilkan hasil pengecekan datanya dulu, lalu ambil keputusan dan jelaskan alasannya.
3. Semua angka harus berasal dari eksekusi kode, jangan menebak.
4. Kalau ada hal ambigu atau butuh keputusanku (mis. pilihan fakta ke-2, strategi imputasi), tanyakan, jangan berasumsi diam-diam.
5. Buat README.md berisi: arsitektur, cara setup (.env.example, install dependency), urutan menjalankan, ERD (Mermaid) OLTP dan star schema, tabel teknik cleansing (masalah -> teknik -> hasil), dan cara menjalankan scheduler.

## Struktur target
dwh-project/
├── data/raw/
├── legacy/                  # script lama, jangan diubah
├── sql/                     # DDL oltp, dwh, etl_log, rejected_rows
├── oltp/                    # load staging + split ke tabel OLTP
├── etl/                     # config, extract, clean, transform, load, run_etl, analytics
├── scheduler/
├── reports/
├── tests/
├── .env.example
└── README.md

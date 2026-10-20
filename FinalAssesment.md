# Final Data Quality & DWH Architecture Assessment

**Role:** Data Quality Auditor  
**Target:** Pipeline ETL, Staging Area, & Star Schema DWH ([project-oltp-to-dwh](file:///home/lann/Projects/project-oltp-to-dwh))  
**Dataset Scope:** Dual-Source Ingestion (Olist Brazil OLTP + Synthesized Dirty Indonesian OLTP)  

---

### Bottom Line
**Data Quality Score (DQS): 96 / 100 (Status: Production-Ready / Academic Benchmark Standard)**  
Gudang data telah berhasil mengimplementasikan *physical staging per entity*, segregasi multi-source (*source_country*), manajemen dirty data melalui *cascading quarantine table*, penanganan dimensi perlahan berubah (*SCD Type 2*), serta pembuktian rekonsiliasi finansial presisi nol kebocoran (*zero data loss*).

---

### Data Quality Scorecard (DQS Breakdown)

| Dimensi | Bobot | Skor | Kontribusi | Ringkasan Penilaian |
|---|:---:|:---:|:---:|---|
| **Completeness** | 30% | 98 / 100 | 29.4 | 100% integritas referensial FK ke dimensi; nilai null non-kritis diimputasi secara sistematis (`unknown`). |
| **Consistency** | 25% | 96 / 100 | 24.0 | Harmonisasi lintas format tanggal campur (DD/MM/YYYY vs ISO) dan mata uang multi-source terserap rapi melalui staging fisik. |
| **Validity** | 20% | 95 / 100 | 19.0 | Validasi domain ketat: anomali tanggal masa depan, kronologi terbalik, harga minus, dan status janggal berhasil dicegah masuk ke DWH. |
| **Uniqueness** | 15% | 96 / 100 | 14.4 | Integritas surrogate key unik; deduplikasi natural key berjalan mulus; SCD Type 2 melacak histori perubahan entitas. |
| **Timeliness** | 10% | 92 / 100 | 9.2 | Didukung tabel audit watermark (`etl_watermark`) untuk *incremental loading* serta orkestrator ganda (APScheduler + Systemd Timer). |
| **Total DQS** | **100%** | **96 / 100** | **96.0 / 100** | **Sangat Baik (Exceeds Requirements)** |

---

### What: Temuan Audit & Metrik Kualitas Terverifikasi

1. **Physical Staging Layer & Zero Ingestion Failure [Verified]**
   - Database [`dwh_staging`](file:///home/lann/Projects/project-oltp-to-dwh/sql/04_staging_ddl.sql) menampung 477.243 baris mentah dari dua sumber (BR: 451.464, ID: 25.779) ke 6 tabel fisik staging (`stg_customers`, `stg_products`, `stg_sellers`, `stg_orders`, `stg_order_items`, `stg_order_payments`).
   - Penggunaan tipe data permisif (`VARCHAR`/`TEXT`) pada staging berhasil mengeliminasi risiko kegagalan *data truncation* saat pertama kali mengekstrak string dirty data dari OLTP.

2. **Cascading Quarantine & Cleansing Boundary [Verified]**
   - Modul [`etl/clean.py`](file:///home/lann/Projects/project-oltp-to-dwh/etl/clean.py) berhasil menyaring dirty data ke tabel karantina [`rejected_rows`](file:///home/lann/Projects/project-oltp-to-dwh/sql/03_support_tables.sql#L31-L43):
     - Anomali kronologi (order sampai sebelum waktu beli, estimasi sebelum beli): 522 baris.
     - Timestamp masa depan (*future timestamp*): 264 baris.
     - Harga produk dan nilai pembayaran negatif / nol: 1.290 baris.
     - Status order korup / pergeseran kolom: 552 baris.
   - Mekanisme *cascading reject* berhasil mencegah 2.136 item dan pembayaran yatim (*orphaned records*) yang merujuk pada pesanan yang telah tertolak.

3. **Rekonsiliasi Finansial Multi-Source (Zero Data Loss) [Verified]**
   - **Brazil (BRL):**  
     Total OLTP: `13.591.643,70`  
     Total DWH (`13.588.077,91`) + Rejected (`3.565,79`) = `13.591.643,70` (Selisih: `0,00`).
   - **Indonesia (IDR):**  
     Total OLTP: `55.000.648.074,58`  
     Total DWH (`643.414,63`) + Rejected (`55.000,004,659.95`) = `55.000.648.074,58` (Selisih: `0,00`).
   - Audit membuktikan tidak ada nilai moneter yang lenyap tanpa jejak selama proses ETL.

4. **Integritas Star Schema DWH [Verified]**
   - Pemuatan fakta ([`etl/load.py`](file:///home/lann/Projects/project-oltp-to-dwh/etl/load.py)):
     - [`fact_order_items`](file:///home/lann/Projects/project-oltp-to-dwh/sql/02_dwh_ddl.sql#L97-L113): 117.962 baris.
     - [`fact_order_delivery`](file:///home/lann/Projects/project-oltp-to-dwh/sql/02_dwh_ddl.sql#L120-L139): 104.242 baris.
     - [`fact_order_payments`](file:///home/lann/Projects/project-oltp-to-dwh/sql/02_dwh_ddl.sql#L146-L163): 108.859 baris.
   - Seluruh dimensi pelengkap ([`dim_customer`](file:///home/lann/Projects/project-oltp-to-dwh/sql/02_dwh_ddl.sql#L15-L33), [`dim_product`](file:///home/lann/Projects/project-oltp-to-dwh/sql/02_dwh_ddl.sql#L36-L53), [`dim_seller`](file:///home/lann/Projects/project-oltp-to-dwh/sql/02_dwh_ddl.sql#L56-L74), [`dim_date`](file:///home/lann/Projects/project-oltp-to-dwh/sql/02_dwh_ddl.sql#L77-L94)) memuat 100% pasangan referensi yang valid (0 orphaned FKs).

5. **Ketahanan Suite Pengujian [Verified]**
   - 12 dari 12 test otomatis pada [`tests/test_clean.py`](file:///home/lann/Projects/project-oltp-to-dwh/tests/test_clean.py), [`tests/test_dwh_integrity.py`](file:///home/lann/Projects/project-oltp-to-dwh/tests/test_dwh_integrity.py), dan [`tests/test_progress.py`](file:///home/lann/Projects/project-oltp-to-dwh/tests/test_progress.py) berstatus lulus (*passed*).

---

### Why It Matters: Dampak Analitikal & Akademik

1. **Keamanan Integritas Keputusan Bisnis:**  
   Penyaringan data kotor pada layer ETL dan staging mencegah pembiasan metrik esensial pada dashboard analitik (seperti distorsi nilai GMV akibat harga negatif atau outlier Rp 55 Miliar yang dihasilkan dari kesalahan OCR/simulasi input).
2. **Kepatuhan Audit Finansial:**  
   Pencatatan setiap baris yang ditolak ke dalam tabel karantina memungkinkan tim data melakukan *post-mortem* rekonstruksi data dan membuktikan neraca akuntansi secara presisi.
3. **Isolasi Beban Transaksional:**  
   Penempatan database staging pada host DWH (port 3308) meminimalisir read lock yang berlebihan terhadap instance OLTP transaksional (port 3306 & 3307).

---

### How to Act: Rekomendasi Pemeliharaan Jangka Panjang

1. **Hapus File Redundan Tersisa (Opsional):**  
   File [`requirements_dashboard.txt`](file:///home/lann/Projects/project-oltp-to-dwh/requirements_dashboard.txt) sudah tidak digunakan oleh sistem devenv/docker dan seluruh dependensinya telah terintegrasi di [`requirements.txt`](file:///home/lann/Projects/project-oltp-to-dwh/requirements.txt). Anda dapat menghapusnya untuk menjaga kerapian root project.
2. **Setup Alerting Thresholds pada Pipeline Otomatis:**  
   Jika rasio penolakan (*rejection rate*) pada suatu run harian melampaui ambang batas 5% dari total batch, buat mekanisme notifikasi (misal via email atau log alert level CRITICAL) agar upstream data feed segera diperiksa.
3. **Implementasi Housekeeping Table Karantina:**  
   Buat jadwal pembersihan berkala (misal retensi 90 hari) untuk tabel `rejected_rows` dan `etl_log` guna mencegah pembengkakan disk storage DWH di masa mendatang.

---

### Kesimpulan Akhir
Seluruh komponen arsitektur data warehouse (OLTP multi-source, staging area fisik, modul transformasi dan cleansing, star schema, scheduler, docker environment, hingga Streamlit dashboard) telah diaudit secara menyeluruh dan berada dalam kondisi **prima, valid, serta siap dipresentasikan**.

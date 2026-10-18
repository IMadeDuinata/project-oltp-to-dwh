# TASK: Build OLTP Indonesia — Fresh, Isolated

## Context

Project DWH dengan source Olist (Brazil). Existing code di `oltp/`, `etl/`,
`dwh/`, `dashboard/`, `legacy/`, `sql/` → **ABAIKAN SEMUA**. Jangan baca,
jangan modifikasi, jangan import.

Bangun **hanya** OLTP Indonesia dari nol di folder baru `oltp_id/`.

## Arsitektur Target
32-hex hash ID Prefixed ID (CID-2024-00001)
ISO date format Mixed date format
Portuguese kategori Mixed kategori (ID/EN/PT)
Mature system Immature system (baru)
│ │
└──────────────┬───────────────┘
▼
(DWH nanti)


Dua sistem **berbeda karakteristik** — DWH yang unify via surrogate key.

## Deliverables

### 1. `oltp_id/generate_olist_id.py`

Generate CSV dummy Indonesia → `data/olist_id/`:

- 9 CSV: customers, orders, order_items, products, sellers, payments, reviews, geolocation, category_translation
- `_manifest.json` — dokumentasi karakteristik sistem

**Spec:**
- Seed: 42 (deterministic)
- Sample: 5% dari `data/raw/olist_orders_dataset.csv` (anchor, ambil order_id yang ada)
- Semua `*_id` → format Indonesia:
  - `customer_id` → `CID-2024-00001`
  - `customer_unique_id` → `UID-2024-00001`
  - `order_id` → `ORD-2024-00001`
  - `product_id` → `PRD-2024-00001`
  - `seller_id` → `SLR-2024-00001`
  - `review_id` → `REV-2024-00001`
- Mapping 1:1 dijaga: old_id → new_id (repeat buyer tetap, orphan tetap orphan)
- Geography: mutate `city` dari pool kota Indonesia, `state` dari 34 provinsi
- `zip_code_prefix`: 5-digit string

**Karakteristik sistem Indonesia (bukan "dirt injection" — ini representasi sistem yang belum mature):**

| # | Tabel | Karakteristik | Rate |
|---|---|---|---|
| 1 | orders | Format tanggal campur (ISO, DD/MM/YYYY, MM-DD-YYYY) | 5% |
| 2 | orders | Tanggal mustahil (`2099-12-31`) | 1% |
| 3 | orders | Status tidak standar (`PENDING?`, `unknown`) | 2% |
| 4 | orders | Orphan FK (customer_id tidak ada di customers) | 2% |
| 5 | customers | Duplikasi (proses dedup belum jalan) | 2% |
| 6 | customers | Whitespace + case inconsistency di city/state | 5% |
| 7 | customers | NULL unique_id (validasi lemah) | 1% |
| 8 | items | Harga negatif (bug input) | 2% |
| 9 | items | Outlier ekstrem (`999_999_999`) | 1% |
| 10 | payments | `payment_value` negatif | 1% |

**Category mismatch (code unification scenario):**
- Untuk tiap `product_category_name` (PT), generate 4-5 varian:
  - Varian 0: canonical ID (`Kecantikan & Kesehatan`)
  - Varian 1: lowercase (`kecantikan & kesehatan`)
  - Varian 2: snake_case (`kecantikan_kesehatan`)
  - Varian 3: truncated (`Kecantikan`)
  - Varian 4: PT untranslated (`Beleza Saude`)
- Assign 1 varian per produk deterministik
- Kolom output: `product_category_name` (variant), `product_category_name_original` (PT asli)

### 2. `oltp_id/load_to_oltp_id.py`

Load CSV → MySQL `olist_oltp_id`:

1. **Staging**: Load semua CSV ke tabel `olist_raw` di db `olist_oltp_id`
2. **Split 3NF**: Split staging ke 6-7 tabel OLTP 3NF:
   `customers`, `products`, `sellers`, `orders`, `order_items`,
   `order_payments`, `order_reviews`
3. **JANGAN clean** — biarkan karakteristik sistem apa adanya
4. **Schema reference**: baca `sql/01_oltp_ddl.sql` (read-only, jangan edit)
5. Kalau butuh modifikasi schema (misal tambah kolom), buat
   `oltp_id/schema_indo.sql` baru — jangan edit yang existing

**Config:**
- Baca `.env` (DB_HOST, DB_USER, DB_PASS)
- Database: `olist_oltp_id`
- Connection: `mysql+pymysql://...` via SQLAlchemy

### 3. `oltp_id/README.md`

- Cara run (2 langkah)
- Prasyarat (MySQL running, db exists)
- Manifest lokasi
- Contoh query verifikasi

## Constraints (WAJIB)

1. ❌ JANGAN baca/modifikasi `oltp/`, `etl/`, `dwh/`, `dashboard/`, `legacy/`, `sql/`, `scheduler/`, `tests/`
2. ✅ BOLEH BACA `sql/01_oltp_ddl.sql` (read-only, schema reference)
3. ✅ BOLEH BACA `data/raw/*.csv` (source)
4. ✅ SEMUA kode baru di `oltp_id/`
5. ✅ Tanpa Faker — `numpy.random.default_rng` + pool statis
6. ✅ Deterministic (seed=42)
7. ✅ ID format Indonesia wajib prefixed (`CID-2024-00001`), BUKAN hash
8. ✅ Repeat buyer pattern preserved (mapping 1:1)

## Acceptance Criteria

1. `data/olist_id/` berisi 9 CSV + `_manifest.json`
2. `_manifest.json` berisi: `system_characteristics` (10 item), `category_variants`, `row_counts`, `config`
3. MySQL `olist_oltp_id` terisi 6-7 tabel OLTP
4. Row counts masuk akal: orders ~4.950, customers ~5.100, items ~5.600
5. FK check: 0 orphan **kecuali** yang intentional (orders.customer_id)
6. Repeat buyer: `SELECT customer_unique_id, COUNT(*) FROM customers GROUP BY 1 HAVING COUNT(*) > 1` → banyak rows
7. Karakteristik visible: `SELECT * FROM orders WHERE order_status LIKE '%?'` → returns
8. Category variants: `SELECT DISTINCT product_category_name FROM products` → mixed formats
9. Sample customers: format `CID-2024-xxxxx`, city/state Indonesia

## Estimasi Output
Total rows: ~33.000 (~4 MB CSV)
Karakteristik rows: ~1.250 (3.8%)
Unique buyers: ~3.800
Category variants: ~6.000 produk


## TIDAK Masuk Scope

- ETL OLTP → DWH
- DWH star schema
- Dashboard, scheduler
- Devenv/Nix config
- Review codebase existing
- OLTP Brazil (biarkan existing)

## Cara Mulai

1. Cek `data/raw/` punya 9 CSV Olist
2. Baca `sql/01_oltp_ddl.sql` untuk schema reference
3. Buat folder `oltp_id/`
4. Generate 3 file di atas
5. Run: `python oltp_id/generate_olist_id.py`
6. Verify CSV + manifest
7. Run: `python oltp_id/load_to_oltp_id.py` (butuh MySQL running + db `olist_oltp_id` created)
8. Verify acceptance criteria

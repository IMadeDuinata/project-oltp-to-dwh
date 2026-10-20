**TASK: Phase E — `source_country` Passthrough ke Fact Tables**

**3 perubahan, semuanya kecil:**

**Perubahan 1 — `etl/transform.py`: tambah `source_country` ke semua `fact_cols`**

Di `build_fact_order_items`, sebelum `return`, tambahkan `"source_country"` ke `fact_cols` list. Source country sudah ada di `df_items` (dari extract). Setelah merge dengan orders, cek dulu: kalau merge `how="left"` dari items ke orders, `source_country` dari items ikut. Tambahkan ke list:

```python
fact_cols = [
    "order_id", "order_item_id", "customer_sk", "product_sk", "seller_sk",
    "purchase_date_sk", "shipping_limit_date_sk", "order_status",
    "price", "freight_value", "total_item_value",
    "source_country",   # ← tambahkan
]
```

Di `build_fact_order_delivery`, `source_country` ada di `df_orders`. Tambahkan ke `fact_cols`:

```python
fact_cols = [
    "order_id", "customer_sk", "purchase_date_sk", "delivered_date_sk", "estimated_date_sk",
    "order_status", "actual_delivery_days", "estimated_delivery_days",
    "delivery_delay_days", "is_delayed",
    "source_country",   # ← tambahkan
]
```

Di `build_fact_order_payments`, setelah merge dengan orders, `source_country` dari payments (bukan orders — payments punya source_country sendiri dari extract). Tambahkan ke `fact_cols`:

```python
fact_cols = [
    "order_id", "payment_sequential", "customer_sk", "payment_type_sk",
    "purchase_date_sk", "payment_value", "payment_installments",
    "source_country",   # ← tambahkan
]
```

**Perubahan 2 — DWH DDL: tambah kolom `source_country` ke 3 fact tables**

File ini kemungkinan ada di `sql/` atau `dwh/` — cari file DDL DWH (biasanya ada `02_dwh_ddl.sql` atau serupa). Tambahkan kolom ini ke ketiga fact tables:

```sql
source_country VARCHAR(5) NOT NULL DEFAULT 'BR'
```

Tambahkan sebelum closing `)` di masing-masing tabel `fact_order_items`, `fact_order_delivery`, `fact_order_payments`. Kalau DWH sudah running dan tabelnya sudah ada, perlu juga ALTER:

```sql
ALTER TABLE fact_order_items ADD COLUMN source_country VARCHAR(5) NOT NULL DEFAULT 'BR';
ALTER TABLE fact_order_delivery ADD COLUMN source_country VARCHAR(5) NOT NULL DEFAULT 'BR';
ALTER TABLE fact_order_payments ADD COLUMN source_country VARCHAR(5) NOT NULL DEFAULT 'BR';
```

Buat file `sql/migrate_add_source_country.sql` untuk ALTER ini — jangan hapus DDL aslinya.

**Perubahan 3 — `build_dim_date` di `transform.py`: extend range**

Sekarang `end_date="2020-12-31"` — data Indonesia bisa sampai 2024 (ID-nya generate dari 2024 based on generate script). Ubah ke `end_date="2025-12-31"` agar `date_sk` lookup tidak jatuh ke `-1` untuk transaksi ID yang lebih baru.

---

**File yang diubah:** `etl/transform.py` (3 fact_cols + 1 date range), file DDL DWH (tambah kolom), buat `sql/migrate_add_source_country.sql`.

**File yang TIDAK boleh diubah:** `load.py`, `clean.py`, `reconcile.py`, `extract.py`, `config.py`.

**Verifikasi:** `python -m py_compile etl/transform.py` bersih.

---

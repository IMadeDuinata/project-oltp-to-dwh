**TASK: Phase C — `etl/reconcile.py` (Schema Harmonization BR↔ID)**

**Context:** Setelah Phase B, `extract_oltp_data()` return dict gabungan dimana setiap tabel punya kolom `source_country` dan bisa punya mixed dtypes antar row. Phase C membuat modul baru `etl/reconcile.py` yang menerima dict itu dan mengembalikan dict yang sudah diharmonisasi — tipe konsisten, nilai comparable, siap masuk ke `clean.py`.

**Buat file baru: `etl/reconcile.py`**

**Entry point tunggal:**
```python
def reconcile(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
```
Terima output `extract_oltp_data()`, return dict dengan schema yang sudah diharmonisasi. Proses per tabel, apply transformasi berbasis `source_country`.

---

**Harmonisasi yang harus dilakukan per tabel:**

**orders — paling kritis:**

Kolom timestamp (`order_purchase_timestamp`, `order_approved_at`, `order_delivered_carrier_date`, `order_delivered_customer_date`, `order_estimated_delivery_date`) di BR bertipe DATETIME (sudah `datetime64[ns]` setelah SQLAlchemy), di ID bertipe VARCHAR dengan format campur. Untuk row ID, parse ke datetime dengan `pd.to_datetime(..., infer_datetime_format=True, errors='coerce')` — hasil NaT untuk yang tidak bisa di-parse. Setelah harmonisasi, semua kolom timestamp harus `datetime64[ns]` untuk seluruh tabel.

Buat fungsi private `_harmonize_timestamps(df, timestamp_cols)` yang apply ini hanya untuk row dimana `source_country == "ID"`, sisakan row BR tidak tersentuh.

**order_items:**

Kolom `price` dan `freight_value` di BR bertipe DECIMAL (sudah `float64`), di ID bertipe VARCHAR. Untuk row ID, cast ke `float64` dengan `pd.to_numeric(..., errors='coerce')` — hasil NaN untuk yang tidak bisa dicast (negatif tetap masuk sebagai nilai numerik, dibersihkan di clean phase nanti). Buat fungsi private `_harmonize_numerics(df, numeric_cols)`.

**order_payments:**

Kolom `payment_value` — sama dengan di atas, ID punya VARCHAR. Apply `_harmonize_numerics`.

**customers:**

Kolom `customer_state` — BR punya kode 2-huruf (UF codes: SP, RJ, dst), ID punya nama provinsi panjang ("Jawa Barat", "Bali", dst). JANGAN normalize ke satu format di sini — biarkan tetap, cukup pastikan tipe adalah `VARCHAR`/`object`. Log info bahwa state representation berbeda antar source.

**products:**

Kolom `product_category_name` di ID bisa punya 5 varian format (mixed case, underscore, etc). JANGAN normalize di sini — itu pekerjaan clean phase. Pastikan kolom `product_category_name_original` ada di result — untuk row BR, kolom ini tidak ada (BR tidak punya kolom itu), jadi isi dengan `None`/`NaN`. Gunakan `df.get('product_category_name_original')` atau assign NaN kalau tidak ada.

Juga: kolom `product_name_length` dan `product_description_length` — di BR kemungkinan bertipe INT, di ID juga INT (karena schema_indo.sql sudah INT). Tapi verifikasi, jika ada yang object, cast ke `pd.Int64Dtype()` (nullable integer) dengan `errors='coerce'`.

**sellers, category_translation:** Tidak perlu harmonisasi khusus — tipe sudah kompatibel.

---

**Setelah harmonisasi, validasi dan log:**

Setelah setiap tabel diproses, log ringkasan: jumlah row per source, jumlah NaT/NaN yang dihasilkan dari coerce (sebagai indikator seberapa banyak data ID yang tidak bisa di-parse), nama kolom yang berhasil diharmonisasi.

Format log: `[RECONCILE] tabel: X baris, Y NaT di kolom Z`

---

**Integrasi ke `run_etl.py`:**

Tambahkan satu baris import dan satu baris call di `run_etl.py` antara Extract dan Clean:

```python
from etl.reconcile import reconcile
# ...
# Di dalam fungsi utama, setelah extract:
data = reconcile(data)
```

Ini satu-satunya perubahan di `run_etl.py`. Jangan ubah yang lain.

---

**File yang diubah:** `etl/reconcile.py` (baru) + satu import + satu call di `run_etl.py`.

**File yang TIDAK boleh diubah:** `extract.py`, `clean.py`, `transform.py`, `load.py`, `config.py`.

**Verifikasi:** `python -m py_compile etl/reconcile.py` bersih.

---

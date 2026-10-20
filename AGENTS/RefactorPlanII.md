**TASK: Phase B — Dual-Source Extract + Source Tagging**

**Context:** `etl/config.py` sudah punya `get_oltp_br_engine()` dan `get_oltp_id_engine()`. `etl/extract.py` sekarang hanya extract dari satu engine dan tidak tahu soal Indonesia. Tujuan Phase B: extract dari kedua OLTP secara terpisah, tag setiap row dengan `source_country`, dan return satu dict gabungan per tabel.

**File yang diubah: `etl/extract.py`** — refactor total, tapi jaga semua fungsi public yang sudah ada agar `run_etl.py` tidak perlu diubah dulu.

**Spesifikasi perubahan:**

**1. Tambah fungsi `extract_from_source(engine, source_country, incremental, watermark)`**

Fungsi internal yang menerima satu engine dan melakukan extract persis seperti logika yang sudah ada, lalu tambahkan kolom `source_country` (string: `"BR"` atau `"ID"`) ke setiap DataFrame yang dikembalikan. Return dict dengan key: `customers`, `products`, `sellers`, `orders`, `order_items`, `order_payments`.

Perhatian khusus untuk ID: kolom `order_purchase_timestamp` di OLTP ID bertipe VARCHAR, bukan DATETIME. Jangan paksa konversi di sini — biarkan raw, konversi nanti di reconcile/clean phase. Watermark comparison untuk ID harus string-based atau skip incremental untuk ID dulu (safe fallback: selalu full extract untuk ID di phase ini, karena timestamp-nya string campur format).

**2. Ubah `extract_oltp_data()` jadi orchestrator dual-source**

```python
def extract_oltp_data(incremental: bool = False, pipeline_name="olist_pipeline") -> dict[str, pd.DataFrame]:
```

Signature tetap sama. Di dalamnya:
- Extract BR: pakai `get_oltp_br_engine()`, `source_country="BR"`, ikuti logika incremental yang sudah ada
- Extract ID: pakai `get_oltp_id_engine()`, `source_country="ID"`, selalu full extract untuk sekarang (watermark ID belum diimplementasi)
- Gabungkan per tabel dengan `pd.concat([df_br, df_id], ignore_index=True)`
- Return dict gabungan

**3. Watermark tetap hanya untuk BR pipeline**

`get_last_watermark()` dan `update_watermark()` tidak diubah. Watermark hanya berlaku untuk `orders` dari BR. ID selalu full extract.

**4. Schema mismatch — JANGAN resolve di sini**

Kolom yang berbeda antara BR dan ID (misalnya BR punya DATETIME `order_purchase_timestamp`, ID punya VARCHAR) akan menyebabkan mixed-dtype column setelah concat. Ini disengaja — biarkan heterogen, Phase C (reconcile.py) yang akan handle. Cukup tambahkan log warning kalau ada kolom yang tipenya tidak cocok antar source.

**5. Tabel yang di-extract dari ID**

Sama dengan BR: `customers`, `products`, `sellers`, `orders`, `order_items`, `order_payments`. OLTP ID juga punya `order_reviews` dan `geolocation`, tapi untuk sekarang skip dulu — focus ke tabel yang paralel dengan BR.

**6. Logging**

Setiap source log terpisah dengan prefix `[BR]` dan `[ID]`. Setelah concat, log jumlah baris gabungan per tabel.

**File yang TIDAK boleh diubah:** `run_etl.py`, `clean.py`, `transform.py`, `load.py`, `config.py`.

**Verifikasi:** `python -m py_compile etl/extract.py` harus bersih.

---

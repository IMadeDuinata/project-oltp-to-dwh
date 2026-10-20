**TASK: Phase D — Source-Aware Patch pada `etl/clean.py`**

**Hanya 4 perubahan, tidak ada rewrite:**

**Patch 1 — `clean_bad_business_logic`, blok validasi orders:**

Setelah mask `mask_deliv_null` dan `mask_canc_deliv` didefinisikan, wrap keduanya dengan source filter:

```python
# 3. status == 'delivered' tapi delivered_date null — hanya untuk BR
mask_deliv_null = (df_ord["order_status"] == "delivered") & \
                  (df_ord["order_delivered_customer_date"].isna()) & \
                  (df_ord.get("source_country", pd.Series("BR", index=df_ord.index)) == "BR")

# 4. status == 'canceled' tapi delivered_date NOT null — hanya untuk BR
mask_canc_deliv = (df_ord["order_status"] == "canceled") & \
                  (df_ord["order_delivered_customer_date"].notna()) & \
                  (df_ord.get("source_country", pd.Series("BR", index=df_ord.index)) == "BR")
```

Note: gunakan `df_ord["source_country"] == "BR"` langsung kalau kolom sudah pasti ada (setelah Phase B selalu ada). Tidak perlu `.get()` — cukup tambahkan `& (df_ord["source_country"] == "BR")` di akhir masing-masing mask.

**Patch 2 — `clean_deduplication`, normalisasi `customer_state`:**

Ganti baris:
```python
df_cust["customer_state"] = df_cust["customer_state"].astype(str).str.strip().str.upper()
```
Dengan:
```python
# BR: UF 2-huruf → uppercase. ID: nama provinsi → preserve case, hanya strip
is_br = df_cust.get("source_country", pd.Series(dtype=str)) == "BR"
df_cust.loc[is_br, "customer_state"] = df_cust.loc[is_br, "customer_state"].astype(str).str.strip().str.upper()
df_cust.loc[~is_br, "customer_state"] = df_cust.loc[~is_br, "customer_state"].astype(str).str.strip()
```

Sama untuk `seller_state` di blok seller (seller ID juga punya nama provinsi panjang).

**Patch 3 — `clean_null_handling`, normalisasi category name untuk ID:**

Di blok produk, setelah `fillna("unknown")` dan sebelum size_cols imputation, tambahkan:

```python
# Normalisasi product_category_name hanya untuk ID: lowercase + underscore
if "source_country" in df_prod_clean.columns:
    is_id = df_prod_clean["source_country"] == "ID"
    # Simpan original dulu jika belum ada
    if "product_category_name_original" in df_prod_clean.columns:
        # Hanya update original untuk ID yang belum punya nilai original
        no_orig = is_id & df_prod_clean["product_category_name_original"].isna()
        df_prod_clean.loc[no_orig, "product_category_name_original"] = \
            df_prod_clean.loc[no_orig, "product_category_name"]
    # Normalize
    df_prod_clean.loc[is_id, "product_category_name"] = (
        df_prod_clean.loc[is_id, "product_category_name"]
        .astype(str).str.strip().str.lower().str.replace(r"\s+", "_", regex=True)
    )
```

**Patch 4 — `clean_domain_validation_and_shift`, tambah validasi `payment_value < 0`:**

Di blok payments, setelah filter `mask_invalid_pay` dan sebelum `return`, tambahkan:

```python
# Validasi payment_value < 0 (karakteristik data kotor ID)
mask_neg_pay = df_pay_clean["payment_value"] < 0
rej_neg_pay = df_pay_clean[mask_neg_pay]
rejections.extend(
    record_rejections(
        rej_neg_pay,
        table_source="order_payments",
        column_name="payment_value",
        reason="negative payment_value"
    )
)
df_pay_clean = df_pay_clean[~mask_neg_pay].copy()
logger.info(f"  -> Ditolak order_payments karena payment_value negatif: {len(rej_neg_pay):,} baris")
```

---

**File yang diubah:** hanya `etl/clean.py`, 4 patch, tidak ada structural change.

**Verifikasi:** `python -m py_compile etl/clean.py` bersih.

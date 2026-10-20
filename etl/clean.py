"""
Modul Cleansing Data ETL:
Mengimplementasikan minimal 3 (disini 4) teknik pembersihan data:
1. Null handling (imputasi kategori unknown, reject approval kosong pada non-canceled)
2. Deduplikasi (text normalization, exact duplicate, business key duplicate)
3. Bad business logic (delivered < purchase, price <= 0, freight < 0, conflict delivery & status, future date)
4. Validasi domain & penanganan column shift (order_status, payment_type)

Semua baris yang ditolak TIDAK didrop diam-diam, melainkan disimpan ke daftar rejected_rows.
"""

import json
import logging
import pandas as pd
from datetime import datetime

from etl.config import VALID_ORDER_STATUSES, VALID_PAYMENT_TYPES

logger = logging.getLogger(__name__)


def record_rejections(df_rejected: pd.DataFrame, table_source: str, column_name: str, reason: str) -> list[dict]:
    """Helper untuk memformat baris yang ditolak menjadi format tabel rejected_rows."""
    records = []
    if df_rejected.empty:
        return records
    
    for _, row in df_rejected.iterrows():
        # Konversi row ke dictionary serializable JSON
        row_dict = row.to_dict()
        for k, v in row_dict.items():
            if isinstance(v, (pd.Timestamp, datetime)):
                row_dict[k] = v.isoformat()
            elif pd.isna(v):
                row_dict[k] = None

        records.append({
            "table_source": table_source,
            "column_name": column_name,
            "rejection_reason": reason,
            "raw_record_json": json.dumps(row_dict),
        })
    return records


# ============================================================
# 1. NULL HANDLING
# ============================================================
def clean_null_handling(df_products: pd.DataFrame, df_orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """
    Teknik 1: Null Handling
    - df_products: product_category_name null -> imputasi 'unknown'.
      (Alasan: data produk tetap berharga untuk analisis order walau kategorinya belum tercatat).
    - df_orders: order_approved_at null pada order non-canceled -> REJECT.
      (Alasan: transaksi yang bukan dibatalkan wajib memiliki bukti otorisasi/approval pembayaran).
    """
    logger.info("Menjalankan Teknik 1: Null Handling...")
    rejections = []

    # Produk: Imputasi
    df_prod_clean = df_products.copy()
    null_cat_count = df_prod_clean["product_category_name"].isna().sum()
    df_prod_clean["product_category_name"] = df_prod_clean["product_category_name"].fillna("unknown")
    logger.info(f"  -> Imputasi product_category_name 'unknown': {null_cat_count:,} baris")

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

    # Imputasi ukuran produk yang kosong dengan 0
    size_cols = ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm", "product_photos_qty"]
    for sc in size_cols:
        if sc in df_prod_clean.columns:
            df_prod_clean[sc] = df_prod_clean[sc].fillna(0)

    # Orders: Validasi Null pada non-canceled
    df_ord_copy = df_orders.copy()
    mask_invalid_appr = (df_ord_copy["order_status"] != "canceled") & (df_ord_copy["order_approved_at"].isna())
    df_ord_rejected = df_ord_copy[mask_invalid_appr]
    df_ord_clean = df_ord_copy[~mask_invalid_appr].copy()

    rejections.extend(
        record_rejections(
            df_ord_rejected,
            table_source="orders",
            column_name="order_approved_at",
            reason="order_approved_at is null on active/non-canceled order"
        )
    )
    logger.info(f"  -> Ditolak orders (approved_at null pd non-canceled): {len(df_ord_rejected):,} baris")

    return df_prod_clean, df_ord_clean, rejections


# ============================================================
# 2. DEDUPLIKASI & NORMALISASI TEKS
# ============================================================
def clean_deduplication(
    df_customers: pd.DataFrame,
    df_sellers: pd.DataFrame,
    df_items: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    """
    Teknik 2: Deduplikasi & Normalisasi Teks
    - Normalisasi: strip whitespace, lowercase pada nama kota dan state.
    - Cek duplikat persis dan duplikat business key (order_id, order_item_id).
    """
    logger.info("Menjalankan Teknik 2: Deduplikasi & Normalisasi Teks...")
    rejections = []

    # Normalisasi teks customer
    df_cust = df_customers.copy()
    df_cust["customer_city"] = df_cust["customer_city"].astype(str).str.strip().str.lower()
    # BR: UF 2-huruf → uppercase. ID: nama provinsi → preserve case, hanya strip
    # Fallback: jika kolom source_country tidak ada, treat semua sebagai BR
    if "source_country" in df_cust.columns:
        is_br_cust = df_cust["source_country"] == "BR"
    else:
        is_br_cust = pd.Series(True, index=df_cust.index)
    df_cust.loc[is_br_cust, "customer_state"] = df_cust.loc[is_br_cust, "customer_state"].astype(str).str.strip().str.upper()
    df_cust.loc[~is_br_cust, "customer_state"] = df_cust.loc[~is_br_cust, "customer_state"].astype(str).str.strip()
    df_cust_clean = df_cust.drop_duplicates(subset=["customer_id"]).copy()

    # Normalisasi teks seller
    df_sell = df_sellers.copy()
    df_sell["seller_city"] = df_sell["seller_city"].astype(str).str.strip().str.lower()
    if "source_country" in df_sell.columns:
        is_br_sell = df_sell["source_country"] == "BR"
    else:
        is_br_sell = pd.Series(True, index=df_sell.index)
    df_sell.loc[is_br_sell, "seller_state"] = df_sell.loc[is_br_sell, "seller_state"].astype(str).str.strip().str.upper()
    df_sell.loc[~is_br_sell, "seller_state"] = df_sell.loc[~is_br_sell, "seller_state"].astype(str).str.strip()
    df_sell_clean = df_sell.drop_duplicates(subset=["seller_id"]).copy()

    # Cek Duplikasi pada order_items
    df_it = df_items.copy()
    
    # Deteksi duplikat persis
    exact_dups_mask = df_it.duplicated(keep="first")
    df_it_exact_rejected = df_it[exact_dups_mask]
    rejections.extend(
        record_rejections(
            df_it_exact_rejected,
            table_source="order_items",
            column_name="all_columns",
            reason="exact_duplicate_row"
        )
    )
    df_it = df_it[~exact_dups_mask].copy()

    # Deteksi duplikat Business Key (order_id, order_item_id)
    bk_dups_mask = df_it.duplicated(subset=["order_id", "order_item_id"], keep="first")
    df_it_bk_rejected = df_it[bk_dups_mask]
    rejections.extend(
        record_rejections(
            df_it_bk_rejected,
            table_source="order_items",
            column_name="order_id, order_item_id",
            reason="duplicate_business_key_order_item"
        )
    )
    df_it_clean = df_it[~bk_dups_mask].copy()

    total_item_rej = len(df_it_exact_rejected) + len(df_it_bk_rejected)
    logger.info(f"  -> Ditolak order_items duplikat: {total_item_rej:,} baris")

    return df_cust_clean, df_sell_clean, df_it_clean, rejections


# ============================================================
# 3. BAD BUSINESS LOGIC
# ============================================================
def clean_bad_business_logic(df_orders: pd.DataFrame, df_items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """
    Teknik 3: Validasi Logika Bisnis (Bad Business Logic)
    Orders:
    - delivered_date < purchase_timestamp
    - estimated_date < purchase_timestamp
    - status == 'delivered' tapi delivered_date is null
    - status == 'canceled' tapi delivered_date is not null
    - purchase_timestamp di masa depan (tahun > 2026)
    Order Items:
    - price <= 0
    - freight_value < 0
    """
    logger.info("Menjalankan Teknik 3: Validasi Bad Business Logic...")
    rejections = []

    # Validasi Orders
    df_ord = df_orders.copy()
    
    # 1. delivered < purchase
    mask_deliv_early = (df_ord["order_delivered_customer_date"].notna()) & (
        df_ord["order_delivered_customer_date"] < df_ord["order_purchase_timestamp"]
    )
    rej_deliv_early = df_ord[mask_deliv_early]
    rejections.extend(
        record_rejections(
            rej_deliv_early,
            table_source="orders",
            column_name="order_delivered_customer_date",
            reason="order delivered before purchase timestamp"
        )
    )

    # 2. estimated < purchase
    mask_est_early = (df_ord["order_estimated_delivery_date"].notna()) & (
        df_ord["order_estimated_delivery_date"] < df_ord["order_purchase_timestamp"]
    )
    rej_est_early = df_ord[mask_est_early]
    rejections.extend(
        record_rejections(
            rej_est_early,
            table_source="orders",
            column_name="order_estimated_delivery_date",
            reason="estimated delivery date before purchase timestamp"
        )
    )

    # 3. status == 'delivered' tapi delivered_date null — hanya untuk BR
    mask_deliv_null = (
        (df_ord["order_status"] == "delivered")
        & (df_ord["order_delivered_customer_date"].isna())
        & (df_ord.get("source_country", pd.Series("BR", index=df_ord.index)) == "BR")
    )
    rej_deliv_null = df_ord[mask_deliv_null]
    rejections.extend(
        record_rejections(
            rej_deliv_null,
            table_source="orders",
            column_name="order_delivered_customer_date",
            reason="delivered status but delivery date is null"
        )
    )

    # 4. status == 'canceled' tapi delivered_date NOT null — hanya untuk BR
    mask_canc_deliv = (
        (df_ord["order_status"] == "canceled")
        & (df_ord["order_delivered_customer_date"].notna())
        & (df_ord.get("source_country", pd.Series("BR", index=df_ord.index)) == "BR")
    )
    rej_canc_deliv = df_ord[mask_canc_deliv]
    rejections.extend(
        record_rejections(
            rej_canc_deliv,
            table_source="orders",
            column_name="order_status, order_delivered_customer_date",
            reason="canceled status but delivery date is present"
        )
    )

    # 5. Future purchase date (> 2026-10-31)
    mask_future = df_ord["order_purchase_timestamp"] > pd.to_datetime("2026-10-31")
    rej_future = df_ord[mask_future]
    rejections.extend(
        record_rejections(
            rej_future,
            table_source="orders",
            column_name="order_purchase_timestamp",
            reason="purchase timestamp in future date"
        )
    )

    # Filter orders bersih
    mask_all_bad_ord = mask_deliv_early | mask_est_early | mask_deliv_null | mask_canc_deliv | mask_future
    df_ord_clean = df_ord[~mask_all_bad_ord].copy()
    logger.info(f"  -> Ditolak orders karena bad business logic: {mask_all_bad_ord.sum():,} baris")

    # Validasi Order Items
    df_it = df_items.copy()
    mask_price_invalid = (df_it["price"] <= 0) | (df_it["price"] > 99999999.99)
    rej_price = df_it[mask_price_invalid]
    rejections.extend(
        record_rejections(
            rej_price,
            table_source="order_items",
            column_name="price",
            reason="price must be greater than zero and within valid range (<= 99999999.99)"
        )
    )

    mask_freight_invalid = (df_it["freight_value"] < 0) | (df_it["freight_value"] > 99999999.99)
    rej_freight = df_it[mask_freight_invalid]
    rejections.extend(
        record_rejections(
            rej_freight,
            table_source="order_items",
            column_name="freight_value",
            reason="freight value cannot be negative or exceed column limits"
        )
    )

    mask_all_bad_it = mask_price_invalid | mask_freight_invalid
    df_it_clean = df_it[~mask_all_bad_it].copy()
    logger.info(f"  -> Ditolak order_items karena price invalid/outlier atau freight < 0: {mask_all_bad_it.sum():,} baris")

    return df_ord_clean, df_it_clean, rejections


# ============================================================
# 4. VALIDASI DOMAIN & PENANGANAN COLUMN SHIFT
# ============================================================
def clean_domain_validation_and_shift(df_orders: pd.DataFrame, df_payments: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """
    Teknik 4: Validasi Domain & Deteksi Column Shift
    - order_status harus ada dalam VALID_ORDER_STATUSES.
      Jika berisi tahun (contoh '2018'), ditolak ke karantina.
    - payment_type harus ada dalam VALID_PAYMENT_TYPES.
      Jika berisi 2 huruf kapital kode state ('SP', 'RJ'), terdeteksi shift dan dikarantina.
    """
    logger.info("Menjalankan Teknik 4: Validasi Domain & Deteksi Column Shift...")
    rejections = []

    # Validasi order_status
    df_ord = df_orders.copy()
    mask_invalid_status = ~df_ord["order_status"].isin(VALID_ORDER_STATUSES)
    rej_status = df_ord[mask_invalid_status]
    rejections.extend(
        record_rejections(
            rej_status,
            table_source="orders",
            column_name="order_status",
            reason="invalid order_status domain (suspected column shift or corrupted value)"
        )
    )
    df_ord_clean = df_ord[~mask_invalid_status].copy()
    logger.info(f"  -> Ditolak orders karena status tidak valid / shift: {len(rej_status):,} baris")

    # Validasi payment_type
    df_pay = df_payments.copy()
    mask_invalid_pay = ~df_pay["payment_type"].isin(VALID_PAYMENT_TYPES)
    rej_pay = df_pay[mask_invalid_pay]
    rejections.extend(
        record_rejections(
            rej_pay,
            table_source="order_payments",
            column_name="payment_type",
            reason="invalid payment_type domain (suspected column shift containing state code)"
        )
    )
    df_pay_clean = df_pay[~mask_invalid_pay].copy()
    logger.info(f"  -> Ditolak order_payments karena payment_type tidak valid / shift: {len(rej_pay):,} baris")

    # Validasi payment_value < 0 (karakteristik data kotor ID)
    # Hanya jalankan jika kolom payment_value ada (bisa tidak ada di data test minimal)
    if "payment_value" in df_pay_clean.columns:
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

    return df_ord_clean, df_pay_clean, rejections


# ============================================================
# ORKESTRASI PIPELINE CLEANSING
# ============================================================
def clean_all_data(data: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], list[dict], dict]:
    """
    Menjalankan seluruh teknik cleansing secara berurutan:
    1. Null handling
    2. Deduplikasi & Text normalisasi
    3. Bad business logic
    4. Validasi domain & shift

    Mengembalikan:
    - dict dataframe bersih
    - list dictionary baris rejected
    - dict audit summary (before vs after)
    """
    audit = {}
    all_rejections = []

    # Catat baris awal (before)
    for k, v in data.items():
        audit[f"{k}_rows_before"] = len(v)

    # 1. Null handling
    df_products, df_orders, rej_null = clean_null_handling(data["products"], data["orders"])
    all_rejections.extend(rej_null)

    # 2. Deduplikasi
    df_customers, df_sellers, df_items, rej_dedup = clean_deduplication(data["customers"], data["sellers"], data["order_items"])
    all_rejections.extend(rej_dedup)

    # 3. Bad business logic
    df_orders, df_items, rej_logic = clean_bad_business_logic(df_orders, df_items)
    all_rejections.extend(rej_logic)

    # 4. Validasi domain & shift
    df_orders, df_payments, rej_domain = clean_domain_validation_and_shift(df_orders, data["order_payments"])
    all_rejections.extend(rej_domain)

    # Harmonisasi relasi: pastikan item & payments hanya merujuk ke orders yang lolos validasi
    valid_order_ids = set(df_orders["order_id"])
    orphan_items = df_items[~df_items["order_id"].isin(valid_order_ids)]
    if not orphan_items.empty:
        all_rejections.extend(
            record_rejections(
                orphan_items,
                table_source="order_items",
                column_name="order_id",
                reason="order_item references an order rejected during cleansing"
            )
        )
        df_items = df_items[df_items["order_id"].isin(valid_order_ids)].copy()

    orphan_payments = df_payments[~df_payments["order_id"].isin(valid_order_ids)]
    if not orphan_payments.empty:
        all_rejections.extend(
            record_rejections(
                orphan_payments,
                table_source="order_payments",
                column_name="order_id",
                reason="payment references an order rejected during cleansing"
            )
        )
        df_payments = df_payments[df_payments["order_id"].isin(valid_order_ids)].copy()

    clean_data = {
        "customers": df_customers,
        "products": df_products,
        "sellers": df_sellers,
        "orders": df_orders,
        "order_items": df_items,
        "order_payments": df_payments,
    }

    # Catat baris akhir (after)
    for k, v in clean_data.items():
        audit[f"{k}_rows_after"] = len(v)
    audit["total_rejected_records"] = len(all_rejections)

    return clean_data, all_rejections, audit


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from etl.extract import extract_oltp_data
    raw_data = extract_oltp_data()
    clean_data, rejections, audit = clean_all_data(raw_data)
    print("\nAudit Ringkasan Cleansing:")
    for k, v in audit.items():
        print(f"  - {k}: {v:,}")


if __name__ == "__main__":
    main()

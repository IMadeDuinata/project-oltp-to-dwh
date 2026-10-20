"""
Modul Cleansing Data ETL:
Implementasi teknik pembersihan data:
1. Null handling (imputasi produk, penolakan pesanan aktif tanpa approval date)
2. Deduplikasi & normalisasi teks (kota, state, exact duplicate, business key duplicate)
3. Bad business logic (kronologi terbalik, harga/ongkir <= 0, tanggal masa depan)
4. Validasi domain & penanganan column shift (order_status, payment_type)
"""

import json
import logging
from datetime import datetime
from typing import Callable, Optional
import pandas as pd

from etl.config import VALID_ORDER_STATUSES, VALID_PAYMENT_TYPES

logger = logging.getLogger(__name__)


def record_rejections(df_rejected: pd.DataFrame, table_source: str, column_name: str, reason: str) -> list[dict]:
    """Helper efisien untuk mencatat baris data yang ditolak ke format rejected_rows."""
    if df_rejected.empty:
        return []

    records = df_rejected.astype(object).where(pd.notna(df_rejected), None).to_dict(orient="records")
    return [
        {
            "table_source": table_source,
            "column_name": column_name,
            "rejection_reason": reason,
            "raw_record_json": json.dumps(r, default=str),
        }
        for r in records
    ]


def clean_null_handling(df_products: pd.DataFrame, df_orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """Teknik 1: Imputasi nilai NULL pada produk dan validasi order_approved_at non-canceled."""
    logger.info("Menjalankan Teknik 1: Null Handling...")
    rejections = []

    # 1. Imputasi Produk
    df_prod = df_products.copy()
    df_prod["product_category_name"] = df_prod["product_category_name"].fillna("unknown")

    # Normalisasi nama kategori untuk ID: lowercase + underscore
    if "source_country" in df_prod.columns:
        is_id = df_prod["source_country"] == "ID"
        if "product_category_name_original" in df_prod.columns:
            no_orig = is_id & df_prod["product_category_name_original"].isna()
            df_prod.loc[no_orig, "product_category_name_original"] = df_prod.loc[no_orig, "product_category_name"]
        df_prod.loc[is_id, "product_category_name"] = (
            df_prod.loc[is_id, "product_category_name"]
            .astype(str).str.strip().str.lower().str.replace(r"\s+", "_", regex=True)
        )

    size_cols = ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm", "product_photos_qty"]
    for sc in size_cols:
        if sc in df_prod.columns:
            df_prod[sc] = df_prod[sc].fillna(0)

    # 2. Orders: Tolak approval null pada order non-canceled
    df_ord = df_orders.copy()
    mask_invalid_appr = (df_ord["order_status"] != "canceled") & (df_ord["order_approved_at"].isna())
    rejections.extend(
        record_rejections(
            df_ord[mask_invalid_appr],
            table_source="orders",
            column_name="order_approved_at",
            reason="order_approved_at is null on active/non-canceled order",
        )
    )
    df_ord_clean = df_ord[~mask_invalid_appr].copy()
    return df_prod, df_ord_clean, rejections


def clean_deduplication(
    df_customers: pd.DataFrame,
    df_sellers: pd.DataFrame,
    df_items: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    """Teknik 2: Deduplikasi entitas dan normalisasi teks (kota & state)."""
    logger.info("Menjalankan Teknik 2: Deduplikasi & Normalisasi Teks...")
    rejections = []

    # Normalisasi teks Customer & Seller
    def normalize_geo(df: pd.DataFrame, city_col: str, state_col: str, id_col: str) -> pd.DataFrame:
        df_out = df.copy()
        df_out[city_col] = df_out[city_col].astype(str).str.strip().str.lower()
        is_br = df_out["source_country"] == "BR" if "source_country" in df_out.columns else pd.Series(True, index=df_out.index)
        df_out.loc[is_br, state_col] = df_out.loc[is_br, state_col].astype(str).str.strip().str.upper()
        df_out.loc[~is_br, state_col] = df_out.loc[~is_br, state_col].astype(str).str.strip()
        return df_out.drop_duplicates(subset=[id_col]).copy()

    df_cust_clean = normalize_geo(df_customers, "customer_city", "customer_state", "customer_id")
    df_sell_clean = normalize_geo(df_sellers, "seller_city", "seller_state", "seller_id")

    # Deduplikasi Order Items (Exact Duplicates & Business Key Duplicates)
    df_it = df_items.copy()
    exact_mask = df_it.duplicated(keep="first")
    rejections.extend(record_rejections(df_it[exact_mask], "order_items", "all_columns", "exact_duplicate_row"))
    df_it = df_it[~exact_mask].copy()

    bk_mask = df_it.duplicated(subset=["order_id", "order_item_id"], keep="first")
    rejections.extend(record_rejections(df_it[bk_mask], "order_items", "order_id, order_item_id", "duplicate_business_key_order_item"))
    df_it_clean = df_it[~bk_mask].copy()

    return df_cust_clean, df_sell_clean, df_it_clean, rejections


def clean_bad_business_logic(df_orders: pd.DataFrame, df_items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """Teknik 3: Validasi anomali logika bisnis (kronologi, batasan numerik, dan tanggal masa depan)."""
    logger.info("Menjalankan Teknik 3: Validasi Bad Business Logic...")
    rejections = []
    df_ord = df_orders.copy()

    # Rule checks untuk Orders
    is_br = df_ord.get("source_country", pd.Series("BR", index=df_ord.index)) == "BR"
    order_rules = [
        (
            df_ord["order_delivered_customer_date"].notna() & (df_ord["order_delivered_customer_date"] < df_ord["order_purchase_timestamp"]),
            "order_delivered_customer_date",
            "order delivered before purchase timestamp",
        ),
        (
            df_ord["order_estimated_delivery_date"].notna() & (df_ord["order_estimated_delivery_date"] < df_ord["order_purchase_timestamp"]),
            "order_estimated_delivery_date",
            "estimated delivery date before purchase timestamp",
        ),
        (
            (df_ord["order_status"] == "delivered") & df_ord["order_delivered_customer_date"].isna() & is_br,
            "order_delivered_customer_date",
            "delivered status but delivery date is null",
        ),
        (
            (df_ord["order_status"] == "canceled") & df_ord["order_delivered_customer_date"].notna() & is_br,
            "order_status, order_delivered_customer_date",
            "canceled status but delivery date is present",
        ),
        (
            df_ord["order_purchase_timestamp"] > pd.to_datetime("2026-10-31"),
            "order_purchase_timestamp",
            "purchase timestamp in future date",
        ),
    ]

    mask_bad_orders = pd.Series(False, index=df_ord.index)
    for mask, col, reason in order_rules:
        rejections.extend(record_rejections(df_ord[mask], "orders", col, reason))
        mask_bad_orders |= mask

    df_ord_clean = df_ord[~mask_bad_orders].copy()

    # Rule checks untuk Order Items
    df_it = df_items.copy()
    item_rules = [
        (
            (df_it["price"] <= 0) | (df_it["price"] > 99999999.99),
            "price",
            "price must be greater than zero and within valid range (<= 99999999.99)",
        ),
        (
            (df_it["freight_value"] < 0) | (df_it["freight_value"] > 99999999.99),
            "freight_value",
            "freight value cannot be negative or exceed column limits",
        ),
    ]

    mask_bad_items = pd.Series(False, index=df_it.index)
    for mask, col, reason in item_rules:
        rejections.extend(record_rejections(df_it[mask], "order_items", col, reason))
        mask_bad_items |= mask

    df_it_clean = df_it[~mask_bad_items].copy()
    return df_ord_clean, df_it_clean, rejections


def clean_domain_validation_and_shift(df_orders: pd.DataFrame, df_payments: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """Teknik 4: Validasi domain diskrit dan penanganan pergeseran kolom (column shift)."""
    logger.info("Menjalankan Teknik 4: Validasi Domain & Deteksi Column Shift...")
    rejections = []

    # Validasi order_status
    df_ord = df_orders.copy()
    mask_invalid_status = ~df_ord["order_status"].isin(VALID_ORDER_STATUSES)
    rejections.extend(
        record_rejections(
            df_ord[mask_invalid_status],
            "orders",
            "order_status",
            "invalid order_status domain (suspected column shift or corrupted value)",
        )
    )
    df_ord_clean = df_ord[~mask_invalid_status].copy()

    # Validasi payment_type & payment_value
    df_pay = df_payments.copy()
    mask_invalid_pay = ~df_pay["payment_type"].isin(VALID_PAYMENT_TYPES)
    rejections.extend(
        record_rejections(
            df_pay[mask_invalid_pay],
            "order_payments",
            "payment_type",
            "invalid payment_type domain (suspected column shift containing state code)",
        )
    )
    df_pay_clean = df_pay[~mask_invalid_pay].copy()

    if "payment_value" in df_pay_clean.columns:
        mask_neg_pay = df_pay_clean["payment_value"] < 0
        rejections.extend(record_rejections(df_pay_clean[mask_neg_pay], "order_payments", "payment_value", "negative payment_value"))
        df_pay_clean = df_pay_clean[~mask_neg_pay].copy()

    return df_ord_clean, df_pay_clean, rejections


def clean_all_data(
    data: dict[str, pd.DataFrame],
    on_progress: Optional[Callable[[str, int, int], None]] = None,
) -> tuple[dict[str, pd.DataFrame], list[dict], dict]:
    """Orkestrator seluruh teknik cleansing dengan proteksi cascading relational rejection."""
    audit = {f"{k}_rows_before": len(v) for k, v in data.items()}
    all_rejections = []

    # 1. Null handling
    df_products, df_orders, rej_null = clean_null_handling(data["products"], data["orders"])
    all_rejections.extend(rej_null)
    if on_progress:
        on_progress("null_handling", 1, 6)

    # 2. Deduplikasi
    df_customers, df_sellers, df_items, rej_dedup = clean_deduplication(data["customers"], data["sellers"], data["order_items"])
    all_rejections.extend(rej_dedup)
    if on_progress:
        on_progress("deduplication", 2, 6)

    # 3. Bad business logic
    df_orders, df_items, rej_logic = clean_bad_business_logic(df_orders, df_items)
    all_rejections.extend(rej_logic)
    if on_progress:
        on_progress("business_logic", 3, 6)

    # 4. Validasi domain & shift
    df_orders, df_payments, rej_domain = clean_domain_validation_and_shift(df_orders, data["order_payments"])
    all_rejections.extend(rej_domain)
    if on_progress:
        on_progress("domain_validation", 4, 6)

    # 5. Cascading Relational Rejection: Buang anak (items & payments) jika order induknya ditolak
    valid_order_ids = set(df_orders["order_id"])

    orphan_items = df_items[~df_items["order_id"].isin(valid_order_ids)]
    if not orphan_items.empty:
        all_rejections.extend(
            record_rejections(
                orphan_items,
                "order_items",
                "order_id",
                "order_item references an order rejected during cleansing",
            )
        )
        df_items = df_items[df_items["order_id"].isin(valid_order_ids)].copy()

    orphan_payments = df_payments[~df_payments["order_id"].isin(valid_order_ids)]
    if not orphan_payments.empty:
        all_rejections.extend(
            record_rejections(
                orphan_payments,
                "order_payments",
                "order_id",
                "payment references an order rejected during cleansing",
            )
        )
        df_payments = df_payments[df_payments["order_id"].isin(valid_order_ids)].copy()

    if on_progress:
        on_progress("relational_integrity", 5, 6)

    clean_data = {
        "customers": df_customers,
        "products": df_products,
        "sellers": df_sellers,
        "orders": df_orders,
        "order_items": df_items,
        "order_payments": df_payments,
    }

    for k, v in clean_data.items():
        audit[f"{k}_rows_after"] = len(v)
    audit["total_rejected_records"] = len(all_rejections)

    if on_progress:
        on_progress("clean_ready", 6, 6)

    return clean_data, all_rejections, audit


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from etl.extract import extract_oltp_data
    raw_data = extract_oltp_data()
    _, _, audit = clean_all_data(raw_data)
    print("\nAudit Ringkasan Cleansing:")
    for k, v in audit.items():
        print(f"  - {k}: {v:,}")


if __name__ == "__main__":
    main()

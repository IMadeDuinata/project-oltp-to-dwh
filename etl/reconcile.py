"""
Modul Reconcile: Harmonisasi Skema Data Multi-Source (Brazil & Indonesia).
Tujuan:
- Menerima data mentah hasil penggabungan extract dual-source.
- Menyelaraskan format timestamp, numerik, dan kolom varian antara data BR dan ID.
- Menghasilkan tipe data yang homogen dan konsisten sebelum masuk ke tahap cleansing.
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def _harmonize_timestamps(df: pd.DataFrame, timestamp_cols: list[str]) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Menyelaraskan kolom timestamp untuk dataset yang memiliki mixed-format.
    Baris ID (VARCHAR beraneka format) diparse menjadi datetime64[ns].
    Baris BR (sudah datetime / standard) tetap dipertahankan atau dipastikan bertipe datetime.
    """
    df = df.copy()
    nat_counts = {}

    for col in timestamp_cols:
        if col not in df.columns:
            continue

        initially_null = df[col].isna().sum()

        if "source_country" in df.columns:
            is_id = df["source_country"] == "ID"
            # Parse datetime hanya untuk baris ID
            parsed_id = pd.to_datetime(df.loc[is_id, col], errors="coerce")
            # Pastikan kolom bertipe datetime secara keseluruhan
            if not pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = pd.to_datetime(df[col], errors="coerce")
            df.loc[is_id, col] = parsed_id
        else:
            df[col] = pd.to_datetime(df[col], errors="coerce")

        final_null = df[col].isna().sum()
        new_nat = max(0, int(final_null - initially_null))
        nat_counts[col] = new_nat

    return df, nat_counts


def _harmonize_numerics(df: pd.DataFrame, numeric_cols: list[str]) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Menyelaraskan kolom numerik (misal float/decimal).
    Baris ID (VARCHAR) dicast ke numeric (float64).
    Nilai invalid dipaksa menjadi NaN (errors='coerce').
    """
    df = df.copy()
    nan_counts = {}

    for col in numeric_cols:
        if col not in df.columns:
            continue

        initially_null = df[col].isna().sum()

        if "source_country" in df.columns:
            is_id = df["source_country"] == "ID"
            parsed_id = pd.to_numeric(df.loc[is_id, col], errors="coerce")
            if not pd.api.types.is_float_dtype(df[col]) and not pd.api.types.is_integer_dtype(df[col]):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df.loc[is_id, col] = parsed_id
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        final_null = df[col].isna().sum()
        new_nan = max(0, int(final_null - initially_null))
        nan_counts[col] = new_nan

    return df, nan_counts


def reconcile(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """
    Entry point harmonisasi skema untuk dual-source OLTP data (BR & ID).
    Menerima output dari extract_oltp_data() dan mengembalikan dictionary dengan skema yang kompatibel.
    """
    logger.info("Memulai proses harmonisasi skema BR <-> ID...")
    reconciled_data: dict[str, pd.DataFrame] = {}

    # 1. orders: harmonisasi timestamp ke datetime64[ns]
    if "orders" in data:
        df_orders = data["orders"].copy()
        ts_cols = [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ]
        df_orders, nat_counts = _harmonize_timestamps(df_orders, ts_cols)
        reconciled_data["orders"] = df_orders

        for c, cnt in nat_counts.items():
            if cnt > 0:
                logger.info(f"[RECONCILE] orders: {len(df_orders):,} baris, {cnt:,} NaT baru di kolom `{c}`")
        logger.info(f"[RECONCILE] orders: {len(df_orders):,} baris berhasil diharmonisasi.")

    # 2. order_items: harmonisasi price & freight_value
    if "order_items" in data:
        df_items = data["order_items"].copy()
        num_cols = ["price", "freight_value"]
        df_items, nan_counts = _harmonize_numerics(df_items, num_cols)
        # Harmonisasikan juga shipping_limit_date jika ada
        if "shipping_limit_date" in df_items.columns:
            df_items, ts_cnt = _harmonize_timestamps(df_items, ["shipping_limit_date"])
            for c, cnt in ts_cnt.items():
                if cnt > 0:
                    logger.info(f"[RECONCILE] order_items: {cnt:,} NaT baru di kolom `{c}`")
        reconciled_data["order_items"] = df_items

        for c, cnt in nan_counts.items():
            if cnt > 0:
                logger.info(f"[RECONCILE] order_items: {len(df_items):,} baris, {cnt:,} NaN baru di kolom `{c}`")
        logger.info(f"[RECONCILE] order_items: {len(df_items):,} baris berhasil diharmonisasi.")

    # 3. order_payments: harmonisasi payment_value
    if "order_payments" in data:
        df_pay = data["order_payments"].copy()
        num_cols = ["payment_value"]
        df_pay, nan_counts = _harmonize_numerics(df_pay, num_cols)
        reconciled_data["order_payments"] = df_pay

        for c, cnt in nan_counts.items():
            if cnt > 0:
                logger.info(f"[RECONCILE] order_payments: {len(df_pay):,} baris, {cnt:,} NaN baru di kolom `{c}`")
        logger.info(f"[RECONCILE] order_payments: {len(df_pay):,} baris berhasil diharmonisasi.")

    # 4. customers: verifikasi customer_state
    if "customers" in data:
        df_cust = data["customers"].copy()
        if "customer_state" in df_cust.columns:
            df_cust["customer_state"] = df_cust["customer_state"].astype("object")
            logger.info(
                "[RECONCILE] customers: `customer_state` dipertahankan sebagai object (BR: UF 2-huruf, ID: nama provinsi)."
            )
        reconciled_data["customers"] = df_cust
        logger.info(f"[RECONCILE] customers: {len(df_cust):,} baris diproses.")

    # 5. products: penanganan product_category_name_original & nullable integer length
    if "products" in data:
        df_prod = data["products"].copy()
        # Pastikan kolom product_category_name_original ada (diisi None / NaN jika BR tidak memiliki)
        if "product_category_name_original" not in df_prod.columns:
            df_prod["product_category_name_original"] = None

        # Harmonisasikan panjang nama & deskripsi ke nullable Int64 jika masih bertipe object
        for col in ["product_name_length", "product_description_length", "product_photos_qty"]:
            if col in df_prod.columns and df_prod[col].dtype == "object":
                df_prod[col] = pd.to_numeric(df_prod[col], errors="coerce").astype("Int64")

        # Pastikan kolom dimensi numerik float
        for col in ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]:
            if col in df_prod.columns and df_prod[col].dtype == "object":
                df_prod[col] = pd.to_numeric(df_prod[col], errors="coerce")

        reconciled_data["products"] = df_prod
        logger.info(f"[RECONCILE] products: {len(df_prod):,} baris berhasil diharmonisasi.")

    # 6. sellers & tabel lainnya: teruskan secara langsung
    for tbl, df in data.items():
        if tbl not in reconciled_data:
            reconciled_data[tbl] = df.copy()
            logger.info(f"[RECONCILE] {tbl}: {len(df):,} baris diteruskan tanpa transformasi khusus.")

    return reconciled_data

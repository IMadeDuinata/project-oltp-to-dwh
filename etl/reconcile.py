"""
Modul Reconcile: Harmonisasi Skema Data Multi-Source (Brazil & Indonesia).
Menyeragamkan format timestamp dan numerik sebelum tahap cleansing.
"""

import logging
from typing import Callable, Optional
import pandas as pd

logger = logging.getLogger(__name__)


def _harmonize_timestamps(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Menyelaraskan kolom timestamp beraneka format menjadi datetime64[ns]."""
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _harmonize_numerics(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Menyelaraskan kolom numerik string/object menjadi float64."""
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def reconcile(
    data: dict[str, pd.DataFrame],
    on_progress: Optional[Callable[[str, int, int], None]] = None,
) -> dict[str, pd.DataFrame]:
    """Menyelaraskan format kolom orders, items, payments, dan products lintas sumber data (BR & ID)."""
    logger.info("Memulai harmonisasi skema BR <-> ID...")
    out = {k: v.copy() for k, v in data.items()}

    # 1. orders: timestamps
    if "orders" in out:
        ts_cols = [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ]
        out["orders"] = _harmonize_timestamps(out["orders"], ts_cols)
        if on_progress:
            on_progress("orders", 1, 6)

    # 2. order_items: numerik & limit date
    if "order_items" in out:
        out["order_items"] = _harmonize_numerics(out["order_items"], ["price", "freight_value"])
        if "shipping_limit_date" in out["order_items"].columns:
            out["order_items"] = _harmonize_timestamps(out["order_items"], ["shipping_limit_date"])
        if on_progress:
            on_progress("order_items", 2, 6)

    # 3. order_payments: numerik payment_value
    if "order_payments" in out:
        out["order_payments"] = _harmonize_numerics(out["order_payments"], ["payment_value"])
        if on_progress:
            on_progress("order_payments", 3, 6)

    # 4. customers: customer_state object
    if "customers" in out:
        if "customer_state" in out["customers"].columns:
            out["customers"]["customer_state"] = out["customers"]["customer_state"].astype("object")
        if on_progress:
            on_progress("customers", 4, 6)

    # 5. products: kolom varian & ukuran numerik
    if "products" in out:
        df_p = out["products"]
        if "product_category_name_original" not in df_p.columns:
            df_p["product_category_name_original"] = None

        int_cols = ["product_name_length", "product_description_length", "product_photos_qty"]
        for col in int_cols:
            if col in df_p.columns and df_p[col].dtype == "object":
                df_p[col] = pd.to_numeric(df_p[col], errors="coerce").astype("Int64")

        float_cols = ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]
        for col in float_cols:
            if col in df_p.columns and df_p[col].dtype == "object":
                df_p[col] = pd.to_numeric(df_p[col], errors="coerce")
        out["products"] = df_p
        if on_progress:
            on_progress("products", 5, 6)

    if on_progress:
        on_progress("sellers", 6, 6)

    logger.info("Harmonisasi skema selesai.")
    return out

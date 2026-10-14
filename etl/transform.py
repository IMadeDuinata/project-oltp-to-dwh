"""
Modul Transform: Mengubah data bersih menjadi Star Schema (Dimensi & Fakta).
Desain DWH:
1. Dimensi:
   - dim_customer (SCD Type 2: valid_from, valid_to, is_current, BK: customer_unique_id)
   - dim_product (BK: product_id)
   - dim_seller (BK: seller_id)
   - dim_payment_type (BK: payment_type)
   - dim_date (Role-Playing Dimension dengan date_sk format YYYYMMDD)
   - Semua dimensi memiliki record UNKNOWN (-1) untuk menangani missing FK tanpa silent drop!
2. Fakta:
   - Fact 1: fact_order_items (grain: order_id + order_item_id, measures: price, freight_value, total)
   - Fact 2: fact_order_delivery (grain: order_id, measures: actual_delivery_days, estimated_delivery_days, delivery_delay_days, is_delayed)
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

UNKNOWN_SK = -1


# ============================================================
# 1. BUILD DIMENSI
# ============================================================
def build_dim_customer(df_customers: pd.DataFrame) -> pd.DataFrame:
    """
    Membangun dim_customer dengan SCD Type 2:
    - customer_unique_id sebagai business key
    - valid_from, valid_to, is_current
    - Record UNKNOWN (-1)
    """
    logger.info("Transforming dim_customer (SCD Type 2)...")
    df = df_customers.copy()
    
    # Ambil baris unik per customer_unique_id
    df_dedup = df.drop_duplicates(subset=["customer_unique_id"]).copy()
    
    dim = pd.DataFrame({
        "customer_id": df_dedup["customer_id"],
        "customer_unique_id": df_dedup["customer_unique_id"],
        "customer_zip_code": df_dedup["customer_zip_code_prefix"].fillna("00000"),
        "customer_city": df_dedup["customer_city"].fillna("unknown"),
        "customer_state": df_dedup["customer_state"].fillna("NA"),
        "valid_from": pd.to_datetime("2016-01-01 00:00:00"),
        "valid_to": pd.NaT,
        "is_current": 1,
    })

    # Tambahkan baris Unknown (-1)
    unknown_row = pd.DataFrame([{
        "customer_sk": UNKNOWN_SK,
        "customer_id": "UNKNOWN",
        "customer_unique_id": "UNKNOWN",
        "customer_zip_code": "00000",
        "customer_city": "unknown",
        "customer_state": "NA",
        "valid_from": pd.to_datetime("1970-01-01 00:00:00"),
        "valid_to": pd.NaT,
        "is_current": 1,
    }])
    
    dim = pd.concat([unknown_row, dim], ignore_index=True)
    return dim


def build_dim_product(df_products: pd.DataFrame) -> pd.DataFrame:
    """Membangun dim_product dengan record UNKNOWN (-1)."""
    logger.info("Transforming dim_product...")
    df = df_products.copy().drop_duplicates(subset=["product_id"])

    dim = pd.DataFrame({
        "product_id": df["product_id"],
        "product_category_name": df["product_category_name"].fillna("unknown"),
        "product_name_length": pd.to_numeric(df["product_name_length"], errors="coerce").fillna(0).astype(int),
        "product_description_length": pd.to_numeric(df["product_description_length"], errors="coerce").fillna(0).astype(int),
        "product_photos_qty": pd.to_numeric(df["product_photos_qty"], errors="coerce").fillna(0).astype(int),
        "product_weight_g": pd.to_numeric(df["product_weight_g"], errors="coerce").fillna(0.0),
        "product_length_cm": pd.to_numeric(df["product_length_cm"], errors="coerce").fillna(0.0),
        "product_height_cm": pd.to_numeric(df["product_height_cm"], errors="coerce").fillna(0.0),
        "product_width_cm": pd.to_numeric(df["product_width_cm"], errors="coerce").fillna(0.0),
    })

    unknown_row = pd.DataFrame([{
        "product_sk": UNKNOWN_SK,
        "product_id": "UNKNOWN",
        "product_category_name": "unknown",
        "product_name_length": 0,
        "product_description_length": 0,
        "product_photos_qty": 0,
        "product_weight_g": 0.0,
        "product_length_cm": 0.0,
        "product_height_cm": 0.0,
        "product_width_cm": 0.0,
    }])

    dim = pd.concat([unknown_row, dim], ignore_index=True)
    return dim


def build_dim_seller(df_sellers: pd.DataFrame) -> pd.DataFrame:
    """Membangun dim_seller dengan record UNKNOWN (-1)."""
    logger.info("Transforming dim_seller...")
    df = df_sellers.copy().drop_duplicates(subset=["seller_id"])

    dim = pd.DataFrame({
        "seller_id": df["seller_id"],
        "seller_zip_code": df["seller_zip_code_prefix"].fillna("00000"),
        "seller_city": df["seller_city"].fillna("unknown"),
        "seller_state": df["seller_state"].fillna("NA"),
    })

    unknown_row = pd.DataFrame([{
        "seller_sk": UNKNOWN_SK,
        "seller_id": "UNKNOWN",
        "seller_zip_code": "00000",
        "seller_city": "unknown",
        "seller_state": "NA",
    }])

    dim = pd.concat([unknown_row, dim], ignore_index=True)
    return dim


def build_dim_payment_type(df_payments: pd.DataFrame) -> pd.DataFrame:
    """Membangun dim_payment_type dengan record UNKNOWN (-1)."""
    logger.info("Transforming dim_payment_type...")
    types = df_payments["payment_type"].dropna().unique()
    dim = pd.DataFrame({"payment_type": types})

    unknown_row = pd.DataFrame([{
        "payment_type_sk": UNKNOWN_SK,
        "payment_type": "unknown",
    }])

    dim = pd.concat([unknown_row, dim], ignore_index=True)
    return dim


def build_dim_date(start_date="2016-01-01", end_date="2020-12-31") -> pd.DataFrame:
    """Membangun dim_date (kalender) dengan date_sk format YYYYMMDD dan UNKNOWN (-1)."""
    logger.info("Transforming dim_date...")
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    dim = pd.DataFrame({"full_date": dates})
    dim["date_sk"] = dim["full_date"].dt.strftime("%Y%m%d").astype(int)
    dim["day"] = dim["full_date"].dt.day
    dim["month"] = dim["full_date"].dt.month
    dim["month_name"] = dim["full_date"].dt.strftime("%B")
    dim["quarter"] = dim["full_date"].dt.quarter
    dim["year"] = dim["full_date"].dt.year
    dim["day_of_week"] = dim["full_date"].dt.strftime("%A")
    dim["is_weekend"] = dim["full_date"].dt.dayofweek.isin([5, 6]).astype(int)

    unknown_row = pd.DataFrame([{
        "date_sk": UNKNOWN_SK,
        "full_date": pd.to_datetime("1970-01-01").date(),
        "day": 1,
        "month": 1,
        "month_name": "January",
        "quarter": 1,
        "year": 1970,
        "day_of_week": "Thursday",
        "is_weekend": 0,
    }])

    dim = pd.concat([unknown_row, dim], ignore_index=True)
    return dim


# ============================================================
# 2. BUILD TABEL FAKTA
# ============================================================
def to_date_sk(series: pd.Series) -> pd.Series:
    """Helper konversi Timestamp ke date_sk integer (YYYYMMDD) atau -1 jika NaT."""
    dt = pd.to_datetime(series, errors="coerce")
    return dt.dt.strftime("%Y%m%d").fillna(UNKNOWN_SK).astype(int)


def build_fact_order_items(
    df_items: pd.DataFrame,
    df_orders: pd.DataFrame,
    cust_sk_map: dict[str, int],
    prod_sk_map: dict[str, int],
    seller_sk_map: dict[str, int],
) -> pd.DataFrame:
    """
    Membangun fact_order_items:
    Grain: order_id + order_item_id
    Measures: price, freight_value, total_item_value
    """
    logger.info("Building fact_order_items...")
    
    # Gabungkan item dengan orders untuk mendapatkan customer_id & status & purchase timestamp
    df = df_items.merge(
        df_orders[["order_id", "customer_id", "order_status", "order_purchase_timestamp"]],
        on="order_id",
        how="left",
    )

    # Lookup surrogate keys
    df["customer_sk"] = df["customer_id"].map(cust_sk_map).fillna(UNKNOWN_SK).astype(int)
    df["product_sk"] = df["product_id"].map(prod_sk_map).fillna(UNKNOWN_SK).astype(int)
    df["seller_sk"] = df["seller_id"].map(seller_sk_map).fillna(UNKNOWN_SK).astype(int)

    # Role-playing date keys
    df["purchase_date_sk"] = to_date_sk(df["order_purchase_timestamp"])
    df["shipping_limit_date_sk"] = to_date_sk(df["shipping_limit_date"])

    # Measures
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df["freight_value"] = pd.to_numeric(df["freight_value"], errors="coerce").fillna(0.0)
    df["total_item_value"] = df["price"] + df["freight_value"]
    df["order_item_id"] = pd.to_numeric(df["order_item_id"], errors="coerce").fillna(1).astype(int)

    fact_cols = [
        "order_id",
        "order_item_id",
        "customer_sk",
        "product_sk",
        "seller_sk",
        "purchase_date_sk",
        "shipping_limit_date_sk",
        "order_status",
        "price",
        "freight_value",
        "total_item_value",
    ]
    return df[fact_cols].copy()


def build_fact_order_delivery(
    df_orders: pd.DataFrame,
    cust_sk_map: dict[str, int],
) -> pd.DataFrame:
    """
    Membangun fact_order_delivery:
    Grain: order_id
    Measures: actual_delivery_days, estimated_delivery_days, delivery_delay_days, is_delayed
    """
    logger.info("Building fact_order_delivery...")
    df = df_orders.copy()

    # Lookup customer_sk
    df["customer_sk"] = df["customer_id"].map(cust_sk_map).fillna(UNKNOWN_SK).astype(int)

    # Role-playing date keys
    df["purchase_date_sk"] = to_date_sk(df["order_purchase_timestamp"])
    df["delivered_date_sk"] = to_date_sk(df["order_delivered_customer_date"])
    df["estimated_date_sk"] = to_date_sk(df["order_estimated_delivery_date"])

    # Hitung Measures Delivery
    p_time = pd.to_datetime(df["order_purchase_timestamp"])
    d_time = pd.to_datetime(df["order_delivered_customer_date"])
    e_time = pd.to_datetime(df["order_estimated_delivery_date"])

    # actual_delivery_days (dalam hari dengan desimal)
    actual_days = (d_time - p_time).dt.total_seconds() / 86400.0
    estimated_days = (e_time - p_time).dt.total_seconds() / 86400.0
    delay_days = actual_days - estimated_days

    df["actual_delivery_days"] = actual_days.round(2)
    df["estimated_delivery_days"] = estimated_days.round(2)
    df["delivery_delay_days"] = delay_days.round(2)

    # is_delayed: 1 jika delivered > estimated
    df["is_delayed"] = ((d_time > e_time) & d_time.notna()).astype(int)

    fact_cols = [
        "order_id",
        "customer_sk",
        "purchase_date_sk",
        "delivered_date_sk",
        "estimated_date_sk",
        "order_status",
        "actual_delivery_days",
        "estimated_delivery_days",
        "delivery_delay_days",
        "is_delayed",
    ]
    return df[fact_cols].copy()

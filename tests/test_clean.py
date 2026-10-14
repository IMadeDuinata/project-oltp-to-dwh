"""
Unit Test Cleansing Data (pytest):
Menguji bahwa setiap fungsi cleansing di `etl/clean.py` mampu mendeteksi data kotor
dan menghasilkan output bersih & daftar rejected yang sesuai.
"""

import pytest
import pandas as pd
from datetime import datetime

from etl.clean import (
    clean_null_handling,
    clean_deduplication,
    clean_bad_business_logic,
    clean_domain_validation_and_shift,
)


def test_null_handling():
    # 1. Product Category Null Imputation
    df_prod = pd.DataFrame([
        {"product_id": "p1", "product_category_name": None, "product_weight_g": None},
        {"product_id": "p2", "product_category_name": "eletronicos", "product_weight_g": 500},
    ])
    
    # 2. Order Approved At Null on non-canceled
    df_ord = pd.DataFrame([
        {"order_id": "o1", "order_status": "delivered", "order_approved_at": None},
        {"order_id": "o2", "order_status": "canceled", "order_approved_at": None},
        {"order_id": "o3", "order_status": "delivered", "order_approved_at": pd.to_datetime("2018-01-01 10:00:00")},
    ])

    df_prod_clean, df_ord_clean, rejections = clean_null_handling(df_prod, df_ord)

    # Verifikasi Imputasi Produk
    assert df_prod_clean.loc[df_prod_clean["product_id"] == "p1", "product_category_name"].iloc[0] == "unknown"
    assert df_prod_clean.loc[df_prod_clean["product_id"] == "p1", "product_weight_g"].iloc[0] == 0

    # Verifikasi Rejection Order: o1 ditolak, o2 (canceled) dan o3 tetap lolos
    assert "o1" not in df_ord_clean["order_id"].values
    assert "o2" in df_ord_clean["order_id"].values
    assert "o3" in df_ord_clean["order_id"].values
    assert len(rejections) == 1
    assert rejections[0]["table_source"] == "orders"
    assert rejections[0]["column_name"] == "order_approved_at"


def test_deduplication_and_text_normalization():
    df_cust = pd.DataFrame([
        {"customer_id": "c1", "customer_city": "  SAO PAULO  ", "customer_state": "sp"},
        {"customer_id": "c1", "customer_city": "sao paulo", "customer_state": "SP"},
    ])
    df_sell = pd.DataFrame([
        {"seller_id": "s1", "seller_city": " Rio De Janeiro ", "seller_state": "rj"}
    ])
    df_items = pd.DataFrame([
        {"order_id": "ord1", "order_item_id": 1, "price": 100.0, "freight_value": 10.0},
        {"order_id": "ord1", "order_item_id": 1, "price": 100.0, "freight_value": 10.0}, # Exact duplicate
        {"order_id": "ord2", "order_item_id": 1, "price": 50.0, "freight_value": 5.0},
        {"order_id": "ord2", "order_item_id": 1, "price": 60.0, "freight_value": 5.0}, # Business Key duplicate
    ])

    df_cust_clean, df_sell_clean, df_items_clean, rejections = clean_deduplication(df_cust, df_sell, df_items)

    # Verifikasi normalisasi teks
    assert df_cust_clean.iloc[0]["customer_city"] == "sao paulo"
    assert df_cust_clean.iloc[0]["customer_state"] == "SP"
    assert df_sell_clean.iloc[0]["seller_city"] == "rio de janeiro"
    assert df_sell_clean.iloc[0]["seller_state"] == "RJ"

    # Verifikasi deduplikasi item
    assert len(df_items_clean) == 2
    assert len(rejections) == 2  # 1 exact duplicate + 1 business key duplicate


def test_bad_business_logic():
    df_ord = pd.DataFrame([
        # Kasus 1: Delivered < Purchase
        {
            "order_id": "o_bad_1",
            "order_status": "delivered",
            "order_purchase_timestamp": pd.to_datetime("2018-05-10 10:00:00"),
            "order_delivered_customer_date": pd.to_datetime("2018-05-01 10:00:00"),
            "order_estimated_delivery_date": pd.to_datetime("2018-05-20 00:00:00"),
        },
        # Kasus 2: Status delivered tapi tanggal delivered kosong
        {
            "order_id": "o_bad_2",
            "order_status": "delivered",
            "order_purchase_timestamp": pd.to_datetime("2018-05-10 10:00:00"),
            "order_delivered_customer_date": pd.NaT,
            "order_estimated_delivery_date": pd.to_datetime("2018-05-20 00:00:00"),
        },
        # Kasus 3: Future purchase date (2035)
        {
            "order_id": "o_bad_3",
            "order_status": "delivered",
            "order_purchase_timestamp": pd.to_datetime("2035-01-01 10:00:00"),
            "order_delivered_customer_date": pd.to_datetime("2035-01-05 10:00:00"),
            "order_estimated_delivery_date": pd.to_datetime("2035-01-15 00:00:00"),
        },
        # Kasus 4: Valid order
        {
            "order_id": "o_good",
            "order_status": "delivered",
            "order_purchase_timestamp": pd.to_datetime("2018-05-01 10:00:00"),
            "order_delivered_customer_date": pd.to_datetime("2018-05-08 10:00:00"),
            "order_estimated_delivery_date": pd.to_datetime("2018-05-15 00:00:00"),
        },
    ])

    df_items = pd.DataFrame([
        {"order_id": "o_good", "order_item_id": 1, "price": 100.0, "freight_value": 15.0},
        {"order_id": "o_good", "order_item_id": 2, "price": 0.0, "freight_value": 15.0},    # Price <= 0
        {"order_id": "o_good", "order_item_id": 3, "price": 50.0, "freight_value": -5.0},   # Freight < 0
    ])

    df_ord_clean, df_items_clean, rejections = clean_bad_business_logic(df_ord, df_items)

    assert len(df_ord_clean) == 1
    assert df_ord_clean.iloc[0]["order_id"] == "o_good"
    assert len(df_items_clean) == 1
    assert df_items_clean.iloc[0]["order_item_id"] == 1
    assert len(rejections) == 5  # 3 orders + 2 items


def test_domain_validation_and_column_shift():
    df_ord = pd.DataFrame([
        {"order_id": "o_valid", "order_status": "delivered"},
        {"order_id": "o_shift", "order_status": "2018"},  # Column shift status=year
    ])
    df_pay = pd.DataFrame([
        {"order_id": "o_valid", "payment_type": "credit_card"},
        {"order_id": "o_shift", "payment_type": "SP"},  # Column shift payment=state
    ])

    df_ord_clean, df_pay_clean, rejections = clean_domain_validation_and_shift(df_ord, df_pay)

    assert len(df_ord_clean) == 1
    assert df_ord_clean.iloc[0]["order_id"] == "o_valid"
    assert len(df_pay_clean) == 1
    assert df_pay_clean.iloc[0]["order_id"] == "o_valid"
    assert len(rejections) == 2

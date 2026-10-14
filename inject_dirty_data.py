"""
Script Injeksi Data Kotor ke Staging (olist_raw).
Digunakan untuk menjamin seluruh skenario cleansing dalam INSTRUCTION.md
terpenuhi dan dapat diuji secara terukur:
1. Duplikasi persis & duplikasi business key (order_id, order_item_id)
2. Bad business logic:
   - delivered < purchase
   - estimated < purchase
   - price <= 0
   - freight_value < 0
   - purchase date di masa depan (tahun 2035)
3. Column shift (pergeseran kolom):
   - order_status berisi tahun '2018'
   - payment_type berisi kode state 'SP' / 'RJ'
4. Text trimming / casing issues:
   - Whitespace di nama kota/state
"""

import os
import json
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secret")
DB_NAME_OLTP = os.getenv("DB_NAME_OLTP", os.getenv("DB_NAME", "oltp_olist"))

url = URL.create(
    drivername="mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME_OLTP,
    query={"charset": "utf8mb4"},
)
engine = create_engine(url, pool_pre_ping=True)


def get_dirty_records_to_inject():
    """Menyiapkan kumpulan baris kotor yang representatif."""
    records = [
        # Skenario 1: Duplikasi persis (akan diduplikasi dari baris ini)
        {
            "order_id": "DIRTY_DUP_EXACT_001",
            "order_item_id": "1",
            "product_id": "prod_clean_001",
            "seller_id": "sell_clean_001",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "150.00",
            "freight_value": "15.00",
            "payment_sequential": "1",
            "payment_type": "credit_card",
            "payment_installments": "2",
            "payment_value": "165.00",
            "customer_id": "cust_dirty_dup_1",
            "customer_unique_id": "cust_uniq_dirty_dup_1",
            "customer_zip_code_prefix": "01310",
            "customer_city": "sao paulo",
            "customer_state": "SP",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-25 15:00:00",
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "beleza_saude",
            "product_name_lenght": "50",
            "product_description_lenght": "200",
            "product_photos_qty": "2",
            "product_weight_g": "500",
            "product_length_cm": "20",
            "product_height_cm": "10",
            "product_width_cm": "15",
        },
        # Duplikat persis dari record di atas
        {
            "order_id": "DIRTY_DUP_EXACT_001",
            "order_item_id": "1",
            "product_id": "prod_clean_001",
            "seller_id": "sell_clean_001",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "150.00",
            "freight_value": "15.00",
            "payment_sequential": "1",
            "payment_type": "credit_card",
            "payment_installments": "2",
            "payment_value": "165.00",
            "customer_id": "cust_dirty_dup_1",
            "customer_unique_id": "cust_uniq_dirty_dup_1",
            "customer_zip_code_prefix": "01310",
            "customer_city": "sao paulo",
            "customer_state": "SP",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-25 15:00:00",
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "beleza_saude",
            "product_name_lenght": "50",
            "product_description_lenght": "200",
            "product_photos_qty": "2",
            "product_weight_g": "500",
            "product_length_cm": "20",
            "product_height_cm": "10",
            "product_width_cm": "15",
        },
        # Skenario 2: Duplikasi Business Key (order_id + order_item_id sama, tapi data sedikit beda)
        {
            "order_id": "DIRTY_DUP_BK_002",
            "order_item_id": "1",
            "product_id": "prod_clean_002",
            "seller_id": "sell_clean_002",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "200.00",
            "freight_value": "20.00",
            "payment_sequential": "1",
            "payment_type": "credit_card",
            "payment_installments": "1",
            "payment_value": "220.00",
            "customer_id": "cust_dirty_dup_2",
            "customer_unique_id": "cust_uniq_dirty_dup_2",
            "customer_zip_code_prefix": "02000",
            "customer_city": "  SAO PAULO  ",  # Perlu text trimming & case normalization
            "customer_state": "SP",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-21 10:00:00",
            "order_approved_at": "2018-04-21 10:30:00",
            "order_delivered_carrier_date": "2018-04-23 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-05-06 00:00:00",
            "product_category_name": "informatica_acessorios",
            "product_name_lenght": "45",
            "product_description_lenght": "300",
            "product_photos_qty": "1",
            "product_weight_g": "800",
            "product_length_cm": "25",
            "product_height_cm": "15",
            "product_width_cm": "20",
        },
        {
            "order_id": "DIRTY_DUP_BK_002",
            "order_item_id": "1",
            "product_id": "prod_clean_002",
            "seller_id": "sell_clean_002",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "200.00",
            "freight_value": "20.00",
            "payment_sequential": "1",
            "payment_type": "credit_card",
            "payment_installments": "1",
            "payment_value": "220.00",
            "customer_id": "cust_dirty_dup_2",
            "customer_unique_id": "cust_uniq_dirty_dup_2",
            "customer_zip_code_prefix": "02000",
            "customer_city": "sao paulo",
            "customer_state": "SP",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-21 10:00:00",
            "order_approved_at": "2018-04-21 10:30:00",
            "order_delivered_carrier_date": "2018-04-23 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-05-06 00:00:00",
            "product_category_name": "informatica_acessorios",
            "product_name_lenght": "45",
            "product_description_lenght": "300",
            "product_photos_qty": "1",
            "product_weight_g": "800",
            "product_length_cm": "25",
            "product_height_cm": "15",
            "product_width_cm": "20",
        },
        # Skenario 3: Bad Logic - delivered_date < purchase_timestamp
        {
            "order_id": "DIRTY_LOGIC_DELIV_EARLY_003",
            "order_item_id": "1",
            "product_id": "prod_clean_003",
            "seller_id": "sell_clean_003",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "89.90",
            "freight_value": "12.50",
            "payment_sequential": "1",
            "payment_type": "credit_card",
            "payment_installments": "1",
            "payment_value": "102.40",
            "customer_id": "cust_dirty_003",
            "customer_unique_id": "cust_uniq_dirty_003",
            "customer_zip_code_prefix": "03000",
            "customer_city": "curitiba",
            "customer_state": "PR",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-25 10:00:00",
            "order_approved_at": "2018-04-25 10:30:00",
            "order_delivered_carrier_date": "2018-04-20 14:00:00",
            "order_delivered_customer_date": "2018-04-20 15:00:00",  # Lebih awal dari purchase!
            "order_estimated_delivery_date": "2018-05-10 00:00:00",
            "product_category_name": "relogios_presentes",
            "product_name_lenght": "40",
            "product_description_lenght": "150",
            "product_photos_qty": "1",
            "product_weight_g": "300",
            "product_length_cm": "15",
            "product_height_cm": "8",
            "product_width_cm": "10",
        },
        # Skenario 4: Bad Logic - Price <= 0 dan Freight < 0
        {
            "order_id": "DIRTY_LOGIC_PRICE_ZERO_004",
            "order_item_id": "1",
            "product_id": "prod_clean_004",
            "seller_id": "sell_clean_004",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "0.00",  # Tidak valid!
            "freight_value": "-10.50",  # Ongkir minus!
            "payment_sequential": "1",
            "payment_type": "boleto",
            "payment_installments": "1",
            "payment_value": "0.00",
            "customer_id": "cust_dirty_004",
            "customer_unique_id": "cust_uniq_dirty_004",
            "customer_zip_code_prefix": "04000",
            "customer_city": "rio de janeiro",
            "customer_state": "RJ",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "esporte_lazer",
            "product_name_lenght": "40",
            "product_description_lenght": "150",
            "product_photos_qty": "1",
            "product_weight_g": "400",
            "product_length_cm": "15",
            "product_height_cm": "8",
            "product_width_cm": "10",
        },
        # Skenario 5: Bad Logic - estimated < purchase
        {
            "order_id": "DIRTY_LOGIC_ESTIMATED_EARLY_005",
            "order_item_id": "1",
            "product_id": "prod_clean_005",
            "seller_id": "sell_clean_005",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "50.00",
            "freight_value": "10.00",
            "payment_sequential": "1",
            "payment_type": "credit_card",
            "payment_installments": "1",
            "payment_value": "60.00",
            "customer_id": "cust_dirty_005",
            "customer_unique_id": "cust_uniq_dirty_005",
            "customer_zip_code_prefix": "05000",
            "customer_city": "campinas",
            "customer_state": "SP",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-04-10 00:00:00",  # Estimasi sebelum purchase!
            "product_category_name": "artes",
            "product_name_lenght": "30",
            "product_description_lenght": "100",
            "product_photos_qty": "1",
            "product_weight_g": "200",
            "product_length_cm": "10",
            "product_height_cm": "5",
            "product_width_cm": "8",
        },
        # Skenario 6: Bad Logic - Future Purchase Date (tahun 2035)
        {
            "order_id": "DIRTY_LOGIC_FUTURE_DATE_006",
            "order_item_id": "1",
            "product_id": "prod_clean_006",
            "seller_id": "sell_clean_006",
            "shipping_limit_date": "2035-05-01 10:00:00",
            "price": "75.00",
            "freight_value": "12.00",
            "payment_sequential": "1",
            "payment_type": "credit_card",
            "payment_installments": "1",
            "payment_value": "87.00",
            "customer_id": "cust_dirty_006",
            "customer_unique_id": "cust_uniq_dirty_006",
            "customer_zip_code_prefix": "06000",
            "customer_city": "salvador",
            "customer_state": "BA",
            "order_status": "delivered",
            "order_purchase_timestamp": "2035-01-15 10:00:00",  # Di masa depan!
            "order_approved_at": "2035-01-15 10:30:00",
            "order_delivered_carrier_date": "2035-01-18 14:00:00",
            "order_delivered_customer_date": "2035-01-22 15:00:00",
            "order_estimated_delivery_date": "2035-02-05 00:00:00",
            "product_category_name": "brinquedos",
            "product_name_lenght": "35",
            "product_description_lenght": "120",
            "product_photos_qty": "1",
            "product_weight_g": "350",
            "product_length_cm": "12",
            "product_height_cm": "6",
            "product_width_cm": "10",
        },
        # Skenario 7: Column Shift - order_status berisi tahun '2018', payment_type berisi kode state 'SP'
        {
            "order_id": "DIRTY_SHIFT_COL_007",
            "order_item_id": "1",
            "product_id": "prod_clean_007",
            "seller_id": "sell_clean_007",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "120.00",
            "freight_value": "18.00",
            "payment_sequential": "1",
            "payment_type": "SP",  # Tergeser! Isinya kode provinsi
            "payment_installments": "2",
            "payment_value": "138.00",
            "customer_id": "cust_dirty_007",
            "customer_unique_id": "cust_uniq_dirty_007",
            "customer_zip_code_prefix": "07000",
            "customer_city": "sao paulo",
            "customer_state": "SP",
            "order_status": "2018",  # Tergeser! Isinya tahun
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "eletronicos",
            "product_name_lenght": "40",
            "product_description_lenght": "220",
            "product_photos_qty": "2",
            "product_weight_g": "600",
            "product_length_cm": "18",
            "product_height_cm": "10",
            "product_width_cm": "12",
        },
        # Skenario 8: Column Shift - payment_type berisi 'RJ'
        {
            "order_id": "DIRTY_SHIFT_COL_008",
            "order_item_id": "1",
            "product_id": "prod_clean_008",
            "seller_id": "sell_clean_008",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "95.00",
            "freight_value": "15.00",
            "payment_sequential": "1",
            "payment_type": "RJ",  # Tergeser!
            "payment_installments": "1",
            "payment_value": "110.00",
            "customer_id": "cust_dirty_008",
            "customer_unique_id": "cust_uniq_dirty_008",
            "customer_zip_code_prefix": "08000",
            "customer_city": "rio de janeiro",
            "customer_state": "RJ",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "perfumaria",
            "product_name_lenght": "40",
            "product_description_lenght": "180",
            "product_photos_qty": "1",
            "product_weight_g": "250",
            "product_length_cm": "15",
            "product_height_cm": "8",
            "product_width_cm": "10",
        },
    ]
    return pd.DataFrame(records)


def inject_dirty_data(table_name="olist_raw"):
    """Menginjeksi data kotor ke tabel staging."""
    df_dirty = get_dirty_records_to_inject()
    print(f"💉 Menginjeksi {len(df_dirty)} baris data kotor ke `{table_name}`...")
    
    with engine.begin() as conn:
        # Hapus dulu jika ID injeksi sudah ada sebelumnya agar idempotent
        ids = tuple(df_dirty["order_id"].unique())
        placeholders = ", ".join([f"'{x}'" for x in ids])
        conn.execute(text(f"DELETE FROM `{table_name}` WHERE order_id IN ({placeholders})"))
        
    df_dirty.to_sql(table_name, con=engine, if_exists="append", index=False)
    print(f"✅ Berhasil menginjeksi {len(df_dirty)} baris data kotor.")


if __name__ == "__main__":
    inject_dirty_data()

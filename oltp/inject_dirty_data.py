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

Random seed 42 digunakan agar injeksi deterministik dan reproducible.
"""

import os
import sys
import random
import json
import datetime
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

# Fixed random seed untuk reproducibility
random.seed(42)

# Pastikan root project bisa di-import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secret")
DB_NAME_OLTP = os.getenv("DB_NAME_OLTP", os.getenv("DB_NAME", "oltp_olist"))

# Direktori reports (relatif terhadap root project)
BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

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
    """Menyiapkan kumpulan baris kotor yang representatif (deterministik dengan seed=42)."""
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
            "customer_id": "cust_dirty_001",
            "customer_unique_id": "cust_uniq_dirty_001",
            "customer_zip_code_prefix": "01000",
            "customer_city": "sao paulo",
            "customer_state": "SP",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "informatica_acessorios",
            "product_name_lenght": "40",
            "product_description_lenght": "200",
            "product_photos_qty": "2",
            "product_weight_g": "500",
            "product_length_cm": "20",
            "product_height_cm": "10",
            "product_width_cm": "15",
        },
        # Skenario 1b: Duplikasi persis dari Skenario 1
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
            "customer_id": "cust_dirty_001",
            "customer_unique_id": "cust_uniq_dirty_001",
            "customer_zip_code_prefix": "01000",
            "customer_city": "sao paulo",
            "customer_state": "SP",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "informatica_acessorios",
            "product_name_lenght": "40",
            "product_description_lenght": "200",
            "product_photos_qty": "2",
            "product_weight_g": "500",
            "product_length_cm": "20",
            "product_height_cm": "10",
            "product_width_cm": "15",
        },
        # Skenario 2: Bad Logic - Delivered sebelum Purchase
        {
            "order_id": "DIRTY_LOGIC_DELV_BEFORE_PURCH_002",
            "order_item_id": "1",
            "product_id": "prod_clean_002",
            "seller_id": "sell_clean_002",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "200.00",
            "freight_value": "20.00",
            "payment_sequential": "1",
            "payment_type": "boleto",
            "payment_installments": "1",
            "payment_value": "220.00",
            "customer_id": "cust_dirty_002",
            "customer_unique_id": "cust_uniq_dirty_002",
            "customer_zip_code_prefix": "02000",
            "customer_city": "rio de janeiro",
            "customer_state": "RJ",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-25 10:00:00",
            "order_approved_at": "2018-04-25 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-20 15:00:00",  # Sebelum purchase!
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "eletronicos",
            "product_name_lenght": "35",
            "product_description_lenght": "150",
            "product_photos_qty": "3",
            "product_weight_g": "800",
            "product_length_cm": "25",
            "product_height_cm": "15",
            "product_width_cm": "20",
        },
        # Skenario 3: Bad Logic - Estimated Delivery sebelum Purchase
        {
            "order_id": "DIRTY_LOGIC_EST_BEFORE_PURCH_003",
            "order_item_id": "1",
            "product_id": "prod_clean_003",
            "seller_id": "sell_clean_003",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "300.00",
            "freight_value": "30.00",
            "payment_sequential": "1",
            "payment_type": "credit_card",
            "payment_installments": "3",
            "payment_value": "330.00",
            "customer_id": "cust_dirty_003",
            "customer_unique_id": "cust_uniq_dirty_003",
            "customer_zip_code_prefix": "03000",
            "customer_city": "belo horizonte",
            "customer_state": "MG",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-25 10:00:00",
            "order_approved_at": "2018-04-25 10:30:00",
            "order_delivered_carrier_date": "2018-04-28 14:00:00",
            "order_delivered_customer_date": "2018-04-30 15:00:00",
            "order_estimated_delivery_date": "2018-04-20 00:00:00",  # Sebelum purchase!
            "product_category_name": "moveis_decoracao",
            "product_name_lenght": "45",
            "product_description_lenght": "300",
            "product_photos_qty": "5",
            "product_weight_g": "5000",
            "product_length_cm": "50",
            "product_height_cm": "30",
            "product_width_cm": "40",
        },
        # Skenario 4: Bad Logic - Price <= 0
        {
            "order_id": "DIRTY_LOGIC_ZERO_PRICE_004",
            "order_item_id": "1",
            "product_id": "prod_clean_004",
            "seller_id": "sell_clean_004",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "0.00",  # Harga nol!
            "freight_value": "10.00",
            "payment_sequential": "1",
            "payment_type": "voucher",
            "payment_installments": "1",
            "payment_value": "10.00",
            "customer_id": "cust_dirty_004",
            "customer_unique_id": "cust_uniq_dirty_004",
            "customer_zip_code_prefix": "04000",
            "customer_city": "curitiba",
            "customer_state": "PR",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "esporte_lazer",
            "product_name_lenght": "30",
            "product_description_lenght": "100",
            "product_photos_qty": "1",
            "product_weight_g": "300",
            "product_length_cm": "10",
            "product_height_cm": "5",
            "product_width_cm": "8",
        },
        # Skenario 5: Bad Logic - Freight < 0
        {
            "order_id": "DIRTY_LOGIC_NEG_FREIGHT_005",
            "order_item_id": "1",
            "product_id": "prod_clean_005",
            "seller_id": "sell_clean_005",
            "shipping_limit_date": "2018-05-01 10:00:00",
            "price": "100.00",
            "freight_value": "-10.00",  # Freight negatif!
            "payment_sequential": "1",
            "payment_type": "debit_card",
            "payment_installments": "1",
            "payment_value": "90.00",
            "customer_id": "cust_dirty_005",
            "customer_unique_id": "cust_uniq_dirty_005",
            "customer_zip_code_prefix": "05000",
            "customer_city": "porto alegre",
            "customer_state": "RS",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-04-20 10:00:00",
            "order_approved_at": "2018-04-20 10:30:00",
            "order_delivered_carrier_date": "2018-04-22 14:00:00",
            "order_delivered_customer_date": "2018-04-26 15:00:00",
            "order_estimated_delivery_date": "2018-05-05 00:00:00",
            "product_category_name": "telefonia",
            "product_name_lenght": "38",
            "product_description_lenght": "180",
            "product_photos_qty": "2",
            "product_weight_g": "200",
            "product_length_cm": "14",
            "product_height_cm": "7",
            "product_width_cm": "9",
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


def generate_injection_summary(df_dirty: pd.DataFrame, table_name: str) -> dict:
    """Membuat ringkasan baris yang diinjeksikan per jenis kotoran."""
    summary = {
        "Duplikasi persis (order_id+item)": 0,
        "Bad Logic: delivered < purchase": 0,
        "Bad Logic: estimated < purchase": 0,
        "Bad Logic: price <= 0": 0,
        "Bad Logic: freight_value < 0": 0,
        "Bad Logic: future purchase date": 0,
        "Column Shift: invalid order_status": 0,
        "Column Shift: invalid payment_type": 0,
    }

    VALID_STATUSES = {"delivered", "shipped", "canceled", "unavailable", "invoiced", "processing", "created", "approved"}
    VALID_PAY_TYPES = {"credit_card", "boleto", "voucher", "debit_card", "not_defined"}
    FUTURE_YEAR = 2030

    seen_grain = {}
    for _, row in df_dirty.iterrows():
        grain = (row["order_id"], row["order_item_id"])
        if grain in seen_grain:
            summary["Duplikasi persis (order_id+item)"] += 1
        else:
            seen_grain[grain] = True

        try:
            purchase = pd.to_datetime(row["order_purchase_timestamp"])
            delivered = pd.to_datetime(row.get("order_delivered_customer_date"))
            estimated = pd.to_datetime(row.get("order_estimated_delivery_date"))
            if pd.notna(delivered) and pd.notna(purchase) and delivered < purchase:
                summary["Bad Logic: delivered < purchase"] += 1
            if pd.notna(estimated) and pd.notna(purchase) and estimated < purchase:
                summary["Bad Logic: estimated < purchase"] += 1
            if pd.notna(purchase) and purchase.year > FUTURE_YEAR:
                summary["Bad Logic: future purchase date"] += 1
        except Exception:
            pass

        try:
            price = float(row["price"])
            if price <= 0:
                summary["Bad Logic: price <= 0"] += 1
        except Exception:
            pass

        try:
            freight = float(row["freight_value"])
            if freight < 0:
                summary["Bad Logic: freight_value < 0"] += 1
        except Exception:
            pass

        if str(row.get("order_status", "")) not in VALID_STATUSES:
            summary["Column Shift: invalid order_status"] += 1
        if str(row.get("payment_type", "")) not in VALID_PAY_TYPES:
            summary["Column Shift: invalid payment_type"] += 1

    return summary


def save_injection_report(df_dirty: pd.DataFrame, table_name: str, summary: dict):
    """Menyimpan laporan ringkasan injeksi ke reports/injection_summary.md."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_rows = len(df_dirty)
    report_path = REPORTS_DIR / "injection_summary.md"

    lines = [
        "# Laporan Injeksi Data Kotor (Dirty Data Injection Summary)",
        "",
        f"**Tanggal Dijalankan**: {now_str}  ",
        f"**Target Tabel**: `{table_name}`  ",
        f"**Random Seed**: 42 (deterministik)  ",
        f"**Total Baris Diinjeksi**: {total_rows}  ",
        "",
        "---",
        "",
        "## Ringkasan Baris per Jenis Kotoran",
        "",
        "| Jenis Kotoran | Jumlah Baris |",
        "|---|---|",
    ]
    for kind, count in summary.items():
        lines.append(f"| {kind} | {count} |")

    lines += [
        "",
        "---",
        "",
        "## Detail Order ID yang Diinjeksi",
        "",
        "| order_id | Jenis Skenario |",
        "|---|---|",
    ]
    scenario_map = {
        "DIRTY_DUP_EXACT_001": "Duplikasi persis (2 baris identical)",
        "DIRTY_LOGIC_DELV_BEFORE_PURCH_002": "Bad Logic: delivered < purchase",
        "DIRTY_LOGIC_EST_BEFORE_PURCH_003": "Bad Logic: estimated < purchase",
        "DIRTY_LOGIC_ZERO_PRICE_004": "Bad Logic: price = 0",
        "DIRTY_LOGIC_NEG_FREIGHT_005": "Bad Logic: freight_value < 0",
        "DIRTY_LOGIC_FUTURE_DATE_006": "Bad Logic: purchase date masa depan (2035)",
        "DIRTY_SHIFT_COL_007": "Column Shift: order_status='2018', payment_type='SP'",
        "DIRTY_SHIFT_COL_008": "Column Shift: payment_type='RJ'",
    }
    for order_id, scenario in scenario_map.items():
        lines.append(f"| `{order_id}` | {scenario} |")

    lines += [
        "",
        "---",
        "",
        "> **Catatan**: Data kotor ini digunakan untuk menguji pipeline cleansing ETL.",
        "> Semua baris diinjeksi dengan seed deterministik `random.seed(42)` agar reproducible.",
    ]

    content = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"📄 Laporan injeksi disimpan ke: {report_path}")
    return report_path


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

    # Generate dan simpan laporan injeksi
    summary = generate_injection_summary(df_dirty, table_name)
    save_injection_report(df_dirty, table_name, summary)

    # Cetak ringkasan ke console
    print("\n📊 Ringkasan Injeksi per Jenis Kotoran:")
    for kind, count in summary.items():
        print(f"   {kind}: {count} baris")

    return summary


if __name__ == "__main__":
    inject_dirty_data()

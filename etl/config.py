"""
Konfigurasi Database, Parameter ETL, dan Konstanta Validasi Domain.
Semua koneksi MySQL menggunakan sqlalchemy.engine.URL.create untuk keamanan password.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from dotenv import load_dotenv

# Path Root
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment
load_dotenv(BASE_DIR / ".env")

# Database Credentials
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secret")
DB_NAME_OLTP = os.getenv("DB_NAME_OLTP", os.getenv("DB_NAME", "oltp_olist"))
DB_NAME_DWH = os.getenv("DB_NAME_DWH", "dwh_olist")

# SQLAlchemy URL Generator
def get_db_url(database_name: str) -> URL:
    return URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=database_name,
        query={"charset": "utf8mb4"},
    )

def get_oltp_engine():
    return create_engine(get_db_url(DB_NAME_OLTP), pool_pre_ping=True)

def get_dwh_engine():
    return create_engine(get_db_url(DB_NAME_DWH), pool_pre_ping=True)

# Validasi Domain Konstanta
VALID_ORDER_STATUSES = {
    "delivered",
    "shipped",
    "canceled",
    "unavailable",
    "invoiced",
    "processing",
    "created",
    "approved",
}

VALID_PAYMENT_TYPES = {
    "credit_card",
    "boleto",
    "voucher",
    "debit_card",
    "not_defined",
}

# Direktori Reports
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

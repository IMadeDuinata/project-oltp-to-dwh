"""
dashboard/utils.py
Shared utilities: DB engine, color palette, dan query helpers.
Koneksi identik dengan etl/config.py — tanpa hardcode credentials.
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ── Environment ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_HOST     = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT     = int(os.getenv("DB_PORT", "3306"))
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME_DWH = os.getenv("DB_NAME_DWH", "dwh_olist")

# ── Engine ────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    url = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME_DWH,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)


# ── Color Palette (dipakai di semua halaman) ──────────────────────────────────
PALETTE        = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#3B1F2B",
                  "#44BBA4", "#E94F37", "#393E41", "#F5A623", "#7B2D8B"]
PRIMARY_COLOR  = "#2E86AB"
SUCCESS_COLOR  = "#44BBA4"
WARNING_COLOR  = "#F18F01"
DANGER_COLOR   = "#C73E1D"

PLOTLY_TEMPLATE = "plotly_white"


# ── Query Helpers ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_date_options() -> dict:
    """Kembalikan dict {year: [months]} untuk sidebar filter."""
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(
            "SELECT DISTINCT year, month FROM dim_date "
            "WHERE year > 1970 ORDER BY year, month",
            conn,
        )
    years  = sorted(df["year"].unique().tolist())
    months = sorted(df["month"].unique().tolist())
    return {"years": years, "months": months}


@st.cache_data(ttl=300)
def get_state_options() -> list:
    """Semua customer_state yang ada di dim_customer (non-null)."""
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(
            "SELECT DISTINCT customer_state FROM dim_customer "
            "WHERE customer_state IS NOT NULL AND customer_state != 'NA' "
            "ORDER BY customer_state",
            conn,
        )
    return df["customer_state"].str.upper().tolist()


def build_date_filter(year_col: str, month_col: str,
                      years: list, months: list) -> str:
    """Bangun klausa WHERE untuk filter tahun dan bulan."""
    parts = []
    if years:
        ys = ", ".join(str(y) for y in years)
        parts.append(f"{year_col} IN ({ys})")
    if months:
        ms = ", ".join(str(m) for m in months)
        parts.append(f"{month_col} IN ({ms})")
    return " AND ".join(parts) if parts else "1=1"


def build_state_filter(state_col: str, states: list) -> str:
    """Bangun klausa WHERE untuk filter state."""
    if not states:
        return "1=1"
    quoted = ", ".join(f"'{s.lower()}'" for s in states)
    return f"LOWER({state_col}) IN ({quoted})"


def empty_chart_message():
    st.info("⚠️ Tidak ada data untuk filter yang dipilih.", icon="🔍")


# ── Sidebar Filter Builder ────────────────────────────────────────────────────
def render_sidebar_filters(page_key: str) -> dict:
    """
    Render sidebar filter: year (multiselect), month (multiselect),
    customer_state (multiselect).
    Kembalikan dict dengan keys: years, months, states.
    """
    opts     = get_date_options()
    all_states = get_state_options()

    st.sidebar.header("🔧 Filter")
    years = st.sidebar.multiselect(
        "Tahun",
        options=opts["years"],
        default=opts["years"],
        key=f"{page_key}_years",
    )
    months = st.sidebar.multiselect(
        "Bulan",
        options=opts["months"],
        default=opts["months"],
        format_func=lambda m: [
            "Jan","Feb","Mar","Apr","Mei","Jun",
            "Jul","Agu","Sep","Okt","Nov","Des"
        ][m - 1],
        key=f"{page_key}_months",
    )
    states = st.sidebar.multiselect(
        "State Customer",
        options=all_states,
        default=all_states,
        key=f"{page_key}_states",
    )
    return {"years": years, "months": months, "states": states}

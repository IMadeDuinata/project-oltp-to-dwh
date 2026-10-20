"""
dashboard/utils.py
Database connection, query builders, and global sidebar filter components.
Menggunakan get_dwh_engine() dari etl/config.py untuk koneksi MySQL port 3308.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# Setup import path to root project
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from etl.config import get_dwh_engine


# ── Database Engine ───────────────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    """Mengambil connection pool SQLAlchemy engine untuk DWH (port 3308)."""
    return get_dwh_engine()


# ── Metadata & Filter Option Queries ──────────────────────────────────────────
@st.cache_data(ttl=300)
def get_available_filter_options() -> Dict:
    """Mengambil list tahun, bulan, dan negara yang valid dari DWH."""
    engine = get_engine()
    with engine.connect() as conn:
        years_df = pd.read_sql(
            """
            SELECT DISTINCT dd.year 
            FROM fact_order_items foi
            JOIN dim_date dd ON foi.purchase_date_sk = dd.date_sk
            WHERE dd.year BETWEEN 2016 AND 2025
            ORDER BY dd.year
            """,
            conn,
        )
        years = years_df["year"].dropna().astype(int).tolist()

        countries_df = pd.read_sql(
            "SELECT DISTINCT source_country FROM fact_order_items WHERE source_country IS NOT NULL ORDER BY source_country",
            conn,
        )
        countries = countries_df["source_country"].dropna().tolist()

    return {
        "years": years if years else [2016, 2017, 2018],
        "months": list(range(1, 13)),
        "countries": countries if countries else ["BR", "ID"],
    }


# ── SQL Filter Clauses Builder ────────────────────────────────────────────────
def build_where_clause(
    years: List[int],
    months: List[int],
    country: str,
    date_alias: str = "dd",
    country_alias: str = "foi",
) -> str:
    """
    Membangun klausa WHERE SQL yang konsisten untuk tahun, bulan, dan negara asal.
    """
    conditions = []

    # Filter Tahun
    if years:
        years_str = ", ".join(map(str, years))
        conditions.append(f"{date_alias}.year IN ({years_str})")
    else:
        conditions.append(f"{date_alias}.year BETWEEN 2016 AND 2025")

    # Filter Bulan
    if months and len(months) < 12:
        months_str = ", ".join(map(str, months))
        conditions.append(f"{date_alias}.month IN ({months_str})")

    # Filter Negara
    if country and country != "ALL":
        conditions.append(f"{country_alias}.source_country = '{country}'")

    return " AND ".join(conditions) if conditions else "1=1"


# ── Shared Sidebar Filters ───────────────────────────────────────────────────
def render_global_sidebar(page_key: str = "main") -> Dict:
    """
    Merender sidebar filter global standar yang konsisten di semua halaman.
    Mengembalikan dict berisi parameter filter yang dipilih pengguna.
    """
    st.sidebar.markdown("### Global Filters")
    st.sidebar.caption("Filter berlaku untuk seluruh visualisasi & metric.")

    options = get_available_filter_options()

    # 1. Source Country Selector
    country_labels = {
        "ALL": "All Countries (BR + ID)",
        "BR": "Brazil (BR)",
        "ID": "Indonesia (ID)",
    }
    
    country_choice = st.sidebar.radio(
        "Source Country",
        options=["ALL", "BR", "ID"],
        format_func=lambda x: country_labels.get(x, x),
        key=f"filter_country_{page_key}",
        help="Pilih cakupan data: Gabungan (Dual-source), Brazil saja, atau Indonesia saja.",
    )

    # 2. Year Multiselect
    available_years = options["years"]
    selected_years = st.sidebar.multiselect(
        "Tahun Transaksi",
        options=available_years,
        default=available_years,
        key=f"filter_years_{page_key}",
        help="Pilih satu atau beberapa tahun transaksi.",
    )

    # 3. Month Filter
    month_names = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
        7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"
    }
    selected_months = st.sidebar.multiselect(
        "Bulan Transaksi",
        options=options["months"],
        default=options["months"],
        format_func=lambda m: f"{m:02d} - {month_names.get(m, '')}",
        key=f"filter_months_{page_key}",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
        <div style="font-size: 0.78rem; color: #64748B;">
            <b>Dual-Source DWH Architecture</b><br>
            • Database: <code>dwh_olist</code> (MySQL:3308)<br>
            • BR: Olist Brazil (Real R$)<br>
            • ID: Mitra Indo (Harmonized)
        </div>
        """,
        unsafe_allow_html=True,
    )

    return {
        "country": country_choice,
        "years": selected_years if selected_years else available_years,
        "months": selected_months if selected_months else options["months"],
    }


# ── Formatting Helpers ────────────────────────────────────────────────────────
def format_currency(val: Optional[float], country: str = "ALL") -> str:
    """Format angka menjadi representasi mata uang yang jelas."""
    if val is None or pd.isna(val):
        return "—"
    if country == "ID":
        # Jika ditampilkan dalam skala jutaan/satuan
        return f"Rp {val:,.2f}"
    return f"R$ {val:,.2f}"


def format_number(val: Optional[float]) -> str:
    """Format integer/float dengan pemisah ribuan koma."""
    if val is None or pd.isna(val):
        return "—"
    return f"{int(val):,}"


def format_percent(val: Optional[float]) -> str:
    """Format persentase desimal."""
    if val is None or pd.isna(val):
        return "—"
    return f"{val:.1f}%"

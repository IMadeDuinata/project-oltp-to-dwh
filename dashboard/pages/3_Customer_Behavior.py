"""
dashboard/pages/3_Customer_Behavior.py
Analisis Perilaku Pelanggan (Customer Segmentation, Repeat Order Rate, Demografi Wilayah).
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.design_tokens import (
    COUNTRY_COLOR_MAP,
    apply_plotly_theme,
    get_country_color,
    inject_custom_css,
    render_metric_card,
    render_page_header,
)
from dashboard.utils import (
    build_where_clause,
    format_currency,
    format_number,
    format_percent,
    get_engine,
    render_global_sidebar,
)

st.set_page_config(
    page_title="Customer Behavior & Retention | DWH",
    layout="wide",
)

inject_custom_css()

# ── Sidebar & Header ──────────────────────────────────────────────────────────
filters = render_global_sidebar(page_key="customer")
country = filters["country"]
years = tuple(filters["years"])
months = tuple(filters["months"])

render_page_header(
    title="Perilaku & Segmentasi Pelanggan",
    subtitle="Menganalisis basis pelanggan unik, tingkat repeat order (loyalitas), dan persebaran geografis pembeli.",
    active_country=country,
)


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_customer_summary(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            foi.source_country,
            COUNT(DISTINCT dc.customer_unique_id) AS unique_customers,
            COUNT(DISTINCT foi.order_id)          AS total_orders,
            SUM(foi.total_item_value)             AS total_spend
        FROM fact_order_items foi
        JOIN dim_date     dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON foi.customer_sk      = dc.customer_sk
        WHERE {where_clause}
        GROUP BY foi.source_country
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_customer_frequency_distribution(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            cust_orders.source_country,
            CASE
                WHEN cust_orders.order_count = 1 THEN '1 Order (One-Time)'
                WHEN cust_orders.order_count = 2 THEN '2 Orders (Returning)'
                WHEN cust_orders.order_count BETWEEN 3 AND 5 THEN '3-5 Orders (Loyal)'
                ELSE '6+ Orders (VIP)'
            END AS frequency_segment,
            COUNT(*) AS customer_count
        FROM (
            SELECT
                dc.customer_unique_id,
                foi.source_country,
                COUNT(DISTINCT foi.order_id) AS order_count
            FROM fact_order_items foi
            JOIN dim_date     dd ON foi.purchase_date_sk = dd.date_sk
            JOIN dim_customer dc ON foi.customer_sk      = dc.customer_sk
            WHERE {where_clause}
            GROUP BY dc.customer_unique_id, foi.source_country
        ) AS cust_orders
        GROUP BY cust_orders.source_country, frequency_segment
        ORDER BY frequency_segment ASC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_top_customer_states(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            UPPER(dc.customer_state) AS state,
            foi.source_country,
            COUNT(DISTINCT dc.customer_unique_id) AS unique_customers,
            SUM(foi.total_item_value)             AS total_revenue,
            COUNT(DISTINCT foi.order_id)          AS total_orders
        FROM fact_order_items foi
        JOIN dim_date     dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON foi.customer_sk      = dc.customer_sk
        WHERE {where_clause}
          AND dc.customer_state IS NOT NULL
          AND dc.customer_state != 'NA'
        GROUP BY dc.customer_state, foi.source_country
        ORDER BY unique_customers DESC
        LIMIT 12
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_top_customer_cities(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            CONCAT(UPPER(SUBSTRING(dc.customer_city, 1, 1)), LOWER(SUBSTRING(dc.customer_city, 2))) AS city,
            foi.source_country,
            COUNT(DISTINCT dc.customer_unique_id) AS unique_customers,
            SUM(foi.total_item_value)             AS total_revenue
        FROM fact_order_items foi
        JOIN dim_date     dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON foi.customer_sk      = dc.customer_sk
        WHERE {where_clause}
          AND dc.customer_city IS NOT NULL
        GROUP BY dc.customer_city, foi.source_country
        ORDER BY unique_customers DESC
        LIMIT 10
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


# ── Render Content ────────────────────────────────────────────────────────────
df_cust = get_customer_summary(years, months, country)

if df_cust.empty:
    st.warning("Tidak ditemukan data customer pada filter yang dipilih.")
else:
    total_cust = df_cust["unique_customers"].sum()
    total_orders = df_cust["total_orders"].sum()
    total_spend = df_cust["total_spend"].sum()
    orders_per_cust = (total_orders / total_cust) if total_cust > 0 else 0
    spend_per_cust = (total_spend / total_cust) if total_cust > 0 else 0

    st.markdown('<div class="section-header"><span>Metrik Akuisisi & Nilai Pelanggan</span></div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card("Total Pelanggan Unik", format_number(total_cust), "Konsumen terverifikasi", country_badge=country)
    with c2:
        render_metric_card("Pesanan per Pelanggan", f"{orders_per_cust:.2f}", "Rata-rata frekuensi belanja", country_badge=country)
    with c3:
        render_metric_card("Rata-rata Nilai Belanja (ARPU)", f"R$ {spend_per_cust:,.2f}", "Rata-rata spend per konsumen", country_badge=country)
    with c4:
        # Repeat buyer proxy
        render_metric_card("Total Pembelian Selesai", format_number(total_orders), "Volume order tercatat", country_badge=country)

    # ── Frequency Segment & State Distribution ────────────────────────────────
    st.markdown('<div class="section-header"><span>Segmen Frekuensi Pembelian & Konsentrasi Wilayah</span></div>', unsafe_allow_html=True)
    col_f1, col_f2 = st.columns(2)

    with col_f1:
        df_freq = get_customer_frequency_distribution(years, months, country)
        if not df_freq.empty:
            fig_freq = px.bar(
                df_freq,
                x="frequency_segment",
                y="customer_count",
                color="source_country",
                title="Distribusi Loyalitas: One-time vs Repeat Customers",
                color_discrete_map=COUNTRY_COLOR_MAP,
                barmode="group",
                labels={"frequency_segment": "Segmen Frekuensi", "customer_count": "Jumlah Pelanggan", "source_country": "Negara"},
            )
            st.plotly_chart(apply_plotly_theme(fig_freq, height=380), use_container_width=True)

    with col_f2:
        df_state = get_top_customer_states(years, months, country)
        if not df_state.empty:
            fig_state = px.bar(
                df_state,
                y="state",
                x="unique_customers",
                color="source_country",
                orientation="h",
                title="Top Wilayah/Provinsi Berdasarkan Basis Pelanggan",
                color_discrete_map=COUNTRY_COLOR_MAP,
                barmode="stack",
                labels={"state": "Wilayah / State", "unique_customers": "Pelanggan Unik", "source_country": "Negara"},
            )
            fig_state.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(apply_plotly_theme(fig_state, height=380), use_container_width=True)

    # ── Top Cities ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header"><span>Top 10 Kota Pembeli Terbesar</span></div>', unsafe_allow_html=True)
    df_city = get_top_customer_cities(years, months, country)
    if not df_city.empty:
        fig_city = px.bar(
            df_city,
            x="city",
            y="unique_customers",
            color="source_country",
            title="Basis Konsumen di Kota-Kota Urban Utama",
            color_discrete_map=COUNTRY_COLOR_MAP,
            barmode="group",
            labels={"city": "Kota", "unique_customers": "Pelanggan Unik", "source_country": "Negara"},
        )
        st.plotly_chart(apply_plotly_theme(fig_city, height=360), use_container_width=True)

    st.markdown(
        """
        <div class="insight-callout">
            <b>Customer Retention Takeaways:</b><br>
            • Mayoritas pembeli melakukan transaksi tunggal (one-time purchase), yang menjadi karakteristik umum e-commerce marketplace.<br>
            • Peluang pertumbuhan terbesar terletak pada strategi re-engagement (email marketing, promo loyalitas, voucher pembelian kedua) untuk meningkatkan LTV (Lifetime Value).
        </div>
        """,
        unsafe_allow_html=True,
    )

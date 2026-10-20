"""
dashboard/pages/1_Revenue_and_Sales.py
Analisis Penjualan & Pendapatan (Sales Performance, Freight Ratio, Category & Seller Ranking).
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
    page_title="Revenue & Sales Analysis | DWH",
    page_icon="📈",
    layout="wide",
)

inject_custom_css()

# ── Sidebar & Header ──────────────────────────────────────────────────────────
filters = render_global_sidebar(page_key="sales")
country = filters["country"]
years = tuple(filters["years"])
months = tuple(filters["months"])

render_page_header(
    title="📈 Analisis Penjualan & Pendapatan",
    subtitle="Mengevaluasi tren GMV, rasio ongkos kirim (freight), performa kategori produk, dan top seller.",
    active_country=country,
)


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_sales_summary(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            foi.source_country,
            SUM(foi.price)              AS total_item_price,
            SUM(foi.freight_value)      AS total_freight,
            SUM(foi.total_item_value)   AS total_gmv,
            COUNT(*)                    AS total_items_sold,
            COUNT(DISTINCT foi.order_id) AS total_orders,
            AVG(foi.price)              AS avg_price,
            AVG(foi.freight_value)      AS avg_freight
        FROM fact_order_items foi
        JOIN dim_date dd ON foi.purchase_date_sk = dd.date_sk
        WHERE {where_clause}
        GROUP BY foi.source_country
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_monthly_sales_breakdown(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            CONCAT(dd.year, '-', LPAD(dd.month, 2, '0')) AS period,
            foi.source_country,
            SUM(foi.price)                                AS total_price,
            SUM(foi.freight_value)                        AS total_freight,
            SUM(foi.total_item_value)                     AS total_revenue
        FROM fact_order_items foi
        JOIN dim_date dd ON foi.purchase_date_sk = dd.date_sk
        WHERE {where_clause}
        GROUP BY period, foi.source_country
        ORDER BY period ASC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_top_sellers(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            ds.seller_id,
            COALESCE(ds.seller_state, 'Unknown') AS seller_state,
            foi.source_country,
            SUM(foi.total_item_value)            AS total_revenue,
            COUNT(*)                             AS items_sold
        FROM fact_order_items foi
        JOIN dim_date   dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_seller ds ON foi.seller_sk        = ds.seller_sk
        WHERE {where_clause}
        GROUP BY ds.seller_id, ds.seller_state, foi.source_country
        ORDER BY total_revenue DESC
        LIMIT 10
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_category_metrics(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            COALESCE(dp.product_category_name, 'Unknown') AS category,
            foi.source_country,
            SUM(foi.total_item_value)                      AS total_revenue,
            SUM(foi.freight_value)                         AS total_freight,
            COUNT(*)                                       AS items_sold,
            AVG(foi.price)                                 AS avg_item_price
        FROM fact_order_items foi
        JOIN dim_date    dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_product dp ON foi.product_sk       = dp.product_sk
        WHERE {where_clause}
        GROUP BY dp.product_category_name, foi.source_country
        ORDER BY total_revenue DESC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


# ── Render Content ────────────────────────────────────────────────────────────
df_summary = get_sales_summary(years, months, country)

if df_summary.empty:
    st.warning("⚠️ Tidak ditemukan data transaksi pada filter yang dipilih.")
else:
    total_gmv = df_summary["total_gmv"].sum()
    total_price = df_summary["total_item_price"].sum()
    total_freight = df_summary["total_freight"].sum()
    total_items = df_summary["total_items_sold"].sum()
    freight_ratio = (total_freight / total_gmv * 100) if total_gmv > 0 else 0
    avg_price = total_price / total_items if total_items > 0 else 0
    avg_freight = total_freight / total_items if total_items > 0 else 0

    st.markdown('<div class="section-header"><span>💰 Metrik Finansial & Komposisi Nilai</span></div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_metric_card("Total GMV", f"R$ {total_gmv:,.0f}", "Item Price + Freight", country_badge=country)
    with c2:
        render_metric_card("Product Sales", f"R$ {total_price:,.0f}", "Murni nilai produk", country_badge=country)
    with c3:
        render_metric_card("Freight Revenue", f"R$ {total_freight:,.0f}", f"Rasio: {freight_ratio:.1f}% dari GMV", country_badge=country)
    with c4:
        render_metric_card("Average Item Price", f"R$ {avg_price:,.2f}", "Rata-rata harga satuan", country_badge=country)
    with c5:
        render_metric_card("Average Freight", f"R$ {avg_freight:,.2f}", "Rata-rata ongkir/item", country_badge=country)

    # ── Monthly Trend ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-header"><span>📅 Tren Penjualan & Komponen Ongkir</span></div>', unsafe_allow_html=True)
    df_monthly = get_monthly_sales_breakdown(years, months, country)

    if not df_monthly.empty:
        col_m1, col_m2 = st.columns([3, 2])
        with col_m1:
            fig_bar = px.bar(
                df_monthly,
                x="period",
                y="total_revenue",
                color="source_country",
                title="Total Revenue Bulanan (BR vs ID)",
                color_discrete_map=COUNTRY_COLOR_MAP,
                barmode="group",
                labels={"period": "Periode", "total_revenue": "Revenue (R$)", "source_country": "Negara"},
            )
            st.plotly_chart(apply_plotly_theme(fig_bar, height=360), use_container_width=True)

        with col_m2:
            # Komposisi Product Price vs Freight
            df_monthly_agg = df_monthly.groupby("period")[["total_price", "total_freight"]].sum().reset_index()
            fig_area = go.Figure()
            fig_area.add_trace(go.Scatter(
                x=df_monthly_agg["period"], y=df_monthly_agg["total_price"],
                name="Product Price", mode="lines", stackgroup="one", fillcolor="rgba(37, 99, 235, 0.4)", line=dict(color="#2563EB")
            ))
            fig_area.add_trace(go.Scatter(
                x=df_monthly_agg["period"], y=df_monthly_agg["total_freight"],
                name="Freight Value", mode="lines", stackgroup="one", fillcolor="rgba(245, 158, 11, 0.4)", line=dict(color="#F59E0B")
            ))
            fig_area = apply_plotly_theme(fig_area, title="Struktur Pendapatan: Harga Produk vs Ongkir", height=360)
            st.plotly_chart(fig_area, use_container_width=True)

    # ── Category & Seller Ranking ─────────────────────────────────────────────
    st.markdown('<div class="section-header"><span>🏆 Analisis Kategori & Top Penjual</span></div>', unsafe_allow_html=True)
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        df_cat = get_category_metrics(years, months, country)
        if not df_cat.empty:
            top_10_cats = df_cat.groupby("category")["total_revenue"].sum().nlargest(10).index
            df_cat_top = df_cat[df_cat["category"].isin(top_10_cats)].copy()
            fig_cat = px.bar(
                df_cat_top,
                y="category",
                x="total_revenue",
                color="source_country",
                orientation="h",
                title="Top 10 Kategori Produk Berdasarkan Nilai Transaksi",
                color_discrete_map=COUNTRY_COLOR_MAP,
                barmode="stack",
                labels={"category": "Kategori", "total_revenue": "Revenue (R$)", "source_country": "Negara"},
            )
            fig_cat.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(apply_plotly_theme(fig_cat, height=420), use_container_width=True)

    with col_c2:
        df_seller = get_top_sellers(years, months, country)
        if not df_seller.empty:
            df_seller["seller_label"] = df_seller["seller_id"].str[:8] + " (" + df_seller["seller_state"] + ")"
            fig_seller = px.bar(
                df_seller,
                y="seller_label",
                x="total_revenue",
                color="source_country",
                orientation="h",
                title="Top 10 Merchant / Seller Berdasarkan Omzet",
                color_discrete_map=COUNTRY_COLOR_MAP,
                barmode="stack",
                labels={"seller_label": "Seller (State)", "total_revenue": "Total Omzet (R$)", "source_country": "Negara"},
            )
            fig_seller.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(apply_plotly_theme(fig_seller, height=420), use_container_width=True)

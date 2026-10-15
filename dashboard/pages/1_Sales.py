"""
dashboard/pages/1_Sales.py  — Analisis Penjualan
- Top 10 kategori by revenue (bar horizontal)
- Revenue per bulan (bar chart)
- Distribusi harga per kategori (box plot, top 10)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.utils import (
    PALETTE, PLOTLY_TEMPLATE,
    build_date_filter, build_state_filter,
    empty_chart_message, get_engine, render_sidebar_filters,
)

st.set_page_config(page_title="Sales · Olist DWH", page_icon="🛍️", layout="wide")
st.title("🛍️ Analisis Penjualan")

filters = render_sidebar_filters("sales")
years, months, states = filters["years"], filters["months"], filters["states"]


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_top_categories(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            COALESCE(dp.product_category_name, 'Unknown') AS category,
            SUM(foi.total_item_value)                      AS revenue,
            COUNT(*)                                       AS items_sold
        FROM fact_order_items foi
        JOIN dim_date     dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON foi.customer_sk      = dc.customer_sk
        JOIN dim_product  dp ON foi.product_sk       = dp.product_sk
        WHERE {date_f} AND {state_f}
        GROUP BY dp.product_category_name
        ORDER BY revenue DESC
        LIMIT 10
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_revenue_monthly(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            CONCAT(dd.year, '-', LPAD(dd.month, 2, '0')) AS period,
            dd.year,
            dd.month,
            SUM(foi.total_item_value)                     AS revenue
        FROM fact_order_items foi
        JOIN dim_date     dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON foi.customer_sk      = dc.customer_sk
        WHERE {date_f} AND {state_f}
        GROUP BY dd.year, dd.month
        ORDER BY dd.year, dd.month
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_price_distribution(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            COALESCE(dp.product_category_name, 'Unknown') AS category,
            foi.price
        FROM fact_order_items foi
        JOIN dim_date     dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON foi.customer_sk      = dc.customer_sk
        JOIN dim_product  dp ON foi.product_sk       = dp.product_sk
        WHERE {date_f} AND {state_f}
          AND foi.price > 0
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    # Batasi ke top 10 kategori by jumlah item agar box plot terbaca
    if not df.empty:
        top10 = df["category"].value_counts().head(10).index.tolist()
        df = df[df["category"].isin(top10)]
    return df


# ── Chart 1: Top 10 Kategori ──────────────────────────────────────────────────
st.subheader("🏆 Top 10 Kategori by Revenue")
df_cat = get_top_categories(tuple(years), tuple(months), tuple(states))

if df_cat.empty:
    empty_chart_message()
else:
    fig = px.bar(
        df_cat.sort_values("revenue"),
        x="revenue",
        y="category",
        orientation="h",
        labels={"revenue": "Revenue (R$)", "category": "Kategori"},
        color="revenue",
        color_continuous_scale=["#AED9E0", "#2E86AB"],
        template=PLOTLY_TEMPLATE,
        text="revenue",
    )
    fig.update_traces(texttemplate="R$ %{text:,.0f}", textposition="outside")
    fig.update_coloraxes(showscale=False)
    fig.update_layout(yaxis_title=None, xaxis_tickformat=",.0f", height=420)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Chart 2: Revenue per Bulan ────────────────────────────────────────────────
st.subheader("📅 Revenue per Bulan")
df_rev = get_revenue_monthly(tuple(years), tuple(months), tuple(states))

if df_rev.empty:
    empty_chart_message()
else:
    fig2 = px.bar(
        df_rev,
        x="period",
        y="revenue",
        labels={"period": "Periode", "revenue": "Revenue (R$)"},
        color_discrete_sequence=[PALETTE[0]],
        template=PLOTLY_TEMPLATE,
    )
    fig2.update_layout(xaxis_tickangle=-45, yaxis_tickformat=",.0f")
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Chart 3: Box Plot Harga per Kategori ─────────────────────────────────────
st.subheader("📊 Distribusi Harga per Kategori (Top 10 by Volume)")
df_box = get_price_distribution(tuple(years), tuple(months), tuple(states))

if df_box.empty:
    empty_chart_message()
else:
    # Urutkan kategori berdasarkan median harga
    order = (
        df_box.groupby("category")["price"]
        .median()
        .sort_values(ascending=False)
        .index.tolist()
    )
    fig3 = px.box(
        df_box,
        x="category",
        y="price",
        category_orders={"category": order},
        labels={"category": "Kategori", "price": "Harga (R$)"},
        color="category",
        color_discrete_sequence=PALETTE,
        template=PLOTLY_TEMPLATE,
        points=False,
    )
    fig3.update_layout(
        showlegend=False,
        xaxis_tickangle=-40,
        yaxis_tickformat=",.0f",
        height=450,
    )
    st.plotly_chart(fig3, use_container_width=True)

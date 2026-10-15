"""
dashboard/Home.py  — Ringkasan Eksekutif
Metric cards: total revenue, total order, avg delivery days, delay rate.
Line chart: revenue per bulan.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.utils import (
    PALETTE, PLOTLY_TEMPLATE, PRIMARY_COLOR,
    build_date_filter, build_state_filter,
    empty_chart_message, get_engine, render_sidebar_filters,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Olist DWH Dashboard",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Olist — Ringkasan Eksekutif")
st.caption("Data Warehouse · Star Schema · MariaDB")

# ── Sidebar Filters ───────────────────────────────────────────────────────────
filters = render_sidebar_filters("home")
years, months, states = filters["years"], filters["months"], filters["states"]

# ── Query helpers ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_kpi(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            SUM(foi.total_item_value)                    AS total_revenue,
            COUNT(DISTINCT foi.order_id)                 AS total_orders,
            AVG(fod.actual_delivery_days)                AS avg_delivery_days,
            AVG(fod.is_delayed) * 100                    AS delay_rate_pct
        FROM fact_order_items foi
        JOIN dim_date     dd  ON foi.purchase_date_sk  = dd.date_sk
        JOIN dim_customer dc  ON foi.customer_sk       = dc.customer_sk
        LEFT JOIN fact_order_delivery fod ON foi.order_id = fod.order_id
        WHERE {date_f} AND {state_f}
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
            dd.year,
            dd.month,
            CONCAT(dd.year, '-', LPAD(dd.month, 2, '0')) AS period,
            SUM(foi.total_item_value)                     AS revenue,
            COUNT(DISTINCT foi.order_id)                  AS orders
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


# ── KPI Cards ─────────────────────────────────────────────────────────────────
df_kpi = get_kpi(tuple(years), tuple(months), tuple(states))

col1, col2, col3, col4 = st.columns(4)

if df_kpi.empty or df_kpi["total_revenue"].isna().all():
    empty_chart_message()
else:
    row = df_kpi.iloc[0]
    col1.metric(
        "💰 Total Revenue",
        f"R$ {row['total_revenue']:,.0f}" if pd.notna(row["total_revenue"]) else "—",
    )
    col2.metric(
        "🛒 Total Order",
        f"{int(row['total_orders']):,}" if pd.notna(row["total_orders"]) else "—",
    )
    col3.metric(
        "🚚 Avg Delivery Days",
        f"{row['avg_delivery_days']:.1f} hari" if pd.notna(row["avg_delivery_days"]) else "—",
    )
    col4.metric(
        "⚠️ Delay Rate",
        f"{row['delay_rate_pct']:.1f}%" if pd.notna(row["delay_rate_pct"]) else "—",
    )

st.divider()

# ── Revenue per Bulan ─────────────────────────────────────────────────────────
st.subheader("📈 Revenue per Bulan")
df_rev = get_revenue_monthly(tuple(years), tuple(months), tuple(states))

if df_rev.empty:
    empty_chart_message()
else:
    fig = px.line(
        df_rev,
        x="period",
        y="revenue",
        markers=True,
        labels={"period": "Periode", "revenue": "Revenue (R$)"},
        color_discrete_sequence=[PRIMARY_COLOR],
        template=PLOTLY_TEMPLATE,
    )
    fig.update_traces(line_width=2.5, marker_size=7)
    fig.update_layout(
        xaxis_tickangle=-45,
        yaxis_tickformat=",.0f",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # secondary: order count
    st.subheader("🛒 Jumlah Order per Bulan")
    fig2 = px.bar(
        df_rev,
        x="period",
        y="orders",
        labels={"period": "Periode", "orders": "Jumlah Order"},
        color_discrete_sequence=[PALETTE[2]],
        template=PLOTLY_TEMPLATE,
    )
    fig2.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig2, use_container_width=True)

"""
dashboard/pages/4_Customer.py  — Segmentasi Pelanggan
- Top 10 state by order (bar)
- Sebaran customer per state (bar)
- Repeat vs New customer
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.utils import (
    DANGER_COLOR, PALETTE, PLOTLY_TEMPLATE, PRIMARY_COLOR, SUCCESS_COLOR,
    build_date_filter, build_state_filter,
    empty_chart_message, get_engine, render_sidebar_filters,
)

st.set_page_config(page_title="Customer · Olist DWH", page_icon="👥", layout="wide")
st.title("👥 Segmentasi Pelanggan")

filters = render_sidebar_filters("customer")
years, months, states = filters["years"], filters["months"], filters["states"]


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_orders_by_state(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            UPPER(dc.customer_state)          AS state,
            COUNT(DISTINCT foi.order_id)      AS orders,
            SUM(foi.total_item_value)         AS revenue,
            COUNT(DISTINCT dc.customer_unique_id) AS unique_customers
        FROM fact_order_items foi
        JOIN dim_date     dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON foi.customer_sk      = dc.customer_sk
        WHERE {date_f} AND {state_f}
          AND dc.customer_state IS NOT NULL
          AND dc.customer_state != 'NA'
        GROUP BY dc.customer_state
        ORDER BY orders DESC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_repeat_vs_new(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            dc.customer_unique_id,
            COUNT(DISTINCT foi.order_id) AS order_count
        FROM fact_order_items foi
        JOIN dim_date     dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON foi.customer_sk      = dc.customer_sk
        WHERE {date_f} AND {state_f}
        GROUP BY dc.customer_unique_id
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    if df.empty:
        return pd.DataFrame()
    df["segment"] = df["order_count"].apply(
        lambda x: "New (1 order)" if x == 1
        else ("Occasional (2–3)" if x <= 3 else "Loyal (4+)")
    )
    return df.groupby("segment").agg(
        customers=("customer_unique_id", "count"),
        total_orders=("order_count", "sum"),
    ).reset_index()


@st.cache_data(ttl=300)
def get_customer_cohort_monthly(years, months, states):
    """Jumlah customer baru per bulan (first order)."""
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            CONCAT(dd.year, '-', LPAD(dd.month, 2, '0')) AS period,
            COUNT(DISTINCT dc.customer_unique_id)          AS new_customers
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


# ── Chart 1: Top 10 State by Order ───────────────────────────────────────────
st.subheader("🏆 Top 10 State by Jumlah Order")
df_state = get_orders_by_state(tuple(years), tuple(months), tuple(states))

if df_state.empty:
    empty_chart_message()
else:
    top10 = df_state.head(10)
    fig = px.bar(
        top10.sort_values("orders"),
        x="orders",
        y="state",
        orientation="h",
        labels={"orders": "Jumlah Order", "state": "State"},
        color="orders",
        color_continuous_scale=["#AED9E0", "#2E86AB"],
        template=PLOTLY_TEMPLATE,
        text="orders",
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_coloraxes(showscale=False)
    fig.update_layout(yaxis_title=None, height=400)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Chart 2: Sebaran Customer per State (semua) ───────────────────────────────
st.subheader("🗺️ Sebaran Customer per State")
if df_state.empty:
    empty_chart_message()
else:
    fig2 = px.bar(
        df_state.sort_values("unique_customers", ascending=False),
        x="state",
        y="unique_customers",
        labels={"state": "State", "unique_customers": "Unique Customers"},
        color="unique_customers",
        color_continuous_scale=["#F7E0C5", "#A23B72"],
        template=PLOTLY_TEMPLATE,
    )
    fig2.update_coloraxes(showscale=False)
    fig2.update_layout(xaxis_tickangle=-45, yaxis_title="Unique Customers")
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Chart 3: Repeat vs New Customer ──────────────────────────────────────────
st.subheader("🔄 Segmentasi: New vs Repeat Customer")
df_repeat = get_repeat_vs_new(tuple(years), tuple(months), tuple(states))

if df_repeat.empty:
    empty_chart_message()
else:
    col_a, col_b = st.columns(2)
    with col_a:
        fig3 = px.pie(
            df_repeat,
            names="segment",
            values="customers",
            color_discrete_sequence=[SUCCESS_COLOR, PRIMARY_COLOR, DANGER_COLOR],
            template=PLOTLY_TEMPLATE,
            hole=0.4,
            title="Distribusi Customer by Segmen",
        )
        fig3.update_traces(textposition="outside", textinfo="percent+label")
        st.plotly_chart(fig3, use_container_width=True)

    with col_b:
        st.markdown("**Tabel Segmentasi Customer**")
        total_cust = df_repeat["customers"].sum()
        df_disp = df_repeat.copy()
        df_disp["pct_customers"] = df_disp["customers"] / total_cust * 100
        df_disp = df_disp.rename(columns={
            "segment": "Segmen",
            "customers": "Customers",
            "total_orders": "Total Orders",
            "pct_customers": "Share (%)",
        })
        st.dataframe(
            df_disp.style.format({
                "Customers": "{:,}",
                "Total Orders": "{:,}",
                "Share (%)": "{:.1f}%",
            }),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "💡 **New** = hanya 1 order | **Occasional** = 2–3 orders | **Loyal** = 4+ orders"
        )

st.divider()

# ── Chart 4: Customer Aktif per Bulan ────────────────────────────────────────
st.subheader("📅 Customer Aktif per Bulan")
df_cohort = get_customer_cohort_monthly(tuple(years), tuple(months), tuple(states))

if df_cohort.empty:
    empty_chart_message()
else:
    fig4 = px.area(
        df_cohort,
        x="period",
        y="new_customers",
        labels={"period": "Periode", "new_customers": "Customer Aktif"},
        color_discrete_sequence=[PALETTE[5]],
        template=PLOTLY_TEMPLATE,
    )
    fig4.update_layout(xaxis_tickangle=-45, yaxis_title="Jumlah Customer Aktif")
    st.plotly_chart(fig4, use_container_width=True)

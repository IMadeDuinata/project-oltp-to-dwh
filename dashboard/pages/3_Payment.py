"""
dashboard/pages/3_Payment.py  — Analisis Pembayaran
- Distribusi metode pembayaran (pie chart)
- Rata-rata cicilan per segmen nilai (bar)
- Revenue per payment type (bar)
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

st.set_page_config(page_title="Payment · Olist DWH", page_icon="💳", layout="wide")
st.title("💳 Analisis Pembayaran")

filters = render_sidebar_filters("payment")
years, months, states = filters["years"], filters["months"], filters["states"]


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_payment_distribution(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            dpt.payment_type,
            COUNT(*)             AS transaction_count,
            SUM(fop.payment_value) AS total_value
        FROM fact_order_payments fop
        JOIN dim_date         dd  ON fop.purchase_date_sk = dd.date_sk
        JOIN dim_customer     dc  ON fop.customer_sk      = dc.customer_sk
        JOIN dim_payment_type dpt ON fop.payment_type_sk  = dpt.payment_type_sk
        WHERE {date_f} AND {state_f}
        GROUP BY dpt.payment_type
        ORDER BY transaction_count DESC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_installments_by_segment(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            CASE
                WHEN fop.payment_value < 50   THEN '< R$50'
                WHEN fop.payment_value < 200  THEN 'R$50–200'
                WHEN fop.payment_value < 500  THEN 'R$200–500'
                WHEN fop.payment_value < 1000 THEN 'R$500–1000'
                ELSE '>= R$1000'
            END                              AS value_segment,
            AVG(fop.payment_installments)    AS avg_installments,
            COUNT(*)                         AS count
        FROM fact_order_payments fop
        JOIN dim_date         dd  ON fop.purchase_date_sk = dd.date_sk
        JOIN dim_customer     dc  ON fop.customer_sk      = dc.customer_sk
        JOIN dim_payment_type dpt ON fop.payment_type_sk  = dpt.payment_type_sk
        WHERE {date_f} AND {state_f}
          AND dpt.payment_type = 'credit_card'
        GROUP BY value_segment
        ORDER BY MIN(fop.payment_value)
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_revenue_by_payment(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            dpt.payment_type,
            SUM(fop.payment_value)           AS total_revenue,
            AVG(fop.payment_value)           AS avg_value,
            COUNT(DISTINCT fop.order_id)     AS orders
        FROM fact_order_payments fop
        JOIN dim_date         dd  ON fop.purchase_date_sk = dd.date_sk
        JOIN dim_customer     dc  ON fop.customer_sk      = dc.customer_sk
        JOIN dim_payment_type dpt ON fop.payment_type_sk  = dpt.payment_type_sk
        WHERE {date_f} AND {state_f}
        GROUP BY dpt.payment_type
        ORDER BY total_revenue DESC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


# ── Layout ────────────────────────────────────────────────────────────────────
df_dist   = get_payment_distribution(tuple(years), tuple(months), tuple(states))
df_rev_pt = get_revenue_by_payment(tuple(years), tuple(months), tuple(states))

col_left, col_right = st.columns(2)

# ── Chart 1: Pie — Distribusi Metode ─────────────────────────────────────────
with col_left:
    st.subheader("🥧 Distribusi Metode Pembayaran")
    if df_dist.empty:
        empty_chart_message()
    else:
        fig = px.pie(
            df_dist,
            names="payment_type",
            values="transaction_count",
            color_discrete_sequence=PALETTE,
            template=PLOTLY_TEMPLATE,
            hole=0.35,
        )
        fig.update_traces(textposition="outside", textinfo="percent+label")
        fig.update_layout(showlegend=True, legend_title="Metode")
        st.plotly_chart(fig, use_container_width=True)

# ── Chart 2: Bar — Revenue per Payment Type ───────────────────────────────────
with col_right:
    st.subheader("💰 Revenue per Payment Type")
    if df_rev_pt.empty:
        empty_chart_message()
    else:
        fig2 = px.bar(
            df_rev_pt,
            x="payment_type",
            y="total_revenue",
            labels={"payment_type": "Metode", "total_revenue": "Revenue (R$)"},
            color="payment_type",
            color_discrete_sequence=PALETTE,
            template=PLOTLY_TEMPLATE,
            text="total_revenue",
        )
        fig2.update_traces(texttemplate="R$ %{text:,.0f}", textposition="outside")
        fig2.update_layout(showlegend=False, yaxis_tickformat=",.0f")
        st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Chart 3: Bar — Avg Installments per Segmen Nilai ─────────────────────────
st.subheader("🔢 Rata-rata Cicilan per Segmen Nilai (Credit Card)")
df_inst = get_installments_by_segment(tuple(years), tuple(months), tuple(states))

if df_inst.empty:
    empty_chart_message()
else:
    fig3 = px.bar(
        df_inst,
        x="value_segment",
        y="avg_installments",
        labels={"value_segment": "Segmen Nilai", "avg_installments": "Avg Cicilan"},
        color="avg_installments",
        color_continuous_scale=["#AED9E0", "#2E86AB"],
        template=PLOTLY_TEMPLATE,
        text="avg_installments",
    )
    fig3.update_traces(texttemplate="%{text:.1f}x", textposition="outside")
    fig3.update_coloraxes(showscale=False)
    fig3.update_layout(xaxis_title="Segmen Nilai Transaksi", yaxis_title="Rata-rata Cicilan")
    st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ── Tabel Ringkasan ───────────────────────────────────────────────────────────
st.subheader("📋 Ringkasan per Metode Pembayaran")
if not df_dist.empty and not df_rev_pt.empty:
    merged = df_dist.merge(
        df_rev_pt[["payment_type", "total_revenue", "avg_value", "orders"]],
        on="payment_type",
        how="left",
    )
    merged = merged.rename(columns={
        "payment_type": "Metode",
        "transaction_count": "Transaksi",
        "total_value": "Total Value (R$)",
        "total_revenue": "Revenue (R$)",
        "avg_value": "Avg Value (R$)",
        "orders": "Order Unik",
    })
    st.dataframe(
        merged.style.format({
            "Transaksi": "{:,}",
            "Total Value (R$)": "R$ {:,.0f}",
            "Revenue (R$)": "R$ {:,.0f}",
            "Avg Value (R$)": "R$ {:,.2f}",
            "Order Unik": "{:,}",
        }),
        use_container_width=True,
    )
else:
    empty_chart_message()

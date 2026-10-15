"""
dashboard/pages/2_Delivery.py  — Performa Logistik
- Rata-rata delivery days per bulan (line chart)
- Delay rate per state (choropleth / bar chart)
- Distribusi delivery days (histogram)
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

st.set_page_config(page_title="Delivery · Olist DWH", page_icon="🚚", layout="wide")
st.title("🚚 Performa Logistik")

filters = render_sidebar_filters("delivery")
years, months, states = filters["years"], filters["months"], filters["states"]


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_delivery_monthly(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            CONCAT(dd.year, '-', LPAD(dd.month, 2, '0')) AS period,
            dd.year,
            dd.month,
            AVG(fod.actual_delivery_days)                AS avg_delivery_days,
            AVG(fod.is_delayed) * 100                    AS delay_rate_pct,
            COUNT(*)                                     AS total_orders
        FROM fact_order_delivery fod
        JOIN dim_date     dd ON fod.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON fod.customer_sk      = dc.customer_sk
        WHERE {date_f} AND {state_f}
          AND fod.actual_delivery_days IS NOT NULL
          AND fod.actual_delivery_days >= 0
        GROUP BY dd.year, dd.month
        ORDER BY dd.year, dd.month
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_delay_by_state(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT
            UPPER(dc.customer_state)      AS state,
            AVG(fod.is_delayed) * 100     AS delay_rate_pct,
            AVG(fod.actual_delivery_days) AS avg_days,
            COUNT(*)                      AS total_orders
        FROM fact_order_delivery fod
        JOIN dim_date     dd ON fod.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON fod.customer_sk      = dc.customer_sk
        WHERE {date_f} AND {state_f}
          AND dc.customer_state IS NOT NULL
          AND dc.customer_state != 'NA'
        GROUP BY dc.customer_state
        ORDER BY delay_rate_pct DESC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_delivery_distribution(years, months, states):
    date_f  = build_date_filter("dd.year", "dd.month", years, months)
    state_f = build_state_filter("dc.customer_state", states)
    sql = f"""
        SELECT fod.actual_delivery_days
        FROM fact_order_delivery fod
        JOIN dim_date     dd ON fod.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON fod.customer_sk      = dc.customer_sk
        WHERE {date_f} AND {state_f}
          AND fod.actual_delivery_days IS NOT NULL
          AND fod.actual_delivery_days BETWEEN 0 AND 120
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


# ── Chart 1: Avg Delivery Days per Bulan ─────────────────────────────────────
st.subheader("📅 Rata-rata Delivery Days per Bulan")
df_monthly = get_delivery_monthly(tuple(years), tuple(months), tuple(states))

if df_monthly.empty:
    empty_chart_message()
else:
    fig = px.line(
        df_monthly,
        x="period",
        y="avg_delivery_days",
        markers=True,
        labels={"period": "Periode", "avg_delivery_days": "Avg Delivery Days"},
        color_discrete_sequence=[PRIMARY_COLOR],
        template=PLOTLY_TEMPLATE,
    )
    fig.update_traces(line_width=2.5, marker_size=7)
    fig.update_layout(xaxis_tickangle=-45, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Chart 2: Delay Rate per State ────────────────────────────────────────────
st.subheader("🗺️ Delay Rate per State")
df_state = get_delay_by_state(tuple(years), tuple(months), tuple(states))

if df_state.empty:
    empty_chart_message()
else:
    col_a, col_b = st.columns([2, 1])

    with col_a:
        fig2 = px.bar(
            df_state,
            x="delay_rate_pct",
            y="state",
            orientation="h",
            labels={"delay_rate_pct": "Delay Rate (%)", "state": "State"},
            color="delay_rate_pct",
            color_continuous_scale=["#AEE8C2", "#C73E1D"],
            template=PLOTLY_TEMPLATE,
            text="delay_rate_pct",
        )
        fig2.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig2.update_coloraxes(showscale=False)
        fig2.update_layout(
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="Delay Rate (%)",
            height=max(350, len(df_state) * 22),
        )
        st.plotly_chart(fig2, use_container_width=True)

    with col_b:
        st.dataframe(
            df_state[["state", "delay_rate_pct", "avg_days", "total_orders"]]
            .rename(columns={
                "state": "State",
                "delay_rate_pct": "Delay Rate (%)",
                "avg_days": "Avg Days",
                "total_orders": "Orders",
            })
            .style.format({
                "Delay Rate (%)": "{:.1f}",
                "Avg Days": "{:.1f}",
                "Orders": "{:,}",
            }),
            use_container_width=True,
            height=400,
        )

st.divider()

# ── Chart 3: Distribusi Delivery Days ────────────────────────────────────────
st.subheader("📊 Distribusi Delivery Days (Histogram)")
df_dist = get_delivery_distribution(tuple(years), tuple(months), tuple(states))

if df_dist.empty:
    empty_chart_message()
else:
    fig3 = px.histogram(
        df_dist,
        x="actual_delivery_days",
        nbins=60,
        labels={"actual_delivery_days": "Delivery Days"},
        color_discrete_sequence=[PALETTE[3]],
        template=PLOTLY_TEMPLATE,
    )
    fig3.update_layout(
        bargap=0.05,
        xaxis_title="Delivery Days",
        yaxis_title="Jumlah Order",
    )
    # Garis vertical: rata-rata
    avg_days = df_dist["actual_delivery_days"].mean()
    fig3.add_vline(
        x=avg_days,
        line_dash="dash",
        line_color=DANGER_COLOR,
        annotation_text=f"Avg: {avg_days:.1f}d",
        annotation_position="top right",
    )
    st.plotly_chart(fig3, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Median", f"{df_dist['actual_delivery_days'].median():.1f} hari")
    c2.metric("Rata-rata", f"{avg_days:.1f} hari")
    c3.metric("Maks", f"{df_dist['actual_delivery_days'].max():.0f} hari")

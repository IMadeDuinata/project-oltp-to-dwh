"""
dashboard/pages/2_Delivery_and_Logistics.py
Operasional Pengiriman, SLA Fulfillment, Lead Time, dan Analisis Bottleneck Logistik.
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
    format_number,
    format_percent,
    get_engine,
    render_global_sidebar,
)

st.set_page_config(
    page_title="Delivery & Logistics SLA | DWH",
    layout="wide",
)

inject_custom_css()

# ── Sidebar & Header ──────────────────────────────────────────────────────────
filters = render_global_sidebar(page_key="delivery")
country = filters["country"]
years = tuple(filters["years"])
months = tuple(filters["months"])

render_page_header(
    title="Operasional Pengiriman & Logistik",
    subtitle="Evaluasi SLA, kepatuhan jadwal kirim (On-Time Delivery), dan identifikasi wilayah rawan keterlambatan.",
    active_country=country,
)


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_delivery_kpis(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "fod")
    sql = f"""
        SELECT
            fod.source_country,
            COUNT(*)                                  AS total_deliveries,
            AVG(fod.actual_delivery_days)             AS avg_actual_days,
            AVG(fod.estimated_delivery_days)          AS avg_estimated_days,
            AVG(fod.delivery_delay_days)              AS avg_delay_days,
            SUM(CASE WHEN fod.is_delayed = 1 THEN 1 ELSE 0 END) AS delayed_orders,
            AVG(fod.is_delayed) * 100                 AS delay_rate_pct
        FROM fact_order_delivery fod
        JOIN dim_date dd ON fod.purchase_date_sk = dd.date_sk
        WHERE {where_clause}
          AND fod.actual_delivery_days IS NOT NULL
          AND fod.actual_delivery_days >= 0
        GROUP BY fod.source_country
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_monthly_delivery_trend(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "fod")
    sql = f"""
        SELECT
            CONCAT(dd.year, '-', LPAD(dd.month, 2, '0')) AS period,
            fod.source_country,
            AVG(fod.actual_delivery_days)                AS avg_actual_days,
            AVG(fod.estimated_delivery_days)             AS avg_estimated_days,
            AVG(fod.is_delayed) * 100                    AS delay_rate_pct,
            COUNT(*)                                     AS order_count
        FROM fact_order_delivery fod
        JOIN dim_date dd ON fod.purchase_date_sk = dd.date_sk
        WHERE {where_clause}
          AND fod.actual_delivery_days IS NOT NULL
        GROUP BY period, fod.source_country
        ORDER BY period ASC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_delay_by_customer_state(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "fod")
    sql = f"""
        SELECT
            UPPER(dc.customer_state)          AS state,
            fod.source_country,
            COUNT(*)                          AS order_count,
            AVG(fod.actual_delivery_days)     AS avg_delivery_days,
            AVG(fod.is_delayed) * 100         AS delay_rate_pct
        FROM fact_order_delivery fod
        JOIN dim_date     dd ON fod.purchase_date_sk = dd.date_sk
        JOIN dim_customer dc ON fod.customer_sk      = dc.customer_sk
        WHERE {where_clause}
          AND dc.customer_state IS NOT NULL
          AND dc.customer_state != 'NA'
        GROUP BY dc.customer_state, fod.source_country
        HAVING order_count >= 50
        ORDER BY delay_rate_pct DESC
        LIMIT 15
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_delivery_duration_buckets(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "fod")
    sql = f"""
        SELECT
            fod.source_country,
            CASE
                WHEN fod.actual_delivery_days <= 5  THEN '1. Cepat (<= 5 hari)'
                WHEN fod.actual_delivery_days <= 10 THEN '2. Standar (6-10 hari)'
                WHEN fod.actual_delivery_days <= 20 THEN '3. Sedang (11-20 hari)'
                WHEN fod.actual_delivery_days <= 30 THEN '4. Lama (21-30 hari)'
                ELSE '5. Sangat Lama (> 30 hari)'
            END AS duration_bucket,
            COUNT(*) AS order_count
        FROM fact_order_delivery fod
        JOIN dim_date dd ON fod.purchase_date_sk = dd.date_sk
        WHERE {where_clause}
          AND fod.actual_delivery_days IS NOT NULL
          AND fod.actual_delivery_days >= 0
        GROUP BY fod.source_country, duration_bucket
        ORDER BY duration_bucket ASC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


# ── Render Content ────────────────────────────────────────────────────────────
df_deliv = get_delivery_kpis(years, months, country)

if df_deliv.empty:
    st.warning("Tidak ditemukan data pengiriman pada filter yang dipilih.")
else:
    total_deliveries = df_deliv["total_deliveries"].sum()
    total_delayed = df_deliv["delayed_orders"].sum()
    overall_delay_rate = (total_delayed / total_deliveries * 100) if total_deliveries > 0 else 0
    on_time_rate = max(0, 100 - overall_delay_rate)
    
    # Rata-rata tertimbang
    weighted_actual = (df_deliv["avg_actual_days"] * df_deliv["total_deliveries"]).sum() / total_deliveries if total_deliveries > 0 else 0
    weighted_est = (df_deliv["avg_estimated_days"] * df_deliv["total_deliveries"]).sum() / total_deliveries if total_deliveries > 0 else 0
    sla_buffer = weighted_est - weighted_actual

    st.markdown('<div class="section-header"><span>SLA & Indikator Kinerja Logistik</span></div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_metric_card("On-Time Delivery", f"{on_time_rate:.1f}%", f"{total_deliveries - total_delayed:,} pesanan tepat waktu", country_badge=country)
    with c2:
        render_metric_card("Keterlambatan (Delay)", f"{overall_delay_rate:.1f}%", f"{total_delayed:,} pesanan tertunda", country_badge=country)
    with c3:
        render_metric_card("Avg Realisasi Kirim", f"{weighted_actual:.1f} hari", "Waktu aktual dari order ke sampai", country_badge=country)
    with c4:
        render_metric_card("Avg Janji Estimasi", f"{weighted_est:.1f} hari", "Estimasi awal tanggal tiba", country_badge=country)
    with c5:
        render_metric_card("Lead Time Buffer", f"{sla_buffer:+.1f} hari", "Tenggat aman sebelum terlambat", country_badge=country)

    # ── Monthly Trend Charts ──────────────────────────────────────────────────
    st.markdown('<div class="section-header"><span>Tren Durasi & Ketepatan Pengiriman Bulanan</span></div>', unsafe_allow_html=True)
    df_trend = get_monthly_delivery_trend(years, months, country)

    if not df_trend.empty:
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            fig_days = px.line(
                df_trend,
                x="period",
                y="avg_actual_days",
                color="source_country",
                markers=True,
                title="Rata-rata Waktu Pengiriman Aktual (Hari)",
                color_discrete_map=COUNTRY_COLOR_MAP,
                labels={"period": "Periode", "avg_actual_days": "Hari Pengiriman", "source_country": "Negara"},
            )
            st.plotly_chart(apply_plotly_theme(fig_days, height=360), use_container_width=True)

        with col_t2:
            fig_delay = px.line(
                df_trend,
                x="period",
                y="delay_rate_pct",
                color="source_country",
                markers=True,
                title="Persentase Keterlambatan Pesanan (Delay Rate %)",
                color_discrete_map=COUNTRY_COLOR_MAP,
                labels={"period": "Periode", "delay_rate_pct": "Delay Rate (%)", "source_country": "Negara"},
            )
            st.plotly_chart(apply_plotly_theme(fig_delay, height=360), use_container_width=True)

    # ── Distribution & Bottlenecks ────────────────────────────────────────────
    st.markdown('<div class="section-header"><span>Wilayah Bottleneck & Distribusi Kecepatan Kirim</span></div>', unsafe_allow_html=True)
    col_b1, col_b2 = st.columns(2)

    with col_b1:
        df_state = get_delay_by_customer_state(years, months, country)
        if not df_state.empty:
            fig_state = px.bar(
                df_state,
                y="state",
                x="delay_rate_pct",
                color="source_country",
                orientation="h",
                title="Top Wilayah/Provinsi dengan Rasio Delay Tertinggi (Min. 50 Order)",
                color_discrete_map=COUNTRY_COLOR_MAP,
                barmode="stack",
                labels={"state": "Wilayah / State", "delay_rate_pct": "Delay Rate (%)", "source_country": "Negara"},
            )
            fig_state.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(apply_plotly_theme(fig_state, height=420), use_container_width=True)

    with col_b2:
        df_bucket = get_delivery_duration_buckets(years, months, country)
        if not df_bucket.empty:
            fig_bucket = px.bar(
                df_bucket,
                x="duration_bucket",
                y="order_count",
                color="source_country",
                title="Distribusi Rentang Kecepatan Pengiriman",
                color_discrete_map=COUNTRY_COLOR_MAP,
                barmode="group",
                labels={"duration_bucket": "Kategori Durasi", "order_count": "Jumlah Paket", "source_country": "Negara"},
            )
            fig_bucket.update_layout(xaxis_tickangle=-15)
            st.plotly_chart(apply_plotly_theme(fig_bucket, height=420), use_container_width=True)

    st.markdown(
        """
        <div class="insight-callout">
            <b>Logistics Operational Summary:</b><br>
            • Rata-rata pengiriman berhasil sampai lebih cepat dari janji estimasi awal (SLA Buffer positif).<br>
            • Wilayah luar pulau atau pelosok menunjukkan kecenderungan keterlambatan lebih tinggi, mengindikasikan perlunya kerja sama dengan kurir regional khusus.
        </div>
        """,
        unsafe_allow_html=True,
    )

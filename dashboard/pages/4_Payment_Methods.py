"""
dashboard/pages/4_Payment_Methods.py
Analisis Metode Pembayaran, Cicilan (Installments), dan Rata-rata Nilai Transaksi per Metode.
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
    CATEGORY_PALETTE,
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
    page_title="Payment Methods & Installments | DWH",
    page_icon="💳",
    layout="wide",
)

inject_custom_css()

# ── Sidebar & Header ──────────────────────────────────────────────────────────
filters = render_global_sidebar(page_key="payment")
country = filters["country"]
years = tuple(filters["years"])
months = tuple(filters["months"])

render_page_header(
    title="💳 Analisis Metode Pembayaran & Pembiayaan",
    subtitle="Membedah penetrasi tipe pembayaran (Credit Card, Boleto, dsb.), rata-rata cicilan, dan ticket size per channel.",
    active_country=country,
)


# ── Queries ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_payment_summary(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "fop")
    sql = f"""
        SELECT
            fop.source_country,
            dpt.payment_type,
            COUNT(*)                        AS total_transactions,
            SUM(fop.payment_value)          AS total_value,
            AVG(fop.payment_value)          AS avg_ticket_size,
            AVG(fop.payment_installments)   AS avg_installments
        FROM fact_order_payments fop
        JOIN dim_date         dd  ON fop.purchase_date_sk = dd.date_sk
        JOIN dim_payment_type dpt ON fop.payment_type_sk  = dpt.payment_type_sk
        WHERE {where_clause}
        GROUP BY fop.source_country, dpt.payment_type
        ORDER BY total_value DESC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_installment_distribution(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "fop")
    sql = f"""
        SELECT
            fop.source_country,
            CASE
                WHEN fop.payment_installments <= 1 THEN '1x (Bayar Lunas)'
                WHEN fop.payment_installments BETWEEN 2 AND 3 THEN '2-3x Cicilan'
                WHEN fop.payment_installments BETWEEN 4 AND 6 THEN '4-6x Cicilan'
                WHEN fop.payment_installments BETWEEN 7 AND 10 THEN '7-10x Cicilan'
                ELSE '>10x Cicilan'
            END AS installment_tier,
            COUNT(*)               AS transaction_count,
            SUM(fop.payment_value) AS total_value,
            AVG(fop.payment_value) AS avg_value
        FROM fact_order_payments fop
        JOIN dim_date dd ON fop.purchase_date_sk = dd.date_sk
        WHERE {where_clause}
          AND fop.payment_installments IS NOT NULL
        GROUP BY fop.source_country, installment_tier
        ORDER BY installment_tier ASC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_monthly_payment_share(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "fop")
    sql = f"""
        SELECT
            CONCAT(dd.year, '-', LPAD(dd.month, 2, '0')) AS period,
            dpt.payment_type,
            SUM(fop.payment_value)                        AS total_value
        FROM fact_order_payments fop
        JOIN dim_date         dd  ON fop.purchase_date_sk = dd.date_sk
        JOIN dim_payment_type dpt ON fop.payment_type_sk  = dpt.payment_type_sk
        WHERE {where_clause}
        GROUP BY period, dpt.payment_type
        ORDER BY period ASC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


# ── Render Content ────────────────────────────────────────────────────────────
df_pay = get_payment_summary(years, months, country)

if df_pay.empty:
    st.warning("⚠️ Tidak ditemukan data transaksi pembayaran pada filter yang dipilih.")
else:
    total_val = df_pay["total_value"].sum()
    total_tx = df_pay["total_transactions"].sum()
    avg_ticket = (total_val / total_tx) if total_tx > 0 else 0
    
    # Hitung rata-rata cicilan berbobot
    avg_inst = (df_pay["avg_installments"] * df_pay["total_transactions"]).sum() / total_tx if total_tx > 0 else 0

    st.markdown('<div class="section-header"><span>💳 Metrik Volume & Karakteristik Transaksi</span></div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card("Total Pembayaran Diproses", f"R$ {total_val:,.0f}", "Nilai total disbursement", country_badge=country)
    with c2:
        render_metric_card("Total Transaksi Pembayaran", format_number(total_tx), "Frekuensi payment records", country_badge=country)
    with c3:
        render_metric_card("Average Ticket Size", f"R$ {avg_ticket:,.2f}", "Nilai rata-rata per transaksi", country_badge=country)
    with c4:
        render_metric_card("Rata-rata Jumlah Cicilan", f"{avg_inst:.1f}x", "Tingkat fleksibilitas pembayaran", country_badge=country)

    # ── Charts Row 1: Payment Method Share & Ticket Size ─────────────────────
    st.markdown('<div class="section-header"><span>📊 Komposisi Metode Pembayaran & Rata-rata Nilai</span></div>', unsafe_allow_html=True)
    col_p1, col_p2 = st.columns(2)

    with col_p1:
        # Grouped by payment type
        pay_type_agg = df_pay.groupby("payment_type").agg({
            "total_value": "sum",
            "total_transactions": "sum",
        }).reset_index()

        fig_pie = px.pie(
            pay_type_agg,
            names="payment_type",
            values="total_value",
            title="Pangsa Nilai Transaksi per Metode Pembayaran",
            color_discrete_sequence=CATEGORY_PALETTE,
            hole=0.45,
        )
        fig_pie.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>Nilai: R$ %{value:,.2f}<br>Porsi: %{percent}",
        )
        st.plotly_chart(apply_plotly_theme(fig_pie, height=360), use_container_width=True)

    with col_p2:
        fig_ticket = px.bar(
            df_pay,
            x="payment_type",
            y="avg_ticket_size",
            color="source_country",
            title="Rata-rata Nilai Transaksi (Ticket Size) per Metode",
            color_discrete_map=COUNTRY_COLOR_MAP,
            barmode="group",
            labels={"payment_type": "Metode Pembayaran", "avg_ticket_size": "Ticket Size (R$)", "source_country": "Negara"},
        )
        st.plotly_chart(apply_plotly_theme(fig_ticket, height=360), use_container_width=True)

    # ── Installments & Timeline Trends ────────────────────────────────────────
    st.markdown('<div class="section-header"><span>🔢 Distribusi Cicilan & Evolusi Bulanan</span></div>', unsafe_allow_html=True)
    col_i1, col_i2 = st.columns(2)

    with col_i1:
        df_inst = get_installment_distribution(years, months, country)
        if not df_inst.empty:
            fig_inst = px.bar(
                df_inst,
                x="installment_tier",
                y="transaction_count",
                color="source_country",
                title="Pilihan Skema Cicilan Konsumen",
                color_discrete_map=COUNTRY_COLOR_MAP,
                barmode="group",
                labels={"installment_tier": "Skema Cicilan", "transaction_count": "Jumlah Transaksi", "source_country": "Negara"},
            )
            st.plotly_chart(apply_plotly_theme(fig_inst, height=380), use_container_width=True)

    with col_i2:
        df_monthly_p = get_monthly_payment_share(years, months, country)
        if not df_monthly_p.empty:
            fig_month = px.area(
                df_monthly_p,
                x="period",
                y="total_value",
                color="payment_type",
                title="Evolusi Nilai Transaksi Bulanan per Metode",
                color_discrete_sequence=CATEGORY_PALETTE,
                labels={"period": "Periode", "total_value": "Nilai (R$)", "payment_type": "Metode"},
            )
            st.plotly_chart(apply_plotly_theme(fig_month, height=380), use_container_width=True)

    st.markdown(
        """
        <div class="insight-callout">
            💳 <b>Payment Strategy Summary:</b><br>
            • <b>Credit Card Dominance:</b> Kartu kredit menyumbang porsi transaksi terbesar sekaligus memberikan ticket size rata-rata tertinggi berkat opsi cicilan multi-bulan.<br>
            • <b>Cash / Voucher Alternatives:</b> Metode non-kredit (seperti boleto / transfer) populer untuk transaksi bernilai lebih kecil atau segmen unbanked.
        </div>
        """,
        unsafe_allow_html=True,
    )

"""
dashboard/main.py
Executive Overview & Dual-Source (Brazil & Indonesia) Analytical Dashboard.
Entry point utama aplikasi Streamlit.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
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

# ── Page Setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Executive DWH Overview | Dual-Source Analytics",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()

# ── Global Sidebar ────────────────────────────────────────────────────────────
filters = render_global_sidebar(page_key="executive")
country = filters["country"]
years = tuple(filters["years"])
months = tuple(filters["months"])

# ── Hero Banner ───────────────────────────────────────────────────────────────
render_page_header(
    title="🌐 Executive DWH Overview",
    subtitle="Dual-Source Strategic Monitoring: Olist Brazil (BR) & Mitra Indonesia (ID)",
    active_country=country,
)


# ── Cached Queries ────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_executive_kpis(sel_years, sel_months, sel_country):
    where_items = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    where_deliv = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "fod")

    engine = get_engine()
    with engine.connect() as conn:
        df_sales = pd.read_sql(
            f"""
            SELECT
                foi.source_country,
                SUM(foi.total_item_value)       AS total_revenue,
                COUNT(DISTINCT foi.order_id)    AS total_orders,
                COUNT(DISTINCT foi.customer_sk) AS unique_customers
            FROM fact_order_items foi
            JOIN dim_date dd ON foi.purchase_date_sk = dd.date_sk
            WHERE {where_items}
            GROUP BY foi.source_country
            """,
            conn,
        )

        df_deliv = pd.read_sql(
            f"""
            SELECT
                fod.source_country,
                AVG(fod.actual_delivery_days) AS avg_delivery_days,
                AVG(fod.is_delayed) * 100     AS delay_rate_pct
            FROM fact_order_delivery fod
            JOIN dim_date dd ON fod.purchase_date_sk = dd.date_sk
            WHERE {where_deliv}
            GROUP BY fod.source_country
            """,
            conn,
        )

    return df_sales, df_deliv


@st.cache_data(ttl=300)
def get_monthly_revenue_trend(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            CONCAT(dd.year, '-', LPAD(dd.month, 2, '0')) AS period,
            foi.source_country,
            SUM(foi.total_item_value)                     AS revenue,
            COUNT(DISTINCT foi.order_id)                  AS order_count
        FROM fact_order_items foi
        JOIN dim_date dd ON foi.purchase_date_sk = dd.date_sk
        WHERE {where_clause}
        GROUP BY period, foi.source_country
        ORDER BY period ASC, foi.source_country ASC
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def get_top_categories_split(sel_years, sel_months, sel_country):
    where_clause = build_where_clause(list(sel_years), list(sel_months), sel_country, "dd", "foi")
    sql = f"""
        SELECT
            COALESCE(dp.product_category_name, 'Unknown') AS category,
            foi.source_country,
            SUM(foi.total_item_value)                      AS revenue,
            COUNT(*)                                       AS items_sold
        FROM fact_order_items foi
        JOIN dim_date    dd ON foi.purchase_date_sk = dd.date_sk
        JOIN dim_product dp ON foi.product_sk       = dp.product_sk
        WHERE {where_clause}
        GROUP BY dp.product_category_name, foi.source_country
        ORDER BY revenue DESC
        LIMIT 20
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


# ── Render Data ───────────────────────────────────────────────────────────────
df_sales, df_deliv = get_executive_kpis(years, months, country)

if df_sales.empty:
    st.warning("⚠️ Tidak ada data untuk kombinasi filter yang dipilih.")
else:
    # Agregasi total KPI
    total_rev = df_sales["total_revenue"].sum()
    total_orders = df_sales["total_orders"].sum()
    total_cust = df_sales["unique_customers"].sum()
    aov = (total_rev / total_orders) if total_orders > 0 else 0

    avg_deliv_days = df_deliv["avg_delivery_days"].mean() if not df_deliv.empty else 0
    avg_delay_rate = df_deliv["delay_rate_pct"].mean() if not df_deliv.empty else 0
    on_time_rate = max(0, 100 - avg_delay_rate)

    # ── KPI Cards ─────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header"><span>📊 Executive KPI Scorecard</span></div>', unsafe_allow_html=True)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        render_metric_card(
            title="Total GMV / Revenue",
            value=f"R$ {total_rev:,.0f}",
            subtitle="Nilai transaksi bruto",
            country_badge=country,
        )
    with col2:
        render_metric_card(
            title="Total Orders",
            value=format_number(total_orders),
            subtitle="Pesanan terverifikasi",
            country_badge=country,
        )
    with col3:
        render_metric_card(
            title="Average Order Value",
            value=f"R$ {aov:,.1f}",
            subtitle="Rata-rata basket order",
            country_badge=country,
        )
    with col4:
        render_metric_card(
            title="On-Time Delivery",
            value=f"{on_time_rate:.1f}%",
            subtitle=f"Delay rate: {avg_delay_rate:.1f}%",
            country_badge=country,
        )
    with col5:
        render_metric_card(
            title="Active Customers",
            value=format_number(total_cust),
            subtitle="Pelanggan unik bertransaksi",
            country_badge=country,
        )

    # ── Dual-Source Comparison Breakdown ──────────────────────────────────────
    if country == "ALL" and len(df_sales) > 1:
        st.markdown('<div class="section-header"><span>🌐 Dual-Source Market Share (BR vs ID)</span></div>', unsafe_allow_html=True)
        col_share1, col_share2 = st.columns(2)
        
        with col_share1:
            fig_pie_rev = px.pie(
                df_sales,
                names="source_country",
                values="total_revenue",
                title="Kontribusi Revenue per Negara",
                color="source_country",
                color_discrete_map=COUNTRY_COLOR_MAP,
                hole=0.45,
            )
            fig_pie_rev.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>Revenue: R$ %{value:,.2f}<br>Share: %{percent}",
            )
            st.plotly_chart(apply_plotly_theme(fig_pie_rev, height=320), use_container_width=True)

        with col_share2:
            fig_pie_ord = px.pie(
                df_sales,
                names="source_country",
                values="total_orders",
                title="Kontribusi Volume Pesanan per Negara",
                color="source_country",
                color_discrete_map=COUNTRY_COLOR_MAP,
                hole=0.45,
            )
            fig_pie_ord.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>Orders: %{value:,}<br>Share: %{percent}",
            )
            st.plotly_chart(apply_plotly_theme(fig_pie_ord, height=320), use_container_width=True)

    # ── Monthly Revenue & Orders Trend ────────────────────────────────────────
    st.markdown('<div class="section-header"><span>📈 Tren Pendapatan & Volume Bulanan</span></div>', unsafe_allow_html=True)
    df_trend = get_monthly_revenue_trend(years, months, country)

    if not df_trend.empty:
        col_t1, col_t2 = st.columns([2, 1])

        with col_t1:
            fig_trend = px.line(
                df_trend,
                x="period",
                y="revenue",
                color="source_country",
                markers=True,
                title="Pertumbuhan Pendapatan Bulanan (Revenue by Period)",
                color_discrete_map=COUNTRY_COLOR_MAP,
                labels={"period": "Periode (Tahun-Bulan)", "revenue": "Revenue (R$)", "source_country": "Negara"},
            )
            fig_trend.update_layout(hovermode="x unified")
            fig_trend.update_traces(line=dict(width=2.5))
            st.plotly_chart(apply_plotly_theme(fig_trend, height=360), use_container_width=True)

        with col_t2:
            fig_ord_bar = px.bar(
                df_trend,
                x="period",
                y="order_count",
                color="source_country",
                title="Volume Pesanan Bulanan",
                color_discrete_map=COUNTRY_COLOR_MAP,
                barmode="stack",
                labels={"period": "Periode", "order_count": "Jumlah Order", "source_country": "Negara"},
            )
            st.plotly_chart(apply_plotly_theme(fig_ord_bar, height=360), use_container_width=True)

    # ── Top Categories Comparison ─────────────────────────────────────────────
    st.markdown('<div class="section-header"><span>🏆 Kategori Produk Teratas</span></div>', unsafe_allow_html=True)
    df_cat = get_top_categories_split(years, months, country)

    if not df_cat.empty:
        # Group by category to find top 10
        top_cats = (
            df_cat.groupby("category")["revenue"]
            .sum()
            .nlargest(10)
            .index.tolist()
        )
        df_cat_top = df_cat[df_cat["category"].isin(top_cats)].copy()

        fig_cat = px.bar(
            df_cat_top,
            y="category",
            x="revenue",
            color="source_country",
            orientation="h",
            title="Top 10 Kategori Produk Berdasarkan Nilai Transaksi (Revenue)",
            color_discrete_map=COUNTRY_COLOR_MAP,
            labels={"category": "Kategori", "revenue": "Revenue (R$)", "source_country": "Negara"},
            barmode="stack",
        )
        fig_cat.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(apply_plotly_theme(fig_cat, height=400), use_container_width=True)

    # ── Executive Key Takeaways ───────────────────────────────────────────────
    st.markdown(
        """
        <div class="insight-callout">
            💡 <b>Executive Insights:</b><br>
            • <b>Market Scale:</b> Olist Brazil (BR) mendominasi nilai transaksi bruto, didorong oleh maturitas katalog dan variasi produk.<br>
            • <b>Market Growth (ID):</b> Pasar Indonesia (ID) memperlihatkan stabilitas operasional pemenuhan pesanan dengan tingkat keterlambatan pengiriman yang sebanding dengan Brazil.<br>
            • <b>Arah Navigasi:</b> Gunakan menu navigasi di sisi kiri untuk melihat eksplorasi terperinci: <i>Revenue & Sales</i>, <i>Delivery Operations</i>, <i>Customer Behavior</i>, dan <i>Payment Methods</i>.
        </div>
        """,
        unsafe_allow_html=True,
    )

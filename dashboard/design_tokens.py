"""
dashboard/design_tokens.py
Design System Tokens & UI Components for Dual-Source (BR / ID) Analytics Dashboard.
Menyediakan token warna, tipografi, spacing, CSS injection, dan Plotly theming konsisten.
"""

import streamlit as st
import plotly.graph_objects as go

# ── Color Palette & Tokens ────────────────────────────────────────────────────
TOKENS = {
    "colors": {
        "primary": "#2563EB",       # Royal Blue
        "primary_dark": "#1D4ED8",
        "primary_light": "#DBEAFE",
        
        # Dual-Source Country Palette
        "br": {
            "main": "#059669",        # Emerald Green (Brazil)
            "dark": "#047857",
            "light": "#D1FAE5",
            "border": "#10B981",
            "label": "Brazil (BR)",
        },
        "id": {
            "main": "#DC2626",        # Vermilion Red (Indonesia)
            "dark": "#B91C1C",
            "light": "#FEE2E2",
            "border": "#EF4444",
            "label": "Indonesia (ID)",
        },
        "both": {
            "main": "#4F46E5",        # Indigo (Combined)
            "dark": "#3730A3",
            "light": "#EEF2FF",
            "border": "#6366F1",
            "label": "All Countries",
        },

        # Semantic
        "success": "#10B981",
        "warning": "#F59E0B",
        "danger": "#EF4444",
        "info": "#0EA5E9",

        # Neutrals
        "neutral_900": "#0F172A",
        "neutral_800": "#1E293B",
        "neutral_700": "#334155",
        "neutral_500": "#64748B",
        "neutral_300": "#CBD5E1",
        "neutral_100": "#F1F5F9",
        "neutral_50":  "#F8FAFC",
        "white":       "#FFFFFF",
    },
    "spacing": {
        "xs": "4px",
        "sm": "8px",
        "md": "16px",
        "lg": "24px",
        "xl": "32px",
    },
    "radius": {
        "sm": "6px",
        "md": "10px",
        "lg": "16px",
        "full": "9999px",
    },
    "shadows": {
        "subtle": "0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px -1px rgba(0, 0, 0, 0.08)",
        "card": "0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -2px rgba(0, 0, 0, 0.07)",
        "hover": "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)",
    }
}

COUNTRY_COLOR_MAP = {
    "BR": TOKENS["colors"]["br"]["main"],
    "ID": TOKENS["colors"]["id"]["main"],
    "Combined": TOKENS["colors"]["both"]["main"],
    "ALL": TOKENS["colors"]["both"]["main"],
}

CATEGORY_PALETTE = [
    "#2563EB", "#059669", "#DC2626", "#D97706", "#7C3AED",
    "#0891B2", "#DB2777", "#4B5563", "#4338CA", "#047857"
]

def get_country_color(code: str) -> str:
    """Mengembalikan hex color untuk kode negara ('BR', 'ID', atau fallback)."""
    return COUNTRY_COLOR_MAP.get(str(code).upper(), TOKENS["colors"]["primary"])

# ── CSS Injection ─────────────────────────────────────────────────────────────
def inject_custom_css():
    """Inject styling modern berbasis design tokens ke antarmuka Streamlit."""
    css = f"""
    <style>
        /* Base typography & page resets */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        
        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}

        /* Clean metric card styles */
        .metric-card-box {{
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: {TOKENS["radius"]["md"]};
            padding: 18px 20px;
            box-shadow: {TOKENS["shadows"]["subtle"]};
            transition: all 0.2s ease-in-out;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .metric-card-box:hover {{
            box-shadow: {TOKENS["shadows"]["card"]};
            border-color: #CBD5E1;
        }}
        .metric-title {{
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
            color: #64748B;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .metric-value {{
            font-size: 1.85rem;
            font-weight: 700;
            color: #0F172A;
            line-height: 1.2;
            margin-bottom: 4px;
        }}
        .metric-subtitle {{
            font-size: 0.8rem;
            color: #64748B;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .badge-country-br {{
            background-color: {TOKENS["colors"]["br"]["light"]};
            color: {TOKENS["colors"]["br"]["dark"]};
            border: 1px solid {TOKENS["colors"]["br"]["border"]};
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.72rem;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-country-id {{
            background-color: {TOKENS["colors"]["id"]["light"]};
            color: {TOKENS["colors"]["id"]["dark"]};
            border: 1px solid {TOKENS["colors"]["id"]["border"]};
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.72rem;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-country-all {{
            background-color: {TOKENS["colors"]["both"]["light"]};
            color: {TOKENS["colors"]["both"]["dark"]};
            border: 1px solid {TOKENS["colors"]["both"]["border"]};
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.72rem;
            font-weight: 700;
            display: inline-block;
        }}

        /* Header banner */
        .page-banner {{
            background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
            color: #FFFFFF;
            padding: 24px 28px;
            border-radius: {TOKENS["radius"]["md"]};
            margin-bottom: 24px;
            border-left: 6px solid #2563EB;
        }}
        .page-banner h1 {{
            color: #FFFFFF !important;
            font-size: 1.75rem !important;
            font-weight: 800 !important;
            margin: 0 0 6px 0 !important;
        }}
        .page-banner p {{
            color: #94A3B8 !important;
            font-size: 0.95rem !important;
            margin: 0 !important;
        }}

        /* Custom section divider */
        .section-header {{
            font-size: 1.15rem;
            font-weight: 700;
            color: #1E293B;
            border-bottom: 2px solid #E2E8F0;
            padding-bottom: 8px;
            margin-top: 24px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        /* Insight callout box */
        .insight-callout {{
            background: #F8FAFC;
            border-left: 4px solid #2563EB;
            padding: 12px 16px;
            border-radius: 0 {TOKENS["radius"]["sm"]} {TOKENS["radius"]["sm"]} 0;
            font-size: 0.88rem;
            color: #334155;
            margin: 12px 0;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def render_metric_card(title: str, value: str, subtitle: str = "", country_badge: str = None, help_text: str = None):
    """Render Metric Card modern berstandar design tokens."""
    badge_html = ""
    if country_badge:
        b_upper = country_badge.upper()
        if "BR" in b_upper:
            badge_html = f'<span class="badge-country-br">🇧🇷 {b_upper}</span>'
        elif "ID" in b_upper:
            badge_html = f'<span class="badge-country-id">🇮🇩 {b_upper}</span>'
        else:
            badge_html = f'<span class="badge-country-all">🌐 {b_upper}</span>'

    card_html = f"""
    <div class="metric-card-box">
        <div>
            <div class="metric-title">
                <span>{title}</span>
                {badge_html}
            </div>
            <div class="metric-value">{value}</div>
        </div>
        {f'<div class="metric-subtitle">{subtitle}</div>' if subtitle else ''}
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


def render_page_header(title: str, subtitle: str, active_country: str = "ALL"):
    """Render page hero banner dengan branding konsisten."""
    country_badge = ""
    if active_country == "BR":
        country_badge = '<span class="badge-country-br" style="font-size:0.85rem; padding:4px 12px; margin-left:12px;">🇧🇷 Filter Aktif: Brazil</span>'
    elif active_country == "ID":
        country_badge = '<span class="badge-country-id" style="font-size:0.85rem; padding:4px 12px; margin-left:12px;">🇮🇩 Filter Aktif: Indonesia</span>'
    else:
        country_badge = '<span class="badge-country-all" style="font-size:0.85rem; padding:4px 12px; margin-left:12px;">🌐 Filter Aktif: Dual Source (BR & ID)</span>'

    banner_html = f"""
    <div class="page-banner">
        <h1>{title} {country_badge}</h1>
        <p>{subtitle}</p>
    </div>
    """
    st.markdown(banner_html, unsafe_allow_html=True)


def apply_plotly_theme(fig: go.Figure, title: str = None, height: int = 400) -> go.Figure:
    """Terapkan styling tema seragam untuk Plotly charts."""
    fig.update_layout(
        template="plotly_white",
        height=height,
        title=dict(
            text=f"<b>{title}</b>" if title else "",
            font=dict(size=14, color="#1E293B", family="Inter, sans-serif"),
            x=0.01,
            xanchor="left",
        ) if title else None,
        font=dict(family="Inter, sans-serif", color="#475569", size=12),
        margin=dict(l=40, r=30, t=50 if title else 20, b=40),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        hoverlabel=dict(
            bgcolor="#0F172A",
            font_size=12,
            font_color="#FFFFFF",
            font_family="Inter, sans-serif"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            title=None,
            font=dict(size=11),
        ),
    )
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor="#F1F5F9",
        linecolor="#CBD5E1",
        tickfont=dict(color="#64748B", size=11),
    )
    fig.update_yaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor="#F1F5F9",
        linecolor="#CBD5E1",
        tickfont=dict(color="#64748B", size=11),
    )
    return fig

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from financial_dashboard import db
from financial_dashboard.analytics import (
    annualized_logarithmic_regression_change,
    calendar_year_change,
    cumulative_interest_growth,
    downsample_for_chart,
    logarithmic_regression_channel,
    period_change,
    rebased_price_level,
)
from financial_dashboard.status import freshness_status


st.set_page_config(
    page_title="Market Daily",
    page_icon="↗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "light_mode" not in st.session_state:
    st.session_state["light_mode"] = True
if "logarithmic" not in st.session_state:
    st.session_state["logarithmic"] = True
if "corridor_enabled" not in st.session_state:
    st.session_state["corridor_enabled"] = True
if "corridor_95" not in st.session_state:
    st.session_state["corridor_95"] = True
if "treasury_cumulative" not in st.session_state:
    st.session_state["treasury_cumulative"] = True
if "fed_target_cumulative" not in st.session_state:
    st.session_state["fed_target_cumulative"] = False

light_mode = st.session_state["light_mode"]
theme = {
    "background": "#ffffff" if light_mode else "#090b10",
    "chart_background": "#ffffff" if light_mode else "#0f131b",
    "surface": "#ffffff" if light_mode else "#0f131b",
    "surface_alt": "#f5f7fa" if light_mode else "#141a24",
    "text": "#131722" if light_mode else "#e8edf5",
    "muted": "#787b86" if light_mode else "#78869c",
    "border": "#e0e3eb" if light_mode else "#1d2633",
    "grid": "#e9edf2" if light_mode else "#171d27",
    "channel": "#3d7f32" if light_mode else "#7fc873",
}

st.markdown(
    f"""
    <style>
    :root {{ color-scheme: {"light" if light_mode else "dark"}; }}
    :root {{ --primary-color: #2962ff; }}
    :root {{ --space-tight: .5rem; --space-group: 1rem; --space-section: 1.5rem; }}
    :root {{ --font-ui: "Source Sans", "Segoe UI", sans-serif;
      --type-body: 1rem; --type-label: .875rem; --type-meta: .875rem;
      --type-metric: 1.5rem; --type-price: clamp(2rem, 3vw, 3rem); }}
    .stApp, input, button, select {{ font-family: var(--font-ui); }}
    header[data-testid="stHeader"], [data-testid="stDecoration"] {{ display: none !important; }}
    [data-testid="stToolbar"], footer {{ visibility: hidden; }}
    [data-testid="stAppViewContainer"], .stApp {{
      background-color: {theme["background"]}; color: {theme["text"]};
      background-image: {"radial-gradient(#c9d0dc 1.15px, transparent 1.15px)" if light_mode else "none"};
      background-size: 22px 22px;
    }}
    [data-testid="stAppViewContainer"] > .main {{ padding-top: 0 !important; }}
    .block-container {{ max-width: 1480px; padding: 1.25rem 2.4rem 3rem; }}
    .masthead {{ display: flex; align-items: baseline; gap: .25rem 1rem; flex-wrap: wrap; }}
    .brand {{ font-size: 1.65rem; line-height: 1.2; font-weight: 700;
             letter-spacing: -.03em; color: #2962ff; margin: 0; }}
    h1.market-title {{ font-size: var(--type-body) !important; font-weight: 400 !important;
      line-height: 1.4 !important; letter-spacing: 0; padding: 0 !important;
      margin: 0; color: {theme["text"]}; }}
    .market-snapshot {{ width: 100%; display: block;
      margin: 0; padding: 1rem 1.25rem;
      color: {theme["text"]}; border: 0; border-radius: 30px;
      box-shadow: 0 14px 30px rgba(25, 38, 67, .09);
      background: {theme["surface"]}; }}
    .snapshot-head {{ display: flex; align-items: center; justify-content: space-between;
      gap: var(--space-tight); flex-wrap: wrap;
      font-size: .75rem; line-height: 1.4; letter-spacing: .04em; font-weight: 600; text-transform: uppercase; }}
    .snapshot-name {{ font-size: 1.25rem; font-weight: 600; letter-spacing: -.01em; text-transform: none; }}
    .snapshot-head span:last-child {{ color: #7b5c11; }}
    .snapshot-price {{
      font-size: var(--type-price); line-height: 1.15; font-weight: 700;
      font-variant-numeric: tabular-nums; letter-spacing: -.03em; margin: .5rem 0; }}
    .snapshot-detail {{ font-size: var(--type-meta); line-height: 1.5; margin-top: .45rem;
      font-variant-numeric: lining-nums tabular-nums; overflow-wrap: anywhere; }}
    .muted {{ color: {theme["text"]}; font-size: var(--type-meta); line-height: 1.5; }}
    .stPlotlyChart {{ position: relative; z-index: 0; margin-bottom: 1rem; border-radius: 30px;
      overflow: hidden; background: {theme["surface"]}; box-shadow: 0 12px 28px rgba(25, 38, 67, .09); }}
    .source-line {{ position: relative; z-index: 1; display: block; margin-top: .35rem;
                    padding: .8rem 0 0; min-height: 2.25rem;
                    border-top: 1px solid {theme["border"]}; background: {theme["surface"]};
                    color: {theme["text"]}; font-size: var(--type-meta); line-height: 1.5; }}
    div[data-testid="stMetric"] {{ background: {theme["surface"]}; border: 0;
                                  border-radius: 26px; padding: .85rem 1.2rem;
                                  box-shadow: 0 10px 24px rgba(25, 38, 67, .075); }}
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
      color: {theme["text"]} !important; opacity: 1 !important;
      font-size: var(--type-label); font-weight: 400; line-height: 1.4;
    }}
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{
      color: {theme["text"]} !important; font-size: var(--type-metric); font-weight: 600;
      line-height: 1.25; font-variant-numeric: lining-nums tabular-nums; letter-spacing: -.01em;
    }}
    [data-testid="stMetricDelta"] {{ font-size: var(--type-meta); font-variant-numeric: tabular-nums; }}
    div[role="radiogroup"] {{ gap: .25rem; }}
    div[role="radiogroup"] label {{ background: {theme["surface"]}; border: 0;
                                    border-radius: 16px; padding: .52rem .9rem;
                                    box-shadow: 0 5px 14px rgba(25, 38, 67, .075); }}
    div[role="radiogroup"] label p, .stButton button, [data-testid="stWidgetLabel"] p {{
      color: {theme["text"]} !important;
    }}
    div[role="radiogroup"] label:has(input:checked),
    div[role="radiogroup"] label:has([aria-checked="true"]) {{
      background: {theme["surface_alt"]}; font-weight: 700;
      box-shadow: inset 0 0 0 1px #2962ff;
    }}
    [data-testid="stSelectbox"] [data-testid="stWidgetLabel"] p,
    [data-testid="stRadio"] [data-testid="stWidgetLabel"] p {{ font-size: var(--type-label); font-weight: 600; }}
    [data-testid="stWidgetLabel"] p {{ font-size: var(--type-label); line-height: 1.4; }}
    [data-testid="stSlider"] p {{ font-variant-numeric: tabular-nums; }}
    [data-testid="stCheckbox"][data-selected="true"] > label > div:first-of-type {{
      background: #2962ff !important;
    }}
    [data-testid="stRadioOption"][data-selected="true"] > div:first-of-type > div:first-of-type {{
      background: #2962ff !important;
    }}
    /* TradingView-like neutral controls for chart selection and switches. */
    [data-testid="stSelectbox"] [data-baseweb="select"],
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] input {{
      background: {"#ffffff" if light_mode else "#20242c"} !important;
      border-color: {"#e3e7ee" if light_mode else "#343a45"} !important;
      border-radius: 18px !important;
      box-shadow: {"0 6px 15px rgba(25, 38, 67, .07)" if light_mode else "none"};
      color: {theme["text"]} !important;
    }}
    [data-testid="stSelectbox"] [data-baseweb="select"] * {{
      color: {theme["text"]} !important;
    }}
    [data-testid="stToggle"] [role="switch"] {{
      background: {"#d1d4dc" if light_mode else "#3a414d"} !important;
      border-color: transparent !important;
    }}
    [data-testid="stToggle"] [role="switch"][aria-checked="true"] {{
      background: {"#787b86" if light_mode else "#8b93a1"} !important;
    }}
    [data-testid="stToggle"] [role="switch"] > div {{
      background: {"#ffffff" if light_mode else "#141820"} !important;
    }}
    .stButton button {{ border-radius: 18px; border-color: {theme["border"]};
                        background: {theme["surface"]}; box-shadow: 0 6px 15px rgba(25, 38, 67, .07);
                        font-weight: 650; }}
    .st-key-dashboard_header > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
      background: {theme["surface"]}; border: 0;
      border-radius: 28px; padding: .85rem 1.15rem; box-shadow: 0 12px 26px rgba(25, 38, 67, .08); }}
    .st-key-theme_mode button {{ width: 44px; height: 44px; min-width: 44px;
      padding: 0; background: {theme["surface_alt"]}; color: {theme["text"]} !important;
      border-color: {theme["border"]}; }}
    .st-key-theme_mode button [data-has-shortcut] {{ gap: 0 !important;
      align-items: center; justify-content: center; }}
    .st-key-theme_mode button [data-testid="stMarkdownContainer"] {{ position: absolute; }}
    /* Keep the action name available to screen readers, but show only its icon. */
    .st-key-theme_mode button p {{ position: absolute; width: 1px; height: 1px;
      padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }}
    [data-testid="stDateInputField"] {{ background: {theme["surface"]} !important;
                                         border: 1px solid {theme["border"]} !important; }}
    [data-testid="stDateInput"] [data-testid="stDateInputField"] * {{ color: {theme["text"]} !important; }}
    [data-testid="stDateInput"] input {{ background: {theme["surface"]} !important;
                                         color: {theme["text"]} !important;
                                         border-color: {theme["border"]} !important; }}
    [data-testid="stDateInput"] button {{ background: {theme["surface"]} !important;
                                           color: {theme["text"]} !important;
                                           border-color: {theme["border"]} !important; }}
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
      color: {theme["text"]} !important; opacity: 1 !important;
      font-size: var(--type-meta); line-height: {"1.5" if light_mode else "1.6"};
      font-weight: {"400" if light_mode else "600"}; max-width: 70ch;
    }}
    .js-plotly-plot text {{ font-variant-numeric: lining-nums tabular-nums; }}
    ::selection {{ background: #2962ff; color: #ffffff; }}
    input {{ caret-color: #2962ff; }}
    button:focus-visible, input:focus-visible, [role="switch"]:focus-visible {{
      outline: 2px solid #2962ff; outline-offset: 3px;
    }}
    .st-key-market_summary {{ margin: var(--space-tight) 0; }}
    .st-key-chart_toolbar {{ margin-top: var(--space-tight); width: calc((100% - 1.5rem) * .76); }}
    .st-key-chart_workspace {{ margin-top: var(--space-tight); }}
    .st-key-change_metrics [data-testid="stHorizontalBlock"] {{ gap: .75rem; }}
    .st-key-change_metrics [data-testid="stMetric"] {{
      min-height: 7rem; box-sizing: border-box;
    }}
    .st-key-chart_toolbar [data-testid="stHorizontalBlock"] {{ align-items: end; }}
    .st-key-chart_workspace > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
      gap: var(--space-section); }}
    @media (max-width: 1100px) {{
      .st-key-market_summary > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap; }}
      .st-key-market_summary > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"]
        > [data-testid="stColumn"] {{ flex: 1 1 100%; width: 100%; min-width: 100%; }}
      .st-key-chart_toolbar [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
      .st-key-chart_toolbar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        flex: 1 1 calc(50% - 1rem); min-width: calc(50% - 1rem); }}
      .st-key-chart_toolbar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) {{
        flex-basis: 100%; }}
    }}
    @media (max-width: 900px) {{
      .st-key-chart_toolbar {{ width: 100%; }}
      .st-key-chart_workspace > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap; gap: var(--space-group); }}
      .st-key-chart_workspace > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"]
        > [data-testid="stColumn"] {{ flex: 1 1 100%; min-width: 100%; }}
    }}
    @media (max-width: 700px) {{
      .block-container {{ padding: .85rem .8rem 1.5rem; }}
      .masthead {{ gap: .25rem; flex-direction: column; }}
      .market-snapshot {{ display: block; padding: 1.1rem 1.2rem; }}
      .snapshot-price {{ margin: .65rem 0 .4rem; }}
      .snapshot-head {{ flex-wrap: wrap; gap: .3rem 1rem; }}
      .st-key-change_metrics [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        flex: 1 1 calc(50% - 1rem); min-width: calc(50% - 1rem); }}
      div[data-testid="stMetric"] {{ padding: .7rem .85rem; }}
      :root {{ --type-metric: 1.375rem; }}
      .st-key-dashboard_header > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap; gap: var(--space-group); padding: .75rem 1rem; }}
      .st-key-dashboard_header > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"]
        > [data-testid="stColumn"]:first-child {{ flex: 1 1 100%; min-width: 100%; }}
      .st-key-dashboard_header > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"]
        > [data-testid="stColumn"]:nth-child(2) {{ flex: 1 1 calc(100% - 128px); min-width: 0; }}
      .st-key-dashboard_header > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"]
        > [data-testid="stColumn"]:last-child {{ flex: 0 1 112px; min-width: 112px; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

INSTRUMENTS = {
    "USD / Toman": {"symbol": "USD/IRT", "accent": "#2962ff", "decimals": 0},
    "Gold": {"symbol": "XAU/USD", "accent": "#d69e2e", "decimals": 2},
    "Silver": {"symbol": "XAG/USD", "accent": "#64748b", "decimals": 2},
    "Oil (Brent)": {"symbol": "BRENT/USD", "accent": "#089981", "decimals": 2},
    "Copper": {"symbol": "COPPER/USD", "accent": "#b87333", "decimals": 2},
    "Broad U.S. Dollar Index": {"symbol": "US_DOLLAR_BROAD", "accent": "#246df0", "decimals": 2},
    "Bitcoin": {"symbol": "BTC/USD", "accent": "#f7931a", "decimals": 0},
    "Ethereum": {"symbol": "ETH/USD", "accent": "#627eea", "decimals": 2},
    "BNB": {"symbol": "BNB/USD", "accent": "#f0b90b", "decimals": 2},
    "S&P 500": {"symbol": "SP500", "accent": "#7b61ff", "decimals": 2},
    "Fed Funds Target": {"symbol": "FED_FUNDS_TARGET", "accent": "#246df0", "decimals": 2},
    "2-Year Treasury Yield": {"symbol": "US_TREASURY_2Y", "accent": "#246df0", "decimals": 2},
    "10-Year Treasury Yield": {"symbol": "US_TREASURY_10Y", "accent": "#7b61ff", "decimals": 2},
    "30-Year Treasury Yield": {"symbol": "US_TREASURY_30Y", "accent": "#089981", "decimals": 2},
    "U.S. Inflation": {"symbol": "US_INFLATION", "accent": "#e76f51", "decimals": 2},
    "Iran Inflation": {"symbol": "IRAN_INFLATION", "accent": "#c05a8b", "decimals": 2},
    "TEDPIX": {"symbol": "TEDPIX", "accent": "#089981", "decimals": 0},
}
IRAN_INSTRUMENTS = ("USD / Toman", "Iran Inflation", "TEDPIX")
US_INSTRUMENTS = (
    "U.S. Inflation", "Fed Funds Target", "2-Year Treasury Yield", "10-Year Treasury Yield",
    "30-Year Treasury Yield", "S&P 500", "Broad U.S. Dollar Index"
)
CRYPTO_INSTRUMENTS = ("Bitcoin", "Ethereum", "BNB")
COMMODITY_INSTRUMENTS = ("Gold", "Silver", "Oil (Brent)", "Copper")
RANGES = {"1M": 31, "3M": 92, "1Y": 366, "5Y": 1827, "All": None}


@st.cache_data(ttl=900)
def read_prices(symbol: str) -> pd.DataFrame:
    return db.load_prices(symbol)


@st.cache_resource
def initialize_database() -> None:
    """Run SQLite schema and compatibility maintenance once per app process."""
    db.initialize()


def format_price(value: float, symbol: str, decimals: int) -> str:
    sign = "-" if value < 0 else ""
    amount = abs(value)
    if symbol == "USD/IRT":
        return f"{sign}{amount:,.0f} T"
    if symbol == "BRENT/USD":
        return f"{sign}${amount:,.{decimals}f} / bbl"
    if symbol == "COPPER/USD":
        return f"{sign}${amount:,.{decimals}f} / tonne"
    if symbol == "US_DOLLAR_BROAD":
        return f"{sign}{amount:,.{decimals}f} pts"
    if symbol == "TEDPIX":
        return f"{sign}{amount:,.0f} pts"
    if symbol == "SP500":
        return f"{sign}{amount:,.{decimals}f} pts"
    if symbol in {"US_INFLATION", "IRAN_INFLATION", "FED_FUNDS_TARGET"} or symbol.startswith("US_TREASURY_"):
        return f"{sign}{amount:,.{decimals}f}%"
    return f"{sign}${amount:,.{decimals}f}"


def build_chart(
    frame: pd.DataFrame,
    title: str,
    accent: str,
    decimals: int,
    logarithmic: bool,
    colors: dict[str, str],
    corridor: pd.DataFrame | None = None,
    comparison_frame: pd.DataFrame | None = None,
    comparison_title: str | None = None,
    step_line: bool = False,
    value_suffix: str = "",
    break_long_gaps: bool = False,
) -> go.Figure:
    first_date = pd.Timestamp(frame["market_date"].iloc[0])
    last_date = pd.Timestamp(frame["market_date"].iloc[-1])
    date_span = max(last_date - first_date, pd.Timedelta(days=1))
    # Match Plotly's comfortable autorange padding, then use that full view as
    # the hard zoom-out limit instead of pinning the data to the chart edges.
    date_padding = max(date_span * 0.05, pd.Timedelta(days=1))
    full_view_start = int((first_date - date_padding).timestamp() * 1000)
    full_view_end = int((last_date + date_padding).timestamp() * 1000)
    fig = go.Figure()
    # Historical crypto archives and Yahoo Finance are one continuous price
    # series.  Rendering every provider as its own trace creates an artificial
    # visual break at a provider handoff, even when consecutive closes agree.
    # The Shiller portion of the S&P 500 is the one intentional exception: it
    # is lower-frequency data and remains visibly dotted.
    source_groups = (
        list(frame.groupby("source", sort=False))
        if "source" in frame.columns and "shiller_monthly" in set(frame["source"])
        else [("combined", frame)]
    )
    for source, source_frame in source_groups:
        is_long_term = source == "shiller_monthly"
        dates, values = [], []
        previous_date = None
        for market_date, close in zip(source_frame["market_date"], source_frame["close"], strict=True):
            if break_long_gaps and previous_date is not None and (market_date - previous_date).days > 120:
                dates.append(market_date)
                values.append(None)
            dates.append(market_date)
            values.append(close)
            previous_date = market_date
        fig.add_trace(
            go.Scatter(
                x=dates, y=values, mode="lines", connectgaps=False,
                name="US equities long-term (monthly)" if is_long_term else title,
                line={
                    "color": accent,
                    "width": 2,
                    "dash": "dot" if is_long_term else "solid",
                    "shape": "hv" if step_line else "linear",
                },
                hovertemplate=f"%{{x|%b %-d, %Y}}<br><b>%{{y:,.{decimals}f}}{value_suffix}</b><extra></extra>",
            )
        )
    if comparison_frame is not None and not comparison_frame.empty:
        fig.add_trace(
            go.Scatter(
                x=comparison_frame["market_date"],
                y=comparison_frame["close"],
                mode="lines",
                name=comparison_title or "Comparison",
                line={"color": "#f59e0b", "width": 2},
                hovertemplate=f"%{{x|%b %-d, %Y}}<br><b>%{{y:,.{decimals}f}}×</b><extra></extra>",
            )
        )
    if corridor is not None and not corridor.empty:
        for column, name, width in (
            ("upper", "Upper corridor", 1.25),
            ("center", "Regression trend", 1.7),
            ("lower", "Lower corridor", 1.25),
        ):
            fig.add_trace(
                go.Scatter(
                    x=corridor["market_date"],
                    y=corridor[column],
                    mode="lines",
                    name=name,
                    line={"color": colors["channel"], "width": width},
                    hoverinfo="skip",
                )
            )
    fig.update_layout(
        height=510,
        margin={"l": 16, "r": 88, "t": 20, "b": 54},
        paper_bgcolor=colors["chart_background"],
        plot_bgcolor=colors["chart_background"],
        showlegend=comparison_frame is not None and not comparison_frame.empty,
        legend={"orientation": "h", "y": 1.05, "x": 0, "font": {"color": colors["muted"]}},
        hovermode="x unified",
        dragmode="zoom",
        font={"family": '"Source Sans", "Segoe UI", sans-serif', "color": colors["text"], "size": 14},
        xaxis={
            "showgrid": True,
            "gridcolor": colors["grid"],
            "zeroline": False,
            "showline": False,
            "rangeslider": {"visible": False},
            "automargin": True,
            "minallowed": full_view_start,
            "maxallowed": full_view_end,
            "autorangeoptions": {
                "minallowed": full_view_start,
                "maxallowed": full_view_end,
            },
        },
        yaxis={
            "type": "log" if logarithmic else "linear",
            "side": "right",
            "showgrid": True,
            "gridcolor": colors["grid"],
            "zeroline": False,
            "tickformat": f",.{decimals}f",
            "ticksuffix": value_suffix,
            "automargin": True,
            "separatethousands": True,
            "fixedrange": False,
            "dtick": "D2" if logarithmic else None,
            "nticks": 8,
        },
    )
    return fig


initialize_database()

# Restore a shareable detail view before Streamlit instantiates its widgets.
query = st.query_params
if "dashboard_view" in query:
    del st.query_params["dashboard_view"]
for key, allowed in {
    "dashboard_section": {"Iran", "U.S.", "Crypto", "Commodity"},
    "selected_range": set(RANGES),
}.items():
    value = query.get(key)
    if value in allowed and key not in st.session_state:
        st.session_state[key] = value
if "selected_range" not in st.session_state:
    st.session_state["selected_range"] = "All"

if st.session_state.get("dashboard_section") not in {"Iran", "U.S.", "Crypto", "Commodity"}:
    st.session_state["dashboard_section"] = "U.S."


def toggle_appearance() -> None:
    st.session_state["light_mode"] = not st.session_state["light_mode"]


with st.container(key="dashboard_header"):
    header_left, market_column, theme_column = st.columns([2.8, 3.8, 1], vertical_alignment="center")
with header_left:
    st.markdown(
        '<div class="masthead"><div class="brand">Market / Daily</div>'
        '<h1 class="market-title">Financial dashboard</h1></div>',
        unsafe_allow_html=True,
    )
with theme_column:
    st.button(
        "Switch to dark mode" if light_mode else "Switch to light mode",
        icon=":material/light_mode:" if light_mode else ":material/dark_mode:",
        key="theme_mode",
        help="Switch to dark mode" if light_mode else "Switch to light mode",
        on_click=toggle_appearance,
    )
with market_column:
    dashboard_section = st.radio(
        "Market",
        ("U.S.", "Iran", "Crypto", "Commodity"),
        horizontal=True,
        label_visibility="collapsed",
        key="dashboard_section",
    )
st.query_params["dashboard_section"] = dashboard_section
chart_options = {
    "Iran": IRAN_INSTRUMENTS,
    "U.S.": US_INSTRUMENTS,
    "Crypto": CRYPTO_INSTRUMENTS,
    "Commodity": COMMODITY_INSTRUMENTS,
}[dashboard_section]
chart_selector_key = {
    "Iran": "iran_chart", "U.S.": "us_chart", "Crypto": "crypto_chart",
    "Commodity": "commodity_chart",
}[dashboard_section]
if query.get("chart") in chart_options and chart_selector_key not in st.session_state:
    st.session_state[chart_selector_key] = query["chart"]
if st.session_state.get(chart_selector_key) not in chart_options:
    st.session_state[chart_selector_key] = chart_options[0]
selected_name = st.session_state[chart_selector_key]
comparison_options = ("None",) + tuple(name for name in chart_options if name != selected_name)
if query.get("compare") in comparison_options and "comparison_chart" not in st.session_state:
    st.session_state["comparison_chart"] = query["compare"]
if st.session_state.get("comparison_chart") not in comparison_options:
    st.session_state["comparison_chart"] = "None"
comparison_name = st.session_state["comparison_chart"]
instrument = INSTRUMENTS[selected_name]
symbol = instrument["symbol"]
frame = read_prices(symbol)
is_inflation = symbol in {"US_INFLATION", "IRAN_INFLATION"}
is_treasury_yield = symbol.startswith("US_TREASURY_")
is_fed_target = symbol == "FED_FUNDS_TARGET"
is_cumulative_interest = (
    (is_treasury_yield and st.session_state["treasury_cumulative"])
    or (is_fed_target and st.session_state["fed_target_cumulative"])
)
is_policy_rate = (is_fed_target or is_treasury_yield) and not is_cumulative_interest

if frame.empty:
    st.markdown("---")
    if symbol == "BRENT/USD":
        st.info("No Brent oil history is stored yet. Configure your FRED key and run the initial backfill.")
    elif symbol == "TEDPIX":
        st.info(
            "No TEDPIX history is stored yet. Run the initial backfill to import the free DataBourse chart history."
        )
    elif symbol == "SP500":
        st.info(
            "No S&P 500 history is stored yet. Add your free FRED key to .env, then run the initial backfill."
        )
    elif symbol == "US_INFLATION":
        st.info(
            "No U.S. inflation history is stored yet. Add your free FRED key to .env, then run the initial backfill."
        )
    elif symbol == "FED_FUNDS_TARGET":
        st.info("No Fed Funds Target history is stored yet. Refresh data to import the official FRED series.")
    elif is_treasury_yield:
        st.info("No Treasury yield history is stored yet. Add your FRED key and run the initial backfill.")
    elif symbol == "IRAN_INFLATION":
        st.info("No Iran inflation history is stored yet. Run the initial backfill to import SCI monthly CPI data.")
    elif symbol in {"XAU/USD", "XAG/USD", "BTC/USD", "ETH/USD", "BNB/USD"}:
        st.info(
            f"No {selected_name} history is stored yet. Add your free Alpha Vantage key to .env, then run the initial backfill."
        )
    else:
        st.info(
            f"No {selected_name} history is stored yet. Run the initial backfill, then return to this view."
        )
    st.code(".venv/bin/python -m financial_dashboard.sync --backfill", language="bash")
    st.stop()

# Keep the raw index levels available for normalized overlay comparisons while
# the primary view can still apply its own display transformation.
if is_cumulative_interest:
    frame = cumulative_interest_growth(frame)
if is_inflation or is_cumulative_interest:
    # The cumulative inflation view deliberately begins in 1960, matching the
    # long-horizon scope used elsewhere in the dashboard.
    frame = frame[frame["market_date"] >= pd.Timestamp("1960-01-01")].reset_index(drop=True)
    inflation_min_start = frame["market_date"].iloc[0].date()
    inflation_max_start = frame["market_date"].iloc[-30].date()
    inflation_channel_key = f"corridor_start_{symbol}"
    if inflation_channel_key not in st.session_state:
        st.session_state[inflation_channel_key] = inflation_min_start
    if not inflation_min_start <= st.session_state[inflation_channel_key] <= inflation_max_start:
        st.session_state[inflation_channel_key] = inflation_max_start
comparison_primary_frame = frame.copy()
if is_inflation or is_cumulative_interest:
    frame = rebased_price_level(comparison_primary_frame, st.session_state[inflation_channel_key])
else:
    comparison_primary_frame = frame.copy()

comparison_frame: pd.DataFrame | None = None
comparison_start = None
comparison_min_start = None
comparison_max_start = None
comparison_error = None
chart_primary_frame = frame
if comparison_name != "None":
    comparison_symbol = INSTRUMENTS[comparison_name]["symbol"]
    comparison_raw = read_prices(comparison_symbol)
    if comparison_symbol.startswith("US_TREASURY_") and st.session_state["treasury_cumulative"]:
        comparison_raw = cumulative_interest_growth(comparison_raw)
    if comparison_symbol == "FED_FUNDS_TARGET" and st.session_state["fed_target_cumulative"]:
        comparison_raw = cumulative_interest_growth(comparison_raw)
    if comparison_symbol in {"US_INFLATION", "IRAN_INFLATION"}:
        comparison_raw = comparison_raw[
            comparison_raw["market_date"] >= pd.Timestamp("1960-01-01")
        ].reset_index(drop=True)
    if comparison_raw.empty:
        comparison_error = f"No stored history is available for {comparison_name}."
    else:
        comparison_min_start = max(
            comparison_primary_frame["market_date"].iloc[0].date(),
            comparison_raw["market_date"].iloc[0].date(),
        )
        comparison_max_start = min(
            comparison_primary_frame["market_date"].iloc[-1].date(),
            comparison_raw["market_date"].iloc[-1].date(),
        )
        if comparison_min_start > comparison_max_start:
            comparison_error = f"{selected_name} and {comparison_name} have no overlapping dates."
        else:
            if "comparison_start" not in st.session_state:
                st.session_state["comparison_start"] = comparison_min_start
            if not comparison_min_start <= st.session_state["comparison_start"] <= comparison_max_start:
                st.session_state["comparison_start"] = comparison_min_start
            comparison_start = st.session_state["comparison_start"]
            chart_primary_frame = rebased_price_level(comparison_primary_frame, comparison_start)
            comparison_frame = rebased_price_level(comparison_raw, comparison_start)

is_cumulative_inflation = is_inflation

latest = frame.iloc[-1]
previous = frame.iloc[-2] if len(frame) > 1 else latest
change = float(latest["close"] - previous["close"])
change_pct = (change / float(previous["close"]) * 100) if previous["close"] else 0.0
direction = "+" if change >= 0 else ""

if is_cumulative_inflation:
    cumulative_inflation = (float(latest["close"]) - 1) * 100
    sign = "+" if cumulative_inflation >= 0 else ""
    price_value = f"{float(latest['close']):,.2f}×"
    price_detail = (
        f"{sign}{cumulative_inflation:.2f}% cumulative inflation since "
        f"{frame['market_date'].iloc[0]:%b %Y} · {latest['market_date']:%b %Y}"
    )
elif is_inflation:
    price_value = format_price(float(latest["close"]), symbol, instrument["decimals"])
    price_detail = f"{direction}{change:.2f} percentage points from the prior month · {latest['market_date']:%b %Y}"
elif is_cumulative_interest:
    price_value = f"{float(latest['close']):,.2f}×"
    price_detail = (
        f"{(float(latest['close']) - 1) * 100:+.2f}% estimated interest growth since "
        f"{frame['market_date'].iloc[0]:%b %d, %Y} · {latest['market_date']:%b %d, %Y}"
    )
elif is_treasury_yield:
    price_value = format_price(float(latest["close"]), symbol, instrument["decimals"])
    price_detail = f"{change:+.2f} percentage points · {latest['market_date']:%b %d, %Y}"
else:
    price_value = format_price(float(latest["close"]), symbol, instrument["decimals"])
    price_detail = (
        f"{direction}{format_price(change, symbol, instrument['decimals'])} · "
        f"{direction}{change_pct:.2f}% · {latest['market_date']:%b %d, %Y}"
    )
with st.container(key="market_summary"):
    quote_column, metrics_column = st.columns([2.1, 5.4], vertical_alignment="center")
with quote_column:
    st.markdown(
        f'<section class="market-snapshot"><div class="snapshot-head"><span class="snapshot-name">{selected_name}</span>'
        f'<span>{"Monthly average" if symbol == "COPPER/USD" else "Estimated growth" if is_cumulative_interest else "Daily yield" if is_treasury_yield else "Daily close"}</span></div>'
        f'<div class="snapshot-price">{price_value}</div><div class="snapshot-detail">{price_detail}</div></section>',
        unsafe_allow_html=True,
    )

daily_absolute, daily_pct = period_change(frame, None)
weekly_absolute, weekly_pct = period_change(frame, 7)
monthly_absolute, monthly_pct = period_change(frame, 30)
yearly_absolute, yearly_pct = period_change(frame, 365)

if is_inflation:
    # Use the stored CPI history so the channel's rebasing start cannot change
    # the latest inflation rates. Consecutive monthly observations avoid
    # skipping a month when the preceding month has fewer than 31 days.
    _, monthly_pct = period_change(comparison_primary_frame, None)
    latest_cpi_date = comparison_primary_frame["market_date"].iloc[-1]
    annual_days = (latest_cpi_date - (latest_cpi_date - pd.DateOffset(years=1))).days
    _, yearly_pct = period_change(comparison_primary_frame, annual_days)
    metric_entries = [("Monthly change", None, monthly_pct), ("Yearly change", None, yearly_pct)]
elif symbol == "COPPER/USD":
    metric_entries = []
    for label, months in (("Monthly change", 1), ("Quarterly change", 3), ("Yearly change", 12), ("5-year change", 60)):
        target = frame["market_date"].iloc[-1].to_period("M") - months
        prior = frame[frame["market_date"].dt.to_period("M") <= target]
        if prior.empty:
            metric_entries.append((label, None, None))
        else:
            base = float(prior.iloc[-1]["close"])
            absolute = float(latest["close"]) - base
            metric_entries.append((label, absolute, absolute / base * 100))
else:
    metric_entries = list(zip(
        ("Daily change", "Weekly change", "Monthly change", "Yearly change"),
        (daily_absolute, weekly_absolute, monthly_absolute, yearly_absolute),
        (daily_pct, weekly_pct, monthly_pct, yearly_pct),
        strict=True,
    ))
    if is_cumulative_interest:
        metric_entries = [(label, None, percentage) for label, _, percentage in metric_entries]
if is_inflation:
    for years in (5, 10):
        result = calendar_year_change(comparison_primary_frame, years)
        percentage = result[1] if result is not None else None
        metric_entries.append((f"{years}-year change", None, percentage))

with metrics_column:
    with st.container(key="change_metrics"):
        columns_per_row = 4
        for row_start in range(0, len(metric_entries), columns_per_row):
            metric_cols = st.columns(columns_per_row)
            for column, (label, absolute, percentage) in zip(
                metric_cols, metric_entries[row_start:row_start + columns_per_row], strict=True
            ):
                if percentage is None:
                    column.metric(label, "N/A", help="Not enough stored history for this period.")
                    continue
                delta = None
                if absolute is not None:
                    absolute_sign = "+" if absolute >= 0 else ""
                    delta = f"{absolute_sign}{format_price(absolute, symbol, instrument['decimals'])}"
                column.metric(
                    label,
                    f"{absolute * 100:+.0f} bp" if is_treasury_yield and not is_cumulative_interest
                    else f"{percentage:+.2f}%",
                    delta=None if is_treasury_yield or is_cumulative_interest else delta,
                    help="Total percentage change over the period, not an annualized return."
                    if label in {"5-year change", "10-year change"}
                    else "Illustrative compounded growth, not an investment return." if is_cumulative_interest
                    else "Yield change in basis points (100 bp = 1 percentage point)." if is_treasury_yield else None,
                )

with st.container(key="chart_toolbar"):
    chart_selector_column, comparison_selector_column, range_column = st.columns(
        [1.5, 1.5, 3.3], vertical_alignment="bottom"
    )
with chart_selector_column:
    st.selectbox("Chart", chart_options, key=chart_selector_key)
with comparison_selector_column:
    st.selectbox("Compare with", comparison_options, key="comparison_chart")
with range_column:
    selected_range = st.radio(
        "Range", list(RANGES), horizontal=True, key="selected_range"
    )

st.query_params.update(
    {
        "chart": st.session_state[chart_selector_key],
        "compare": st.session_state["comparison_chart"],
        "selected_range": selected_range,
    }
)

with st.container(key="chart_workspace"):
    chart_column, details_column = st.columns([5.7, 1.8], vertical_alignment="top")
logarithmic = st.session_state["logarithmic"]
corridor_enabled = st.session_state["corridor_enabled"]
corridor_95 = st.session_state["corridor_95"]
with details_column:
    if is_fed_target:
        st.toggle(
            "Cumulative growth", key="fed_target_cumulative",
            help="On: illustrative growth starting at 1× using the prior policy rate. Off: policy target in percent. Not an actual investment return.",
        )
    if is_treasury_yield:
        st.toggle(
            "Cumulative growth", key="treasury_cumulative",
            help="On: estimated compounded interest starting at 1×. Off: published Treasury yield in percent.",
        )
    if is_inflation or is_cumulative_interest:
        corridor_start = st.slider(
            "Channel start",
            min_value=inflation_min_start,
            max_value=inflation_max_start,
            key=inflation_channel_key,
            help="This observation is rebased to 1.00× and is also the regression start.",
        )
    elif corridor_enabled and not is_policy_rate:
        corridor_key = f"corridor_start_{symbol}"
        corridor_min_start = frame["market_date"].iloc[0].date()
        corridor_max_start = frame["market_date"].iloc[-30].date()
        if corridor_key not in st.session_state:
            st.session_state[corridor_key] = corridor_min_start
        if not corridor_min_start <= st.session_state[corridor_key] <= corridor_max_start:
            st.session_state[corridor_key] = corridor_min_start
        corridor_start = st.slider(
            "Channel start",
            min_value=corridor_min_start,
            max_value=corridor_max_start,
            key=corridor_key,
        )
    if comparison_start is not None:
        st.slider(
            "Compare start",
            min_value=comparison_min_start,
            max_value=comparison_max_start,
            key="comparison_start",
            help="Both chart lines are rebased to 1.00× at this shared start date.",
        )

days = RANGES[selected_range]
visible = chart_primary_frame
visible_comparison = comparison_frame
if days is not None:
    cutoff = pd.Timestamp(datetime.now(timezone.utc).date() - timedelta(days=days))
    visible = chart_primary_frame[chart_primary_frame["market_date"] >= cutoff]
    if comparison_frame is not None:
        visible_comparison = comparison_frame[comparison_frame["market_date"] >= cutoff]
if visible.empty:
    # Monthly sources can have no observation inside a short calendar range;
    # keep their latest point visible instead of rendering an empty chart.
    visible = chart_primary_frame.tail(1)

# Keep every stored observation for metrics and regression.  Only the plotted
# traces are reduced, so long ranges remain responsive without altering any
# analytical result.
display_visible = downsample_for_chart(visible)
display_visible_comparison = (
    downsample_for_chart(visible_comparison) if visible_comparison is not None else None
)

corridor = None
annualized_regression_change = None
regression_frame = chart_primary_frame
# Long-range daily series should not give the most recent period thousands of
# times more weight than their early history.  Fit their All-range trend from
# monthly closes, then project that trend back onto the displayed dates.
if symbol in {"SP500", "BTC/USD", "ETH/USD", "BNB/USD"} and selected_range == "All":
    regression_frame = (
        frame.set_index("market_date").resample("ME").last().dropna(subset=["close"]).reset_index()
    )
if corridor_enabled and not is_policy_rate:
    try:
        corridor = logarithmic_regression_channel(
            regression_frame,
            corridor_start,
            coverage=0.95 if corridor_95 else 1.0,
            output_dates=display_visible["market_date"],
        )
        annualized_regression_change = annualized_logarithmic_regression_change(
            regression_frame, corridor_start
        )
    except ValueError as error:
        st.warning(str(error))
if comparison_error:
    st.warning(comparison_error)

chart = build_chart(
    display_visible,
    selected_name,
    instrument["accent"],
    2 if comparison_frame is not None else instrument["decimals"],
    logarithmic and not is_policy_rate,
    theme,
    corridor,
    display_visible_comparison,
    comparison_name if comparison_frame is not None else None,
    step_line=is_fed_target and not is_cumulative_interest,
    value_suffix=("×" if is_cumulative_interest or comparison_frame is not None else "%")
    if is_treasury_yield or is_fed_target else "",
    break_long_gaps=is_treasury_yield,
)

if annualized_regression_change is not None:
    trend_sign = "+" if annualized_regression_change >= 0 else ""
    with details_column:
        st.metric(
            "Trend / year",
            f"{trend_sign}{annualized_regression_change:.2f}% / year",
            help="Annualized percentage change implied by the logarithmic regression trend.",
        )
with details_column:
    st.toggle(
        "Log scale",
        key="logarithmic",
        help="Use equal vertical space for equal percentage moves",
        disabled=is_policy_rate,
    )
    st.toggle(
        "Regression corridor",
        key="corridor_enabled",
        help="Fit a log-price trend from the selected start date and enclose all daily closes.",
        disabled=is_policy_rate,
    )
    st.toggle(
        "95% corridor",
        key="corridor_95",
        help="Ignore the 5% most extreme logarithmic residuals for a tighter channel.",
        disabled=not corridor_enabled or is_policy_rate,
    )
with chart_column:
    st.plotly_chart(
        chart,
        use_container_width=True,
        theme=None,
        config={"displayModeBar": False, "scrollZoom": False, "responsive": True},
    )
    st.caption("Drag to zoom · Double-click to reset")

freshness_state, freshness = freshness_status(latest["market_date"], latest["source"])
source_label = latest["source"].replace("_", " ").title()
if symbol == "SP500":
    if "spx_csv" in set(frame["source"]):
        source_label += " · Daily history: local SPX CSV (1960–2016)"
    elif "shiller_monthly" in set(frame["source"]):
        source_label += " · Long-term dotted segment: Shiller-derived monthly US equities"
elif symbol == "BRENT/USD":
    source_label = "U.S. Energy Information Administration via FRED · Brent crude spot price · USD per barrel"
elif symbol == "COPPER/USD":
    source_label = "World Bank Pink Sheet · Monthly copper averages · USD per metric ton"
elif symbol == "US_DOLLAR_BROAD":
    source_label = "Federal Reserve via FRED · Broad trade-weighted U.S. dollar index · January 2006 = 100 · Not ICE DXY"
elif symbol == "FED_FUNDS_TARGET":
    source_label = (
        "Federal Reserve via FRED · Single target (DFEDTAR) before Dec 16, 2008; "
        "target range upper limit (DFEDTARU) thereafter · Pre-1994 targets are reconstructed research data"
    )
    if is_cumulative_interest:
        source_label += " · Illustrative growth: prior annual policy rate compounded over elapsed days / 365.25; not an investment return"
elif is_treasury_yield:
    source_label = (
        "FRED / Federal Reserve H.15 · Estimated interest-growth index, not bond total return"
        " · Prior annual yield compounded over elapsed days (365.25-day year)"
        if is_cumulative_interest else "FRED / Federal Reserve H.15 · Daily constant-maturity yield"
    )
    if symbol == "US_TREASURY_30Y":
        source_label += (
            " · Starts after the 2002–2006 publication gap; missing yields are not estimated"
            if is_cumulative_interest else " · No published 30-year yields Feb 2002–Feb 2006 (gap preserved)"
        )
elif symbol == "IRAN_INFLATION":
    source_label = "Statistical Center of Iran (SCI)"
elif symbol == "ETH/USD" and "gemini_eth_usd_archive" in set(frame["source"]):
    source_label += " · Early history: Gemini ETH/USD archive"
elif symbol == "BNB/USD" and "binance_bnb_usdt_archive" in set(frame["source"]):
    source_label += " · Early history: Binance BNB/USDT (USDT≈USD)"
elif symbol == "BTC/USD" and "blockchain_market_price" in set(frame["source"]):
    source_label += " · Early history: Blockchain.com market-price index"
st.markdown(
    f'<div class="source-line">Source: {source_label} &nbsp;·&nbsp; {freshness} &nbsp;·&nbsp; Informational data, not financial advice.</div>',
    unsafe_allow_html=True,
)

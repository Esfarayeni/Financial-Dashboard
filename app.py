from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from financial_dashboard import db
from financial_dashboard.analytics import (
    annualized_logarithmic_regression_change,
    drawdown_from_peak,
    derived_series,
    inflation_adjusted_series,
    logarithmic_regression_channel,
    logarithmic_regression_r_squared,
    monthly_log_return_correlation,
    period_change,
    rebased_price_level,
    rolling_volatility,
)
from financial_dashboard.status import freshness_status
from financial_dashboard.sync import synchronize


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

light_mode = st.session_state["light_mode"]
theme = {
    "background": "#ffffff" if light_mode else "#090b10",
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
    header[data-testid="stHeader"], [data-testid="stDecoration"] {{ display: none !important; }}
    [data-testid="stToolbar"], footer {{ visibility: hidden; }}
    [data-testid="stAppViewContainer"], .stApp {{
      background: {theme["background"]}; color: {theme["text"]};
    }}
    [data-testid="stAppViewContainer"] > .main {{ padding-top: 0 !important; }}
    .block-container {{ max-width: 1440px; padding: 1.1rem 2rem 2rem; }}
    .brand {{ font: 700 0.78rem/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
             letter-spacing: .16em; color: {theme["muted"]}; text-transform: uppercase; }}
    .market-title {{ font-size: 1.55rem; font-weight: 650; letter-spacing: -.025em;
                     margin: .15rem 0 0; color: {theme["text"]}; }}
    .price {{ font-size: clamp(2rem, 4vw, 3.8rem); line-height: 1; font-weight: 640;
             letter-spacing: -.055em; margin: .65rem 0 .35rem; color: {theme["text"]}; }}
    .muted {{ color: {theme["muted"]}; font-size: .84rem; }}
    .stPlotlyChart {{ position: relative; z-index: 0; margin-bottom: 1rem; }}
    .source-line {{ position: relative; z-index: 1; display: block; margin-top: .35rem;
                    padding: .8rem 0 0; min-height: 2.25rem;
                    border-top: 1px solid {theme["border"]}; background: {theme["background"]};
                    color: {theme["muted"]}; font-size: .8rem; }}
    div[data-testid="stMetric"] {{ background: {theme["surface"]}; border: 1px solid {theme["border"]};
                                  border-radius: 10px; padding: .85rem 1rem; }}
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
      color: {theme["muted"]} !important; opacity: 1 !important;
    }}
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{
      color: {theme["text"]} !important; font-size: 1.15rem;
    }}
    div[role="radiogroup"] {{ gap: .25rem; }}
    div[role="radiogroup"] label {{ background: {theme["surface"]}; border: 1px solid {theme["border"]};
                                    border-radius: 8px; padding: .42rem .72rem; }}
    div[role="radiogroup"] label p, .stButton button, [data-testid="stWidgetLabel"] p {{
      color: {theme["text"]} !important;
    }}
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
      background: {"#f1f1f1" if light_mode else "#20242c"} !important;
      border-color: {"#dedede" if light_mode else "#343a45"} !important;
      border-radius: 8px !important;
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
    .stButton button {{ border-radius: 8px; border-color: {theme["border"]};
                        background: {theme["surface_alt"]}; }}
    [data-testid="stDateInputField"] {{ background: {theme["surface"]} !important;
                                         border: 1px solid {theme["border"]} !important; }}
    [data-testid="stDateInput"] [data-testid="stDateInputField"] * {{ color: {theme["text"]} !important; }}
    [data-testid="stDateInput"] input {{ background: {theme["surface"]} !important;
                                         color: {theme["text"]} !important;
                                         border-color: {theme["border"]} !important; }}
    [data-testid="stDateInput"] button {{ background: {theme["surface"]} !important;
                                           color: {theme["text"]} !important;
                                           border-color: {theme["border"]} !important; }}
    [data-testid="stCaptionContainer"] {{ color: {theme["muted"]}; }}
    @media (max-width: 700px) {{
      .block-container {{ padding: .85rem .8rem 1.5rem; }}
      .price {{ font-size: 2.35rem; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

INSTRUMENTS = {
    "USD / Toman": {"symbol": "USD/IRT", "accent": "#2962ff", "decimals": 0},
    "Gold": {"symbol": "XAU/USD", "accent": "#d69e2e", "decimals": 2},
    "Silver": {"symbol": "XAG/USD", "accent": "#64748b", "decimals": 2},
    "Bitcoin": {"symbol": "BTC/USD", "accent": "#f7931a", "decimals": 0},
    "S&P 500": {"symbol": "SP500", "accent": "#7b61ff", "decimals": 2},
    "U.S. Inflation": {"symbol": "US_INFLATION", "accent": "#e76f51", "decimals": 2},
    "Iran Inflation": {"symbol": "IRAN_INFLATION", "accent": "#c05a8b", "decimals": 2},
    "TEDPIX": {"symbol": "TEDPIX", "accent": "#089981", "decimals": 0},
}
IRAN_INSTRUMENTS = ("USD / Toman", "Iran Inflation", "TEDPIX")
US_INSTRUMENTS = ("U.S. Inflation", "S&P 500", "Gold", "Silver", "Bitcoin")
RANGES = {"1M": 31, "3M": 92, "1Y": 366, "5Y": 1827, "All": None}


@st.cache_data(ttl=900)
def read_prices(symbol: str) -> pd.DataFrame:
    return db.load_prices(symbol)


def format_price(value: float, symbol: str, decimals: int) -> str:
    sign = "-" if value < 0 else ""
    amount = abs(value)
    if symbol == "USD/IRT":
        return f"{sign}{amount:,.0f} T"
    if symbol == "TEDPIX":
        return f"{sign}{amount:,.0f} pts"
    if symbol == "SP500":
        return f"{sign}{amount:,.{decimals}f} pts"
    if symbol in {"US_INFLATION", "IRAN_INFLATION"}:
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
    source_groups = (
        list(frame.groupby("source", sort=False)) if "source" in frame.columns else [("derived", frame)]
    )
    for source, source_frame in source_groups:
        is_long_term = source == "shiller_monthly"
        fig.add_trace(
            go.Scatter(
                x=source_frame["market_date"], y=source_frame["close"], mode="lines",
                name="US equities long-term (monthly)" if is_long_term else title,
                line={"color": accent, "width": 2, "dash": "dot" if is_long_term else "solid"},
                hovertemplate=f"%{{x|%b %-d, %Y}}<br><b>%{{y:,.{decimals}f}}</b><extra></extra>",
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
        paper_bgcolor=colors["background"],
        plot_bgcolor=colors["background"],
        showlegend=comparison_frame is not None and not comparison_frame.empty,
        legend={"orientation": "h", "y": 1.05, "x": 0, "font": {"color": colors["muted"]}},
        hovermode="x unified",
        dragmode="zoom",
        font={"family": "Inter, ui-sans-serif, system-ui", "color": colors["muted"], "size": 12},
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
            "automargin": True,
            "separatethousands": True,
            "fixedrange": False,
        },
    )
    return fig


db.initialize()

# Restore a shareable detail view before Streamlit instantiates its widgets.
query = st.query_params
for key, allowed in {
    "dashboard_section": {"Iran", "U.S."},
    "selected_range": set(RANGES),
    "dashboard_view": {"Detail", "Overview"},
}.items():
    value = query.get(key)
    if value in allowed and key not in st.session_state:
        st.session_state[key] = value
if "selected_range" not in st.session_state:
    st.session_state["selected_range"] = "All"

header_left, theme_column, header_right = st.columns([5, 1.05, 1.35], vertical_alignment="center")
with header_left:
    st.markdown('<div class="brand">Market / Daily</div>', unsafe_allow_html=True)
    st.markdown('<div class="market-title">Financial dashboard</div>', unsafe_allow_html=True)
with theme_column:
    st.toggle(
        "☀ Light",
        key="light_mode",
        help="Switch between light and dark appearance",
    )
with header_right:
    if st.button("↻  Refresh data", use_container_width=True, help="Fetch the latest completed daily values"):
        with st.spinner("Updating sources…"):
            st.session_state["sync_results"] = synchronize("daily")
            read_prices.clear()

if "dashboard_view" not in st.session_state:
    st.session_state["dashboard_view"] = "Detail"
dashboard_view = st.selectbox(
    "Workspace", ("Detail", "Overview"), key="dashboard_view", label_visibility="collapsed"
)
st.query_params["dashboard_view"] = dashboard_view

if "sync_results" in st.session_state:
    results = st.session_state["sync_results"]
    failures = [r for r in results if r["status"] == "failed"]
    if failures:
        st.warning("Some sources could not be updated. Existing chart data was preserved.")
    else:
        st.toast("Market data refreshed")
    with st.expander("Latest refresh results"):
        st.dataframe(
            pd.DataFrame(results).rename(columns={"source": "Source", "status": "Status", "rows": "Rows", "error": "Message"}),
            use_container_width=True,
            hide_index=True,
        )

if dashboard_view == "Overview":
    st.markdown("### Market overview")
    st.caption("Latest locally stored observations. Select an instrument to open its detailed chart.")
    for country, names in (("Iran", IRAN_INSTRUMENTS), ("U.S.", US_INSTRUMENTS)):
        st.markdown(f"#### {country}")
        columns = st.columns(min(3, len(names)))
        for column, name in zip(columns * ((len(names) + len(columns) - 1) // len(columns)), names):
            instrument = INSTRUMENTS[name]
            overview_frame = read_prices(instrument["symbol"])
            with column:
                if overview_frame.empty:
                    st.metric(name, "No data")
                else:
                    latest_overview = overview_frame.iloc[-1]
                    _, one_day = period_change(overview_frame, 1)
                    _, one_month = period_change(overview_frame, 30)
                    _, one_year = period_change(overview_frame, 365)
                    st.metric(
                        name,
                        format_price(float(latest_overview["close"]), instrument["symbol"], instrument["decimals"]),
                        delta=f"1D {one_day:+.1f}% · 1M {one_month:+.1f}% · 1Y {one_year:+.1f}%",
                    )
                    sparkline = go.Figure(go.Scatter(
                        x=overview_frame.tail(90)["market_date"], y=overview_frame.tail(90)["close"],
                        mode="lines", line={"color": instrument["accent"], "width": 1.5}, hoverinfo="skip"
                    ))
                    sparkline.update_layout(height=80, margin={"l": 0, "r": 0, "t": 0, "b": 0},
                                            paper_bgcolor=theme["background"], plot_bgcolor=theme["background"],
                                            xaxis={"visible": False}, yaxis={"visible": False})
                    st.plotly_chart(sparkline, use_container_width=True, theme=None, config={"displayModeBar": False})
                    if st.button(f"Open {name}", key=f"open_overview_{name}"):
                        st.session_state["dashboard_section"] = country
                        st.session_state["iran_chart" if country == "Iran" else "us_chart"] = name
                        st.session_state["dashboard_view"] = "Detail"
                        st.rerun()
    st.stop()

if st.session_state.get("dashboard_section") not in {"Iran", "U.S."}:
    st.session_state["dashboard_section"] = "Iran"

dashboard_section = st.radio(
    "Country",
    ("Iran", "U.S."),
    horizontal=True,
    label_visibility="collapsed",
    key="dashboard_section",
)
st.query_params["dashboard_section"] = dashboard_section
chart_options = IRAN_INSTRUMENTS if dashboard_section == "Iran" else US_INSTRUMENTS
chart_selector_key = "iran_chart" if dashboard_section == "Iran" else "us_chart"
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

if frame.empty:
    st.markdown("---")
    if symbol == "TEDPIX":
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
    elif symbol == "IRAN_INFLATION":
        st.info("No Iran inflation history is stored yet. Run the initial backfill to import SCI monthly CPI data.")
    elif symbol in {"XAU/USD", "XAG/USD"}:
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
if is_inflation:
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
if is_inflation:
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

st.markdown(
    f'<div class="price">{float(latest["close"]):,.2f}×</div>'
    if is_cumulative_inflation
    else f'<div class="price">{format_price(float(latest["close"]), symbol, instrument["decimals"])}</div>',
    unsafe_allow_html=True,
)
if is_cumulative_inflation:
    cumulative_inflation = (float(latest["close"]) - 1) * 100
    sign = "+" if cumulative_inflation >= 0 else ""
    st.markdown(
        f'<div class="muted">{sign}{cumulative_inflation:.2f}% cumulative inflation '
        f'since {frame["market_date"].iloc[0]:%b %Y} &nbsp;·&nbsp; {latest["market_date"]:%b %Y}</div>',
        unsafe_allow_html=True,
    )
elif is_inflation:
    st.markdown(
        f'<div class="muted">{direction}{change:.2f} percentage points from the prior month '
        f'&nbsp;·&nbsp; {latest["market_date"]:%b %Y}</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="muted">{direction}{format_price(change, symbol, instrument["decimals"])} &nbsp; '
        f'{direction}{change_pct:.2f}% &nbsp;·&nbsp; {latest["market_date"]:%b %d, %Y}</div>',
        unsafe_allow_html=True,
    )

daily_absolute, daily_pct = period_change(frame, None)
weekly_absolute, weekly_pct = period_change(frame, 7)
monthly_absolute, monthly_pct = period_change(frame, 30)
yearly_absolute, yearly_pct = period_change(frame, 365)

metric_cols = st.columns(4)
if is_inflation:
    monthly_change, monthly_pct = period_change(frame, 31)
    yearly_change, yearly_pct = period_change(frame, 366)
    cumulative_pct = (float(latest["close"]) - 1) * 100
    metric_cols[0].metric("Since start", f"{cumulative_pct:+.2f}%")
    metric_cols[1].metric("Purchasing power", f"{100 / float(latest['close']):.2f}%")
    metric_cols[2].metric("1 month CPI", f"{monthly_pct:+.2f}%")
    metric_cols[3].metric("1 year CPI", f"{yearly_pct:+.2f}%")
else:
    for column, label, absolute, percentage in zip(
        metric_cols,
        ("Daily change", "Weekly change", "Monthly change", "Yearly change"),
        (daily_absolute, weekly_absolute, monthly_absolute, yearly_absolute),
        (daily_pct, weekly_pct, monthly_pct, yearly_pct),
        strict=True,
    ):
        sign = "+" if percentage >= 0 else ""
        absolute_sign = "+" if absolute >= 0 else ""
        column.metric(
            label,
            f"{sign}{percentage:.2f}%",
            delta=f"{absolute_sign}{format_price(absolute, symbol, instrument['decimals'])}",
        )

chart_selector_column, comparison_selector_column, analysis_column, range_column, controls_right = st.columns(
    [1.45, 1.45, 1.45, 3.0, 1.1], vertical_alignment="center"
)
with chart_selector_column:
    st.selectbox("Chart", chart_options, key=chart_selector_key, label_visibility="collapsed")
with comparison_selector_column:
    st.selectbox("Compare with", comparison_options, key="comparison_chart", label_visibility="collapsed")
with analysis_column:
    analysis_mode = st.selectbox(
        "View", ("Price", "Drawdown", "30D volatility", "Inflation-adjusted"),
        label_visibility="collapsed", key="analysis_mode"
    )
with range_column:
    selected_range = st.radio(
        "Range", list(RANGES), horizontal=True, label_visibility="collapsed", key="selected_range"
    )
with controls_right:
    st.caption("Drag to zoom · Double-click to reset")

st.query_params.update(
    {
        "chart": st.session_state[chart_selector_key],
        "compare": st.session_state["comparison_chart"],
        "selected_range": selected_range,
    }
)

chart_column, details_column = st.columns([6.15, 1.45], vertical_alignment="top")
logarithmic = st.session_state["logarithmic"]
corridor_enabled = st.session_state["corridor_enabled"]
corridor_95 = st.session_state["corridor_95"]
with details_column:
    if is_inflation:
        corridor_start = st.slider(
            "Channel start",
            min_value=inflation_min_start,
            max_value=inflation_max_start,
            key=inflation_channel_key,
            help="This CPI observation is rebased to 1.00× and is also the regression start.",
        )
    elif corridor_enabled:
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

display_frame = chart_primary_frame.copy()
display_comparison = comparison_frame
display_title = selected_name
display_accent = instrument["accent"]
display_decimals = 2 if comparison_frame is not None else instrument["decimals"]
display_logarithmic = logarithmic
if analysis_mode == "Drawdown":
    display_frame = drawdown_from_peak(comparison_primary_frame)[["market_date", "drawdown"]].rename(
        columns={"drawdown": "close"}
    )
    display_title = f"{selected_name} drawdown"
    display_accent = "#e76f51"
    display_decimals = 2
    display_logarithmic = False
    display_comparison = None
elif analysis_mode == "30D volatility":
    display_frame = rolling_volatility(comparison_primary_frame)[["market_date", "volatility"]].rename(
        columns={"volatility": "close"}
    )
    display_title = f"{selected_name} volatility"
    display_accent = "#7b61ff"
    display_decimals = 2
    display_logarithmic = False
    display_comparison = None
elif analysis_mode == "Inflation-adjusted":
    cpi_symbol = "IRAN_INFLATION" if dashboard_section == "Iran" else "US_INFLATION"
    cpi_frame = read_prices(cpi_symbol)
    display_frame = inflation_adjusted_series(comparison_primary_frame, cpi_frame)
    display_title = f"{selected_name} in constant purchasing power"
    display_comparison = None
    display_logarithmic = logarithmic
    if display_frame.empty:
        st.info("No matching CPI observations are available for this inflation-adjusted view.")
        display_frame = chart_primary_frame.copy()
        display_title = selected_name

days = RANGES[selected_range]
visible = display_frame
visible_comparison = display_comparison
if days is not None:
    cutoff = pd.Timestamp(datetime.now(timezone.utc).date() - timedelta(days=days))
    visible = chart_primary_frame[chart_primary_frame["market_date"] >= cutoff]
    if display_comparison is not None:
        visible_comparison = display_comparison[display_comparison["market_date"] >= cutoff]
if visible.empty:
    # Monthly sources can have no observation inside a short calendar range;
    # keep their latest point visible instead of rendering an empty chart.
    visible = chart_primary_frame.tail(1)

corridor = None
annualized_regression_change = None
regression_frame = display_frame
# A century of monthly history plus a recent daily segment must not give the
# recent decade thousands of times more weight in the long-term trend fit.
if symbol == "SP500" and selected_range == "All" and analysis_mode == "Price":
    regression_frame = (
        frame.set_index("market_date").resample("ME").last().dropna(subset=["close"]).reset_index()
    )
if corridor_enabled and analysis_mode == "Price":
    try:
        corridor = logarithmic_regression_channel(
            regression_frame, corridor_start, coverage=0.95 if corridor_95 else 1.0
        )
        annualized_regression_change = annualized_logarithmic_regression_change(
            regression_frame, corridor_start
        )
        corridor = corridor[corridor["market_date"].isin(visible["market_date"])]
    except ValueError as error:
        st.warning(str(error))
if comparison_error:
    st.warning(comparison_error)

chart = build_chart(
    visible,
    display_title,
    display_accent,
    display_decimals,
    display_logarithmic,
    theme,
    corridor,
    visible_comparison,
    comparison_name if visible_comparison is not None else None,
)

if annualized_regression_change is not None:
    trend_sign = "+" if annualized_regression_change >= 0 else ""
    with details_column:
        st.metric(
            "Trend / year",
            f"{trend_sign}{annualized_regression_change:.2f}% / year",
            help="Annualized percentage change implied by the logarithmic regression trend.",
        )
        st.caption(
            f"R² {logarithmic_regression_r_squared(regression_frame, corridor_start):.3f} · "
            "descriptive trend, not a prediction"
        )
with details_column:
    st.toggle(
        "Log scale",
        key="logarithmic",
        help="Use equal vertical space for equal percentage moves",
    )
    st.toggle(
        "Regression corridor",
        key="corridor_enabled",
        help="Fit a log-price trend from the selected start date and enclose all daily closes.",
    )
    st.toggle(
        "95% corridor",
        key="corridor_95",
        help="Ignore the 5% most extreme logarithmic residuals for a tighter channel.",
        disabled=not corridor_enabled or analysis_mode != "Price",
    )
with chart_column:
    st.plotly_chart(
        chart,
        use_container_width=True,
        theme=None,
        config={"displayModeBar": False, "scrollZoom": False, "responsive": True},
    )
    download_frame = visible[["market_date", "close"]].copy()
    st.download_button(
        "Download visible CSV",
        data=download_frame.to_csv(index=False),
        file_name=f"{symbol.lower().replace('/', '-')}-{analysis_mode.lower().replace(' ', '-')}.csv",
        mime="text/csv",
    )

freshness_state, freshness = freshness_status(latest["market_date"], latest["source"])
source_label = latest["source"].replace("_", " ").title()
if symbol == "SP500":
    if "spx_csv" in set(frame["source"]):
        source_label += " · Daily history: local SPX CSV (1960–2016)"
    elif "shiller_monthly" in set(frame["source"]):
        source_label += " · Long-term dotted segment: Shiller-derived monthly US equities"
elif symbol == "IRAN_INFLATION":
    source_label = "Statistical Center of Iran (SCI)"
st.markdown(
    f'<div class="source-line">Source: {source_label} &nbsp;·&nbsp; {freshness} &nbsp;·&nbsp; Informational data, not financial advice.</div>',
    unsafe_allow_html=True,
)

with st.expander("Data status"):
    status_frame = db.source_status()
    if status_frame.empty:
        st.caption("No sync runs have been recorded yet.")
    else:
        freshness_parts = status_frame.apply(
            lambda row: freshness_status(row["market_date"], row["source"]), axis=1
        )
        status_frame["observation status"] = [item[0] for item in freshness_parts]
        status_frame["latest observation"] = [item[1] for item in freshness_parts]
        status_frame = status_frame.rename(
            columns={"source": "source", "finished_at": "last successful fetch", "row_count": "rows"}
        )
        st.dataframe(status_frame, use_container_width=True, hide_index=True)

with st.expander("Cross-market analytics"):
    country_frames = {name: read_prices(INSTRUMENTS[name]["symbol"]) for name in chart_options}
    correlation, overlap = monthly_log_return_correlation(country_frames)
    if correlation.empty:
        st.caption("At least two instruments with overlapping monthly observations are required.")
    else:
        st.caption(f"Monthly log-return correlation · overlap {overlap[0]:%b %Y}–{overlap[1]:%b %Y}")
        st.dataframe(correlation.style.format("{:.2f}"), use_container_width=True)
    if dashboard_section == "Iran":
        usd = read_prices("USD/IRT")
        gold_toman = derived_series(read_prices("XAU/USD"), usd, "multiply", "Gold in Toman")
        tedpix_usd = derived_series(read_prices("TEDPIX"), usd, "divide", "TEDPIX in USD")
        for derived, label in ((gold_toman, "Gold in Toman"), (tedpix_usd, "TEDPIX in USD terms")):
            if derived.empty:
                st.caption(f"{label}: no common observation dates yet.")
            else:
                st.metric(label, f"{float(derived.iloc[-1]['close']):,.2f}")
                st.download_button(
                    f"Download {label} CSV", derived.to_csv(index=False),
                    file_name=f"{label.lower().replace(' ', '-')}.csv", mime="text/csv"
                )

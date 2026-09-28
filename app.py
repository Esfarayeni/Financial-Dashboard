from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from financial_dashboard import db
from financial_dashboard.analytics import (
    annualized_logarithmic_regression_change,
    logarithmic_regression_channel,
    period_change,
    rebased_price_level,
)
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


@st.cache_data(ttl=30)
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
    if symbol == "US_INFLATION":
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
    source_groups = list(frame.groupby("source", sort=False))
    for source, source_frame in source_groups:
        is_long_term = source == "shiller_monthly"
        fig.add_trace(
            go.Scatter(
                x=source_frame["market_date"], y=source_frame["close"], mode="lines",
                name="US equities long-term (monthly)" if is_long_term else title,
                line={"color": accent, "width": 2, "dash": "dot" if is_long_term else "solid"},
                hovertemplate=f"<b>%{{y:,.{decimals}f}}</b><extra></extra>",
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
                hovertemplate=f"<b>%{{y:,.{decimals}f}}×</b><extra></extra>",
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
        hovermode="closest",
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

if "sync_results" in st.session_state:
    failures = [r for r in st.session_state["sync_results"] if r["status"] == "failed"]
    if failures:
        st.warning("Some sources could not be updated. Existing chart data was preserved.")
    else:
        st.toast("Market data refreshed")

if st.session_state.get("dashboard_section") not in {"Iran", "U.S."}:
    st.session_state["dashboard_section"] = "Iran"

dashboard_section = st.radio(
    "Country",
    ("Iran", "U.S."),
    horizontal=True,
    label_visibility="collapsed",
    key="dashboard_section",
)
chart_options = IRAN_INSTRUMENTS if dashboard_section == "Iran" else US_INSTRUMENTS
chart_selector_key = "iran_chart" if dashboard_section == "Iran" else "us_chart"
if st.session_state.get(chart_selector_key) not in chart_options:
    st.session_state[chart_selector_key] = chart_options[0]
selected_name = st.session_state[chart_selector_key]
comparison_options = ("None",) + tuple(name for name in chart_options if name != selected_name)
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

chart_selector_column, comparison_selector_column, range_column, controls_right = st.columns(
    [1.65, 1.65, 3.25, 1.1], vertical_alignment="center"
)
with chart_selector_column:
    st.selectbox("Chart", chart_options, key=chart_selector_key, label_visibility="collapsed")
with comparison_selector_column:
    st.selectbox("Compare with", comparison_options, key="comparison_chart", label_visibility="collapsed")
with range_column:
    selected_range = st.radio("Range", list(RANGES), index=4, horizontal=True, label_visibility="collapsed")
with controls_right:
    st.caption("Drag to zoom · Double-click to reset")

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

corridor = None
annualized_regression_change = None
regression_frame = chart_primary_frame
# A century of monthly history plus a recent daily segment must not give the
# recent decade thousands of times more weight in the long-term trend fit.
if symbol == "SP500" and selected_range == "All":
    regression_frame = (
        frame.set_index("market_date").resample("ME").last().dropna(subset=["close"]).reset_index()
    )
if corridor_enabled:
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
    selected_name,
    instrument["accent"],
    2 if comparison_frame is not None else instrument["decimals"],
    logarithmic,
    theme,
    corridor,
    visible_comparison,
    comparison_name if comparison_frame is not None else None,
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
        disabled=not corridor_enabled,
    )
with chart_column:
    st.plotly_chart(
        chart,
        use_container_width=True,
        theme=None,
        config={"displayModeBar": False, "scrollZoom": False, "responsive": True},
    )

fetched_at = pd.to_datetime(latest["fetched_at"], utc=True)
age = datetime.now(timezone.utc) - fetched_at.to_pydatetime()
freshness = "Current" if age < timedelta(days=2) else f"Stored {age.days}d ago"
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

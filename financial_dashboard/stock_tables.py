"""Escaped, semantic stock tables using only locally stored market data."""
from html import escape
from urllib.parse import urlencode

import pandas as pd


def chart_identity_html(name: str, ticker: str, logo: str | None) -> str:
    """Stock chart heading; local logos only, with a text-only fallback."""
    image = ''
    if isinstance(logo, str) and logo.startswith('data:image/png;base64,'):
        css = 'chart-stock-logo chart-stock-logo-navy' if ticker in {'V', 'ABBV', 'UNH'} else 'chart-stock-logo'
        image = f'<img class="{css}" src="{escape(logo, quote=True)}" alt="" width="32" height="32">'
    return f'<span class="snapshot-name stock-chart-identity">{image}<span>{escape(name)}</span></span>'


def movers_html(frame: pd.DataFrame, label: str, half_life_years: float | None = None) -> str:
    rows = []
    for rank, (_, row) in enumerate(frame.iterrows(), 1):
        name, ticker = str(row.Company), str(row.Ticker)
        params = dict(dashboard_view="Charts", dashboard_section="Stocks",
                      chart=f"{name} ({ticker})", selected_range="All", compare="None")
        if half_life_years is not None:
            params["half_life"] = f"{half_life_years:g}"
        href = '?' + urlencode(params)
        logo = row.get("Logo")
        image = (f'<img src="{escape(logo, quote=True)}" alt="" width="24" height="24">'
                 if isinstance(logo, str) and logo.startswith("data:image/png;base64,") else '<span class="mover-logo-placeholder"></span>')
        color = 'positive' if row.Change > 0 else 'negative'
        rows.append(f'<li><a href="{escape(href, quote=True)}" target="_self" title="{escape(name + " · " + ticker, quote=True)}">'
                    f'<span class="mover-rank">{rank}</span>{image}<span class="mover-identity"><strong>{escape(ticker)}</strong>'
                    f'<span>{escape(name)}</span></span><span class="mover-percent {color}">{row.Change:+.2f}%</span></a></li>')
    return (f'<ol class="movers-list" aria-label="{escape(label, quote=True)}">{"".join(rows)}</ol>'
            if rows else '<p>No matching stocks for this period.</p>')


def table_html(frame: pd.DataFrame, columns: list[tuple[str, str, str]], label: str,
               half_life_years: float | None = None) -> str:
    position_help = 'Latest adjusted close vs full-history 95% log regression corridor: 0 = trend, +1 = upper, -1 = lower. Values outside ±1 are outside the corridor. Uses Recent emphasis when enabled. Not a z-score or a return.'
    headers = ''.join(f'<th scope="col" class="{"numeric" if kind in {"percent", "money", "integer", "position", "deviation", "absolute_percent"} else ""}"'
                      + (f' title="{escape(position_help, quote=True)}"' if kind == "position" else '')
                      + (' title="Mean absolute Trend position across all stored adjusted closes, using one fixed full-history 95% log regression corridor. Uses Recent emphasis when enabled. Lower means historically closer to trend. Nonnegative, not a percentage or rolling fit."' if kind == "deviation" else '')
                      + (' title="Mean absolute percentage distance of adjusted prices from the fixed full-history log regression trend: mean(abs(price/trend - 1)) × 100. Uses Recent emphasis when enabled; otherwise equally weighted observations; no corridor normalization. Lower means closer to trend, not lower daily-return volatility. History windows differ between companies."' if key == "Avg. deviation from trend (%)" else '')
                      + (' title="Full 95% corridor width at the latest stored date divided by the latest adjusted close: (upper - lower) / price × 100. Uses a fixed full-history log regression and Recent emphasis when enabled; not half-width, an average over time, or annualized volatility."' if key == "Corridor width / price (%)" else '')
                      + (' title="Latest adjusted close compared with its highest adjusted close in the stored history. 0% = at high; negative = below high. Not maximum historical drawdown or an intraday high."' if key == "Drawdown from ATH (%)" else '')
                      + f'>{escape(title)}</th>' for key, title, kind in columns)
    rows = []
    for _, row in frame.iterrows():
        cells = []
        for key, _, kind in columns:
            value = row.get(key)
            css = "numeric" if kind in {"percent", "money", "integer", "position", "deviation", "absolute_percent"} else ""
            if kind == "symbol":
                name, ticker = str(row["Company"]), str(row["Ticker"])
                params = dict(dashboard_view="Charts", dashboard_section="Stocks",
                              chart=f"{name} ({ticker})", selected_range="All", compare="None")
                if half_life_years is not None:
                    params["half_life"] = f"{half_life_years:g}"
                href = '?' + urlencode(params)
                logo = row.get("Logo")
                image = (f'<img src="{escape(logo, quote=True)}" alt="" width="28" height="28">'
                         if isinstance(logo, str) and logo.startswith("data:image/png;base64,") else '<span class="logo-placeholder" aria-hidden="true"></span>')
                content = (f'<a class="stock-symbol" href="{escape(href, quote=True)}" target="_self">{image}'
                           f'<span class="ticker">{escape(ticker)}</span><span class="company">{escape(name)}</span></a>')
            elif value is None or pd.isna(value):
                content = "—"
            elif kind == "percent":
                css += " positive" if value > 0 else " negative" if value < 0 else ""
                content = f'{value:+,.2f}%'
            elif kind == "position":
                content = f'{value:+.2f}' if abs(value) >= 0.005 else '0.00'
            elif kind == "deviation":
                content = f'{value:.2f}'
            elif kind == "absolute_percent":
                content = f'{value:,.2f}%'
            elif kind == "money":
                content = f'${value:,.2f}' + ('B' if key == "Market cap ($B)" else '')
            elif kind == "integer":
                content = str(int(value)) if key == "Listing year" else f'{int(value):,}'
            elif kind == "date":
                content = pd.Timestamp(value).strftime('%b %d, %Y')
            else:
                content = escape(str(value))
            cells.append(f'<td class="{css}">{content}</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    if not rows:
        rows.append(f'<tr><td colspan="{len(columns)}">No matching data.</td></tr>')
    return (f'<div class="stock-table-scroll" role="region" aria-label="{escape(label, quote=True)}" tabindex="0">'
            f'<table class="stock-table"><caption class="sr-only">{escape(label)}</caption>'
            f'<thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')

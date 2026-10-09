"""Escaped, semantic stock tables using only locally stored market data."""
from html import escape
from urllib.parse import urlencode

import pandas as pd


def movers_html(frame: pd.DataFrame, label: str) -> str:
    rows = []
    for rank, (_, row) in enumerate(frame.iterrows(), 1):
        name, ticker = str(row.Company), str(row.Ticker)
        href = '?' + urlencode(dict(dashboard_view="Charts", dashboard_section="Stocks",
                                     chart=f"{name} ({ticker})", selected_range="All", compare="None"))
        logo = row.get("Logo")
        image = (f'<img src="{escape(logo, quote=True)}" alt="" width="24" height="24">'
                 if isinstance(logo, str) and logo.startswith("data:image/png;base64,") else '<span class="mover-logo-placeholder"></span>')
        color = 'positive' if row.Change > 0 else 'negative'
        rows.append(f'<li><a href="{escape(href, quote=True)}" target="_self" title="{escape(name + " · " + ticker, quote=True)}">'
                    f'<span class="mover-rank">{rank}</span>{image}<span class="mover-identity"><strong>{escape(ticker)}</strong>'
                    f'<span>{escape(name)}</span></span><span class="mover-percent {color}">{row.Change:+.2f}%</span></a></li>')
    return (f'<ol class="movers-list" aria-label="{escape(label, quote=True)}">{"".join(rows)}</ol>'
            if rows else '<p>No matching stocks for this period.</p>')


def table_html(frame: pd.DataFrame, columns: list[tuple[str, str, str]], label: str) -> str:
    headers = ''.join(f'<th scope="col" class="{"numeric" if kind in {"percent", "money", "integer"} else ""}">{escape(title)}</th>' for _, title, kind in columns)
    rows = []
    for _, row in frame.iterrows():
        cells = []
        for key, _, kind in columns:
            value = row.get(key)
            css = "numeric" if kind in {"percent", "money", "integer"} else ""
            if kind == "symbol":
                name, ticker = str(row["Company"]), str(row["Ticker"])
                href = '?' + urlencode(dict(dashboard_view="Charts", dashboard_section="Stocks",
                                             chart=f"{name} ({ticker})", selected_range="All", compare="None"))
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

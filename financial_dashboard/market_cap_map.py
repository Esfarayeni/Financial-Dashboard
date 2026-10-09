"""Logo-bearing, sector-grouped market-cap map; no remote assets or scripts."""
from html import escape
from urllib.parse import urlencode

import pandas as pd

COLORS = {
    "Information Technology": "#72a5bc", "Energy": "#ed8c86",
    "Financials": "#b3cb75", "Communication Services": "#c29ab0",
    "Consumer Discretionary": "#f2b274", "Consumer Staples": "#e4c775",
    "Health Care": "#94c0ad", "Industrials": "#a3bfc5",
    "Materials": "#c4a88c", "Real Estate": "#b8a8cf", "Utilities": "#a8bd93",
}


def rectangles(values, x, y, width, height):
    """Squarified layout, preserving input order and proportional areas."""
    if not values:
        return []
    areas = [v / sum(values) * width * height for v in values]
    result = []

    def worst(row, side):
        total = sum(row)
        return max(side * side * max(row) / total**2, total**2 / (side * side * min(row)))

    while areas:
        side = min(width, height)
        row = [areas.pop(0)]
        while areas and worst(row + areas[:1], side) <= worst(row, side):
            row.append(areas.pop(0))
        strip = sum(row) / side
        cursor = y if width >= height else x
        for area in row:
            length = area / strip
            if width >= height:
                result.append((x, cursor, strip, length))
            else:
                result.append((cursor, y, length, strip))
            cursor += length
        if width >= height:
            x, width = x + strip, width - strip
        else:
            y, height = y + strip, height - strip
    return result


def cap_label(value):
    return f"${value / 1e12:,.2f}T" if value >= 1e12 else f"${value / 1e9:,.0f}B"


def map_html(caps: pd.DataFrame, dark=False):
    width, height = 1100, 780
    sectors = caps.groupby("Sector")["Market cap (USD)"].sum().sort_values(ascending=False)
    sector_boxes = rectangles(sectors.tolist(), 0, 0, width, height)
    tiles = []
    for sector, (x, y, w, h) in zip(sectors.index, sector_boxes):
        companies = caps[caps.Sector == sector].sort_values("Market cap (USD)", ascending=False)
        if h <= 6 or w <= 6:
            continue
        boxes = rectangles(companies["Market cap (USD)"].tolist(), x + 3, y + 3, w - 6, h - 6)
        for (_, row), (tx, ty, tw, th) in zip(companies.iterrows(), boxes):
            name, ticker = str(row.Company), str(row.Ticker)
            cap = cap_label(row["Market cap (USD)"])
            link = '?' + urlencode(dict(dashboard_view="Charts", dashboard_section="Stocks", chart=f"{name} ({ticker})", selected_range="All", compare="None"))
            large = tw >= 140 and th >= 110
            logo = row.get("Logo")
            image = (f'<span class="cap-logo"><img src="{escape(logo, quote=True)}" alt="" loading="lazy"></span>'
                     if large and isinstance(logo, str) and logo.startswith("data:image/png;base64,") else '')
            tiles.append(
                f'<a class="cap-tile{" cap-large" if large else ""}" href="{escape(link, quote=True)}" target="_self" '
                f'aria-label="{escape(name + " (" + ticker + "), " + cap + ". Open chart", quote=True)}" title="{escape(name + " · " + ticker + " · " + cap, quote=True)}" '
                f'style="left:{tx/width*100:.4f}%;top:{ty/height*100:.4f}%;width:{tw/width*100:.4f}%;height:{th/height*100:.4f}%;background:{COLORS[sector]}">'
                f'<span class="cap-corner">{escape(cap)}</span><span class="cap-brand">{image}<span class="cap-name">{escape(name)}</span>'
                f'<span class="cap-ticker">{escape(ticker)}</span></span></a>'
            )
    surface = '#182130' if dark else '#fbf9f2'
    legend = ''.join(f'<li><span class="cap-swatch" style="background:{COLORS[sector]}" aria-hidden="true"></span>{escape(sector)}</li>'
                     for sector in sectors.index)
    return f'''<style>
    .cap-map-scroll {{ overflow-x:auto; background:{surface}; padding:12px; border-radius:12px; margin-bottom:24px; }}
    .cap-map {{ position:relative; width:100%; min-width:900px; aspect-ratio:1100 / 780; font-variant-numeric:tabular-nums; color:#142c35; }}
    .cap-legend {{ display:flex; flex-wrap:wrap; gap:12px 20px; list-style:none; padding:0!important; margin:0 0 24px!important; font-size:13px; color:{'#dce3ed' if dark else '#394452'}; }}
    .cap-legend li {{ display:flex; align-items:center; gap:7px; margin:0; }}
    .cap-swatch {{ width:14px; height:14px; border-radius:3px; flex-shrink:0; }}
    a.cap-tile {{ position:absolute; box-sizing:border-box; border:1.5px solid {surface}; color:#142c35; text-decoration:none; overflow:hidden; container-type:size; }}
    .cap-tile:hover {{ filter:brightness(1.07); }}
    .cap-tile:focus-visible {{ outline:3px solid #142c35; outline-offset:-4px; z-index:1; }}
    .cap-corner {{ position:absolute; left:8px; top:6px; font-size:clamp(11px,8cqw,20px); font-weight:600; }}
    .cap-brand {{ position:absolute; inset:30px 8px 6px; display:flex; flex-direction:column; justify-content:center; align-items:center; gap:6px; text-align:center; }}
    .cap-name {{ font-size:clamp(11px,8cqw,22px); font-weight:600; line-height:1.15; }}
    .cap-ticker {{ font-size:11px; line-height:1.1; }}
    .cap-logo {{ display:flex; justify-content:center; align-items:center; background:transparent; padding:8px; width:min(28cqw,28cqh,80px); height:min(28cqw,28cqh,80px); flex-shrink:0; }}
    .cap-logo img {{ width:100%; height:100%; object-fit:contain; mix-blend-mode:multiply; }}
    @container (max-height:100px) {{ .cap-logo {{ display:none; }} .cap-ticker {{ display:none; }} .cap-brand {{ inset:26px 5px 4px; }} }}
    @container (max-height:160px) {{ .cap-large .cap-ticker {{ display:none; }} }}
    @container (max-height:55px) {{ .cap-brand {{ display:none; }} }}
    @container (max-width:95px) {{ .cap-logo, .cap-name {{ display:none; }} .cap-corner {{ left:4px; font-size:10px; }} .cap-ticker {{ font-size:12px; font-weight:600; }} }}
    </style><div class="cap-map-scroll" role="region" aria-label="Top 50 companies by market cap; scroll horizontally on small screens" tabindex="0"><div class="cap-map">{''.join(tiles)}</div></div><ul class="cap-legend" aria-label="Sector color key">{legend}</ul>'''

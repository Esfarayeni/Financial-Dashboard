"""Logo-bearing market-cap map, nested by sector and industry; local assets only."""
from html import escape
from urllib.parse import urlencode

import pandas as pd

COLORS = {
    "Information Technology": "#72a5bc", "Energy": "#ed8c86",
    "Financials": "#b3cb75", "Communication Services": "#c29ab0",
    "Consumer Discretionary": "#f2b274", "Consumer Staples": "#e4c775",
    "Health Care": "#94c0ad", "Industrials": "#a3bfc5",
    "Materials": "#c4a88c", "Real Estate": "#b8a8cf", "Utilities": "#a8bd93",
    "Crypto assets": "#91b8d4",
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
    if value >= 1e12:
        return f"${value / 1e12:,.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:,.1f}B" if value < 10e9 else f"${value / 1e9:,.0f}B"
    if value >= 1e6:
        return f"${value / 1e6:,.1f}M"
    if value >= 1e3:
        return f"${value / 1e3:,.0f}K"
    return f"${value:,.0f}"


def industry_bars_html(caps: pd.DataFrame, industry: str, dark=False):
    """Accessible linked ranking with linear bars, scaled within this industry."""
    foreground = "#e1e7ef" if dark else "#142c35"
    muted = "#b4c1d0" if dark else "#526174"
    track = "#273344" if dark else "#edf1f5"
    rows = []
    maximum = caps["Market cap (USD)"].max() if not caps.empty else 1
    for _, row in caps.iterrows():
        name, ticker = str(row.Company), str(row.Ticker)
        value = float(row["Market cap (USD)"])
        link = '?' + urlencode(dict(dashboard_view="Charts", dashboard_section="Stocks",
                                   chart=f"{name} ({ticker})", selected_range="All", compare="None"))
        logo = row.get("Logo")
        image = (f'<img src="{escape(logo, quote=True)}" alt="" loading="lazy">'
                 if isinstance(logo, str) and logo.startswith("data:image/png;base64,") else '')
        rows.append(f'<li><a href="{escape(link, quote=True)}" target="_self" '
                    f'aria-label="{escape(name + ", " + cap_label(value) + ". Open chart", quote=True)}">'
                    f'<span class="industry-company">{image}<span><strong>{escape(ticker)}</strong>'
                    f'<span class="industry-name">{escape(name)}</span></span></span>'
                    f'<span class="industry-track" aria-hidden="true"><span style="width:{value/maximum*100:.6f}%;background:{COLORS.get(row.Sector, "#aab2bf")}"></span></span>'
                    f'<span class="industry-value" title="${value:,.0f}">{cap_label(value)}</span></a></li>')
    return f'''<style>
    .industry-ranking {{ margin:0 0 28px; color:{foreground}; }}
    .industry-ranking figcaption {{ font-size:18px; font-weight:600; margin-bottom:12px; overflow-wrap:anywhere; }}
    .industry-ranking ol {{ list-style:none; margin:0!important; padding:0!important; }}
    .industry-ranking li {{ margin:0; border-bottom:1px solid {track}; }}
    .industry-ranking a {{ display:grid; grid-template-columns:minmax(0,1.25fr) minmax(36px,1fr) 76px; gap:12px; align-items:center; padding:9px 0; color:inherit; text-decoration:none; font-variant-numeric:tabular-nums; }}
    .industry-ranking a:hover {{ background:{track}; }}
    .industry-ranking a:focus-visible {{ outline:2px solid {foreground}; outline-offset:2px; }}
    .industry-company {{ display:flex; align-items:center; gap:8px; min-width:0; }}
    .industry-company > span {{ min-width:0; }}
    .industry-company img {{ width:24px; height:24px; object-fit:contain; flex-shrink:0; }}
    .industry-company strong {{ display:block; font-size:13px; line-height:1.3; }}
    .industry-name {{ display:block; color:{muted}; font-size:12px; line-height:1.35; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .industry-track {{ display:block; height:14px; background:{track}; border-radius:3px; overflow:hidden; }}
    .industry-track > span {{ display:block; height:100%; }}
    .industry-value {{ text-align:right; font-size:13px; white-space:nowrap; }}
    @media(max-width:600px) {{ .industry-ranking a {{ grid-template-columns:minmax(0,1.4fr) minmax(28px,1fr) 64px; gap:8px; }} }}
    </style><figure class="industry-ranking"><figcaption>{escape(industry)}</figcaption><ol>{''.join(rows)}</ol></figure>'''


def map_html(caps: pd.DataFrame, dark=False, label="Top 50 companies by market cap"):
    width, height = 1100, 780
    sectors = caps.groupby("Sector")["Market cap (USD)"].sum().sort_values(ascending=False)
    sector_boxes = rectangles(sectors.tolist(), 0, 0, width, height)
    tiles = []
    headings = []
    placements = []
    for sector, (x, y, w, h) in zip(sectors.index, sector_boxes):
        companies = caps[caps.Sector == sector].sort_values("Market cap (USD)", ascending=False)
        if h <= 6 or w <= 6:
            continue
        # Missing classifications stay explicitly separate; never infer from a company name.
        companies = companies.assign(Industry=companies.get("Industry", pd.Series(index=companies.index, dtype=str)).fillna("Industry unavailable").replace("", "Industry unavailable"))
        industries = companies.groupby("Industry")["Market cap (USD)"].sum().sort_values(ascending=False)
        industry_boxes = rectangles(industries.tolist(), x + 3, y + 3, w - 6, h - 6)
        for industry, (ix, iy, iw, ih) in zip(industries.index, industry_boxes):
            members = companies[companies.Industry == industry]
            header = 22 if iw >= 110 and ih >= 85 else 0
            if header:
                headings.append(f'<span class="cap-industry" title="{escape(industry, quote=True)}" '
                                f'style="left:{ix/width*100:.4f}%;top:{iy/height*100:.4f}%;width:{iw/width*100:.4f}%">{escape(industry)}</span>')
            boxes = rectangles(members["Market cap (USD)"].tolist(), ix, iy + header, iw, ih - header)
            placements.extend((sector, industry, row, box) for (_, row), box in zip(members.iterrows(), boxes))
    for sector, industry, row, (tx, ty, tw, th) in placements:
        name, ticker = str(row.Company), str(row.Ticker)
        cap = cap_label(row["Market cap (USD)"])
        link = '?' + urlencode(dict(dashboard_view="Charts", dashboard_section=row.get("Section", "Stocks"), chart=row.get("Chart name", f"{name} ({ticker})"), selected_range="All", compare="None"))
        large = tw >= 140 and th >= 110
        logo = row.get("Logo")
        logo_class = 'cap-logo cap-logo-navy' if ticker in {'V', 'ABBV', 'UNH'} else 'cap-logo'
        image = (f'<span class="{logo_class}"><img src="{escape(logo, quote=True)}" alt="" loading="lazy"></span>'
                 if isinstance(logo, str) and logo.startswith("data:image/png;base64,") else '')
        size_class = ' cap-large' if large else ' cap-compact' if image else ''
        tiles.append(
            f'<a class="cap-tile{size_class}" href="{escape(link, quote=True)}" target="_self" '
            f'aria-label="{escape(name + " (" + ticker + "), " + cap + ", " + industry + ". Open chart", quote=True)}" title="{escape(name + " · " + ticker + " · " + cap + " · " + industry, quote=True)}" '
            f'style="left:{tx/width*100:.4f}%;top:{ty/height*100:.4f}%;width:{tw/width*100:.4f}%;height:{th/height*100:.4f}%;background:{COLORS.get(sector, "#aab2bf")}">'
            f'<span class="cap-corner">{escape(cap)}</span><span class="cap-brand">{image}<span class="cap-name">{escape(name)}</span>'
            f'<span class="cap-ticker">{escape(ticker)}</span></span></a>'
        )
    surface = '#182130' if dark else '#fbf9f2'
    legend = ''.join(f'<li><span class="cap-swatch" style="background:{COLORS.get(sector, "#aab2bf")}" aria-hidden="true"></span>{escape(sector)}</li>'
                     for sector in sectors.index)
    return f'''<style>
    .cap-map-scroll {{ overflow-x:auto; background:{surface}; padding:12px; border-radius:12px; margin-bottom:24px; }}
    .cap-map {{ position:relative; width:100%; min-width:900px; aspect-ratio:1100 / 780; font-variant-numeric:tabular-nums; color:#142c35; }}
    .cap-industry {{ position:absolute; box-sizing:border-box; height:2.8205%; padding:2px 5px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; font-size:11px; line-height:1.2; font-weight:600; color:{'#dce3ed' if dark else '#394452'}; }}
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
    /* Transparent white Visa, AbbVie and UnitedHealth marks need a navy tint on pastel tiles. */
    .cap-logo-navy img {{ mix-blend-mode:normal; filter:brightness(0) saturate(100%) invert(15%) sepia(76%) saturate(1660%) hue-rotate(209deg) brightness(91%) contrast(108%); }}
    .cap-compact .cap-brand {{ inset:24px 4px 4px; gap:3px; }}
    .cap-compact .cap-name {{ display:none; }}
    .cap-compact .cap-logo {{ padding:0; width:min(35cqw,30cqh,32px); height:min(35cqw,30cqh,32px); }}
    .cap-compact .cap-ticker {{ display:block; font-size:11px; font-weight:600; }}
    @container (max-height:100px) {{ .cap-logo {{ display:none; }} .cap-ticker {{ display:none; }} .cap-brand {{ inset:26px 5px 4px; }} }}
    @container (max-height:160px) {{ .cap-large .cap-ticker {{ display:none; }} }}
    @container (max-height:55px) {{ .cap-brand {{ display:none; }} }}
    @container (max-width:95px) {{ .cap-logo, .cap-name {{ display:none; }} .cap-corner {{ left:4px; font-size:10px; }} .cap-ticker {{ font-size:12px; font-weight:600; }} }}
    @container (min-width:40px) and (min-height:40px) {{
      .cap-compact .cap-brand {{ display:flex; inset:22px 3px 3px; }}
      .cap-compact .cap-logo {{ display:flex; width:min(35cqw,30cqh,32px); height:min(35cqw,30cqh,32px); }}
    }}
    @container (max-height:64px) {{
      .cap-compact .cap-ticker {{ display:none; }}
      .cap-compact .cap-logo {{ width:min(35cqw,25cqh,24px); height:min(35cqw,25cqh,24px); }}
      .cap-compact .cap-corner {{ font-size:10px; left:4px; top:4px; }}
    }}
    </style><div class="cap-map-scroll" role="region" aria-label="{escape(label, quote=True)}; scroll horizontally on small screens" tabindex="0"><div class="cap-map">{''.join(headings)}{''.join(tiles)}</div></div><ul class="cap-legend" aria-label="Sector color key">{legend}</ul>'''

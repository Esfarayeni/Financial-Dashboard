import pandas as pd
import pytest

from financial_dashboard.market_cap_map import rectangles, map_html


def test_squarified_map_preserves_area_and_bounds():
    values = [100, 60, 25, 15, 10, 2]
    boxes = rectangles(values, 0, 0, 1000, 700)
    assert len(boxes) == len(values)
    for value, (x, y, w, h) in zip(values, boxes):
        assert w * h == pytest.approx(value / sum(values) * 700000)
        assert x >= -1e-8 and y >= -1e-8
        assert x + w <= 1000 + 1e-8 and y + h <= 700 + 1e-8
    for i, (x, y, w, h) in enumerate(boxes):
        for a, b, c, d in boxes[i + 1:]:
            assert min(x + w, a + c) <= max(x, a) + 1e-8 or min(y + h, b + d) <= max(y, b) + 1e-8


def test_map_uses_local_logos_and_chart_links():
    frame = pd.DataFrame([{"Company": "A & B", "Ticker": "AB", "Sector": "Information Technology",
                           "Market cap (USD)": 2e12, "Logo": "data:image/png;base64,AAAA"}])
    html = map_html(frame)
    assert 'cap-logo' in html and 'src="data:image/png;base64,AAAA"' in html
    assert '$2.00T' in html and 'A &amp; B' in html
    assert 'dashboard_section=Stocks' in html and 'target="_self"' in html
    assert 'background:transparent' in html and 'mix-blend-mode:multiply' in html
    assert 'class="cap-sector"' not in html
    assert 'aria-label="Sector color key"' in html
    assert '<span class="cap-swatch" style="background:#72a5bc"' in html
    assert html.count('Information Technology') == 1


def test_medium_tiles_show_compact_local_logos():
    frame = pd.DataFrame([{"Company": f"Company {i}", "Ticker": f"C{i}",
                           "Sector": "Information Technology", "Market cap (USD)": 1e11,
                           "Logo": "data:image/png;base64,AAAA"} for i in range(50)])
    html = map_html(frame)
    assert 'class="cap-tile cap-compact"' in html
    assert html.count('<img') == 50
    assert '.cap-compact .cap-name { display:none; }' in html


def test_white_marks_get_navy_tint_without_changing_other_logos():
    frame = pd.DataFrame([{"Company": name, "Ticker": ticker,
                           "Sector": "Financials", "Market cap (USD)": 1e12,
                           "Logo": "data:image/png;base64,AAAA"}
                          for name, ticker in [("Visa", "V"), ("AbbVie", "ABBV"),
                                               ("UnitedHealth Group", "UNH"), ("Mastercard", "MA")]])
    html = map_html(frame)
    assert html.count('class="cap-logo cap-logo-navy"') == 3
    assert html.count('class="cap-logo"') == 1
    assert '.cap-logo-navy img { mix-blend-mode:normal; filter:brightness(0)' in html


def test_small_tiles_include_logos_and_keep_missing_logo_fallback():
    frame = pd.DataFrame([{"Company": f"Company {i}", "Ticker": f"C{i}",
                           "Sector": "Information Technology", "Market cap (USD)": 1e11,
                           "Logo": "data:image/png;base64,AAAA" if i else None} for i in range(150)])
    html = map_html(frame)
    assert html.count('<img') == 149
    assert 'C0' in html
    assert '@container (max-height:64px)' in html

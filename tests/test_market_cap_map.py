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

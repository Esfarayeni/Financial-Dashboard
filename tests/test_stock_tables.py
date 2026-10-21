import pandas as pd

from financial_dashboard.stock_tables import movers_html, table_html, chart_identity_html


def test_chart_identity_uses_local_logo_and_escapes_name():
    html = chart_identity_html('A & <B>', 'AB', 'data:image/png;base64,AAAA')
    assert 'A &amp; &lt;B&gt;' in html
    assert 'src="data:image/png;base64,AAAA"' in html
    assert 'alt=""' in html
    assert 'chart-stock-logo-navy' not in html
    for ticker in ('V', 'ABBV', 'UNH'):
        assert 'chart-stock-logo-navy' in chart_identity_html(ticker, ticker, 'data:image/png;base64,AAAA')


def test_chart_identity_keeps_name_without_missing_or_remote_logo():
    for logo in (None, 'https://example.com/logo.png'):
        html = chart_identity_html('Company (AB)', 'AB', logo)
        assert '<img' not in html
        assert 'Company (AB)' in html


def test_stock_table_formats_values_and_escapes_company():
    frame = pd.DataFrame([{"Company": "A & <B>", "Ticker": "AB", "Change": 12.5,
                           "Price": 1234.5, "Sector": None, "Logo": None}])
    html = table_html(frame, [("Company", "Symbol", "symbol"), ("Change", "Change", "percent"),
                              ("Price", "Price", "money"), ("Sector", "Sector", "text")], "Gainers")
    assert "A &amp; &lt;B&gt;" in html
    assert "positive" in html and "+12.50%" in html and "$1,234.50" in html
    assert "dashboard_section=Stocks" in html and 'target="_self"' in html
    assert "—" in html and '<caption class="sr-only">Gainers</caption>' in html


def test_stock_table_empty_and_negative():
    columns = [("Change", "Change", "percent")]
    assert "No matching data." in table_html(pd.DataFrame(), columns, "Losers")
    assert 'numeric negative' in table_html(pd.DataFrame({"Change": [-2]}), columns, "Losers")


def test_trend_position_is_signed_dimensionless_and_missing_is_dash():
    html = table_html(pd.DataFrame({"Trend position": [1.25, -0.4, 0, None]}),
                      [("Trend position", "Trend position", "position")], "Stocks")
    assert '+1.25</td>' in html and '-0.40</td>' in html and '0.00</td>' in html
    assert 'numeric">—</td>' in html
    assert '0 = trend, +1 = upper, -1 = lower' in html
    assert '1.25%' not in html


def test_average_deviation_is_unsigned_dimensionless_and_missing_is_dash():
    html = table_html(pd.DataFrame({"Avg. trend deviation": [0.42, 0, None]}),
                      [("Avg. trend deviation", "Avg. trend deviation", "deviation")], "Stocks")
    assert '0.42</td>' in html and '0.00</td>' in html and 'numeric">—</td>' in html
    assert '+0.42' not in html and '0.42%' not in html


def test_movers_are_compact_escaped_chart_links():
    frame = pd.DataFrame([{"Company": "A & <B>", "Ticker": "AB", "Change": -2.5,
                           "Price": 1234, "Sector": "Technology", "Logo": None}])
    html = movers_html(frame, "Top losers")
    assert 'aria-label="Top losers"' in html
    assert "A &amp; &lt;B&gt;" in html
    assert 'mover-percent negative">-2.50%' in html
    assert "dashboard_section=Stocks" in html and 'target="_self"' in html
    assert "Technology" not in html and "1234" not in html
    assert "No matching stocks" in movers_html(pd.DataFrame(), "Gainers")
def test_percentage_deviation_is_unsigned_neutral_and_missing_is_dash():
    html = table_html(pd.DataFrame({"Avg. deviation from trend (%)": [12.345, 0, None]}),
                      [("Avg. deviation from trend (%)", "Avg. deviation from trend (%)", "absolute_percent")], "Stocks")
    assert '12.35%' in html
    assert '0.00%' in html
    assert '—' in html
    assert 'no corridor normalization' in html
    assert 'positive' not in html
    assert '+12.35%' not in html


def test_relative_corridor_width_is_unsigned_percent_with_own_tooltip():
    key = "Corridor width / price (%)"
    html = table_html(pd.DataFrame({key: [42.125, 0, None]}), [(key, key, "absolute_percent")], "Stocks")
    assert '42.12%' in html
    assert '0.00%' in html
    assert '—' in html
    assert '(upper - lower) / price' in html
    assert 'Mean absolute percentage distance' not in html
    assert 'positive' not in html


def test_stock_links_preserve_recent_emphasis():
    frame = pd.DataFrame([{"Company": "Company", "Ticker": "AB", "Change": 5}])
    assert 'half_life=3' in table_html(frame, [("Company", "Symbol", "symbol")], "Stocks", half_life_years=3)
    assert 'half_life=3' in movers_html(frame, "Gainers", half_life_years=3)
    assert 'half_life=0.5' in table_html(frame, [("Company", "Symbol", "symbol")], "Stocks", half_life_years=0.5)
    assert 'half_life=1.0' not in table_html(frame, [("Company", "Symbol", "symbol")], "Stocks", half_life_years=1.0)
    assert 'half_life=0.0833333' in table_html(frame, [("Company", "Symbol", "symbol")], "Stocks", half_life_years=1 / 12)
    assert 'half_life=0.25' in movers_html(frame, "Gainers", half_life_years=0.25)
    assert 'half_life=' not in table_html(frame, [("Company", "Symbol", "symbol")], "Stocks")

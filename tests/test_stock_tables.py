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

from financial_dashboard.providers.shiller import _extract_rows


def test_extract_rows_uses_month_end_dates():
    rows = _extract_rows("Date,SP500\n1959-12-01,59.89\n1960-01-01,59.91\n1960-02-01,56.86\n")
    assert [row.market_date.isoformat() for row in rows] == ["1960-01-31", "1960-02-29"]
    assert [row.close for row in rows] == [59.91, 56.86]

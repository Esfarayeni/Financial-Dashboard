from financial_dashboard.providers.spx_csv import extract_rows


def test_extract_rows_keeps_daily_closes_only_in_dashboard_range(tmp_path):
    path = tmp_path / "SPX.csv"
    path.write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "1959-12-31,59,60,58,59.89,59.89,1\n"
        "1960-01-04,59,60,58,59.91,59.91,1\n"
        "2016-09-21,2160,2165,2159,2163.12,2163.12,1\n"
        "2016-09-22,2170,2180,2169,2177.18,2177.18,1\n"
    )

    rows = extract_rows(path)

    assert [row.market_date.isoformat() for row in rows] == ["1960-01-04", "2016-09-21"]
    assert [row.close for row in rows] == [59.91, 2163.12]
    assert {row.source for row in rows} == {"spx_csv"}

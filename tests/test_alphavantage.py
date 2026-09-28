from datetime import datetime, timezone

from financial_dashboard.providers.alphavantage import _extract_bitcoin_rows


def test_extract_bitcoin_rows_uses_daily_close_and_skips_today():
    today = datetime.now(timezone.utc).date().isoformat()
    rows = _extract_bitcoin_rows(
        {
            "Time Series (Digital Currency Daily)": {
                "2020-01-02": {"4. close": "7200.50"},
                "2020-01-01": {"4. close": "7100.25"},
                today: {"4. close": "99999.00"},
            }
        }
    )

    assert [row.market_date.isoformat() for row in rows] == ["2020-01-01", "2020-01-02"]
    assert [row.close for row in rows] == [7100.25, 7200.50]
    assert all(row.symbol == "BTC/USD" for row in rows)
    assert all(row.source == "alpha_vantage" for row in rows)

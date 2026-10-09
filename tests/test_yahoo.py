from datetime import date

import pandas as pd

from financial_dashboard.providers.yahoo import _rows


def test_rows_turns_yahoo_closes_into_crypto_prices():
    frame = pd.DataFrame(
        {"Close": [100.25, 101.5]},
        index=pd.to_datetime([date(2020, 1, 1), date(2020, 1, 2)]),
    )

    rows = _rows(frame, "BNB-USD")

    assert [row.market_date.isoformat() for row in rows] == ["2020-01-01", "2020-01-02"]
    assert [row.close for row in rows] == [100.25, 101.5]
    assert {row.symbol for row in rows} == {"BNB/USD"}
    assert {row.source for row in rows} == {"yahoo_finance"}


def test_brent_futures_have_separate_symbol_and_barrel_units():
    frame = pd.DataFrame({"Close": [80.5]}, index=pd.to_datetime(["2020-01-02"]))
    row = _rows(frame, "BZ=F")[0]
    assert row.symbol == "BRENT_FUTURES/USD"
    assert row.unit == "usd_per_barrel"
    assert row.currency == "USD"

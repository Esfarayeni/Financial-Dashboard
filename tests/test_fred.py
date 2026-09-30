from financial_dashboard.providers.fred import CPI_SYMBOL, TARGET_SYMBOL, _extract_rows


def test_extract_rows_reads_sp500_and_skips_missing_values():
    rows = _extract_rows(
        {
            "observations": [
                {"date": "2016-09-22", "value": "2177.18"},
                {"date": "2016-09-23", "value": "."},
                {"date": "2016-09-26", "value": "2164.69"},
            ]
        }
    )

    assert [row.market_date.isoformat() for row in rows] == ["2016-09-22", "2016-09-26"]
    assert [row.close for row in rows] == [2177.18, 2164.69]
    assert {row.symbol for row in rows} == {"SP500"}
    assert {row.source for row in rows} == {"fred"}


def test_extract_rows_supports_cpi_symbol_and_unit():
    rows = _extract_rows(
        {"observations": [{"date": "2026-08-01", "value": "334.131"}]},
        symbol=CPI_SYMBOL,
        unit="cpi_index_1982_1984_100",
    )

    assert rows[0].symbol == "US_INFLATION"
    assert rows[0].unit == "cpi_index_1982_1984_100"


def test_extract_rows_supports_fed_funds_target_rate():
    rows = _extract_rows(
        {"observations": [{"date": "2026-08-01", "value": "4.25"}]},
        symbol=TARGET_SYMBOL,
        unit="percent",
    )

    assert rows[0].symbol == "FED_FUNDS_TARGET"
    assert rows[0].close == 4.25
    assert rows[0].unit == "percent"

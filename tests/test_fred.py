import pytest

from financial_dashboard.providers import fred
from financial_dashboard.providers.fred import CPI_SYMBOL, TARGET_SYMBOL, _extract_rows


def test_broad_dollar_index_provider(monkeypatch):
    calls = []
    def download(key, series, start):
        calls.append((series, start))
        return {"observations": [{"date": "2020-01-02", "value": "115.2"}]}
    monkeypatch.setattr(fred, "_download", download)
    rows = fred.fetch_dollar_history("test-key", "2020-01-01")
    assert calls == [("DTWEXBGS", "2020-01-01")]
    assert rows[0].symbol == "US_DOLLAR_BROAD"
    assert rows[0].unit == "index_jan_2006_100"


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


def test_target_history_splices_at_range_transition(monkeypatch):
    def download(key, series):
        if series == "DFEDTAR":
            return {"observations": [
                {"date": "1982-09-27", "value": "10.25"},
                {"date": "2008-12-15", "value": "1.0"},
                {"date": "2008-12-16", "value": "1.0"},
            ]}
        assert series == "DFEDTARU"
        return {"observations": [
            {"date": "2008-12-15", "value": "0.25"},
            {"date": "2008-12-16", "value": "0.25"},
        ]}
    monkeypatch.setattr(fred, "_download", download)
    rows = fred.fetch_target_history("test-key")
    assert [(row.market_date.isoformat(), row.close) for row in rows] == [
        ("1982-09-27", 10.25), ("2008-12-15", 1.0), ("2008-12-16", 0.25),
    ]
    assert all(row.symbol == "FED_FUNDS_TARGET" for row in rows)


@pytest.mark.parametrize("series_id,symbol", fred.TREASURY_SERIES.items())
def test_treasury_history_uses_correct_series_and_incremental_start(monkeypatch, series_id, symbol):
    calls = []
    def download(key, series, start):
        calls.append((key, series, start))
        return {"observations": [
            {"date": "2020-01-01", "value": "."},
            {"date": "2020-01-02", "value": "1.85"},
        ]}
    monkeypatch.setattr(fred, "_download", download)
    rows = fred.fetch_treasury_history("test-key", series_id, "2020-01-01")
    assert calls == [("test-key", series_id, "2020-01-01")]
    assert len(rows) == 1
    assert rows[0].symbol == symbol
    assert rows[0].unit == "percent"
    assert rows[0].close == 1.85


def test_treasury_rejects_unknown_series():
    with pytest.raises(ValueError, match="Unsupported"):
        fred.fetch_treasury_history("test-key", "INVALID")


def test_oil_history_uses_brent_series_units_and_incremental_start(monkeypatch):
    calls = []
    def download(key, series, start):
        calls.append((key, series, start))
        return {"observations": [
            {"date": "2020-01-01", "value": "."},
            {"date": "2020-01-02", "value": "66.25"},
        ]}
    monkeypatch.setattr(fred, "_download", download)
    rows = fred.fetch_oil_history("test-key", "2020-01-01")
    assert calls == [("test-key", "DCOILBRENTEU", "2020-01-01")]
    assert len(rows) == 1
    assert rows[0].symbol == "BRENT/USD"
    assert rows[0].unit == "usd_per_barrel"
    assert rows[0].close == 66.25

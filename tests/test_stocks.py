from datetime import date
import json

import pandas as pd
import pytest

from financial_dashboard import stocks


def history(values=(100.0, 102.0), adjusted=(90.0, 92.0)):
    return pd.DataFrame({"Close": values, "Adj Close": adjusted},
                        index=pd.to_datetime(["2020-01-01", "2020-01-02"]).tz_localize("America/New_York"))


def test_stock_history_excludes_uncompleted_day_and_preserves_both_prices():
    frame = stocks.normalize_history(history(), today=date(2020, 1, 2))
    assert len(frame) == 1
    assert frame.iloc[0].quote_close == 100
    assert frame.iloc[0].adjusted_close == 90


def test_stock_reading_selects_quote_or_adjusted_without_network(tmp_path):
    stocks.normalize_history(history()).to_parquet(tmp_path / "AAPL.parquet", index=False)
    assert stocks.load_prices("STOCK:AAPL", directory=tmp_path).close.tolist() == [90, 92]
    assert stocks.load_prices("STOCK:AAPL", adjusted=False, directory=tmp_path).close.tolist() == [100, 102]
    assert stocks.load_prices("STOCK:MSFT", directory=tmp_path).empty


def test_stock_update_uses_overlap_and_refetches_revised_history(monkeypatch, tmp_path):
    calls = []

    class FakeTicker:
        def history(self, **kwargs):
            calls.append(kwargs)
            return history()

    monkeypatch.setattr(stocks.yf, "Ticker", lambda ticker: FakeTicker())
    stocks.update_stock("AAPL", directory=tmp_path)
    assert calls[-1]["period"] == "max"
    calls.clear()
    assert stocks.update_stock("AAPL", directory=tmp_path) == 0
    assert "start" in calls[0] and len(calls) == 1
    old = pd.read_parquet(tmp_path / "AAPL.parquet")
    old["adjusted_close"] *= 0.9
    old.to_parquet(tmp_path / "AAPL.parquet", index=False)
    calls.clear()
    stocks.update_stock("AAPL", directory=tmp_path)
    assert len(calls) == 2 and calls[1]["period"] == "max"


def test_stock_catalog_has_unique_valid_symbols_and_share_classes():
    tickers = [stock["ticker"] for stock in stocks.STOCKS]
    assert len(tickers) == len(set(tickers)) == 503
    assert len({s["company_id"] for s in stocks.STOCKS}) == 500
    assert {"GOOG", "GOOGL", "BRK-B"}.issubset(tickers)


def test_failed_stock_download_preserves_existing_snapshot(monkeypatch, tmp_path):
    path = tmp_path / "AAPL.parquet"
    stocks.normalize_history(history()).to_parquet(path, index=False)
    before = path.read_bytes()

    class EmptyTicker:
        def history(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(stocks.yf, "Ticker", lambda ticker: EmptyTicker())
    with pytest.raises(ValueError):
        stocks.update_stock("AAPL", directory=tmp_path)
    assert path.read_bytes() == before


def test_leaderboard_ranks_annualized_trend_and_keeps_missing_data(monkeypatch, tmp_path):
    monkeypatch.setattr(stocks, "STOCKS", stocks.STOCKS[:3])
    for stock, annual_growth in zip(stocks.STOCKS[:2], [0.1, 0.2]):
        dates = pd.date_range("2020-01-01", periods=400)
        prices = 100 * (1 + annual_growth) ** ((dates - dates[0]).days / 365.25)
        pd.DataFrame({"market_date": dates, "quote_close": prices,
                      "adjusted_close": prices}).to_parquet(tmp_path / f"{stock['ticker']}.parquet", index=False)
    ticker = stocks.STOCKS[1]["ticker"]
    (tmp_path / "metadata.json").write_text(json.dumps({ticker: {"market_cap": 1e9, "listing_year": 1980}}))
    ranking = stocks.leaderboard(tmp_path)
    assert ranking.Ticker.iloc[0] == ticker
    assert ranking["Trend/year (%)"].iloc[0] == pytest.approx(20, abs=0.01)
    assert ranking["Market cap (USD)"].iloc[0] == 1e9
    assert ranking["Listing year"].iloc[0] == 1980
    assert pd.isna(ranking.Rank.iloc[-1])
    known = ranking[ranking["Trend/year (%)"].notna() & ranking["Listing year"].notna()]
    expected = known.groupby("Sector")["Trend/year (%)"].mean()
    for _, row in known.iterrows():
        assert row["Sector avg/year (%)"] == pytest.approx(expected[row.Sector])


def test_metadata_failure_preserves_previous_values(monkeypatch, tmp_path):
    monkeypatch.setattr(stocks, "STOCKS", [stocks.STOCKS[0]])
    ticker = stocks.STOCKS[0]["ticker"]
    previous = {ticker: {"market_cap": 1e9, "listing_year": 1980}}
    (tmp_path / "metadata.json").write_text(json.dumps(previous))

    class MissingMetadata:
        def get_info(self):
            return {}

    monkeypatch.setattr(stocks.yf, "Ticker", lambda ticker: MissingMetadata())
    assert stocks.update_metadata(tmp_path)[0]["status"] == "failed"
    assert json.loads((tmp_path / "metadata.json").read_text()) == previous


def test_metadata_reads_yahoo_millisecond_first_trade_date(monkeypatch, tmp_path):
    monkeypatch.setattr(stocks, "STOCKS", [stocks.STOCKS[0]])

    class Metadata:
        def get_info(self):
            return {"marketCap": 1e9, "firstTradeDateMilliseconds": 345479400000}

    monkeypatch.setattr(stocks.yf, "Ticker", lambda ticker: Metadata())
    assert stocks.update_metadata(tmp_path)[0]["status"] == "success"
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata[stocks.STOCKS[0]["ticker"]]["listing_year"] == 1980


def test_market_cap_view_counts_companies_once_and_excludes_missing_caps():
    ranking = pd.DataFrame({"Company ID": ["1", "1", "2", "3", "4"],
                            "Market cap (USD)": [100, 100, 50, None, 0]})
    caps = stocks.market_cap_data(ranking)
    assert caps["Company ID"].tolist() == ["1", "2"]
    assert caps["Market cap (USD)"].sum() == 150


def test_logos_cached_locally_and_invalid_download_not_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(stocks, "STOCKS", [stocks.STOCKS[0]])

    class Response:
        content = b"not an image"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(stocks.requests, "get", lambda *a, **kw: Response())
    assert stocks.update_logos(tmp_path)[0]["status"] == "failed"
    ticker = stocks.STOCKS[0]["ticker"]
    assert stocks.logo_uri(ticker, tmp_path) is None
    (tmp_path / "logos" / f"{ticker}.png").write_bytes(b"test")
    assert stocks.update_logos(tmp_path)[0]["status"] == "cached"
    assert stocks.logo_uri(ticker, tmp_path).startswith("data:image/png;base64,")


def test_daily_movers_use_latest_common_session_and_quote_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(stocks, "STOCKS", stocks.STOCKS[:4])
    for stock, prices, end in zip(stocks.STOCKS, [[100, 120], [100, 90], [100, 150], [100, 100]],
                                  ["2020-01-02", "2020-01-02", "2020-01-01", "2020-01-02"]):
        pd.DataFrame({"market_date": pd.date_range(end=end, periods=2), "quote_close": prices,
                      "adjusted_close": [1, 1000]}).to_parquet(tmp_path / f"{stock['ticker']}.parquet", index=False)
    movers = stocks.daily_movers(tmp_path)
    assert movers.Change.tolist() == pytest.approx([20, 0, -10])
    assert len(movers[movers.Change > 0]) == len(movers[movers.Change < 0]) == 1
    assert stocks.daily_movers(tmp_path / "missing").empty


@pytest.mark.parametrize("period,expected", [("Daily", 10), ("Weekly", 37.5), ("Monthly", 120), ("Yearly", 175)])
def test_movers_calendar_periods(monkeypatch, tmp_path, period, expected):
    monkeypatch.setattr(stocks, "STOCKS", stocks.STOCKS[:1])
    pd.DataFrame({"market_date": pd.to_datetime(["2023-10-06", "2024-09-06", "2024-09-30", "2024-10-07", "2024-10-08"]),
                  "quote_close": [40, 50, 80, 100, 110]}).to_parquet(tmp_path / f"{stocks.STOCKS[0]['ticker']}.parquet")
    assert stocks.daily_movers(tmp_path, period).Change.iloc[0] == pytest.approx(expected)


def test_sector_leaderboard_deduplicates_companies():
    ranking = pd.DataFrame({"Company ID": [1, 1, 2, 3], "Sector": ["Tech", "Tech", "Tech", "Energy"],
                            "Trend/year (%)": [10, 12, 20, 25], "Listing year": [2000] * 4})
    sectors = stocks.sector_leaderboard(ranking)
    assert sectors.Sector.tolist() == ["Energy", "Tech"]
    assert sectors["Average trend/year (%)"].tolist() == [25, 15]
    assert sectors["Companies with trend"].tolist() == [1, 2]


def test_sector_averages_exclude_new_and_unknown_listings():
    ranking = pd.DataFrame({"Company ID": [1, 2, 3, 4, 5], "Sector": ["Tech"] * 4 + ["New"],
                            "Trend/year (%)": [10, 2000, 30, 900, 3000],
                            "Listing year": [2000, 2025, 2021, None, 2025],
                            "Listing date": [None, None, "2021-10-09", None, None]})
    result = stocks.sector_leaderboard(ranking, as_of="2026-10-09").set_index("Sector")
    assert result.loc["Tech", "Average trend/year (%)"] == 20
    assert result.loc["Tech", "Companies with trend"] == 2
    assert pd.isna(result.loc["New", "Average trend/year (%)"])
    before = stocks.sector_leaderboard(ranking, as_of="2026-10-08").set_index("Sector")
    assert before.loc["Tech", "Average trend/year (%)"] == 10

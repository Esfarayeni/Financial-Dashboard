import json
import pytest

from financial_dashboard import stock_selection, stocks


def test_selection_ranks_caps_before_taking_limit_and_ignores_invalids():
    quotes = [{"symbol": "A", "marketCap": 10}, {"symbol": "B", "marketCap": 30},
              {"symbol": "C", "marketCap": 20}, {"symbol": "OTHER", "marketCap": 1000},
              {"symbol": "BAD", "marketCap": float("nan")}, {"symbol": "ZERO", "marketCap": 0}]
    selected = stock_selection.largest_stocks(quotes, {"A", "B", "C", "BAD", "ZERO"}, 2)
    assert [row["ticker"] for row in selected] == ["B", "C"]


def test_selection_does_not_fill_unknown_caps_with_smaller_or_arbitrary_stocks():
    with pytest.raises(ValueError, match="Selection was not changed"):
        stock_selection.largest_stocks([{"symbol": "A", "marketCap": 10}], {"A", "B"}, 2)


def test_bulk_selection_preserves_profile_and_existing_prices(monkeypatch, tmp_path):
    tickers = [row["ticker"] for row in stocks.ALL_STOCKS[:3]]
    quotes = [{"symbol": ticker, "marketCap": (i+1)*1e9} for i, ticker in enumerate(tickers)]
    monkeypatch.setattr(stock_selection.yf, "screen", lambda *args, **kwargs: {"start": 0, "total": 3, "quotes": quotes})
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({tickers[2]: {"business_summary": "Existing profile", "listing_year": 1980}}))
    price_path = tmp_path / (tickers[2] + ".parquet")
    price_path.write_bytes(b"existing price snapshot")
    manifest = stock_selection.select_largest(2, tmp_path / "universe.json")
    assert manifest["tickers"] == tickers[:0:-1]
    metadata = json.loads(metadata_path.read_text())
    assert metadata[tickers[2]]["business_summary"] == "Existing profile"
    assert metadata[tickers[2]]["listing_year"] == 1980
    assert metadata[tickers[2]]["market_cap"] == 3e9
    assert price_path.read_bytes() == b"existing price snapshot"


def test_failed_screener_preserves_existing_selection(monkeypatch, tmp_path):
    path = tmp_path / "universe.json"
    path.write_text('{"old": true}')
    monkeypatch.setattr(stock_selection.yf, "screen", lambda *args, **kwargs: {"start": 0, "quotes": []})
    with pytest.raises(ValueError):
        stock_selection.select_largest(2, path)
    assert json.loads(path.read_text()) == {"old": True}


def test_active_universe_matches_saved_market_cap_selection():
    if not stocks.UNIVERSE_PATH.exists():
        pytest.skip("No selected universe stored")
    manifest = json.loads(stocks.UNIVERSE_PATH.read_text())
    assert [row["ticker"] for row in stocks.STOCKS] == manifest["tickers"]
    assert len(stocks.STOCKS) == manifest["count"]
    caps = [row["market_cap"] for row in manifest["ranking"]]
    assert caps == sorted(caps, reverse=True)

from datetime import datetime, timezone

import pandas as pd
import pytest

from financial_dashboard import crypto
from financial_dashboard.market_cap_map import map_html
from financial_dashboard.providers.yahoo import _rows


def markets():
    return [{"id": coin, "name": coin.title(), "symbol": str(i), "market_cap": (30-i)*1e9,
             "current_price": .001, "last_updated": "2026-10-24T00:00:00Z"}
            for i, coin in enumerate(["bitcoin", "ethereum", "binancecoin"] + [f"coin-{i}" for i in range(27)])]


def test_validated_top_30_preserves_legacy_symbols():
    coins = crypto.normalize_markets(markets())
    assert len(coins) == 30
    assert [c["symbol"] for c in coins[:3]] == ["BTC/USD", "ETH/USD", "BNB/USD"]
    assert coins[-1]["symbol"].startswith("CRYPTO:")
    assert [c["market_cap"] for c in coins] == sorted([c["market_cap"] for c in coins], reverse=True)


@pytest.mark.parametrize("kind", ["short", "duplicate", "invalid_cap", "invalid_id"])
def test_reject_incomplete_or_ambiguous_ranking(kind):
    payload = markets()
    if kind == "short": payload.pop()
    if kind == "duplicate": payload[-1]["id"] = "bitcoin"
    if kind == "invalid_cap": payload[-1]["market_cap"] = float("nan")
    if kind == "invalid_id": payload[-1]["id"] = "../escape"
    with pytest.raises(ValueError): crypto.normalize_markets(payload)


def test_local_catalog_builds_all_charts_and_clickable_map(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto, "CATALOG", tmp_path / "market_caps.json")
    monkeypatch.setattr(crypto, "DIRECTORY", tmp_path)
    crypto._save({"coins": crypto.normalize_markets(markets()), "fetched_at": "2026-10-24"})
    monkeypatch.setattr(crypto, "_get", lambda *a, **kw: pytest.fail("Rendering must not fetch data"))
    instruments = crypto.instruments()
    assert len(instruments) == 30
    assert instruments["Coin-0 (3)"]["decimals"] == 8
    html = map_html(crypto.market_caps())
    assert "dashboard_section=Crypto" in html
    assert "chart=Bitcoin" in html
    assert "Coin-0+%283%29" in html
    assert html.count('class="cap-tile') == 30


def test_daily_observations_exclude_incomplete_invalid_and_duplicate_points():
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    stamp = lambda day: datetime(2026, 10, day, tzinfo=timezone.utc).timestamp()*1000
    rows = crypto._chart_rows({"symbol": "CRYPTO:test"}, {"prices": [
        [stamp(23), 2], [stamp(23)+3600000, 3], [stamp(24), -1], [stamp(25), 4]]}, now)
    assert len(rows) == 1 and rows[0].close == 3
    assert rows[0].source == "coingecko_crypto_chart"


def test_yahoo_accepts_explicit_crypto_identity_without_altering_legacy_assets():
    rows = _rows(pd.DataFrame({"Close": [1.25]}, index=pd.to_datetime(["2020-01-01"])),
                 "NEW-USD", asset=("CRYPTO:new", "usd"))
    assert rows[0].symbol == "CRYPTO:new"
    with pytest.raises(ValueError): _rows(pd.DataFrame(), "NEW-USD")


def test_sync_keeps_catalog_on_ranking_failure_and_falls_back_for_new_coin(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto, "DIRECTORY", tmp_path)
    monkeypatch.setattr(crypto, "CATALOG", tmp_path / "market_caps.json")
    coin = {"id": "test", "symbol": "CRYPTO:test", "name": "Test", "ticker": "TST"}
    crypto._save({"coins": [coin], "fetched_at": "previous"})
    def get(path, **kwargs):
        if path == "coins/markets": raise RuntimeError("ranking unavailable")
        return {"prices": [[1577836800000, 1.2]]}
    monkeypatch.setattr(crypto, "_get", get)
    monkeypatch.setattr(crypto, "_yahoo_ticker", lambda coin: "TST-USD")
    monkeypatch.setattr(crypto.db, "load_prices", lambda symbol: pd.DataFrame())
    monkeypatch.setattr(crypto.db, "upsert_prices", lambda rows: len(rows))
    monkeypatch.setattr(crypto.time, "sleep", lambda seconds: None)
    import yfinance
    class EmptyTicker:
        def history(self, **kwargs): return pd.DataFrame()
    monkeypatch.setattr(yfinance, "Ticker", lambda ticker: EmptyTicker())
    results = crypto.sync()
    assert results[0]["status"] == "failed"
    assert results[1]["status"] == "success"
    saved = crypto.load_catalog()
    assert saved["fetched_at"] == "previous"
    assert saved["coins"][0]["history_provider"] == "coingecko_crypto_chart"


def test_incremental_sync_uses_saved_ticker_and_preserves_history_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto, "DIRECTORY", tmp_path)
    monkeypatch.setattr(crypto, "CATALOG", tmp_path / "market_caps.json")
    coin = {"id": "test", "symbol": "CRYPTO:test", "name": "Test", "ticker": "TST",
            "history_provider": "yahoo_finance", "yahoo_ticker": "TST123-USD"}
    crypto._save({"coins": [coin], "fetched_at": "previous"})
    calls = []
    monkeypatch.setattr(crypto, "_get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(crypto.db, "load_prices", lambda symbol: pd.DataFrame({"market_date": pd.to_datetime(["2026-10-24"])}))
    monkeypatch.setattr(crypto.db, "upsert_prices", lambda rows: pytest.fail("Failed fetch must not write"))
    import yfinance
    class FailedTicker:
        def history(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("offline")
    monkeypatch.setattr(yfinance, "Ticker", lambda ticker: FailedTicker())
    results = crypto.sync()
    assert results[1]["status"] == "failed"
    assert calls == [{"interval": "1d", "auto_adjust": False, "start": "2026-10-17"}]
    assert crypto.load_catalog()["coins"][0] == coin

from datetime import date, datetime, timezone

import pytest

from financial_dashboard.db import Price, initialize, load_prices, source_status, sync_run, upsert_prices


def test_upsert_is_idempotent(tmp_path):
    path = tmp_path / "market.db"
    initialize(path)
    row = Price(
        symbol="BTC/USD",
        market_date=date(2026, 9, 19),
        close=100_000,
        currency="USD",
        unit="usd",
        source="test",
        fetched_at=datetime.now(timezone.utc),
    )
    upsert_prices([row], path)
    upsert_prices([row], path)
    frame = load_prices("BTC/USD", path)
    assert len(frame) == 1
    assert frame.iloc[0]["close"] == 100_000


def test_world_bank_monthly_history_stops_when_daily_alpha_history_begins(tmp_path):
    path = tmp_path / "market.db"
    initialize(path)
    fetched_at = datetime.now(timezone.utc)
    upsert_prices(
        [
            Price("XAU/USD", date(2011, 5, 31), 1530, "USD", "usd_per_troy_ounce", "world_bank_pink_sheet", fetched_at),
            Price("XAU/USD", date(2011, 6, 1), 1540, "USD", "usd_per_troy_ounce", "alpha_vantage", fetched_at),
            Price("XAU/USD", date(2011, 6, 30), 1550, "USD", "usd_per_troy_ounce", "world_bank_pink_sheet", fetched_at),
        ],
        path,
    )

    frame = load_prices("XAU/USD", path)

    assert list(frame["market_date"].dt.date) == [date(2011, 5, 31), date(2011, 6, 1)]


def test_daily_spx_csv_supersedes_shiller_until_fred_begins(tmp_path):
    path = tmp_path / "market.db"
    initialize(path)
    fetched_at = datetime.now(timezone.utc)
    upsert_prices(
        [
            Price("SP500", date(2016, 8, 31), 2170, "USD", "index_points", "spx_csv", fetched_at),
            Price("SP500", date(2016, 9, 21), 2163, "USD", "index_points", "spx_csv", fetched_at),
            Price("SP500", date(2016, 8, 31), 2170, "USD", "index_points_monthly", "shiller_monthly", fetched_at),
            Price("SP500", date(2016, 9, 30), 2168, "USD", "index_points_monthly", "shiller_monthly", fetched_at),
            Price("SP500", date(2016, 9, 22), 2177, "USD", "index_points", "fred", fetched_at),
        ],
        path,
    )

    frame = load_prices("SP500", path)

    assert list(frame["source"]) == ["spx_csv", "spx_csv", "fred"]


@pytest.mark.parametrize(
    ("symbol", "archive_source"),
    [
        ("BTC/USD", "blockchain_market_price"),
        ("ETH/USD", "gemini_eth_usd_archive"),
        ("BNB/USD", "binance_bnb_usdt_archive"),
    ],
)
def test_crypto_archive_handoff_to_yahoo(tmp_path, symbol, archive_source):
    path = tmp_path / "market.db"
    initialize(path)
    fetched_at = datetime.now(timezone.utc)
    upsert_prices(
        [
            Price(symbol, date(2020, 1, 1), 10, "USD", "usd", archive_source, fetched_at),
            Price(symbol, date(2020, 1, 2), 11, "USD", "usd", archive_source, fetched_at),
            Price(symbol, date(2020, 1, 3), 12, "USD", "usd", archive_source, fetched_at),
            Price(symbol, date(2020, 1, 2), 21, "USD", "usd", "yahoo_finance", fetched_at),
            Price(symbol, date(2020, 1, 3), 22, "USD", "usd", "coingecko", fetched_at),
        ],
        path,
    )

    frame = load_prices(symbol, path)

    assert frame["source"].tolist() == [archive_source, "yahoo_finance"]
    assert frame["close"].tolist() == [10, 21]


def test_crypto_archive_remains_available_without_yahoo(tmp_path):
    path = tmp_path / "market.db"
    initialize(path)
    fetched_at = datetime.now(timezone.utc)
    upsert_prices(
        [
            Price("ETH/USD", date(2016, 5, 9), 10, "USD", "usd", "gemini_eth_usd_archive", fetched_at),
            Price("ETH/USD", date(2016, 5, 10), 11, "USD", "usd", "gemini_eth_usd_archive", fetched_at),
            Price("ETH/USD", date(2016, 5, 10), 12, "USD", "usd", "coingecko", fetched_at),
        ],
        path,
    )

    frame = load_prices("ETH/USD", path)

    assert set(zip(frame["market_date"].dt.date, frame["source"], strict=True)) == {
        (date(2016, 5, 9), "gemini_eth_usd_archive"),
        (date(2016, 5, 10), "gemini_eth_usd_archive"),
        (date(2016, 5, 10), "coingecko"),
    }


def test_source_status_combines_sync_and_observation_details(tmp_path):
    path = tmp_path / "market.db"
    initialize(path)
    row = Price("USD/IRT", date(2026, 9, 25), 100, "IRT", "toman", "bonbast", datetime.now(timezone.utc))
    upsert_prices([row], path)
    with sync_run("bonbast", "daily", path) as run:
        run["rows_written"] = 1

    status = source_status(path)

    assert status.iloc[0]["source"] == "bonbast"
    assert status.iloc[0]["market_date"].date() == date(2026, 9, 25)
    assert status.iloc[0]["row_count"] == 1

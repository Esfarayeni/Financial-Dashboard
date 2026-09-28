from datetime import date, datetime, timezone

from financial_dashboard.db import Price, initialize, load_prices, upsert_prices


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

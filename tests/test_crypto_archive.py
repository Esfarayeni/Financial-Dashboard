from datetime import datetime, timezone

from financial_dashboard.providers.crypto_archive import _parse_binance_klines


def test_parse_binance_klines_creates_bnb_usd_proxy_prices():
    rows = _parse_binance_klines(
        [[1_500_000_000_000, "", "", "", "12.50"]],
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0].symbol == "BNB/USD"
    assert rows[0].close == 12.5
    assert rows[0].unit == "usd_proxy_usdt"

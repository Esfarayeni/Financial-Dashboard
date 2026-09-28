from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price


URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
SOURCE = "coingecko"


class CoinGeckoError(RuntimeError):
    pass


def _parse(payload: dict[str, Any]) -> list[Price]:
    raw_prices = payload.get("prices")
    if not isinstance(raw_prices, list):
        raise CoinGeckoError("CoinGecko returned an unexpected response")

    fetched_at = datetime.now(timezone.utc)
    by_date: dict[str, Price] = {}
    for item in raw_prices:
        if not isinstance(item, list) or len(item) < 2:
            continue
        timestamp_ms, raw_value = item[0], item[1]
        value = float(raw_value)
        if value <= 0:
            continue
        market_date = datetime.fromtimestamp(float(timestamp_ms) / 1000, tz=timezone.utc).date()
        by_date[market_date.isoformat()] = Price(
            symbol="BTC/USD",
            market_date=market_date,
            close=value,
            currency="USD",
            unit="usd",
            source=SOURCE,
            fetched_at=fetched_at,
        )
    if not by_date:
        raise CoinGeckoError("CoinGecko returned no usable prices")
    return sorted(by_date.values(), key=lambda row: row.market_date)


def fetch(days: str | int, api_key: str = "") -> list[Price]:
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    response = requests.get(
        URL,
        params={"vs_currency": "usd", "days": str(days), "interval": "daily"},
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _parse(response.json())


def fetch_backfill(api_key: str = "") -> list[Price]:
    try:
        return fetch("max", api_key)
    except (requests.RequestException, CoinGeckoError):
        return fetch(365, api_key)


def fetch_latest_completed(api_key: str = "") -> list[Price]:
    rows = fetch(3, api_key)
    today_utc = datetime.now(timezone.utc).date()
    completed = [row for row in rows if row.market_date < today_utc]
    return (completed or rows)[-1:]


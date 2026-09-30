from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any

import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price


URL = "https://www.alphavantage.co/query"
SOURCE = "alpha_vantage"
SYMBOLS = {
    "GOLD": ("XAU/USD", "USD", "usd_per_troy_ounce"),
    "SILVER": ("XAG/USD", "USD", "usd_per_troy_ounce"),
}
BITCOIN_FUNCTION = "DIGITAL_CURRENCY_DAILY"


class AlphaVantageError(RuntimeError):
    pass


def _extract_rows(payload: dict[str, Any], provider_symbol: str) -> list[Price]:
    message = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
    if message:
        raise AlphaVantageError(str(message))

    data = payload.get("data")
    if not isinstance(data, list):
        raise AlphaVantageError("Alpha Vantage returned an unexpected response")

    symbol, currency, unit = SYMBOLS[provider_symbol]
    fetched_at = datetime.now(timezone.utc)
    prices: list[Price] = []
    for item in data:
        if not isinstance(item, dict) or "date" not in item:
            continue
        raw_value = item.get("value", item.get("price", item.get("close")))
        if raw_value in (None, ".", ""):
            continue
        value = float(raw_value)
        if value <= 0:
            continue
        prices.append(
            Price(
                symbol=symbol,
                market_date=date.fromisoformat(str(item["date"])[:10]),
                close=value,
                currency=currency,
                unit=unit,
                source=SOURCE,
                fetched_at=fetched_at,
            )
        )
    if not prices:
        raise AlphaVantageError("Alpha Vantage returned no usable prices")
    return sorted(prices, key=lambda row: row.market_date)


def fetch_history(provider_symbol: str, api_key: str) -> list[Price]:
    response = requests.get(
        URL,
        params={
            "function": "GOLD_SILVER_HISTORY",
            "symbol": provider_symbol,
            "interval": "daily",
            "apikey": api_key,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _extract_rows(response.json(), provider_symbol)


def _extract_bitcoin_rows(payload: dict[str, Any]) -> list[Price]:
    message = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
    if message:
        raise AlphaVantageError(str(message))

    data = payload.get("Time Series (Digital Currency Daily)")
    if not isinstance(data, dict):
        raise AlphaVantageError("Alpha Vantage returned an unexpected Bitcoin response")

    fetched_at = datetime.now(timezone.utc)
    today_utc = fetched_at.date()
    prices: list[Price] = []
    for raw_date, item in data.items():
        if not isinstance(item, dict):
            continue
        market_date = date.fromisoformat(str(raw_date)[:10])
        if market_date >= today_utc:
            continue
        raw_value = item.get("4. close")
        if raw_value in (None, "", "."):
            continue
        value = float(raw_value)
        if value <= 0:
            continue
        prices.append(
            Price(
                symbol="BTC/USD",
                market_date=market_date,
                close=value,
                currency="USD",
                unit="usd",
                source=SOURCE,
                fetched_at=fetched_at,
            )
        )
    if not prices:
        raise AlphaVantageError("Alpha Vantage returned no usable Bitcoin prices")
    return sorted(prices, key=lambda row: row.market_date)


def fetch_bitcoin_history(api_key: str) -> list[Price]:
    response = requests.get(
        URL,
        params={
            "function": BITCOIN_FUNCTION,
            "symbol": "BTC",
            "market": "USD",
            "apikey": api_key,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _extract_bitcoin_rows(response.json())


def fetch_metals(api_key: str, latest_only: bool = False) -> list[Price]:
    prices: list[Price] = []
    for index, provider_symbol in enumerate(SYMBOLS):
        if index:
            time.sleep(1.1)
        rows = fetch_history(provider_symbol, api_key)
        prices.extend(rows[-1:] if latest_only else rows)
    return prices


def fetch_all(api_key: str, latest_only: bool = False) -> list[Price]:
    """Compatibility helper retaining Alpha Vantage's historical BTC import."""
    prices = fetch_metals(api_key, latest_only)
    time.sleep(1.1)
    bitcoin_rows = fetch_bitcoin_history(api_key)
    prices.extend(bitcoin_rows[-1:] if latest_only else bitcoin_rows)
    return prices

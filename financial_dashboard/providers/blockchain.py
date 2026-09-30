from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price


URL = "https://api.blockchain.info/charts/market-price"
SOURCE = "blockchain_market_price"


class BlockchainChartError(RuntimeError):
    pass


def _parse(payload: dict[str, Any]) -> list[Price]:
    values = payload.get("values")
    if not isinstance(values, list):
        raise BlockchainChartError("Blockchain.com returned an unexpected market-price response")

    fetched_at = datetime.now(timezone.utc)
    by_date: dict[str, Price] = {}
    for item in values:
        if not isinstance(item, dict):
            continue
        try:
            market_date = datetime.fromtimestamp(float(item["x"]), tz=timezone.utc).date()
            close = float(item["y"])
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if close <= 0:
            continue
        by_date[market_date.isoformat()] = Price(
            symbol="BTC/USD",
            market_date=market_date,
            close=close,
            currency="USD",
            unit="usd_market_price_index",
            source=SOURCE,
            fetched_at=fetched_at,
        )
    if not by_date:
        raise BlockchainChartError("Blockchain.com returned no usable market-price observations")
    return sorted(by_date.values(), key=lambda row: row.market_date)


def fetch_history() -> list[Price]:
    response = requests.get(
        URL,
        params={"timespan": "all", "format": "json", "sampled": "false"},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _parse(response.json())

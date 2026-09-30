from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from typing import Any

import pandas as pd
import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price


GEMINI_ETH_URL = "https://www.cryptodatadownload.com/cdd/Gemini_ETHUSD_d.csv"
BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
GEMINI_SOURCE = "gemini_eth_usd_archive"
BINANCE_SOURCE = "binance_bnb_usdt_archive"
DAY_MS = 86_400_000


class CryptoArchiveError(RuntimeError):
    pass


def fetch_gemini_ethereum_history() -> list[Price]:
    response = requests.get(
        GEMINI_ETH_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text), skiprows=1)
    if not {"date", "close"}.issubset(frame.columns):
        raise CryptoArchiveError("Gemini ETH/USD archive has an unexpected format")

    fetched_at = datetime.now(timezone.utc)
    prices: list[Price] = []
    for item in frame[["date", "close"]].itertuples(index=False):
        market_date = pd.Timestamp(item.date).date()
        close = float(item.close)
        if close <= 0:
            continue
        prices.append(
            Price(
                symbol="ETH/USD",
                market_date=market_date,
                close=close,
                currency="USD",
                unit="usd",
                source=GEMINI_SOURCE,
                fetched_at=fetched_at,
            )
        )
    if not prices:
        raise CryptoArchiveError("Gemini ETH/USD archive contains no usable prices")
    return sorted({row.market_date: row for row in prices}.values(), key=lambda row: row.market_date)


def _parse_binance_klines(payload: list[Any], fetched_at: datetime) -> list[Price]:
    prices: list[Price] = []
    for item in payload:
        if not isinstance(item, list) or len(item) < 5:
            continue
        market_date = datetime.fromtimestamp(float(item[0]) / 1000, tz=timezone.utc).date()
        close = float(item[4])
        if close <= 0:
            continue
        prices.append(
            Price(
                symbol="BNB/USD",
                market_date=market_date,
                close=close,
                currency="USD",
                unit="usd_proxy_usdt",
                source=BINANCE_SOURCE,
                fetched_at=fetched_at,
            )
        )
    return prices


def fetch_binance_bnb_history() -> list[Price]:
    fetched_at = datetime.now(timezone.utc)
    cursor_ms = int(datetime(2017, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    prices: list[Price] = []
    while True:
        response = requests.get(
            BINANCE_KLINES_URL,
            params={"symbol": "BNBUSDT", "interval": "1d", "startTime": cursor_ms, "limit": 1000},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise CryptoArchiveError("Binance returned an unexpected BNB/USDT response")
        batch = _parse_binance_klines(payload, fetched_at)
        if not batch:
            break
        prices.extend(batch)
        cursor_ms = int(datetime.combine(batch[-1].market_date, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000) + DAY_MS
        if len(payload) < 1000:
            break
    if not prices:
        raise CryptoArchiveError("Binance returned no usable BNB/USDT prices")
    return sorted({row.market_date: row for row in prices}.values(), key=lambda row: row.market_date)

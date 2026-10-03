from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import requests

from ..config import USER_AGENT
from ..db import Price


URL = "https://api.stlouisfed.org/fred/series/observations"
SOURCE = "fred"
SYMBOL = "SP500"
CPI_SYMBOL = "US_INFLATION"
CPI_SERIES = "CPIAUCNS"
TARGET_SYMBOL = "FED_FUNDS_TARGET"
TARGET_SERIES = "DFEDTARU"
HISTORICAL_TARGET_SERIES = "DFEDTAR"
TARGET_RANGE_START = date(2008, 12, 16)
OIL_SYMBOL = "BRENT/USD"
OIL_SERIES = "DCOILBRENTEU"
DOLLAR_SYMBOL = "US_DOLLAR_BROAD"
DOLLAR_SERIES = "DTWEXBGS"
TREASURY_SERIES = {"DGS2": "US_TREASURY_2Y", "DGS10": "US_TREASURY_10Y", "DGS30": "US_TREASURY_30Y"}


class FredError(RuntimeError):
    pass


def _extract_rows(
    payload: dict[str, Any],
    latest_only: bool = False,
    *,
    symbol: str = SYMBOL,
    unit: str = "index_points",
) -> list[Price]:
    if payload.get("error_message"):
        raise FredError(str(payload["error_message"]))
    observations = payload.get("observations")
    if not isinstance(observations, list):
        raise FredError("FRED returned an unexpected response")
    fetched_at = datetime.now(timezone.utc)
    today = fetched_at.date()
    prices: list[Price] = []
    for row in observations:
        if not isinstance(row, dict):
            continue
        try:
            market_date = date.fromisoformat(str(row.get("date", "")))
            close = float(str(row.get("value", "")).strip())
        except (TypeError, ValueError):
            continue
        if market_date >= today or close <= 0:
            continue
        prices.append(
            Price(
                symbol=symbol,
                market_date=market_date,
                close=close,
                currency="USD",
                unit=unit,
                source=SOURCE,
                fetched_at=fetched_at,
            )
        )
    if not prices:
        raise FredError("FRED returned no usable observations")
    prices.sort(key=lambda row: row.market_date)
    return prices[-1:] if latest_only else prices


def fetch_history(api_key: str) -> list[Price]:
    return _extract_rows(_download(api_key))


def fetch_latest_completed(api_key: str) -> list[Price]:
    return _extract_rows(_download(api_key), latest_only=True)


def fetch_cpi_history(api_key: str) -> list[Price]:
    return _extract_rows(
        _download(api_key, CPI_SERIES), symbol=CPI_SYMBOL, unit="cpi_index_1982_1984_100"
    )


def fetch_cpi_latest_completed(api_key: str) -> list[Price]:
    return _extract_rows(
        _download(api_key, CPI_SERIES),
        latest_only=True,
        symbol=CPI_SYMBOL,
        unit="cpi_index_1982_1984_100",
    )


def fetch_target_history(api_key: str) -> list[Price]:
    """Single target before Dec 16, 2008; target range upper limit thereafter."""
    historical = _extract_rows(
        _download(api_key, HISTORICAL_TARGET_SERIES), symbol=TARGET_SYMBOL, unit="percent"
    )
    current = _extract_rows(
        _download(api_key, TARGET_SERIES), symbol=TARGET_SYMBOL, unit="percent"
    )
    return sorted(
        [row for row in historical if row.market_date < TARGET_RANGE_START]
        + [row for row in current if row.market_date >= TARGET_RANGE_START],
        key=lambda row: row.market_date,
    )


def fetch_target_latest_completed(api_key: str) -> list[Price]:
    return _extract_rows(
        _download(api_key, TARGET_SERIES),
        latest_only=True,
        symbol=TARGET_SYMBOL,
        unit="percent",
    )


def fetch_treasury_history(
    api_key: str, series_id: str, observation_start: str | None = None
) -> list[Price]:
    """Daily constant-maturity yields; optionally fetch only recent observations."""
    if series_id not in TREASURY_SERIES:
        raise ValueError("Unsupported Treasury maturity")
    return _extract_rows(
        _download(api_key, series_id, observation_start),
        symbol=TREASURY_SERIES[series_id], unit="percent",
    )


def fetch_oil_history(api_key: str, observation_start: str | None = None) -> list[Price]:
    """Brent crude spot prices in USD per barrel, from EIA via FRED."""
    return _extract_rows(
        _download(api_key, OIL_SERIES, observation_start),
        symbol=OIL_SYMBOL, unit="usd_per_barrel",
    )


def fetch_dollar_history(api_key: str, observation_start: str | None = None) -> list[Price]:
    return _extract_rows(
        _download(api_key, DOLLAR_SERIES, observation_start),
        symbol=DOLLAR_SYMBOL, unit="index_jan_2006_100",
    )


def _download(
    api_key: str, series_id: str = SYMBOL, observation_start: str | None = None
) -> dict[str, Any]:
    params = {
        "series_id": series_id, "api_key": api_key, "file_type": "json", "sort_order": "asc",
    }
    if observation_start:
        params["observation_start"] = observation_start
    response = requests.get(
        URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise FredError("FRED returned an unexpected response")
    return payload

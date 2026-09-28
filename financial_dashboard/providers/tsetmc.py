from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price


URL = "https://cdn.tsetmc.com/api/Index/GetIndexB2History/32097828799138957"
SOURCE = "tsetmc"
SYMBOL = "TEDPIX"


class TSETMCError(RuntimeError):
    pass


def _parse_date(value: object) -> date:
    raw = str(value).strip()
    if len(raw) != 8 or not raw.isdigit():
        raise TSETMCError(f"TSETMC returned an invalid market date: {raw!r}")
    return datetime.strptime(raw, "%Y%m%d").date()


def _close_value(item: dict[str, Any]) -> float:
    # ``xNivInuClM`` is TSETMC's official daily closing level for IndexB2.
    # The alternative names make the parser tolerant to a documented API rename.
    for field in ("xNivInuClM", "indexValue", "close", "value"):
        raw_value = item.get(field)
        if raw_value not in (None, ""):
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise TSETMCError(f"TSETMC returned a non-numeric {field}") from exc
            if value > 0:
                return value
    raise TSETMCError("TSETMC returned an index row without a positive closing level")


def parse_index_history(payload: dict[str, Any], fetched_at: datetime | None = None) -> list[Price]:
    records = payload.get("indexB2")
    if not isinstance(records, list):
        raise TSETMCError("TSETMC returned an unexpected TEDPIX response")

    fetched = fetched_at or datetime.now(timezone.utc)
    by_date: dict[date, Price] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        market_date = _parse_date(item.get("dEven"))
        by_date[market_date] = Price(
            symbol=SYMBOL,
            market_date=market_date,
            close=_close_value(item),
            currency="index_points",
            unit="points",
            source=SOURCE,
            fetched_at=fetched,
        )
    if not by_date:
        raise TSETMCError("TSETMC returned no usable TEDPIX history")
    return [by_date[market_date] for market_date in sorted(by_date)]


def fetch_history() -> list[Price]:
    response = requests.get(
        URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise TSETMCError(
            "TSETMC could not be reached. Its public API may require an Iran-based connection."
        ) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise TSETMCError(
            "TSETMC returned a non-JSON response. Its public API may require an Iran-based connection."
        ) from exc
    if not isinstance(payload, dict):
        raise TSETMCError("TSETMC returned an unexpected TEDPIX response")
    return parse_index_history(payload)


def fetch_latest_completed() -> list[Price]:
    # This endpoint returns the full series in one request; retain only the
    # completed latest observation during the normal daily sync.
    return fetch_history()[-1:]

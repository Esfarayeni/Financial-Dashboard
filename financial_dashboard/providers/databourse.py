from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price


URL = "https://databourse.ir/indices/1"
SOURCE = "databourse"
SYMBOL = "TEDPIX"


class DataBourseError(RuntimeError):
    pass


def jalali_to_gregorian(year: int, month: int, day: int) -> date:
    """Convert a Jalali calendar date to its Gregorian equivalent."""
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise DataBourseError("DataBourse returned an invalid Jalali date")

    jalali_year = year + 1595
    elapsed_days = (
        -355668
        + 365 * jalali_year
        + (jalali_year // 33) * 8
        + ((jalali_year % 33 + 3) // 4)
        + day
    )
    elapsed_days += (month - 1) * 31 if month < 7 else (month - 7) * 30 + 186

    gregorian_year = 400 * (elapsed_days // 146097)
    elapsed_days %= 146097
    if elapsed_days > 36524:
        gregorian_year += 100 * ((elapsed_days - 1) // 36524)
        elapsed_days = (elapsed_days - 1) % 36524
        if elapsed_days >= 365:
            elapsed_days += 1
    gregorian_year += 4 * (elapsed_days // 1461)
    elapsed_days %= 1461
    if elapsed_days > 365:
        gregorian_year += (elapsed_days - 1) // 365
        elapsed_days = (elapsed_days - 1) % 365

    return date(gregorian_year, 1, 1) + timedelta(days=elapsed_days)


def _parse_jalali_date(value: object) -> date:
    match = re.fullmatch(r"(1\d{3})-(\d{2})-(\d{2})", str(value).strip())
    if not match:
        raise DataBourseError(f"DataBourse returned an invalid Jalali date: {value!r}")
    return jalali_to_gregorian(*(int(part) for part in match.groups()))


def parse_index_history(html: str, fetched_at: datetime | None = None) -> list[Price]:
    match = re.search(r"var\s+dataArray\s*=\s*(\[.*?\]);", html, flags=re.DOTALL)
    if not match:
        raise DataBourseError("DataBourse chart data was not found in the response")
    try:
        records = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise DataBourseError("DataBourse chart data was not valid JSON") from exc
    if not isinstance(records, list):
        raise DataBourseError("DataBourse returned an unexpected chart response")

    fetched = fetched_at or datetime.now(timezone.utc)
    by_date: dict[date, Price] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        market_date = _parse_jalali_date(item.get("date"))
        try:
            close = float(item.get("value"))
        except (TypeError, ValueError) as exc:
            raise DataBourseError("DataBourse returned a non-numeric TEDPIX value") from exc
        if close <= 0:
            raise DataBourseError("DataBourse returned a non-positive TEDPIX value")
        by_date[market_date] = Price(
            symbol=SYMBOL,
            market_date=market_date,
            close=close,
            currency="index_points",
            unit="points",
            source=SOURCE,
            fetched_at=fetched,
        )
    if not by_date:
        raise DataBourseError("DataBourse returned no usable TEDPIX history")
    return [by_date[market_date] for market_date in sorted(by_date)]


def fetch_history() -> list[Price]:
    response = requests.get(
        URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return parse_index_history(response.text)


def fetch_latest_completed() -> list[Price]:
    # The page serves the complete chart in one request. Select the final
    # completed Tehran calendar day rather than an in-progress market session.
    tehran_today = datetime.now(timezone(timedelta(hours=3, minutes=30))).date()
    completed = [row for row in fetch_history() if row.market_date < tehran_today]
    if not completed:
        raise DataBourseError("DataBourse returned no completed TEDPIX value")
    return completed[-1:]

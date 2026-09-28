from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price


URL = "https://bonbast.com/graph"
ARCHIVE_URL = "https://raw.githubusercontent.com/SamadiPour/rial-exchange-rates-archive/data/gregorian_imp.min.json"
SOURCE = "bonbast"
GRAPH_SYNC_SOURCE = "bonbast_graph"
ARCHIVE_SYNC_SOURCE = "bonbast_archive"


class BonbastFormatError(ValueError):
    pass


def parse_graph_html(html: str, fetched_at: datetime | None = None) -> list[Price]:
    chart_match = re.search(
        r"var\s+chart\s*=\s*new\s+Chart\(.*?labels\s*:\s*\[(.*?)\]\s*,\s*datasets\s*:\s*\[(.*?)\]\s*}\s*,\s*options",
        html,
        flags=re.DOTALL,
    )
    if not chart_match:
        raise BonbastFormatError("Bonbast chart data was not found in the response")

    label_block, dataset_block = chart_match.groups()
    dates = [
        date.fromisoformat(value)
        for value in re.findall(r"new\s+Date\(['\"](\d{4}-\d{2}-\d{2})['\"]\)", label_block)
    ]
    data_match = re.search(r"data\s*:\s*\[([^\]]*)\]", dataset_block, flags=re.DOTALL)
    if not data_match:
        raise BonbastFormatError("Bonbast price array was not found in the response")

    raw_values = [item.strip() for item in data_match.group(1).split(",") if item.strip()]
    try:
        values = [float(item) for item in raw_values]
    except ValueError as exc:
        raise BonbastFormatError("Bonbast returned a non-numeric price") from exc

    if not dates or len(dates) != len(values):
        raise BonbastFormatError(
            f"Bonbast returned {len(dates)} dates and {len(values)} prices"
        )
    if any(value <= 0 for value in values):
        raise BonbastFormatError("Bonbast returned a zero or negative price")

    fetched = fetched_at or datetime.now(timezone.utc)
    return [
        Price(
            symbol="USD/IRT",
            market_date=market_date,
            close=value,
            currency="IRT",
            unit="toman",
            source=SOURCE,
            fetched_at=fetched,
        )
        for market_date, value in zip(dates, values, strict=True)
    ]


def fetch_range(start_date: date, end_date: date, strict_range: bool = True) -> list[Price]:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    response = requests.post(
        URL,
        data={
            "currency": "usd",
            "stdate": start_date.isoformat(),
            "endate": end_date.isoformat(),
        },
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    rows = parse_graph_html(response.text)
    if strict_range and any(
        row.market_date < start_date or row.market_date > end_date for row in rows
    ):
        raise BonbastFormatError(
            f"Bonbast ignored the requested date range {start_date} to {end_date}"
        )
    return rows


def fetch_backfill() -> list[Price]:
    response = requests.get(
        ARCHIVE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise BonbastFormatError("Bonbast archive returned an unexpected response")

    fetched_at = datetime.now(timezone.utc)
    rows: list[Price] = []
    for raw_date, instruments in payload.items():
        if not isinstance(instruments, dict):
            continue
        usd = instruments.get("usd")
        if not isinstance(usd, dict) or usd.get("sell") in (None, ""):
            continue
        value = float(usd["sell"])
        if value <= 0:
            continue
        rows.append(
            Price(
                symbol="USD/IRT",
                market_date=date.fromisoformat(str(raw_date).replace("/", "-")),
                close=value,
                currency="IRT",
                unit="toman",
                source=SOURCE,
                fetched_at=fetched_at,
            )
        )
    if not rows:
        raise BonbastFormatError("Bonbast archive returned no usable USD prices")
    return sorted(rows, key=lambda row: row.market_date)


def fetch_latest_completed() -> list[Price]:
    # At the scheduled run time Tehran has entered the next calendar day.
    target = datetime.now(timezone(timedelta(hours=3, minutes=30))).date() - timedelta(days=1)
    rows = fetch_range(target - timedelta(days=7), target, strict_range=False)
    completed = [row for row in rows if row.market_date <= target]
    if not completed:
        raise BonbastFormatError("Bonbast returned no completed daily price")
    return completed[-1:]

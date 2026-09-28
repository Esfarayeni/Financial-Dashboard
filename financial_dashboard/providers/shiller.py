from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from io import StringIO

import pandas as pd
import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price


URL = "https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv"
SOURCE = "shiller_monthly"
SYMBOL = "SP500"
START_DATE = date(1960, 1, 1)


class ShillerError(RuntimeError):
    pass


def _extract_rows(text: str) -> list[Price]:
    fetched_at = datetime.now(timezone.utc)
    rows: list[Price] = []
    for row in csv.DictReader(StringIO(text)):
        try:
            month = date.fromisoformat(str(row.get("Date", "")))
            close = float(str(row.get("SP500", "")).strip())
        except (TypeError, ValueError):
            continue
        if month < START_DATE or close <= 0:
            continue
        rows.append(
            Price(
                symbol=SYMBOL,
                market_date=pd.Period(month, freq="M").end_time.date(),
                close=close,
                currency="USD",
                unit="index_points_monthly",
                source=SOURCE,
                fetched_at=fetched_at,
            )
        )
    if not rows:
        raise ShillerError("Shiller monthly dataset contained no usable S&P values")
    return sorted(rows, key=lambda row: row.market_date)


def fetch_history() -> list[Price]:
    response = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return _extract_rows(response.text)

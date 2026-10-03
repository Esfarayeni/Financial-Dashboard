from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
import re

import pandas as pd
import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price


# The World Bank updates this workbook monthly. Its document identifier changes
# occasionally, so keeping it as a single constant makes a future update clear.
MONTHLY_PRICES_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)
SOURCE = "world_bank_pink_sheet"
SHEET_NAME = "Monthly Prices"
SERIES = {
    "Gold": ("XAU/USD", "USD", "usd_per_troy_ounce"),
    "Silver": ("XAG/USD", "USD", "usd_per_troy_ounce"),
    "Copper": ("COPPER/USD", "USD", "usd_per_metric_ton"),
}
MONTH_RE = re.compile(r"^(?P<year>\d{4})M(?P<month>0[1-9]|1[0-2])$")


class WorldBankError(RuntimeError):
    pass


def _market_date(value: object) -> date | None:
    match = MONTH_RE.match(str(value).strip())
    if not match:
        return None
    period = pd.Period(
        year=int(match.group("year")), month=int(match.group("month")), freq="M"
    )
    return period.end_time.date()


def _extract_rows(frame: pd.DataFrame) -> list[Price]:
    header_index = next(
        (
            index
            for index, row in frame.iterrows()
            if {"Gold", "Silver"}.issubset({str(value).strip() for value in row.tolist()})
        ),
        None,
    )
    if header_index is None:
        raise WorldBankError("World Bank workbook did not contain Gold and Silver columns")

    header = frame.iloc[header_index]
    columns = {name: header[header == name].index[0] for name in SERIES if (header == name).any()}
    fetched_at = datetime.now(timezone.utc)
    prices: list[Price] = []

    for _, row in frame.iloc[header_index + 1 :].iterrows():
        market_date = _market_date(row.iloc[0])
        if market_date is None:
            continue
        for name, (symbol, currency, unit) in SERIES.items():
            if name not in columns:
                continue
            raw_value = row.iloc[columns[name]]
            if pd.isna(raw_value) or str(raw_value).strip() in {"", "…", ".."}:
                continue
            try:
                close = float(raw_value)
            except (TypeError, ValueError):
                continue
            if close <= 0:
                continue
            prices.append(
                Price(
                    symbol=symbol,
                    market_date=market_date,
                    close=close,
                    currency=currency,
                    unit=unit,
                    source=SOURCE,
                    fetched_at=fetched_at,
                )
            )

    if not prices:
        raise WorldBankError("World Bank workbook contained no usable gold or silver prices")
    return sorted(prices, key=lambda row: (row.symbol, row.market_date))


def fetch_history() -> list[Price]:
    response = requests.get(
        MONTHLY_PRICES_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    try:
        frame = pd.read_excel(BytesIO(response.content), sheet_name=SHEET_NAME, header=None)
    except Exception as exc:  # pandas normalizes reader-specific failures.
        raise WorldBankError("Could not read the World Bank monthly prices workbook") from exc
    return _extract_rows(frame)


def fetch_copper_history() -> list[Price]:
    return [row for row in fetch_history() if row.symbol == "COPPER/USD"]

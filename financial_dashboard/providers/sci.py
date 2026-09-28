from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price
from .databourse import jalali_to_gregorian


# Public structured mirror of the Statistical Center of Iran's monthly
# national all-household CPI releases. The mirror retains SCI attribution and
# exposes the raw index level, which is necessary for cumulative inflation.
URL = "https://huggingface.co/datasets/Farmaanaa/iran_cpi_statistical_center/resolve/main/cpi_sci.parquet"
SOURCE = "sci"
SYMBOL = "IRAN_INFLATION"


class SciError(RuntimeError):
    pass


def _extract_rows(frame: pd.DataFrame) -> list[Price]:
    required = {"source_id", "freq", "period", "cpi_index"}
    if not required.issubset(frame.columns):
        raise SciError("SCI CPI dataset is missing required columns")

    fetched_at = datetime.now(timezone.utc)
    rows: list[Price] = []
    for record in frame.to_dict("records"):
        if str(record.get("source_id", "")).lower() != "sci" or record.get("freq") != "M":
            continue
        try:
            year_text, month_text = str(record["period"]).split("-", maxsplit=1)
            market_date = jalali_to_gregorian(int(year_text), int(month_text), 1)
            close = float(record["cpi_index"])
        except (TypeError, ValueError, SciError) as exc:
            raise SciError("SCI CPI dataset has an invalid monthly observation") from exc
        if close <= 0:
            raise SciError("SCI CPI dataset has a non-positive index value")
        rows.append(
            Price(
                symbol=SYMBOL,
                market_date=market_date,
                close=close,
                currency="IRR",
                unit="cpi_index_base_1400_100",
                source=SOURCE,
                fetched_at=fetched_at,
            )
        )
    if not rows:
        raise SciError("SCI CPI dataset contained no usable monthly observations")
    return sorted(rows, key=lambda row: row.market_date)


def fetch_history() -> list[Price]:
    response = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    try:
        frame = pd.read_parquet(BytesIO(response.content))
    except Exception as exc:
        raise SciError("SCI CPI dataset was not a readable Parquet file") from exc
    return _extract_rows(frame)


def fetch_latest_completed() -> list[Price]:
    # The public SCI mirror is compact and monthly; one request gets the latest
    # revised observation, while retaining normal refreshes at low frequency.
    return fetch_history()[-1:]

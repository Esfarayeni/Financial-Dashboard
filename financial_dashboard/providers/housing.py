"""Offline, source-linked CBI Tehran transaction-price archive."""
from datetime import datetime, timedelta, timezone
import math

import pandas as pd

from ..config import DATA_DIR
from ..db import Price
from .databourse import jalali_to_gregorian

SOURCE = "cbi_tehran_housing_archive"
SYMBOL = "TEHRAN_HOUSING"
ARCHIVE = DATA_DIR / "housing" / "cbi_tehran_monthly.csv"


def extract_rows(frame: pd.DataFrame) -> list[Price]:
    required = {"jalali_year", "jalali_month", "price_per_m2_toman", "source_url"}
    if not required.issubset(frame.columns):
        raise ValueError("Housing archive is missing required columns")
    rows = []
    seen = set()
    fetched = datetime.now(timezone.utc)
    for record in frame.to_dict("records"):
        year, month = int(record["jalali_year"]), int(record["jalali_month"])
        value = float(record["price_per_m2_toman"])
        if not 1 <= month <= 12 or not math.isfinite(value) or value <= 0:
            raise ValueError("Invalid housing observation")
        if not str(record["source_url"]).startswith("https://"):
            raise ValueError("Housing observation needs a source URL")
        # Label the reporting month at its end, never as a daily quote or
        # publication timestamp. Do not interpolate missing reporting months.
        end = jalali_to_gregorian(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
        if end in seen:
            raise ValueError("Duplicate housing reporting month")
        seen.add(end)
        rows.append(Price(SYMBOL, end, value, "IRT", "toman_per_m2", SOURCE, fetched))
    if not rows:
        raise ValueError("Housing archive is empty")
    return sorted(rows, key=lambda row: row.market_date)


def fetch_history() -> list[Price]:
    return extract_rows(pd.read_csv(ARCHIVE))

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path

from ..db import Price


SOURCE = "spx_csv"
SYMBOL = "SP500"
START_DATE = date(1960, 1, 1)
# FRED's daily SP500 series begins on the following date, so this one-time
# import deliberately stops before it. That leaves a single source of truth
# for every displayed date.
END_DATE = date(2016, 9, 21)


class SpxCsvError(RuntimeError):
    pass


def extract_rows(path: Path) -> list[Price]:
    """Read the supplied daily SPX export, retaining the dashboard's range."""
    fetched_at = datetime.now(timezone.utc)
    rows: list[Price] = []
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                try:
                    market_date = date.fromisoformat(str(row.get("Date", "")))
                    close = float(str(row.get("Close", "")).strip())
                except (TypeError, ValueError):
                    continue
                if not START_DATE <= market_date <= END_DATE or close <= 0:
                    continue
                rows.append(
                    Price(
                        symbol=SYMBOL,
                        market_date=market_date,
                        close=close,
                        currency="USD",
                        unit="index_points",
                        source=SOURCE,
                        fetched_at=fetched_at,
                    )
                )
    except OSError as exc:
        raise SpxCsvError(f"Could not read S&P 500 CSV: {path}") from exc

    if not rows:
        raise SpxCsvError("S&P 500 CSV contained no usable daily closes from 1960 to 2016")
    return sorted(rows, key=lambda row: row.market_date)

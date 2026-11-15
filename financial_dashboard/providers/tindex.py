"""Tindex's dated Tehran asking-price history, kept separate from CBI sales."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import math
import re

import requests

from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..db import Price
from .databourse import jalali_to_gregorian

URL = "https://tindex.app/indicators/housing/average-housing-price-in-tehranm/"
SOURCE = "tindex_tehran_asking"
SYMBOL = "TEHRAN_HOUSING_ASKING"
MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def observation(date_text: str, price_text: str) -> Price:
    date_text = date_text.translate(DIGITS)
    match = re.fullmatch(r"\s*(\d{1,2})\s+(\S+)\s+(\d{4})\s*", date_text)
    if not match or match[2] not in MONTHS:
        raise ValueError("Invalid Tindex observation date")
    day, month, year = int(match[1]), MONTHS.index(match[2]) + 1, int(match[3])
    if not 1 <= day <= (31 if month <= 6 else 30):
        raise ValueError("Invalid Tindex day")
    price = float(price_text.translate(DIGITS).replace("٬", "").replace(",", "").strip())
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Invalid Tindex price")
    return Price(SYMBOL, jalali_to_gregorian(year, month, day), price,
                 "IRT", "toman_per_m2", SOURCE, datetime.now(timezone.utc))


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_history(html: str) -> list[Price]:
    parser = _Tables()
    parser.feed(html)
    close_column = None
    rows = {}
    for cells in parser.rows:
        if "تاریخ" in cells and "پایانی" in cells:
            close_column = cells.index("پایانی")
            continue
        if not cells or not re.match(r"[۰-۹٠-٩0-9]", cells[0]):
            continue
        if close_column is None or len(cells) <= close_column:
            continue
        row = observation(cells[0], cells[close_column])
        if row.market_date in rows and rows[row.market_date].close != row.close:
            raise ValueError("Conflicting Tindex observations")
        rows[row.market_date] = row
    if not rows:
        raise ValueError("Tindex dated closing-price table was not found")
    return sorted(rows.values(), key=lambda row: row.market_date)


def fetch_history() -> list[Price]:
    response = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return parse_history(response.text)


def fetch_latest_completed() -> list[Price]:
    # Public page returns its full compact table in one request; only upsert
    # the latest saved date (possible revision) and newly dated observations.
    from .. import db
    rows = fetch_history()
    stored = db.load_prices(SYMBOL)
    if stored.empty:
        return rows
    cutoff = stored.market_date.max().date()
    return [row for row in rows if row.market_date >= cutoff]

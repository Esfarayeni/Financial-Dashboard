"""Current Nasdaq/NYSE directory, stored locally independently of price history."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re

import requests

DIRECTORY = Path(__file__).with_name("us_listings.json")
SOURCES = {
    "Nasdaq": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "NYSE": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}


def company_name(security_name: str) -> str:
    """Keep the issuer name; retain the full security description separately."""
    company = security_name.split(" - ")[0].strip()
    return re.split(r"\s+(?:American Depositary Shares|American Depository Shares|Common Stock|Common Shares|Ordinary Shares?)\b",
                    company, maxsplit=1, flags=re.I)[0].strip()


def parse_directory(text: str, exchange: str) -> list[dict]:
    """Exclude test issues, ETFs, preferreds, warrants, rights, units and debt."""
    rows = csv.DictReader(io.StringIO(text), delimiter="|")
    required = {"Security Name", "Test Issue", "ETF", "Symbol" if exchange == "Nasdaq" else "ACT Symbol"}
    if not required.issubset(rows.fieldnames or []):
        raise ValueError(f"Invalid {exchange} symbol directory")
    result = []
    excluded = re.compile(r"\b(preferred|preference|warrants?|rights?|units?|debentures?|notes|bonds)\b", re.I)
    for row in rows:
        if row.get("Test Issue") != "N" or row.get("ETF") != "N":
            continue
        if exchange == "NYSE" and row.get("Exchange") != "N":
            continue
        symbol = row.get("Symbol" if exchange == "Nasdaq" else "ACT Symbol", "").strip()
        name = row.get("Security Name", "").strip()
        if not name or excluded.search(name) or not re.fullmatch(r"[A-Z][A-Z0-9]*(?:\.[A-Z])?", symbol):
            continue
        ticker = symbol.replace(".", "-")
        # Directory descriptions often append security type after ' - '.
        company = company_name(name)
        result.append({"ticker": ticker, "name": company, "exchange": exchange,
                       "sector": "Unknown", "company_id": f"listing:{ticker}",
                       "security_name": name})
    return result


def load() -> list[dict]:
    return json.loads(DIRECTORY.read_text())["listings"] if DIRECTORY.exists() else []


def refresh(path: Path = DIRECTORY) -> dict:
    listings = {}
    for exchange, url in SOURCES.items():
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        parsed = parse_directory(response.text, exchange)
        if len(parsed) < 500:
            raise ValueError(f"Suspiciously small {exchange} directory; preserving the existing catalog")
        listings.update({row["ticker"]: row for row in parsed})
    snapshot = {"sources": SOURCES, "retrieved": datetime.now(timezone.utc).isoformat(),
                "listings": sorted(listings.values(), key=lambda row: row["ticker"])}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, indent=2) + "\n")
    temporary.replace(path)
    return snapshot


if __name__ == "__main__":
    from collections import Counter
    snapshot = refresh()
    print(dict(Counter(row["exchange"] for row in snapshot["listings"])))

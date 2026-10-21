"""Persist a market-cap-ranked download universe using Yahoo's bulk screener."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import yfinance as yf

from .config import DATA_DIR

SELECTION_PATH = DATA_DIR / "stocks" / "universe.json"


def largest_stocks(quotes: list[dict], eligible: set[str], count: int) -> list[dict]:
    if count < 1:
        raise ValueError("Count must be positive")
    valid = {}
    for row in quotes:
        ticker, cap = row.get("symbol"), row.get("marketCap")
        if ticker not in eligible or not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap <= 0:
            continue
        valid[ticker] = {"ticker": ticker, "market_cap": cap}
    if len(valid) < count:
        raise ValueError(f"Only {len(valid)} eligible market caps available; need {count}. Selection was not changed.")
    return sorted(valid.values(), key=lambda row: (-row["market_cap"], row["ticker"]))[:count]


def select_largest(count: int = 2000, path: Path = SELECTION_PATH) -> dict:
    from . import listings
    if count < 1:
        raise ValueError("Count must be positive")
    sp500 = json.loads(Path(__file__).with_name("sp500.json").read_text())["constituents"]
    eligible = {stock["ticker"] for stock in [*listings.load(), *sp500]}
    query = yf.EquityQuery("is-in", ["exchange", "NMS", "NGM", "NCM", "NYQ"])
    quotes = []
    offset = 0
    while True:
        response = yf.screen(query, size=250, offset=offset, sortField="intradaymarketcap", sortAsc=False)
        page = response.get("quotes", [])
        if response.get("start") != offset:
            raise ValueError("Screener returned an unexpected page; preserving the existing universe")
        if not page:
            raise ValueError("Screener ended before enough eligible stocks could be ranked")
        quotes.extend(page)
        print(f"Market-cap ranking: {len(quotes)} quotes checked", flush=True)
        try:
            selected = largest_stocks(quotes, eligible, count)
            break
        except ValueError:
            offset += len(page)
            if offset >= response.get("total", offset):
                raise
    now = datetime.now(timezone.utc).isoformat()
    manifest = {"source": "Yahoo Finance equity screener", "retrieved": now,
                "sort": "market cap descending", "count": count,
                "tickers": [row["ticker"] for row in selected], "ranking": selected}
    path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve full profiles and first-trade dates while refreshing cap values.
    metadata_path = path.parent / "metadata.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    for row in selected:
        entry = metadata.setdefault(row["ticker"], {})
        entry.update(market_cap=row["market_cap"], market_cap_updated=now,
                     market_cap_source=manifest["source"])
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(metadata, indent=2) + "\n")
    temporary.replace(metadata_path)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(path)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Select the largest eligible stocks before downloading history")
    parser.add_argument("--count", type=int, default=2000)
    args = parser.parse_args()
    selected = select_largest(args.count)
    print(f"Selected {selected['count']} stocks; smallest selected cap ${selected['ranking'][-1]['market_cap']:,.0f}", flush=True)

"""Saved top-30 circulating-cap universe. Network access is confined to sync()."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import math
import re
import time

import pandas as pd
import requests

from . import db
from .config import DATA_DIR

DIRECTORY = DATA_DIR / "crypto"
CATALOG = DIRECTORY / "market_caps.json"
LEGACY = {"bitcoin": ("Bitcoin", "BTC/USD"), "ethereum": ("Ethereum", "ETH/USD"),
          "binancecoin": ("BNB", "BNB/USD")}
YAHOO = {"bitcoin": "BTC-USD", "ethereum": "ETH-USD", "binancecoin": "BNB-USD",
         "tether": "USDT-USD", "ripple": "XRP-USD", "usd-coin": "USDC-USD",
         "solana": "SOL-USD", "tron": "TRX-USD", "zcash": "ZEC-USD",
         "dogecoin": "DOGE-USD", "monero": "XMR-USD", "chainlink": "LINK-USD",
         "cardano": "ADA-USD", "near": "NEAR-USD", "stellar": "XLM-USD",
         "bitcoin-cash": "BCH-USD", "dai": "DAI-USD", "litecoin": "LTC-USD",
         "uniswap": "UNI7083-USD", "avalanche-2": "AVAX-USD", "sui": "SUI20947-USD"}


def load_catalog():
    if not CATALOG.exists():
        return {"coins": [], "fetched_at": None}
    return json.loads(CATALOG.read_text())


def _save(catalog):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    temporary = CATALOG.with_suffix(".tmp")
    temporary.write_text(json.dumps(catalog, indent=2) + "\n")
    temporary.replace(CATALOG)


def normalize_markets(payload):
    if not isinstance(payload, list) or len(payload) != 30:
        raise ValueError("CoinGecko did not return a complete top-30 ranking")
    coins = []
    for item in payload:
        coin_id = item["id"]
        if not re.fullmatch(r"[a-z0-9-]+", coin_id):
            raise ValueError("Invalid CoinGecko ID")
        cap = float(item["market_cap"])
        if not math.isfinite(cap) or cap <= 0:
            raise ValueError("Missing or invalid circulating market cap")
        label, symbol = LEGACY.get(coin_id, (f'{item["name"]} ({item["symbol"].upper()})', f"CRYPTO:{coin_id}"))
        coins.append({"id": coin_id, "ticker": item["symbol"].upper(), "name": item["name"],
                      "label": label, "symbol": symbol, "market_cap": cap,
                      "price": item.get("current_price"), "image": item.get("image"),
                      "provider_updated_at": item.get("last_updated")})
    if len({coin["id"] for coin in coins}) != 30:
        raise ValueError("Duplicate coins in ranking")
    return sorted(coins, key=lambda coin: coin["market_cap"], reverse=True)


def instruments():
    coins = load_catalog()["coins"]
    if not coins:
        return {label: {"symbol": symbol, "accent": "#2962ff", "decimals": 2}
                for label, symbol in LEGACY.values()}
    result = {}
    for coin in coins:
        price = coin.get("price") or 0
        decimals = 2 if price >= 100 else 4 if price >= 1 else 6 if price >= .01 else 8
        result[coin["label"]] = {"symbol": coin["symbol"], "accent": "#2962ff", "decimals": decimals}
    return result


def market_caps():
    rows = []
    for coin in load_catalog()["coins"]:
        logo_path = DIRECTORY / "logos" / f'{coin["id"]}.png'
        logo = "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode() if logo_path.exists() else None
        rows.append({"Company": coin["name"], "Ticker": coin["ticker"], "Market cap (USD)": coin["market_cap"],
                     "Sector": "Crypto assets", "Industry": "Top 30 by circulating market cap",
                     "Logo": logo, "Section": "Crypto", "Chart name": coin["label"]})
    return pd.DataFrame(rows)


def _get(path, **params):
    response = requests.get("https://api.coingecko.com/api/v3/" + path, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _yahoo_ticker(coin):
    if coin.get("yahoo_ticker") or coin["id"] in YAHOO:
        return coin.get("yahoo_ticker") or YAHOO[coin["id"]]
    import yfinance as yf
    def normalized(name):
        return re.sub(r"[^a-z0-9]", "", name.lower())
    matches = [q["symbol"] for q in yf.Search(coin["name"], max_results=8).quotes
               if q.get("quoteType") == "CRYPTOCURRENCY" and q.get("symbol", "").endswith("-USD")
               and normalized(q.get("shortname", "").removesuffix(" USD")) == normalized(coin["name"])]
    return matches[0] if len(matches) == 1 else None


def _chart_rows(coin, payload, now):
    # CoinGecko's observations are aggregated prices, not exchange closing candles.
    values = {}
    for timestamp, value in payload.get("prices", []):
        date = datetime.fromtimestamp(timestamp / 1000, timezone.utc).date()
        if date < now.date() and value is not None and math.isfinite(value) and value > 0:
            values[date] = float(value)
    if not values:
        raise ValueError("No completed daily observations returned")
    return [db.Price(coin["symbol"], date, value, "USD", "usd", "coingecko_crypto_chart", now)
            for date, value in sorted(values.items())]


def sync(backfill=False, include_legacy=True):
    """Refresh ranking once, then persist each coin independently; retain old data on failures."""
    old = load_catalog()
    previous = {coin["id"]: coin for coin in old["coins"]}
    results = []
    try:
        coins = normalize_markets(_get("coins/markets", vs_currency="usd", order="market_cap_desc",
                                      per_page=30, page=1, sparkline="false"))
        for coin in coins:
            for key in ("yahoo_ticker", "history_provider"):
                if key in previous.get(coin["id"], {}):
                    coin[key] = previous[coin["id"]][key]
        catalog = {"fetched_at": datetime.now(timezone.utc).isoformat(), "coins": coins}
        _save(catalog)
        results.append({"source": "crypto_market_caps", "status": "success", "rows": 30})
    except Exception as error:
        catalog = old
        results.append({"source": "crypto_market_caps", "status": "failed", "rows": 0, "error": str(error)})
    import yfinance as yf
    from .providers.yahoo import _rows
    for coin in catalog["coins"]:
        if include_legacy or coin["id"] not in LEGACY or db.load_prices(coin["symbol"]).empty:
            try:
                stored = db.load_prices(coin["symbol"])
                # Keep the chosen source stable rather than splice unlike observations together.
                try:
                    ticker = None if coin.get("history_provider") == "coingecko_crypto_chart" else _yahoo_ticker(coin)
                except Exception:
                    if not stored.empty or coin["id"] in LEGACY:
                        raise
                    ticker = None
                now = datetime.now(timezone.utc)
                rows = None
                if ticker:
                    kwargs = {"period": "max"} if backfill or stored.empty else {
                        "start": (stored.market_date.iloc[-1].date() - timedelta(days=7)).isoformat()}
                    try:
                        frame = yf.Ticker(ticker).history(interval="1d", auto_adjust=False, **kwargs)
                        rows = _rows(frame, ticker, asset=(coin["symbol"], "usd"))
                        coin.update(yahoo_ticker=ticker, history_provider="yahoo_finance")
                    except Exception:
                        if not stored.empty or coin["id"] in LEGACY:
                            raise  # Do not splice a fallback into established Yahoo history.
                if rows is None:
                    time.sleep(2.1)
                    days = 365 if backfill or stored.empty else min(365, max(2, (now.date() - stored.market_date.iloc[-1].date()).days + 2))
                    rows = _chart_rows(coin, _get(f'coins/{coin["id"]}/market_chart', vs_currency="usd", days=days), now)
                    coin["history_provider"] = "coingecko_crypto_chart"
                count = db.upsert_prices(rows)
                results.append({"source": coin["id"], "status": "success", "rows": count})
                _save(catalog)
            except Exception as error:
                results.append({"source": coin["id"], "status": "failed", "rows": 0, "error": str(error)})
                if isinstance(error, requests.HTTPError) and error.response.status_code == 429:
                    results.append({"source": "crypto_histories", "status": "failed", "rows": 0,
                                    "error": "Rate limited; remaining coins deferred to the next sync"})
                    break
        logo_path = DIRECTORY / "logos" / f'{coin["id"]}.png'
        if not logo_path.exists() and coin.get("image"):
            try:
                from urllib.parse import urlparse
                if urlparse(coin["image"]).hostname not in {"coin-images.coingecko.com", "assets.coingecko.com"}:
                    continue
                response = requests.get(coin["image"], timeout=20)
                response.raise_for_status()
                if response.content.startswith(b"\x89PNG\r\n\x1a\n"):
                    logo_path.parent.mkdir(parents=True, exist_ok=True)
                    logo_path.write_bytes(response.content)
            except requests.RequestException:
                pass  # Logos are optional; identity remains available as text.
    return results


if __name__ == "__main__":
    import argparse
    from filelock import FileLock
    from .config import LOCK_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true")
    args = parser.parse_args()
    db.initialize()
    with FileLock(str(LOCK_PATH), timeout=1):
        outcomes = sync(backfill=args.backfill)
    for outcome in outcomes:
        print(outcome, flush=True)
    raise SystemExit(int(any(row["status"] == "failed" for row in outcomes)))

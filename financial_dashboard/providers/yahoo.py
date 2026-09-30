from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from ..db import Price


SOURCE = "yahoo_finance"
ASSETS = {
    "BTC-USD": ("BTC/USD", "usd"),
    "ETH-USD": ("ETH/USD", "usd"),
    "BNB-USD": ("BNB/USD", "usd"),
}


class YahooFinanceError(RuntimeError):
    pass


def _rows(frame: pd.DataFrame, ticker: str) -> list[Price]:
    if ticker not in ASSETS:
        raise ValueError(f"Unsupported Yahoo Finance ticker: {ticker}")
    if frame.empty or "Close" not in frame:
        raise YahooFinanceError(f"Yahoo Finance returned no close prices for {ticker}")

    symbol, unit = ASSETS[ticker]
    fetched_at = datetime.now(timezone.utc)
    today_utc = fetched_at.date()
    prices: list[Price] = []
    for timestamp, raw_close in frame["Close"].items():
        if pd.isna(raw_close):
            continue
        market_date = pd.Timestamp(timestamp).date()
        close = float(raw_close)
        if market_date >= today_utc or close <= 0:
            continue
        prices.append(
            Price(
                symbol=symbol,
                market_date=market_date,
                close=close,
                currency="USD",
                unit=unit,
                source=SOURCE,
                fetched_at=fetched_at,
            )
        )
    if not prices:
        raise YahooFinanceError(f"Yahoo Finance returned no completed daily prices for {ticker}")
    return prices


def fetch_history(ticker: str) -> list[Price]:
    frame = yf.Ticker(ticker).history(period="max", interval="1d", auto_adjust=False)
    return _rows(frame, ticker)


def fetch_latest_completed(ticker: str) -> list[Price]:
    frame = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
    return _rows(frame, ticker)[-1:]


def fetch_all(latest_only: bool = False) -> list[Price]:
    fetcher = fetch_latest_completed if latest_only else fetch_history
    prices: list[Price] = []
    for ticker in ASSETS:
        prices.extend(fetcher(ticker))
    return prices

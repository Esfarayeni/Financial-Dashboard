"""Local volume snapshots and display aggregation; rendering never fetches data."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

from .config import DATA_DIR

VOLUME_DIR = DATA_DIR / "volumes"


def normalize(frame: pd.DataFrame, today=None) -> pd.DataFrame:
    if frame.empty or "Volume" not in frame:
        raise ValueError("Provider returned no volume history")
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    result = pd.DataFrame({
        "market_date": [pd.Timestamp(day).tz_localize(None).normalize() for day in frame.index],
        "volume": pd.to_numeric(frame["Volume"], errors="coerce").to_numpy(),
    })
    result = result[np.isfinite(result.volume) & (result.volume >= 0) & (result.market_date.dt.date < today)]
    if result.empty:
        raise ValueError("Provider returned no completed-session volume")
    return result.sort_values("market_date").drop_duplicates("market_date", keep="last").reset_index(drop=True)


def _path(symbol: str, directory: Path) -> Path:
    from .stocks import STOCKS
    ticker = symbol.removeprefix("STOCK:")
    if symbol != "SP500" and (not symbol.startswith("STOCK:") or ticker not in {s["ticker"] for s in STOCKS}):
        raise ValueError("Volume is supported only for S&P 500 and catalog stocks")
    return directory / f"{ticker}.parquet"


def load(symbol: str, directory: Path = VOLUME_DIR) -> pd.DataFrame:
    path = _path(symbol, directory)
    return pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=["market_date", "volume"])


def update(symbol: str, backfill: bool = False, directory: Path = VOLUME_DIR) -> int:
    path = _path(symbol, directory)
    old = load(symbol, directory)
    kwargs = {"period": "max"} if backfill or old.empty else {
        "start": (old.market_date.max() - pd.Timedelta(days=14)).date().isoformat()}
    ticker = "^GSPC" if symbol == "SP500" else symbol.removeprefix("STOCK:")
    fresh = normalize(yf.Ticker(ticker).history(**kwargs, interval="1d", auto_adjust=False))
    merged = (fresh if old.empty else pd.concat([old, fresh], ignore_index=True)).drop_duplicates("market_date", keep="last").sort_values("market_date").reset_index(drop=True)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.tmp")
    merged.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)
    return len(fresh)


def synchronize_missing() -> list[dict]:
    """One-time stock-volume backfill, without changing any price snapshots."""
    from .stocks import STOCKS
    symbols = ["SP500", *(f"STOCK:{s['ticker']}" for s in STOCKS)]
    def fetch(symbol):
        if not load(symbol).empty:
            return {"symbol": symbol, "status": "stored"}
        try:
            return {"symbol": symbol, "status": "success", "rows": update(symbol)}
        except Exception as error:
            return {"symbol": symbol, "status": "failed", "error": str(error)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(fetch, symbols))


def for_chart(prices: pd.DataFrame, volumes: pd.DataFrame) -> pd.DataFrame:
    """Weekly totals throughout history; missing volume is never filled with zero."""
    if prices.empty or volumes.empty:
        return pd.DataFrame(columns=["market_date", "volume", "period", "color"])
    ordered = prices[["market_date", "close"]].sort_values("market_date").copy()
    result = ordered.merge(volumes, on="market_date", how="left")
    grouped = result.groupby(result.market_date.dt.to_period("W-FRI"), sort=True)
    bars = grouped.agg(market_date=("market_date", "last"),
                       volume=("volume", lambda values: values.sum(min_count=1)))
    bars["period"] = "Weekly total"
    bars["color"] = np.where(grouped.close.last() >= grouped.close.first(),
                             "rgba(8,153,129,0.65)", "rgba(216,58,70,0.60)")
    return bars.dropna(subset=["volume"]).reset_index(drop=True)


if __name__ == "__main__":
    results = synchronize_missing()
    failures = [row for row in results if row["status"] == "failed"]
    print(f"Volume snapshots: {len(results) - len(failures)}/{len(results)} ready", flush=True)
    for row in failures:
        print(row, flush=True)
    raise SystemExit(bool(failures))

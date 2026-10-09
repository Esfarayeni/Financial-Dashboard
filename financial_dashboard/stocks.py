"""Database-free, compressed stock snapshots; no network access while rendering."""
from __future__ import annotations

import argparse
import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf
from filelock import FileLock

from .config import DATA_DIR
from .analytics import annualized_logarithmic_regression_change

CATALOG = json.loads(Path(__file__).with_name("sp500.json").read_text())
STOCKS = CATALOG["constituents"]
STOCK_DIR = DATA_DIR / "stocks"
INSTRUMENTS = {
    f"{stock['name']} ({stock['ticker']})": {
        "symbol": f"STOCK:{stock['ticker']}", "accent": "#2962ff", "decimals": 2,
    } for stock in STOCKS
}


def _path(ticker: str, directory: Path) -> Path:
    if ticker not in {stock["ticker"] for stock in STOCKS}:
        raise ValueError("Ticker is not in the stock catalog")
    return directory / f"{ticker}.parquet"


def normalize_history(frame: pd.DataFrame, today=None) -> pd.DataFrame:
    """Keep completed NY sessions and both Yahoo Close and dividend-adjusted Close."""
    if frame.empty or not {"Close", "Adj Close"}.issubset(frame.columns):
        raise ValueError("Missing stock close or adjusted close history")
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    result = pd.DataFrame({
        "market_date": [pd.Timestamp(day).tz_localize(None).normalize() for day in frame.index],
        "quote_close": frame["Close"].to_numpy(),
        "adjusted_close": frame["Adj Close"].to_numpy(),
    })
    result = result.dropna()
    result = result[(result.market_date.dt.date < today) &
                    (result.quote_close > 0) & (result.adjusted_close > 0)]
    if result.empty:
        raise ValueError("No completed stock sessions returned")
    return result.sort_values("market_date").drop_duplicates("market_date", keep="last").reset_index(drop=True)


def load_prices(symbol: str, adjusted: bool = True, directory: Path = STOCK_DIR) -> pd.DataFrame:
    path = _path(symbol.removeprefix("STOCK:"), directory)
    if not path.exists():
        return pd.DataFrame(columns=["market_date", "close", "currency", "unit", "source", "fetched_at"])
    frame = pd.read_parquet(path)
    frame["close"] = frame["adjusted_close" if adjusted else "quote_close"]
    frame["currency"], frame["unit"], frame["source"] = "USD", "usd", "yahoo_finance"
    frame["fetched_at"] = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC")
    return frame


def update_stock(ticker: str, backfill: bool = False, directory: Path = STOCK_DIR) -> int:
    path = _path(ticker, directory)
    old = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    start = None if backfill or old.empty else (old.market_date.max() - pd.Timedelta(days=14)).date()
    stock = yf.Ticker(ticker)
    kwargs = {"period": "max"} if start is None else {"start": str(start)}
    history = stock.history(**kwargs, interval="1d", auto_adjust=False, actions=True)
    fresh = normalize_history(history)
    if start is not None:
        # Splits/dividends revise past adjusted prices: refresh the whole series
        # only if overlap values actually changed, not on every daily update.
        overlap = old.merge(fresh, on="market_date", suffixes=("_old", "_new"))
        revised = any(
            ((overlap[f"{col}_old"] - overlap[f"{col}_new"]).abs() > 0.00001).any()
            for col in ("quote_close", "adjusted_close")
        )
        if revised:
            fresh = normalize_history(stock.history(period="max", interval="1d", auto_adjust=False))
            old = pd.DataFrame()
    merged = pd.concat([old, fresh], ignore_index=True).drop_duplicates("market_date", keep="last")
    merged = merged.sort_values("market_date").reset_index(drop=True)
    directory.mkdir(parents=True, exist_ok=True)
    if old.equals(merged):
        return 0
    temporary = path.with_suffix(".parquet.tmp")
    merged.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)
    return len(fresh)


def synchronize(backfill: bool = False, missing_only: bool = False) -> list[dict]:
    def update(stock):
        ticker = stock["ticker"]
        for attempt in range(2):
            try:
                return {"source": f"stock_{ticker}", "status": "success", "rows": update_stock(ticker, backfill)}
            except Exception as exc:
                if attempt == 0:
                    time.sleep(2)
                else:
                    return {"source": f"stock_{ticker}", "status": "failed", "rows": 0,
                            "error": type(exc).__name__}
    with FileLock(str(DATA_DIR / "stocks.lock"), timeout=1):
        with ThreadPoolExecutor(max_workers=3) as pool:
            targets = [s for s in STOCKS if not missing_only or not _path(s["ticker"], STOCK_DIR).exists()]
            return list(pool.map(update, targets))


def update_metadata(directory: Path = STOCK_DIR, missing_only: bool = False) -> list[dict]:
    """Store quote metadata separately; failed lookups preserve existing values."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "metadata.json"
    metadata = json.loads(path.read_text()) if path.exists() else {}
    def fetch(stock):
        ticker = stock["ticker"]
        try:
            info = yf.Ticker(ticker).get_info()
            cap = info.get("marketCap")
            first_trade = info.get("firstTradeDateEpochUtc")
            if first_trade is None and info.get("firstTradeDateMilliseconds") is not None:
                first_trade = info["firstTradeDateMilliseconds"] / 1000
            if cap is None:
                raise ValueError("Missing market capitalization")
            entry = {"market_cap": cap, "updated": datetime.now(ZoneInfo("UTC")).isoformat()}
            if first_trade:
                listing_date = datetime.fromtimestamp(first_trade, ZoneInfo("UTC")).date()
                entry["listing_year"] = listing_date.year
                entry["listing_date"] = listing_date.isoformat()
            else:
                entry["listing_year"] = metadata.get(ticker, {}).get("listing_year")
                entry["listing_date"] = metadata.get(ticker, {}).get("listing_date")
            return ticker, entry, {"source": f"stock_metadata_{ticker}", "status": "success", "rows": 1}
        except Exception as exc:
            return ticker, None, {"source": f"stock_metadata_{ticker}", "status": "failed", "rows": 0,
                                 "error": type(exc).__name__}
    results = []
    targets = [s for s in STOCKS if not missing_only or s["ticker"] not in metadata]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for ticker, entry, result in pool.map(fetch, targets):
            if entry is not None:
                metadata[ticker] = entry
            results.append(result)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(metadata, indent=2) + "\n")
    temporary.replace(path)
    return results


def update_logos(directory: Path = STOCK_DIR) -> list[dict]:
    """Download verified PNG logos once; rendering uses only local assets."""
    logo_dir = directory / "logos"
    logo_dir.mkdir(parents=True, exist_ok=True)

    def fetch(stock):
        ticker = stock["ticker"]
        path = logo_dir / f"{ticker}.png"
        if path.exists():
            return {"source": f"logo_{ticker}", "status": "cached", "rows": 0}
        try:
            response = requests.get(f"https://images.financialmodelingprep.com/symbol/{ticker}.png", timeout=15)
            response.raise_for_status()
            if not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Invalid logo image")
            path.write_bytes(response.content)
            return {"source": f"logo_{ticker}", "status": "success", "rows": 1}
        except Exception as exc:
            return {"source": f"logo_{ticker}", "status": "failed", "rows": 0, "error": type(exc).__name__}

    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(fetch, STOCKS))


def logo_uri(ticker: str, directory: Path = STOCK_DIR) -> str | None:
    path = directory / "logos" / f"{ticker}.png"
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode() if path.exists() else None


def leaderboard(directory: Path = STOCK_DIR) -> pd.DataFrame:
    path = directory / "metadata.json"
    metadata = json.loads(path.read_text()) if path.exists() else {}
    rows = []
    for stock in STOCKS:
        ticker = stock["ticker"]
        frame = load_prices(f"STOCK:{ticker}", directory=directory)
        trend = None
        if len(frame) >= 30:
            try:
                trend = annualized_logarithmic_regression_change(frame, frame.market_date.iloc[0].date())
            except ValueError:
                pass
        entry = metadata.get(ticker, {})
        rows.append({"Logo": logo_uri(ticker, directory), "Company": stock["name"], "Company ID": stock.get("company_id", ticker), "Ticker": ticker, "Trend/year (%)": trend,
                     "Market cap (USD)": entry.get("market_cap"), "Listing year": entry.get("listing_year"),
                     "Listing date": entry.get("listing_date"),
                     "Sector": stock["sector"], "History from": None if frame.empty else frame.market_date.iloc[0].date(),
                     "Price date": None if frame.empty else frame.market_date.iloc[-1].date(),
                     "Cap updated": entry.get("updated")})
    result = pd.DataFrame(rows).sort_values("Trend/year (%)", ascending=False, na_position="last").reset_index(drop=True)
    sector_average = sector_leaderboard(result).set_index("Sector")["Average trend/year (%)"]
    result["Sector avg/year (%)"] = result["Sector"].map(sector_average)
    result.insert(0, "Rank", pd.Series(range(1, len(result) + 1)).where(result["Trend/year (%)"].notna()).astype("Int64"))
    return result


def market_cap_data(ranking: pd.DataFrame) -> pd.DataFrame:
    """Company caps, not index weights; don't count share classes twice."""
    return (ranking[ranking["Market cap (USD)"].notna() & (ranking["Market cap (USD)"] > 0)]
            .sort_values("Market cap (USD)", ascending=False)
            .drop_duplicates("Company ID").copy())


def daily_movers(directory: Path = STOCK_DIR, period: str = "Daily") -> pd.DataFrame:
    """Latest completed-session quote changes; rank only the same session."""
    rows = []
    for stock in STOCKS:
        path = _path(stock["ticker"], directory)
        if not path.exists():
            continue
        frame = pd.read_parquet(path, columns=["market_date", "quote_close"])
        frame = frame.sort_values("market_date").drop_duplicates("market_date", keep="last")
        if len(frame) < 2:
            continue
        latest_date = pd.Timestamp(frame.market_date.iloc[-1])
        offsets = {"Weekly": pd.DateOffset(weeks=1), "Monthly": pd.DateOffset(months=1), "Yearly": pd.DateOffset(years=1)}
        if period == "Daily":
            previous = frame.iloc[-2]
        else:
            history = frame[frame.market_date <= latest_date - offsets[period]]
            if history.empty:
                continue
            previous = history.iloc[-1]
        if previous.quote_close <= 0:
            continue
        change = (frame.quote_close.iloc[-1] / previous.quote_close - 1) * 100
        rows.append({"Name": f"{stock['name']} ({stock['ticker']})", "Change": change,
                     "Date": frame.market_date.iloc[-1]})
    result = pd.DataFrame(rows, columns=["Name", "Change", "Date"])
    if result.empty:
        return result
    return result[result.Date == result.Date.max()].sort_values(["Change", "Name"], ascending=[False, True])


def sector_leaderboard(ranking: pd.DataFrame, as_of=None) -> pd.DataFrame:
    """Equal-weight trends for companies listed at least five calendar years."""
    cutoff = pd.Timestamp(as_of or datetime.now(ZoneInfo("America/New_York")).date()) - pd.DateOffset(years=5)
    companies = ranking.drop_duplicates("Company ID")
    listing = pd.to_datetime(companies.get("Listing date", pd.Series(pd.NaT, index=companies.index)), errors="coerce")
    years = pd.to_numeric(companies["Listing year"], errors="coerce").astype("Int64")
    history = pd.to_datetime(companies.get("History from", pd.Series(pd.NaT, index=companies.index)), errors="coerce")
    # Existing snapshots lack exact listing dates; use matching first-trade
    # history, otherwise year-end conservatively avoids premature eligibility.
    listing = listing.fillna(history.where(history.dt.year == years))
    year_end = pd.to_datetime(years.astype("string") + "-12-31", errors="coerce")
    listing = listing.fillna(year_end)
    eligible = companies[listing <= cutoff]
    result = eligible.groupby("Sector")["Trend/year (%)"].agg(["mean", "count"])
    result = result.reindex(companies.Sector.unique())
    result["count"] = result["count"].fillna(0).astype(int)
    result = result.reset_index()
    result.columns = ["Sector", "Average trend/year (%)", "Companies with trend"]
    result = result.sort_values("Average trend/year (%)", ascending=False, na_position="last").reset_index(drop=True)
    result.insert(0, "Rank", pd.Series(range(1, len(result) + 1)).where(result["Average trend/year (%)"].notna()).astype("Int64"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import/update S&P 500 stock snapshots")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--metadata", action="store_true", help="Update market caps and listing years only")
    parser.add_argument("--logos", action="store_true", help="Download missing company logos")
    parser.add_argument("--missing-only", action="store_true", help="Import only missing stock snapshots/metadata")
    args = parser.parse_args()
    results = update_logos() if args.logos else update_metadata(missing_only=args.missing_only) if args.metadata else synchronize(args.backfill, args.missing_only)
    for result in results:
        print(result)
    raise SystemExit(any(result["status"] == "failed" for result in results))

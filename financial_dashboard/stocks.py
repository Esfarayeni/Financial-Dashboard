"""Database-free, compressed stock snapshots; no network access while rendering."""
from __future__ import annotations

import argparse
import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf
from filelock import FileLock

from .config import DATA_DIR
from . import listings
from .analytics import annualized_logarithmic_regression_change, logarithmic_regression_deviation_stats

CATALOG = json.loads(Path(__file__).with_name("sp500.json").read_text())
SP500_STOCKS = CATALOG["constituents"]
_listed = {stock["ticker"]: stock for stock in listings.load()}
for _stock in SP500_STOCKS:
    _listed[_stock["ticker"]] = {**_listed.get(_stock["ticker"], {}), **_stock}
STOCKS = [_listed[stock["ticker"]] for stock in SP500_STOCKS]
_sp500_tickers = {stock["ticker"] for stock in SP500_STOCKS}
STOCKS.extend(_listed[ticker] for ticker in sorted(_listed) if ticker not in _sp500_tickers)
STOCK_DIR = DATA_DIR / "stocks"
ALL_STOCKS = STOCKS
UNIVERSE_PATH = STOCK_DIR / "universe.json"
if UNIVERSE_PATH.exists():
    _selection = json.loads(UNIVERSE_PATH.read_text())
    _catalog = {stock["ticker"]: stock for stock in ALL_STOCKS}
    _tickers = _selection["tickers"]
    if len(_tickers) != _selection["count"] or len(set(_tickers)) != len(_tickers) or not set(_tickers).issubset(_catalog):
        raise ValueError("Invalid stock universe; refresh the market-cap selection before syncing")
    STOCKS = [_catalog[ticker] for ticker in _tickers]
TICKERS = frozenset(stock["ticker"] for stock in STOCKS)
INSTRUMENTS = {
    f"{stock['name']} ({stock['ticker']})": {
        "symbol": f"STOCK:{stock['ticker']}", "accent": "#2962ff", "decimals": 2,
    } for stock in STOCKS
}
MARKET_CAP_BANDS = (
    ("Mega-cap", 200e9, None, "$200B and above"),
    ("Large-cap", 10e9, 200e9, "$10B to under $200B"),
    ("Mid-cap", 2e9, 10e9, "$2B to under $10B"),
    ("Small-cap", 250e6, 2e9, "$250M to under $2B"),
    ("Micro-cap", 0, 250e6, "Under $250M"),
)


def _path(ticker: str, directory: Path) -> Path:
    if ticker not in TICKERS:
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
    if "Volume" in frame:
        result["volume"] = pd.to_numeric(frame["Volume"], errors="coerce").to_numpy()
        result.loc[result.volume < 0, "volume"] = float("nan")
    result = result.dropna(subset=["market_date", "quote_close", "adjusted_close"])
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


def synchronize(backfill: bool = False, missing_only: bool = False, limit: int | None = None, progress: bool = False,
                workers: int = 3, pause: float = 0) -> list[dict]:
    if workers < 1 or workers > 3 or pause < 0:
        raise ValueError("Use 1–3 workers and a nonnegative pause")
    rate_limited = Event()
    def update(stock):
        ticker = stock["ticker"]
        for attempt in range(2):
            if rate_limited.is_set():
                return {"source": f"stock_{ticker}", "status": "skipped", "rows": 0,
                        "error": "Deferred after Yahoo rate limit; rerun --missing-only later"}
            try:
                if pause:
                    time.sleep(pause)
                return {"source": f"stock_{ticker}", "status": "success", "rows": update_stock(ticker, backfill)}
            except Exception as exc:
                if "ratelimit" in type(exc).__name__.lower() or "too many requests" in str(exc).lower():
                    rate_limited.set()
                    return {"source": f"stock_{ticker}", "status": "failed", "rows": 0, "error": "Yahoo rate limit; remaining downloads deferred"}
                if attempt == 0:
                    time.sleep(2)
                else:
                    return {"source": f"stock_{ticker}", "status": "failed", "rows": 0,
                            "error": f"{type(exc).__name__}: {exc}"}
    with FileLock(str(DATA_DIR / "stocks.lock"), timeout=1):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            targets = [s for s in STOCKS if not missing_only or not _path(s["ticker"], STOCK_DIR).exists()]
            results = []
            targets = targets[:limit]
            for index, result in enumerate(pool.map(update, targets), 1):
                results.append(result)
                if progress and (index % 25 == 0 or index == len(targets)):
                    failures = sum(row["status"] == "failed" for row in results)
                    print(f"Price backfill: {index}/{len(targets)} checked; {failures} failed", flush=True)
            return results


def update_metadata(directory: Path = STOCK_DIR, missing_only: bool = False, limit: int | None = None,
                    stale_days: int | None = None, progress: bool = False,
                    missing_industry: bool = False) -> list[dict]:
    """Store quote metadata separately; failed lookups preserve existing values."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "metadata.json"
    metadata = json.loads(path.read_text()) if path.exists() else {}
    rate_limited = Event()
    def fetch(stock):
        ticker = stock["ticker"]
        if rate_limited.is_set():
            return ticker, None, {"source": f"stock_metadata_{ticker}", "status": "skipped", "rows": 0,
                                  "error": "Deferred after Yahoo rate limit"}
        try:
            info = yf.Ticker(ticker).get_info()
            cap = info.get("marketCap")
            first_trade = info.get("firstTradeDateEpochUtc")
            if first_trade is None and info.get("firstTradeDateMilliseconds") is not None:
                first_trade = info["firstTradeDateMilliseconds"] / 1000
            if cap is None:
                raise ValueError("Missing market capitalization")
            entry = {**metadata.get(ticker, {}), "market_cap": cap,
                     "updated": datetime.now(ZoneInfo("UTC")).isoformat()}
            entry["market_cap_updated"] = entry["updated"]
            entry["market_cap_source"] = "Yahoo Finance"
            if info.get("sector"):
                entry["sector"] = {"Technology": "Information Technology", "Healthcare": "Health Care",
                                   "Financial Services": "Financials", "Basic Materials": "Materials",
                                   "Consumer Cyclical": "Consumer Discretionary", "Consumer Defensive": "Consumer Staples"}.get(info["sector"], info["sector"])
            if isinstance(info.get("industry"), str) and info["industry"].strip():
                entry["industry"] = info["industry"].strip()
                entry["industry_source"] = "Yahoo Finance"
                entry["industry_updated"] = entry["updated"]
            summary = info.get("longBusinessSummary")
            if isinstance(summary, str) and summary.strip():
                entry["business_summary"] = " ".join(summary.split())
                entry["profile_updated"] = entry["updated"]
                entry["profile_source"] = "Yahoo Finance"
                entry.pop("profile_source_url", None)
            if first_trade:
                listing_date = datetime.fromtimestamp(first_trade, ZoneInfo("UTC")).date()
                entry["listing_year"] = listing_date.year
                entry["listing_date"] = listing_date.isoformat()
            else:
                entry["listing_year"] = metadata.get(ticker, {}).get("listing_year")
                entry["listing_date"] = metadata.get(ticker, {}).get("listing_date")
            return ticker, entry, {"source": f"stock_metadata_{ticker}", "status": "success", "rows": 1}
        except Exception as exc:
            if "ratelimit" in type(exc).__name__.lower() or "too many requests" in str(exc).lower():
                rate_limited.set()
            return ticker, None, {"source": f"stock_metadata_{ticker}", "status": "failed", "rows": 0,
                                 "error": type(exc).__name__}
    results = []
    def checkpoint():
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(metadata, indent=2) + "\n")
        temporary.replace(path)
    targets = [s for s in STOCKS if not missing_only or not metadata.get(s["ticker"], {}).get("business_summary")]
    if missing_industry:
        targets = [s for s in targets if not metadata.get(s["ticker"], {}).get("industry")]
    if stale_days is not None:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=stale_days)
        def stale(stock):
            updated = pd.to_datetime(metadata.get(stock["ticker"], {}).get("updated"), utc=True, errors="coerce")
            return pd.isna(updated) or updated < cutoff
        targets = [s for s in targets if stale(s)]
    targets = targets[:limit]
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for ticker, entry, result in pool.map(fetch, targets):
                if entry is not None:
                    metadata[ticker] = entry
                results.append(result)
                if len(results) % 25 == 0:
                    checkpoint()
                if progress and (len(results) % 25 == 0 or len(results) == len(targets)):
                    print(f"Company metadata: {len(results)}/{len(targets)} checked", flush=True)
    finally:
        checkpoint()
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


def summarize_company_profile(text: str) -> str:
    """Extract a business overview and a compact product sentence, without inventing facts."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", " ".join(text.split()))
    if not sentences or not sentences[0]:
        return ""

    def compact(sentence):
        # Long product catalogues use semicolons. Keep complete initial items,
        # not an arbitrary character/word cutoff in the middle of an item.
        parts = sentence.split(";")
        kept = [parts[0]]
        for part in parts[1:3]:
            if len((";".join(kept) + part).split()) > 65:
                break
            kept.append(part)
        result = ";".join(kept).strip()
        return result if result.endswith((".", "!", "?")) else result + "."

    overview = compact(sentences[0])
    candidates = []
    for index, sentence in enumerate(sentences[1:]):
        if re.search(r"\b(founded|headquartered|formerly|incorporated)\b", sentence, re.I):
            continue
        score = 3 * bool(re.search(r"\b(offers|provides|manufactures|develops|sells|brands|products)\b", sentence, re.I))
        score += bool(re.search(r"\b(products|services|platforms|solutions|brands)\b", sentence, re.I))
        candidate = compact(sentence)
        if score and len(candidate.split()) <= 75 and candidate != overview:
            candidates.append((score, -index, candidate))
    return overview + (" " + max(candidates)[2] if candidates else "")


def company_market_cap(ticker: str, directory: Path = STOCK_DIR) -> dict:
    """Latest locally stored company capitalization, independent of chart dates."""
    path = directory / "metadata.json"
    metadata = json.loads(path.read_text()) if path.exists() else {}
    entry = metadata.get(ticker, {})
    raw = entry.get("market_cap")
    try:
        value = float(raw) if not isinstance(raw, bool) else None
    except (TypeError, ValueError):
        value = None
    if value is not None and not 0 < value < float("inf"):
        value = None
    updated = entry.get("market_cap_updated", entry.get("updated"))
    source = entry.get("market_cap_source", "Yahoo Finance")
    # Older quote imports refreshed caps without stamping the cap-specific fields.
    quote_date = pd.to_datetime(entry.get("updated"), utc=True, errors="coerce")
    cap_date = pd.to_datetime(updated, utc=True, errors="coerce")
    if pd.notna(quote_date) and (pd.isna(cap_date) or quote_date > cap_date):
        updated, source = entry["updated"], "Yahoo Finance"
    return {"value": value, "updated": updated, "source": source}


def company_profile(ticker: str, directory: Path = STOCK_DIR) -> dict:
    """Read the full company/product profile locally, never from a live API."""
    path = directory / "metadata.json"
    metadata = json.loads(path.read_text()) if path.exists() else {}
    entry = metadata.get(ticker, {})
    summary = entry.get("business_summary")
    if not isinstance(summary, str) or not summary.strip():
        return {"description": "", "full_description": "", "updated": None, "source": None}
    summary = " ".join(summary.split())
    return {"description": summarize_company_profile(summary), "full_description": summary,
            "updated": entry.get("profile_updated"),
            "source": entry.get("profile_source", "Yahoo Finance"),
            "source_url": entry.get("profile_source_url")}


def leaderboard(directory: Path = STOCK_DIR, half_life_years: float | None = None) -> pd.DataFrame:
    path = directory / "metadata.json"
    metadata = json.loads(path.read_text()) if path.exists() else {}
    rows = []
    for stock in STOCKS:
        ticker = stock["ticker"]
        frame = load_prices(f"STOCK:{ticker}", directory=directory)
        trend = None
        position = None
        average_deviation = None
        percent_deviation = None
        corridor_width = None
        drawdown = None
        if not frame.empty:
            peak = float(frame["close"].max())
            drawdown = (float(frame["close"].iloc[-1]) / peak - 1) * 100
        if len(frame) >= 30:
            try:
                trend = annualized_logarithmic_regression_change(frame, frame.market_date.iloc[0].date(), half_life_years=half_life_years)
                position, average_deviation, percent_deviation, corridor_width = logarithmic_regression_deviation_stats(frame, frame.market_date.iloc[0].date(), half_life_years=half_life_years)
            except ValueError:
                pass
        entry = metadata.get(ticker, {})
        rows.append({"Logo": logo_uri(ticker, directory), "Company": stock["name"], "Company ID": stock.get("company_id", ticker), "Ticker": ticker, "Trend/year (%)": trend,
                     "Trend position": position,
                     "Avg. trend deviation": average_deviation,
                     "Avg. deviation from trend (%)": percent_deviation,
                     "Corridor width / price (%)": corridor_width,
                     "Drawdown from ATH (%)": drawdown,
                     "Market cap (USD)": entry.get("market_cap"), "Listing year": entry.get("listing_year"),
                     "Listing date": entry.get("listing_date"),
                     "Industry": entry.get("industry") or "Industry unavailable",
                     "Sector": stock["sector"] if stock["sector"] != "Unknown" else entry.get("sector", {
                         "Technology": "Information Technology", "Healthcare": "Health Care",
                         "Financial Services": "Financials", "Basic Materials": "Materials",
                         "Consumer Cyclical": "Consumer Discretionary", "Consumer Defensive": "Consumer Staples",
                     }.get(entry.get("industry_sector"), entry.get("industry_sector", "Unknown"))), "Exchange": stock.get("exchange", "Unknown"),
                     "History from": None if frame.empty else frame.market_date.iloc[0].date(),
                     "Price date": None if frame.empty else frame.market_date.iloc[-1].date(),
                     "Cap updated": entry.get("market_cap_updated", entry.get("updated"))})
    result = pd.DataFrame(rows).sort_values("Trend/year (%)", ascending=False, na_position="last").reset_index(drop=True)
    sector_average = sector_leaderboard(result).set_index("Sector")["Average trend/year (%)"]
    result["Sector avg/year (%)"] = result["Sector"].map(sector_average)
    result.insert(0, "Rank", pd.Series(range(1, len(result) + 1)).where(result["Trend/year (%)"].notna()).astype("Int64"))
    return result


def market_cap_data(ranking: pd.DataFrame) -> pd.DataFrame:
    """Company caps, not index weights; don't count share classes twice."""
    values = pd.to_numeric(ranking["Market cap (USD)"], errors="coerce")
    return (ranking.assign(**{"Market cap (USD)": values})[values.gt(0) & values.lt(float("inf"))]
            .sort_values("Market cap (USD)", ascending=False)
            .drop_duplicates("Company ID").copy())


def market_cap_groups(ranking: pd.DataFrame) -> list[tuple[str, str, pd.DataFrame]]:
    """Five disjoint size bands, with positive finite caps and company deduplication."""
    caps = market_cap_data(ranking)
    return [(name, description, caps[caps["Market cap (USD)"].ge(lower) &
              (caps["Market cap (USD)"].lt(upper) if upper is not None else True)].copy())
            for name, lower, upper, description in MARKET_CAP_BANDS]


def industry_cap_groups(ranking: pd.DataFrame, sector: str | None = None) -> list[tuple[str, pd.DataFrame, int]]:
    """Top ten companies per industry across size bands, optionally in one sector."""
    caps = market_cap_data(ranking)
    if sector is not None:
        caps = caps[caps["Sector"].eq(sector)].copy()
    caps["Industry"] = caps["Industry"].fillna("Industry unavailable").replace("", "Industry unavailable")
    return [(name, group.head(10).copy(), len(group))
            for name, group in caps.groupby("Industry", sort=True)]


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
    eligible = companies[(listing <= cutoff) & companies.Sector.ne("Unknown")]
    result = eligible.groupby("Sector")["Trend/year (%)"].agg(["mean", "count"])
    result = result.reindex(companies.Sector.unique())
    result["count"] = result["count"].fillna(0).astype(int)
    result = result.reset_index()
    result.columns = ["Sector", "Average trend/year (%)", "Companies with trend"]
    result = result.sort_values("Average trend/year (%)", ascending=False, na_position="last").reset_index(drop=True)
    result.insert(0, "Rank", pd.Series(range(1, len(result) + 1)).where(result["Average trend/year (%)"].notna()).astype("Int64"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import/update local stock snapshots")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--metadata", action="store_true", help="Update market caps and listing years only")
    parser.add_argument("--logos", action="store_true", help="Download missing company logos")
    parser.add_argument("--missing-only", action="store_true", help="Import only missing stock snapshots/metadata")
    parser.add_argument("--limit", type=int, help="Maximum price downloads this run; combine with --missing-only for resumable batches")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--pause", type=float, default=0, help="Seconds to pause before each price request")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    results = update_logos() if args.logos else update_metadata(missing_only=args.missing_only, limit=args.limit, progress=True) if args.metadata else synchronize(args.backfill, args.missing_only, args.limit, progress=True, workers=args.workers, pause=args.pause)
    for result in results:
        print(result)
    raise SystemExit(any(result["status"] == "failed" for result in results))

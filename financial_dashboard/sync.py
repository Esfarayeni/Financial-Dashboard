from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import timedelta

import pandas as pd
from filelock import FileLock, Timeout

from . import db
from .config import ALPHAVANTAGE_API_KEY, FRED_API_KEY, LOCK_PATH
from .providers import (
    alphavantage,
    blockchain,
    bonbast,
    crypto_archive,
    databourse,
    fred,
    sci,
    shiller,
    worldbank,
    yahoo,
)


def _run_provider(source: str, mode: str, fetcher: Callable):
    try:
        with db.sync_run(source, mode) as run:
            rows = fetcher()
            run["rows_written"] = db.upsert_prices(rows)
            return {"source": source, "status": "success", "rows": run["rows_written"]}
    except Exception as exc:
        return {"source": source, "status": "failed", "rows": 0, "error": str(exc)}


def synchronize(mode: str) -> list[dict]:
    if mode not in {"backfill", "daily"}:
        raise ValueError("mode must be 'backfill' or 'daily'")
    db.initialize()

    results: list[dict] = []
    try:
        with FileLock(str(LOCK_PATH), timeout=1):
            bonbast_fetcher = (
                bonbast.fetch_backfill if mode == "backfill" else bonbast.fetch_latest_completed
            )
            bonbast_sync_source = (
                bonbast.ARCHIVE_SYNC_SOURCE if mode == "backfill" else bonbast.GRAPH_SYNC_SOURCE
            )
            results.append(_run_provider(bonbast_sync_source, mode, bonbast_fetcher))

            tedpix_fetcher = (
                databourse.fetch_history if mode == "backfill" else databourse.fetch_latest_completed
            )
            results.append(_run_provider(databourse.SOURCE, mode, tedpix_fetcher))

            sci_fetcher = sci.fetch_history if mode == "backfill" else sci.fetch_latest_completed
            results.append(_run_provider(sci.SOURCE, mode, sci_fetcher))

            if FRED_API_KEY:
                sp500_fetcher = (
                    (lambda: fred.fetch_history(FRED_API_KEY))
                    if mode == "backfill"
                    else (lambda: fred.fetch_latest_completed(FRED_API_KEY))
                )
                results.append(_run_provider(fred.SOURCE, mode, sp500_fetcher))
                cpi_fetcher = (
                    (lambda: fred.fetch_cpi_history(FRED_API_KEY))
                    if mode == "backfill"
                    else (lambda: fred.fetch_cpi_latest_completed(FRED_API_KEY))
                )
                results.append(_run_provider("fred_cpi", mode, cpi_fetcher))
                target_fetcher = (
                    (lambda: fred.fetch_target_history(FRED_API_KEY))
                    if mode == "backfill"
                    else (lambda: fred.fetch_target_latest_completed(FRED_API_KEY))
                )
                results.append(_run_provider("fred_target", mode, target_fetcher))
                oil_stored = db.load_prices(fred.OIL_SYMBOL) if mode == "daily" else None
                oil_start = (
                    (oil_stored["market_date"].iloc[-1].date() - timedelta(days=7)).isoformat()
                    if oil_stored is not None and not oil_stored.empty else None
                )
                results.append(_run_provider(
                    "fred_oil", mode, lambda: fred.fetch_oil_history(FRED_API_KEY, oil_start),
                ))
                dollar_stored = db.load_prices(fred.DOLLAR_SYMBOL) if mode == "daily" else None
                dollar_start = (
                    (dollar_stored["market_date"].iloc[-1].date() - timedelta(days=7)).isoformat()
                    if dollar_stored is not None and not dollar_stored.empty else None
                )
                results.append(_run_provider(
                    "fred_dollar", mode, lambda: fred.fetch_dollar_history(FRED_API_KEY, dollar_start),
                ))
                for series_id, symbol in fred.TREASURY_SERIES.items():
                    stored = db.load_prices(symbol) if mode == "daily" else None
                    start = (
                        (stored["market_date"].iloc[-1].date() - timedelta(days=7)).isoformat()
                        if stored is not None and not stored.empty else None
                    )
                    results.append(_run_provider(
                        f"fred_{series_id.lower()}", mode,
                        lambda series_id=series_id, start=start: fred.fetch_treasury_history(
                            FRED_API_KEY, series_id, start
                        ),
                    ))
            else:
                reason = "FRED_API_KEY is not configured"
                db.record_skipped(fred.SOURCE, mode, reason)
                results.append({"source": fred.SOURCE, "status": "skipped", "rows": 0, "error": reason})
                db.record_skipped("fred_cpi", mode, reason)
                results.append({"source": "fred_cpi", "status": "skipped", "rows": 0, "error": reason})
                db.record_skipped("fred_target", mode, reason)
                results.append({"source": "fred_target", "status": "skipped", "rows": 0, "error": reason})
                db.record_skipped("fred_oil", mode, reason)
                results.append({"source": "fred_oil", "status": "skipped", "rows": 0, "error": reason})
                db.record_skipped("fred_dollar", mode, reason)
                results.append({"source": "fred_dollar", "status": "skipped", "rows": 0, "error": reason})
                for series_id in fred.TREASURY_SERIES:
                    source = f"fred_{series_id.lower()}"
                    db.record_skipped(source, mode, reason)
                    results.append({"source": source, "status": "skipped", "rows": 0, "error": reason})

            # The Pink Sheet is a long-range, monthly backfill. Daily refreshes
            # remain with the higher-frequency providers already in use.
            if mode == "backfill":
                results.append(_run_provider(worldbank.SOURCE, mode, worldbank.fetch_history))
                results.append(_run_provider(shiller.SOURCE, mode, shiller.fetch_history))
                results.append(_run_provider(blockchain.SOURCE, mode, blockchain.fetch_history))
                results.append(
                    _run_provider(
                        crypto_archive.GEMINI_SOURCE, mode, crypto_archive.fetch_gemini_ethereum_history
                    )
                )
                results.append(
                    _run_provider(
                        crypto_archive.BINANCE_SOURCE, mode, crypto_archive.fetch_binance_bnb_history
                    )
                )

            if mode == "daily":
                copper_stored = db.load_prices("COPPER/USD")
                latest_month = pd.Timestamp.now(tz="UTC").tz_localize(None).to_period("M") - 1
                if copper_stored.empty or copper_stored["market_date"].iloc[-1].to_period("M") < latest_month:
                    results.append(_run_provider("world_bank_copper", mode, worldbank.fetch_copper_history))

            if ALPHAVANTAGE_API_KEY:
                results.append(
                    _run_provider(
                        alphavantage.SOURCE,
                        mode,
                        lambda: alphavantage.fetch_metals(
                            ALPHAVANTAGE_API_KEY, latest_only=mode == "daily"
                        ),
                    )
                )
            else:
                reason = "ALPHAVANTAGE_API_KEY is not configured"
                db.record_skipped(alphavantage.SOURCE, mode, reason)
                results.append(
                    {"source": alphavantage.SOURCE, "status": "skipped", "rows": 0, "error": reason}
                )

            results.append(
                _run_provider(
                    yahoo.SOURCE,
                    mode,
                    lambda: yahoo.fetch_all(latest_only=mode == "daily"),
                )
            )
    except Timeout:
        return [{"source": "all", "status": "failed", "rows": 0, "error": "A sync is already running"}]

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Update the local market database")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--backfill", action="store_true", help="Import all available history")
    group.add_argument("--daily", action="store_true", help="Import the latest completed values")
    args = parser.parse_args()

    results = synchronize("backfill" if args.backfill else "daily")
    for result in results:
        detail = f" ({result.get('error')})" if result.get("error") else ""
        print(f"{result['source']}: {result['status']} — {result['rows']} rows{detail}")
    return 1 if any(result["status"] == "failed" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from .config import DB_PATH


@dataclass(frozen=True)
class Price:
    symbol: str
    market_date: date
    close: float
    currency: str
    unit: str
    source: str
    fetched_at: datetime


def _connection(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def initialize(path: Path = DB_PATH) -> None:
    with _connection(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS prices (
                symbol TEXT NOT NULL,
                market_date TEXT NOT NULL,
                close REAL NOT NULL CHECK (close > 0),
                currency TEXT NOT NULL,
                unit TEXT NOT NULL,
                source TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (symbol, market_date, source)
            );

            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
                rows_written INTEGER NOT NULL DEFAULT 0,
                error TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sync_runs_source_started
            ON sync_runs(source, started_at DESC);
            """
        )
        conn.execute(
            "UPDATE prices SET source = 'bonbast' WHERE source = 'bonbast_graph'"
        )
        # DataBourse replaced the geo-restricted TSETMC import for TEDPIX.
        # Avoid duplicate daily points if an earlier TSETMC backfill succeeded.
        conn.execute("DELETE FROM prices WHERE symbol = 'TEDPIX' AND source = 'tsetmc'")
        # Alpha Vantage is now the preferred long-history BTC source. Remove the
        # old one-year fallback only after the replacement series exists.
        conn.execute(
            """
            DELETE FROM prices
            WHERE symbol = 'BTC/USD'
              AND source = 'coingecko'
              AND EXISTS (
                  SELECT 1 FROM prices
                  WHERE symbol = 'BTC/USD' AND source = 'alpha_vantage'
              )
            """
        )
        conn.execute("PRAGMA optimize")


def upsert_prices(prices: Iterable[Price], path: Path = DB_PATH) -> int:
    rows = list(prices)
    if not rows:
        return 0
    with _connection(path) as conn:
        conn.executemany(
            """
            INSERT INTO prices (
                symbol, market_date, close, currency, unit, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, market_date, source) DO UPDATE SET
                close=excluded.close,
                currency=excluded.currency,
                unit=excluded.unit,
                fetched_at=excluded.fetched_at
            """,
            [
                (
                    row.symbol,
                    row.market_date.isoformat(),
                    row.close,
                    row.currency,
                    row.unit,
                    row.source,
                    row.fetched_at.astimezone(timezone.utc).isoformat(),
                )
                for row in rows
            ],
        )
    return len(rows)


def load_prices(symbol: str, path: Path = DB_PATH) -> pd.DataFrame:
    with _connection(path) as conn:
        frame = pd.read_sql_query(
            """
            WITH alpha_start AS (
                SELECT MIN(market_date) AS market_date
                FROM prices
                WHERE symbol = ? AND source = 'alpha_vantage'
            ), fred_start AS (
                SELECT MIN(market_date) AS market_date
                FROM prices
                WHERE symbol = ? AND source = 'fred'
            ), spx_csv_coverage AS (
                SELECT MIN(market_date) AS start_date, MAX(market_date) AS end_date
                FROM prices
                WHERE symbol = ? AND source = 'spx_csv'
            )
            SELECT p.market_date, p.close, p.currency, p.unit, p.source, p.fetched_at
            FROM prices AS p
            CROSS JOIN alpha_start AS alpha
            CROSS JOIN fred_start AS fred
            CROSS JOIN spx_csv_coverage AS spx_csv
            WHERE p.symbol = ?
              -- Do not interleave monthly averages with the existing daily
              -- Alpha Vantage series. The Pink Sheet fills only the earlier gap.
              AND NOT (
                  p.source = 'world_bank_pink_sheet'
                  AND alpha.market_date IS NOT NULL
                  AND p.market_date >= alpha.market_date
              )
              AND NOT (
                  p.source = 'shiller_monthly'
                  AND fred.market_date IS NOT NULL
                  AND p.market_date >= fred.market_date
              )
              -- A user-provided daily SPX export supersedes the lower-frequency
              -- Shiller segment for the exact dates it covers.
              AND NOT (
                  p.source = 'shiller_monthly'
                  AND spx_csv.start_date IS NOT NULL
                  AND p.market_date BETWEEN spx_csv.start_date AND spx_csv.end_date
              )
              -- FRED remains authoritative from its first daily observation.
              AND NOT (
                  p.source = 'spx_csv'
                  AND fred.market_date IS NOT NULL
                  AND p.market_date >= fred.market_date
              )
            ORDER BY p.market_date
            """,
            conn,
            params=(symbol, symbol, symbol, symbol),
            parse_dates=["market_date", "fetched_at"],
        )
    return frame


def latest_sync(path: Path = DB_PATH) -> sqlite3.Row | None:
    with _connection(path) as conn:
        return conn.execute(
            """
            SELECT source, mode, finished_at, status, rows_written, error
            FROM sync_runs
            WHERE status != 'running'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()


def source_status(path: Path = DB_PATH) -> pd.DataFrame:
    """Return latest sync and latest stored observation for each source."""
    with _connection(path) as conn:
        return pd.read_sql_query(
            """
            WITH latest_runs AS (
                SELECT source, finished_at, status, rows_written, error,
                       ROW_NUMBER() OVER (PARTITION BY source ORDER BY id DESC) AS rank
                FROM sync_runs WHERE status != 'running'
            ), observations AS (
                SELECT source, MAX(market_date) AS market_date, COUNT(*) AS row_count
                FROM prices GROUP BY source
            )
            SELECT COALESCE(r.source, o.source) AS source, r.finished_at, r.status,
                   r.rows_written, r.error, o.market_date, COALESCE(o.row_count, 0) AS row_count
            FROM latest_runs AS r FULL OUTER JOIN observations AS o ON r.source = o.source
            WHERE r.rank = 1 OR r.rank IS NULL
            ORDER BY source
            """,
            conn,
            parse_dates=["finished_at", "market_date"],
        )


@contextmanager
def sync_run(source: str, mode: str, path: Path = DB_PATH):
    started_at = datetime.now(timezone.utc).isoformat()
    with _connection(path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO sync_runs (source, mode, started_at, status)
            VALUES (?, ?, ?, 'running')
            """,
            (source, mode, started_at),
        )
        run_id = cursor.lastrowid

    result = {"rows_written": 0, "status": "success", "error": None}
    try:
        yield result
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)[:1000]
        raise
    finally:
        with _connection(path) as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, status = ?, rows_written = ?, error = ?
                WHERE id = ?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    result["status"],
                    result["rows_written"],
                    result["error"],
                    run_id,
                ),
            )


def record_skipped(source: str, mode: str, reason: str, path: Path = DB_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connection(path) as conn:
        conn.execute(
            """
            INSERT INTO sync_runs (
                source, mode, started_at, finished_at, status, rows_written, error
            ) VALUES (?, ?, ?, ?, 'skipped', 0, ?)
            """,
            (source, mode, now, now, reason),
        )

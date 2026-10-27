"""One-time, audited USD2Rials CSV extension strictly before Bonbast coverage."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil

import pandas as pd

from filelock import FileLock

from . import db
from .config import DATA_DIR, DB_PATH, LOCK_PATH
from .providers.databourse import jalali_to_gregorian

ARCHIVE = DATA_DIR / "usd_irt_history"
DEFAULT_CSV = ARCHIVE / "USD2Rials.csv"
SOURCE_PREFIX = "usd2rials_"


def with_regression_weights(frame: pd.DataFrame) -> pd.DataFrame:
    """Calendar-duration base weights, in years, without expanding observations.

    Coarse observations represent their declared Persian calendar period. Daily
    observations cover short preceding quote gaps (up to seven days), never a
    future gap. Longer outages receive one day rather than invented coverage.
    Channel selection subsequently selects observations, not fractional periods.
    """
    result = frame.sort_values("market_date").copy()
    dates = pd.to_datetime(result.market_date)
    days = dates.diff().dt.total_seconds().div(86400).fillna(1)
    days = days.where(days.between(1, 7), 1)
    for index, row in result.iterrows():
        if row.unit not in {"toman_annual_average", "toman_monthly_average"}:
            continue
        end = pd.Timestamp(row.market_date).date()
        found = False
        for year in (end.year - 622, end.year - 621):
            months = (1,) if row.unit == "toman_annual_average" else range(1, 13)
            for month in months:
                start = jalali_to_gregorian(year, month, 1)
                following = (jalali_to_gregorian(year + 1, 1, 1)
                             if row.unit == "toman_annual_average" or month == 12
                             else jalali_to_gregorian(year, month + 1, 1))
                if following - timedelta(days=1) == end:
                    days.loc[index] = (following - start).days
                    found = True
                    break
            if found:
                break
        if not found:
            raise ValueError(f"Invalid Persian period-end observation: {end}")
    result["regression_weight"] = days / 365.25
    return result


def prepare(path: Path, cutoff: date) -> tuple[list[db.Price], dict]:
    """Validate all rows before writing. Annual/monthly observations use period end.

    Only the audited BourseView ranges are collapsed: 1360–1363 annual and
    1364–1379 monthly. Their repeated values must agree within each period.
    Persian dates are canonical; Gregorian discrepancies are counted, not used.
    """
    now = datetime.now(timezone.utc)
    groups = {}
    seen = {}
    report = {"input_rows": 0, "duplicate_rows": 0, "gregorian_mismatches": 0,
              "excluded_at_or_after_bonbast": 0, "bonbast_start": cutoff.isoformat()}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or []) != {"date_pr", "date_gr", "source", "price_avg"}:
            raise ValueError("Unexpected USD2Rials CSV columns")
        for raw in reader:
            report["input_rows"] += 1
            year, month, day = map(int, raw["date_pr"].split("/"))
            observed = jalali_to_gregorian(year, month, day)
            gregorian = datetime.strptime(raw["date_gr"], "%Y/%m/%d" if len(raw["date_gr"].split("/")[0]) == 4 else "%m/%d/%Y").date()
            report["gregorian_mismatches"] += int(gregorian != observed)
            price = float(raw["price_avg"].replace(",", "")) / 10
            source = raw["source"].strip()
            if source not in {"bourseview", "tgju"} or not math.isfinite(price) or price <= 0:
                raise ValueError(f"Invalid price or source at {raw['date_pr']}")
            if observed in seen:
                if seen[observed] != (price, source):
                    raise ValueError(f"Conflicting duplicate at {observed}")
                report["duplicate_rows"] += 1
                continue
            seen[observed] = (price, source)
            if observed >= cutoff:
                report["excluded_at_or_after_bonbast"] += 1
                continue
            if source == "bourseview" and 1360 <= year <= 1363:
                period_date = jalali_to_gregorian(year + 1, 1, 1) - timedelta(days=1)
                frequency = "annual_average"
            elif source == "bourseview" and 1364 <= year <= 1379:
                period_date = (jalali_to_gregorian(year + 1, 1, 1) if month == 12
                               else jalali_to_gregorian(year, month + 1, 1)) - timedelta(days=1)
                frequency = "monthly_average"
            else:
                period_date = observed
                frequency = "midpoint" if source == "tgju" else "observation"
            if period_date >= cutoff:
                continue
            key = (period_date, source, frequency)
            if key in groups and groups[key] != price:
                raise ValueError(f"Multiple prices in assumed {frequency} period ending {period_date}")
            groups[key] = price
    rows = [db.Price("USD/IRT", day, price, "IRT", f"toman_{frequency}",
                     f"{SOURCE_PREFIX}{source}_{frequency}", now)
            for (day, source, frequency), price in sorted(groups.items())]
    if not rows or len({row.market_date for row in rows}) != len(rows):
        raise ValueError("No usable extension, or overlapping observation dates")
    report.update(imported_observations=len(rows), first_observation=rows[0].market_date.isoformat(),
                  last_observation=rows[-1].market_date.isoformat(),
                  observations_by_source=dict(Counter(row.source for row in rows)),
                  original_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  date_policy="Persian date canonical; annual/monthly values at Persian period end",
                  units="Original IRR divided by 10 to Toman; no interpolation",
                  provenance="User-supplied USD2Rials.csv; source labels BourseView/TGJU. Early primary methodology unverified.")
    return rows, report


def import_history(path: Path, database: Path = DB_PATH, archive: Path = ARCHIVE) -> dict:
    with db._connection(database) as conn:
        first = conn.execute("SELECT MIN(market_date) FROM prices WHERE symbol='USD/IRT' AND source LIKE 'bonbast%'").fetchone()[0]
    if first is None:
        raise ValueError("Import Bonbast first; its actual first date determines the cutoff")
    rows, report = prepare(path, date.fromisoformat(first))
    with db.sync_run("usd2rials_csv", "backfill", path=database) as run:
        run["rows_written"] = db.upsert_prices(rows, database)
    archive.mkdir(parents=True, exist_ok=True)
    saved = archive / "USD2Rials.csv"
    if path.resolve() != saved.resolve():
        shutil.copyfile(path, saved)
    (archive / "import_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    db.initialize()
    with FileLock(str(LOCK_PATH), timeout=1):
        print(json.dumps(import_history(args.path), indent=2))

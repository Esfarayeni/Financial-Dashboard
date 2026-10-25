"""Portable, data-versioned leaderboard snapshots; calculations stay off the UI path."""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
from filelock import FileLock

from . import stocks

HALF_LIVES = (None, 1 / 12, 0.25, 0.5, 1, 2, 3, 5)


def _stamps(paths):
    return tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns,
                  path.stat().st_ctime_ns) for path in paths if path.exists())


@lru_cache(maxsize=8)
def _content_digest(stamps, catalog):
    digest = sha256(catalog.encode())
    for name, *_ in stamps:
        path = Path(name)
        digest.update(path.name.encode())
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def input_signature(directory=stocks.STOCK_DIR):
    """Stat scans are cheap; content hashing runs only when input files change.

    Hashes (not file mtimes) are stored, so Git checkout/restarts don't invalidate
    identical datasets. Code and the selected stock catalog are inputs as well.
    """
    directory = Path(directory)
    paths = [directory / "metadata.json", *(directory / f"{s['ticker']}.parquet" for s in stocks.STOCKS)]
    paths.extend(Path(__file__).with_name(name) for name in ("analytics.py", "stocks.py", "leaderboard_cache.py"))
    return _content_digest(_stamps(paths), json.dumps(stocks.STOCKS, sort_keys=True))


def _snapshot_path(directory, half_life_years):
    if half_life_years not in HALF_LIVES:
        raise ValueError("Unsupported leaderboard half-life")
    key = "equal" if half_life_years is None else f"half_life_{half_life_years:g}"
    return Path(directory) / "leaderboards" / f"{key}.parquet"


def _read(path, signature):
    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError, pa.ArrowInvalid):
        return None
    return frame if frame.attrs.get("input_signature") == signature else None


def load(half_life_years=None, directory=stocks.STOCK_DIR):
    """Read saved metrics, calculating only a genuinely missing/outdated variant."""
    signature = input_signature(directory)
    path = _snapshot_path(directory, half_life_years)
    frame = _read(path, signature)
    if frame is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=180):
            frame = _read(path, signature)
            if frame is None:
                frame = stocks.leaderboard(directory, half_life_years)
                # Don't publish results if a concurrent data update changed inputs.
                if input_signature(directory) != signature:
                    raise RuntimeError("Stock data changed during calculation; reload after the update finishes")
                frame.attrs["input_signature"] = signature
                temporary = path.with_suffix(".parquet.tmp")
                frame.to_parquet(temporary, index=False)
                temporary.replace(path)
    # Eligibility for sector averages ages by calendar date, not by price update.
    averages = stocks.sector_leaderboard(frame).set_index("Sector")["Average trend/year (%)"]
    frame["Sector avg/year (%)"] = frame["Sector"].map(averages)
    return frame


def precompute(directory=stocks.STOCK_DIR):
    for half_life in HALF_LIVES:
        frame = load(half_life, directory)
        print(f"Leaderboard ready: half-life={half_life}, {len(frame)} stocks", flush=True)
    return len(HALF_LIVES)


if __name__ == "__main__":
    precompute()

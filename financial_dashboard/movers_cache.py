"""Persist period rankings so gainers/losers don't scan histories during rendering."""
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pyarrow as pa
from filelock import FileLock

from . import leaderboard_cache, stocks

PERIODS = ("Daily", "Weekly", "Monthly", "Yearly")


def input_signature(directory=stocks.STOCK_DIR):
    # Reuse the leaderboard's memoized content hash, including prices and catalog.
    # This module's code is an additional input, without invalidating leaderboards.
    return sha256(leaderboard_cache.input_signature(directory).encode()
                  + Path(__file__).read_bytes()).hexdigest()


def _read(path, signature):
    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError, pa.ArrowInvalid):
        return None
    return frame if frame.attrs.get("input_signature") == signature else None


def load(period="Daily", directory=stocks.STOCK_DIR):
    if period not in PERIODS:
        raise ValueError("Unsupported movers period")
    signature = input_signature(directory)
    path = Path(directory) / "leaderboards" / f"movers_{period.lower()}.parquet"
    frame = _read(path, signature)
    if frame is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=180):
            frame = _read(path, signature)
            if frame is None:
                frame = stocks.daily_movers(directory, period)
                if input_signature(directory) != signature:
                    raise RuntimeError("Stock data changed during calculation; reload after the update finishes")
                frame.attrs["input_signature"] = signature
                temporary = path.with_suffix(".parquet.tmp")
                frame.to_parquet(temporary, index=False)
                temporary.replace(path)
    return frame


def precompute(directory=stocks.STOCK_DIR):
    for period in PERIODS:
        frame = load(period, directory)
        print(f"Movers ready: {period}, {len(frame)} stocks", flush=True)
    return len(PERIODS)


if __name__ == "__main__":
    precompute()

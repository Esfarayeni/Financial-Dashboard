from __future__ import annotations

import pandas as pd


def latest_change(frame: pd.DataFrame, symbol: str) -> dict:
    """Raw latest observation and previous-period change; never cumulative."""
    if frame.empty:
        return {"latest": None, "change": None, "basis": "No stored data", "previous_date": None}
    ordered = frame.sort_values("market_date").drop_duplicates("market_date", keep="last")
    latest = ordered.iloc[-1]
    monthly = symbol in {"US_INFLATION", "IRAN_INFLATION", "COPPER/USD"} or latest["source"] == "world_bank_pink_sheet"
    rate = symbol == "FED_FUNDS_TARGET" or symbol.startswith("US_TREASURY_")
    basis = "Monthly" if monthly else "Previous observation"
    if len(ordered) < 2:
        return {"latest": latest, "change": None, "basis": basis, "previous_date": None}
    previous = ordered.iloc[-2]
    absolute = float(latest["close"]) - float(previous["close"])
    change = absolute * 100 if rate else absolute / float(previous["close"]) * 100 if previous["close"] != 0 else None
    return {"latest": latest, "change": change, "basis": basis,
            "previous_date": previous["market_date"], "unit": "bp" if rate else "%"}

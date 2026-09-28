"""Source freshness and display status helpers."""

from __future__ import annotations

from datetime import date

import pandas as pd


SOURCE_CADENCE_DAYS = {
    "bonbast": 3,
    "bonbast_graph": 3,
    "bonbast_archive": 3,
    "databourse": 4,
    "fred": 4,
    "fred_cpi": 45,
    "sci": 45,
    "alpha_vantage": 4,
    "coingecko": 3,
    "world_bank_pink_sheet": 45,
    "shiller_monthly": 45,
    "spx_csv": 4,
}


def expected_cadence(source: str) -> str:
    """Return the human-readable expected publication cadence for a source."""
    return "monthly" if SOURCE_CADENCE_DAYS.get(source, 4) > 10 else "daily"


def freshness_status(
    market_date: date | pd.Timestamp | None,
    source: str,
    today: date | None = None,
) -> tuple[str, str]:
    """Return a status and a transparent observation-based freshness label.

    Freshness deliberately uses the latest market observation, rather than the
    time the dashboard last happened to fetch it. This tolerates market
    weekends and monthly publication lags while revealing genuinely stale data.
    """
    cadence = expected_cadence(source)
    if market_date is None or pd.isna(market_date):
        return "missing", f"No observations (expected {cadence})"
    observation_date = pd.Timestamp(market_date).date()
    reference_date = today or date.today()
    age_days = max((reference_date - observation_date).days, 0)
    allowed_age = SOURCE_CADENCE_DAYS.get(source, 4)
    status = "current" if age_days <= allowed_age else "stale"
    return status, f"Latest observation: {observation_date:%b %-d, %Y} (expected {cadence})"

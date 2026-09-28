from __future__ import annotations

import math
from datetime import date

import pandas as pd


def period_change(frame: pd.DataFrame, days: int | None) -> tuple[float, float]:
    """Return absolute and percentage change from a prior observation.

    ``days=None`` compares with the immediately preceding observation. Calendar
    periods use the most recent observation on or before the target date.
    """
    if len(frame) < 2:
        return 0.0, 0.0

    latest = frame.iloc[-1]
    if days is None:
        reference = frame.iloc[-2]
    else:
        target = pd.Timestamp(latest["market_date"]) - pd.to_timedelta(days, unit="D")
        candidates = frame[frame["market_date"] <= target]
        reference = candidates.iloc[-1] if not candidates.empty else frame.iloc[0]

    absolute = float(latest["close"] - reference["close"])
    reference_value = float(reference["close"])
    percentage = absolute / reference_value * 100 if reference_value else 0.0
    return absolute, percentage


def year_over_year_change(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert a monthly index series to the conventional annual inflation rate."""
    result = frame.sort_values("market_date").copy()
    prior_year = result["close"].shift(12)
    result["close"] = (result["close"] / prior_year - 1) * 100
    return result.dropna(subset=["close"]).reset_index(drop=True)


def rebased_price_level(frame: pd.DataFrame, start_date: date | pd.Timestamp) -> pd.DataFrame:
    """Rebase a positive price index to 1.00 at the first observation on/after start."""
    start = pd.Timestamp(start_date)
    result = frame.loc[frame["market_date"] >= start].sort_values("market_date").copy()
    if result.empty:
        raise ValueError("Select a start date within the available CPI history")
    base = float(result.iloc[0]["close"])
    if base <= 0:
        raise ValueError("The selected CPI starting value must be positive")
    result["close"] = result["close"] / base
    return result.reset_index(drop=True)


def _fit_logarithmic_regression(
    frame: pd.DataFrame,
    start_date: date | pd.Timestamp,
    minimum_observations: int = 30,
) -> tuple[pd.DataFrame, pd.Series, float]:
    """Return selected data, fitted log prices, and the daily slope."""
    start = pd.Timestamp(start_date)
    selected = frame.loc[frame["market_date"] >= start, ["market_date", "close"]].copy()
    selected = selected[selected["close"] > 0].sort_values("market_date").reset_index(drop=True)
    if len(selected) < minimum_observations:
        raise ValueError(f"Select a start date with at least {minimum_observations} observations")

    elapsed_days = (selected["market_date"] - selected["market_date"].iloc[0]).dt.days.astype(float)
    log_prices = selected["close"].map(math.log)
    x_centered = elapsed_days - elapsed_days.mean()
    denominator = float((x_centered**2).sum())
    if denominator == 0:
        raise ValueError("Select a start date spanning more than one day")

    slope = float((x_centered * (log_prices - log_prices.mean())).sum() / denominator)
    intercept = float(log_prices.mean() - slope * elapsed_days.mean())
    fitted_log = intercept + slope * elapsed_days
    return selected, fitted_log, slope


def logarithmic_regression_channel(
    frame: pd.DataFrame,
    start_date: date | pd.Timestamp,
    minimum_observations: int = 30,
    coverage: float = 1.0,
) -> pd.DataFrame:
    """Fit a log-price trend and return a symmetric envelope around it.

    ``coverage=1.0`` uses the largest logarithmic residual. Lower coverage,
    such as ``0.95``, creates a tighter channel by excluding extreme residuals.
    """
    if not 0 < coverage <= 1:
        raise ValueError("Coverage must be greater than 0 and at most 1")
    selected, fitted_log, _ = _fit_logarithmic_regression(
        frame, start_date, minimum_observations
    )
    log_prices = selected["close"].map(math.log)
    absolute_residuals = (log_prices - fitted_log).abs()
    envelope = float(absolute_residuals.quantile(coverage))

    return pd.DataFrame(
        {
            "market_date": selected["market_date"],
            "center": fitted_log.map(math.exp),
            "upper": (fitted_log + envelope).map(math.exp),
            "lower": (fitted_log - envelope).map(math.exp),
        }
    )


def annualized_logarithmic_regression_change(
    frame: pd.DataFrame, start_date: date | pd.Timestamp, minimum_observations: int = 30
) -> float:
    """Return the fitted logarithmic trend as an equivalent annual percentage change."""
    _, _, daily_slope = _fit_logarithmic_regression(frame, start_date, minimum_observations)
    return math.expm1(daily_slope * 365.25) * 100

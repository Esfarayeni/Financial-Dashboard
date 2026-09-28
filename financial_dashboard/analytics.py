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


def logarithmic_regression_r_squared(
    frame: pd.DataFrame, start_date: date | pd.Timestamp, minimum_observations: int = 30
) -> float:
    """Return goodness-of-fit for the log-price regression, from 0 to 1."""
    selected, fitted_log, _ = _fit_logarithmic_regression(frame, start_date, minimum_observations)
    actual_log = selected["close"].map(math.log)
    total = float(((actual_log - actual_log.mean()) ** 2).sum())
    if total == 0:
        return 1.0
    residual = float(((actual_log - fitted_log) ** 2).sum())
    return max(0.0, 1 - residual / total)


def drawdown_from_peak(frame: pd.DataFrame) -> pd.DataFrame:
    """Return percentage drawdown from the prior running high for a positive series."""
    result = frame[["market_date", "close"]].copy().sort_values("market_date")
    if result.empty:
        result["drawdown"] = pd.Series(dtype=float)
        return result
    peak = result["close"].cummax()
    result["drawdown"] = (result["close"] / peak - 1) * 100
    return result.reset_index(drop=True)


def rolling_volatility(frame: pd.DataFrame, window: int = 30, periods_per_year: int = 365) -> pd.DataFrame:
    """Return annualized rolling volatility of logarithmic returns in percent."""
    if window < 2:
        raise ValueError("window must be at least 2")
    result = frame[["market_date", "close"]].copy().sort_values("market_date")
    result["volatility"] = result["close"].map(math.log).diff().rolling(window).std() * math.sqrt(periods_per_year) * 100
    return result.dropna(subset=["volatility"]).reset_index(drop=True)


def monthly_log_return_correlation(series: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, tuple[pd.Timestamp, pd.Timestamp] | None]:
    """Correlate monthly log returns over the common overlapping period."""
    monthly: list[pd.Series] = []
    for name, frame in series.items():
        if frame.empty:
            continue
        item = frame.set_index("market_date")["close"].sort_index().resample("ME").last()
        monthly.append(item.map(math.log).diff().rename(name))
    if len(monthly) < 2:
        return pd.DataFrame(), None
    joined = pd.concat(monthly, axis=1, join="inner").dropna()
    if joined.empty:
        return pd.DataFrame(), None
    return joined.corr(), (joined.index.min(), joined.index.max())


def derived_series(
    left: pd.DataFrame, right: pd.DataFrame, operation: str, name: str
) -> pd.DataFrame:
    """Create a derived series on dates shared by both inputs."""
    aligned = left[["market_date", "close"]].merge(
        right[["market_date", "close"]], on="market_date", suffixes=("_left", "_right")
    )
    if operation == "multiply":
        close = aligned["close_left"] * aligned["close_right"]
    elif operation == "divide":
        close = aligned["close_left"] / aligned["close_right"]
    else:
        raise ValueError("operation must be 'multiply' or 'divide'")
    return pd.DataFrame({"market_date": aligned["market_date"], "close": close, "name": name})


def inflation_adjusted_series(price: pd.DataFrame, cpi: pd.DataFrame) -> pd.DataFrame:
    """Express a price series in prices at the first matched CPI observation."""
    if price.empty or cpi.empty:
        return pd.DataFrame(columns=["market_date", "close"])
    aligned = pd.merge_asof(
        price[["market_date", "close"]].sort_values("market_date"),
        cpi[["market_date", "close"]].sort_values("market_date"),
        on="market_date", direction="backward", suffixes=("_price", "_cpi"),
    ).dropna()
    if aligned.empty:
        return pd.DataFrame(columns=["market_date", "close"])
    base_cpi = float(aligned.iloc[0]["close_cpi"])
    return pd.DataFrame({
        "market_date": aligned["market_date"],
        "close": aligned["close_price"] * base_cpi / aligned["close_cpi"],
    })

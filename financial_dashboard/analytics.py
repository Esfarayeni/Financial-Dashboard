from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd


def chart_price_bounds(frame: pd.DataFrame, comparison: pd.DataFrame | None = None,
                       logarithmic: bool = False) -> tuple[float, float] | None:
    """Padded bounds of plotted prices only, never regression/channel values."""
    values = []
    for part in (frame, comparison):
        if part is not None:
            values.extend(float(v) for v in pd.to_numeric(part["close"], errors="coerce")
                          if math.isfinite(v) and (not logarithmic or v > 0))
    if not values:
        return None
    low, high = min(values), max(values)
    if logarithmic:
        low, high = math.log10(low), math.log10(high)
    padding = (high - low) * 0.05 if high > low else max(abs(low) * 0.05, 0.01)
    low, high = low - padding, high + padding
    return (10**low, 10**high) if logarithmic else (low, high)


def downsample_for_chart(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce older display points without changing the underlying series.

    The newest year stays daily, years one through five are represented by
    their final weekly observation, and earlier history by its final monthly
    observation.  The original observation date and all metadata are kept, so
    this can safely be used for a plotted line while metrics and regression
    continue to use the complete frame.
    """
    if frame.empty:
        return frame.copy()

    result = frame.sort_values("market_date").copy()
    latest = pd.Timestamp(result["market_date"].iloc[-1])
    recent_start = latest - pd.DateOffset(years=1)
    medium_start = latest - pd.DateOffset(years=5)

    recent = result[result["market_date"] >= recent_start]
    medium = result[
        (result["market_date"] >= medium_start) & (result["market_date"] < recent_start)
    ]
    older = result[result["market_date"] < medium_start]

    def last_in_period(part: pd.DataFrame, frequency: str) -> pd.DataFrame:
        if part.empty:
            return part
        return part.groupby(pd.Grouper(key="market_date", freq=frequency)).tail(1)

    return (
        pd.concat(
            [last_in_period(older, "ME"), last_in_period(medium, "W-FRI"), recent],
            ignore_index=True,
        )
        .sort_values("market_date")
        .reset_index(drop=True)
    )


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


def calendar_year_change(frame: pd.DataFrame, years: int) -> tuple[float, float] | None:
    """Total change over calendar years, or None when that history is absent."""
    if years < 1:
        raise ValueError("Years must be positive")
    if frame.empty:
        return None
    ordered = frame.sort_values("market_date")
    latest_date = pd.Timestamp(ordered.iloc[-1]["market_date"])
    target = latest_date - pd.DateOffset(years=years)
    if not (ordered["market_date"] <= target).any():
        return None
    return period_change(ordered, (latest_date - target).days)


def year_over_year_change(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert a monthly index series to the conventional annual inflation rate."""
    result = frame.sort_values("market_date").copy()
    prior_year = result["close"].shift(12)
    result["close"] = (result["close"] / prior_year - 1) * 100
    return result.dropna(subset=["close"]).reset_index(drop=True)


def cumulative_interest_growth(frame: pd.DataFrame, max_gap_days: int = 14) -> pd.DataFrame:
    """Estimated 1x growth using prior quoted annual yield and actual/365.25 time.

    This is an illustrative reinvestment index, not a bond total-return series.
    Start after the last long publication gap: unknown yields are not imputed.
    """
    result = frame.sort_values("market_date").copy().reset_index(drop=True)
    if result.empty:
        return result
    gaps = result["market_date"].diff().dt.days
    breaks = gaps[gaps > max_gap_days].index
    if len(breaks):
        result = result.iloc[breaks[-1]:].reset_index(drop=True)
    elapsed_years = result["market_date"].diff().dt.total_seconds().fillna(0) / (365.25 * 86400)
    prior_yield = result["close"].shift(1).fillna(0) / 100
    if (prior_yield <= -1).any():
        raise ValueError("Annual yields must exceed -100%")
    growth_log = (prior_yield.map(math.log1p) * elapsed_years).cumsum()
    result["close"] = growth_log.map(math.exp)
    return result


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


def _recency_weights(dates: pd.Series, half_life_years: float | None) -> pd.Series:
    """Calendar-time exponential weights, anchored to the latest observation."""
    if half_life_years is None:
        return pd.Series(1.0, index=dates.index)
    if not math.isfinite(half_life_years) or half_life_years <= 0:
        raise ValueError("Half-life must be a positive finite number of years")
    age_years = (dates.max() - dates).dt.total_seconds() / (365.25 * 86400)
    return 2.0 ** (-age_years / half_life_years)


def _residual_envelope(residuals: pd.Series, coverage: float, weights: pd.Series | None) -> float:
    if coverage == 1:
        return float(residuals.abs().max())
    if weights is None:
        return float(residuals.abs().quantile(coverage))
    order = residuals.abs().sort_values().index
    cumulative = weights.loc[order].cumsum()
    # Inverse weighted empirical CDF; 100% coverage still encloses every point.
    index = cumulative.searchsorted(coverage * float(cumulative.iloc[-1]))
    return float(residuals.abs().loc[order[min(index, len(order) - 1)]])


def regression_observation_weights(
    frame: pd.DataFrame, start_date: date | pd.Timestamp,
    end_date: date | pd.Timestamp | None = None, half_life_years: float | None = None,
) -> pd.DataFrame:
    """Relative weights for one selected training fit; newest observation is 1.

    These are not normalized to sum to one. For a historical prediction pass its
    training_end, not its evaluation date, to avoid displaying a future weight.
    """
    selected, _, _ = _fit_logarithmic_regression(frame, start_date, half_life_years=half_life_years, end_date=end_date)
    return pd.DataFrame({"market_date": selected.market_date,
                         "weight": _recency_weights(selected.market_date, half_life_years)})


def historical_corridor_crossings(
    frame: pd.DataFrame, start_date: date | pd.Timestamp,
    end_date: date | pd.Timestamp | None = None, half_life_years: float | None = 3,
    coverage: float = 0.95, minimum_observations: int = 30,
) -> pd.DataFrame:
    """Expanding-window, one-observation-ahead corridor predictions and crossings.

    Each prediction uses only earlier positive closes, with calendar-age weights
    anchored to the final training observation. Signals require a transition from
    inside to outside and matching close-to-close price direction: rising through
    the upper boundary or falling through the lower. Consecutive outside
    observations do not repeat a signal, even if an initial exit was filtered.
    On the first prediction, the prior close's fitted position initializes state.
    None for half-life uses equal weights and an ordinary residual percentile.
    No trades, execution assumptions, or returns are simulated.
    """
    if not 0 < coverage <= 1:
        raise ValueError("Coverage must be greater than 0 and at most 1")
    if minimum_observations < 30:
        raise ValueError("Use at least 30 training observations")
    start = pd.Timestamp(start_date)
    if end_date is not None and pd.Timestamp(end_date) < start:
        raise ValueError("Channel end must be on or after Channel start")
    selected = frame.loc[frame.market_date >= start, ["market_date", "close"]].copy()
    if end_date is not None:
        selected = selected[selected.market_date <= pd.Timestamp(end_date)]
    selected = selected[np.isfinite(selected.close) & (selected.close > 0)].sort_values("market_date").reset_index(drop=True)
    if selected.market_date.duplicated().any():
        raise ValueError("Backtest requires one close per observation date")
    _recency_weights(selected.market_date, half_life_years)
    if len(selected) <= minimum_observations:
        raise ValueError("Historical crossings need at least 31 observations: 30 for training and one to test")
    x = (selected.market_date - selected.market_date.iloc[0]).dt.total_seconds().to_numpy() / 86400
    y = np.log(selected.close.to_numpy(dtype=float))
    rows = []
    previous_state = None
    for i in range(minimum_observations, len(selected)):
        # NumPy avoids constructing thousands of pandas fits for long daily series.
        weights = np.ones(i) if half_life_years is None else np.exp2((x[:i] - x[i - 1]) / (365.25 * half_life_years))
        total = weights.sum()
        x_mean = float(np.sum(weights * x[:i]) / total)
        y_mean = float(np.sum(weights * y[:i]) / total)
        centered_x = x[:i] - x_mean
        denominator = float(np.sum(weights * centered_x ** 2))
        if denominator <= 0:
            raise ValueError("Training observations must span more than one day")
        slope = float(np.sum(weights * centered_x * (y[:i] - y_mean)) / denominator)
        intercept = y_mean - slope * x_mean
        residuals = y[:i] - (intercept + slope * x[:i])
        if half_life_years is None:
            width = float(np.quantile(np.abs(residuals), coverage))
        elif coverage == 1:
            width = float(np.abs(residuals).max())
        else:
            order = np.argsort(np.abs(residuals))
            cumulative = np.cumsum(weights[order])
            index = min(int(np.searchsorted(cumulative, coverage * cumulative[-1])), i - 1)
            width = float(abs(residuals[order[index]]))
        # Remove floating-point noise for an exactly exponential series.
        if width < 1e-12:
            width = 0.0
        tolerance = 1e-12
        if previous_state is None:
            previous_state = 1 if residuals[-1] > width + tolerance else -1 if residuals[-1] < -width - tolerance else 0
        predicted_log = intercept + slope * x[i]
        residual = float(y[i] - predicted_log)
        state = 1 if residual > width + tolerance else -1 if residual < -width - tolerance else 0
        price_change = float(selected.close.iloc[i] - selected.close.iloc[i - 1])
        matching_direction = (state == 1 and price_change > 0) or (state == -1 and price_change < 0)
        signal = state if previous_state == 0 and matching_direction else 0
        rows.append((selected.market_date.iloc[i], selected.close.iloc[i],
                     math.exp(predicted_log), math.exp(predicted_log + width), math.exp(predicted_log - width),
                     signal, state, selected.market_date.iloc[i - 1], i,
                     math.expm1(slope * 365.25) * 100))
        previous_state = state
    return pd.DataFrame(rows, columns=["market_date", "close", "center", "upper", "lower", "signal", "state",
                                       "training_end", "training_observations", "annual_growth"])


def _fit_logarithmic_regression(
    frame: pd.DataFrame,
    start_date: date | pd.Timestamp,
    minimum_observations: int = 30,
    half_life_years: float | None = None,
    end_date: date | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.Series, float]:
    """Return selected data, fitted log prices, and the daily slope."""
    start = pd.Timestamp(start_date)
    selected = frame.loc[frame["market_date"] >= start, ["market_date", "close"]].copy()
    if end_date is not None:
        end = pd.Timestamp(end_date)
        if end < start:
            raise ValueError("Channel end must be on or after Channel start")
        selected = selected[selected["market_date"] <= end]
    selected = selected[selected["close"] > 0].sort_values("market_date").reset_index(drop=True)
    if len(selected) < minimum_observations:
        raise ValueError(f"Select a start date with at least {minimum_observations} observations")

    elapsed_days = (selected["market_date"] - selected["market_date"].iloc[0]).dt.days.astype(float)
    log_prices = selected["close"].map(math.log)
    weights = _recency_weights(selected["market_date"], half_life_years)
    x_mean = float((elapsed_days * weights).sum() / weights.sum())
    y_mean = float((log_prices * weights).sum() / weights.sum())
    x_centered = elapsed_days - x_mean
    denominator = float((weights * x_centered**2).sum())
    if denominator == 0:
        raise ValueError("Select a start date spanning more than one day")

    slope = float((weights * x_centered * (log_prices - y_mean)).sum() / denominator)
    intercept = float(y_mean - slope * x_mean)
    fitted_log = intercept + slope * elapsed_days
    return selected, fitted_log, slope


def logarithmic_regression_channel(
    frame: pd.DataFrame,
    start_date: date | pd.Timestamp,
    minimum_observations: int = 30,
    coverage: float = 1.0,
    output_dates: pd.Series | None = None,
    half_life_years: float | None = None,
    end_date: date | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Fit a log-price trend and return a symmetric envelope around it.

    ``coverage=1.0`` uses the largest logarithmic residual. Lower coverage,
    such as ``0.95``, creates a tighter channel by excluding extreme residuals.
    """
    if not 0 < coverage <= 1:
        raise ValueError("Coverage must be greater than 0 and at most 1")
    selected, fitted_log, daily_slope = _fit_logarithmic_regression(
        frame, start_date, minimum_observations, half_life_years, end_date
    )
    log_prices = selected["close"].map(math.log)
    weights = None if half_life_years is None else _recency_weights(selected["market_date"], half_life_years)
    envelope = _residual_envelope(log_prices - fitted_log, coverage, weights)

    dates = selected["market_date"] if output_dates is None else pd.to_datetime(output_dates)
    dates = pd.Series(dates).dropna().drop_duplicates().sort_values().reset_index(drop=True)
    dates = dates[dates >= selected["market_date"].iloc[0]].reset_index(drop=True)
    if end_date is not None:
        dates = dates[dates <= pd.Timestamp(end_date)].reset_index(drop=True)
    elapsed_output_days = (dates - selected["market_date"].iloc[0]).dt.days.astype(float)
    intercept = float(fitted_log.iloc[0])
    projected_log = intercept + elapsed_output_days * daily_slope

    return pd.DataFrame(
        {
            "market_date": dates,
            "center": projected_log.map(math.exp),
            "upper": (projected_log + envelope).map(math.exp),
            "lower": (projected_log - envelope).map(math.exp),
        }
    )


def logarithmic_regression_position(
    frame: pd.DataFrame, start_date: date | pd.Timestamp, coverage: float = 0.95,
    half_life_years: float | None = None,
) -> float | None:
    """Latest normalized log residual: center 0, upper +1, lower -1."""
    return logarithmic_regression_position_stats(frame, start_date, coverage, half_life_years)[0]


def logarithmic_regression_position_stats(
    frame: pd.DataFrame, start_date: date | pd.Timestamp, coverage: float = 0.95,
    half_life_years: float | None = None,
) -> tuple[float | None, float | None]:
    return logarithmic_regression_deviation_stats(frame, start_date, coverage, half_life_years)[:2]


def logarithmic_regression_deviation_stats(
    frame: pd.DataFrame, start_date: date | pd.Timestamp, coverage: float = 0.95,
    half_life_years: float | None = None,
) -> tuple[float | None, float | None, float, float]:
    """Return position, mean absolute position, percent deviation, and width/price percent.

    The first two statistics use the chart's symmetric residual-quantile corridor.
    They are not clipped and are undefined for a zero-width corridor. The third
    statistic is mean(abs(price/trend - 1)) * 100, independent of corridor width.
    The fourth is the full corridor width at the latest date divided by its price,
    expressed as a percentage.
    By default each observation has equal weight. A half-life applies exponential
    calendar-age weights consistently to the fit, corridor and historical means.
    """
    if not 0 < coverage <= 1:
        raise ValueError("Coverage must be greater than 0 and at most 1")
    selected, fitted_log, _ = _fit_logarithmic_regression(frame, start_date, half_life_years=half_life_years)
    return _deviation_stats_from_fit(selected, fitted_log, coverage, half_life_years)


def logarithmic_regression_metrics(frame, start_date, coverage=0.95, half_life_years=None):
    """Annual growth and all four deviation metrics from a single identical fit."""
    if not 0 < coverage <= 1:
        raise ValueError("Coverage must be greater than 0 and at most 1")
    selected, fitted_log, slope = _fit_logarithmic_regression(frame, start_date, half_life_years=half_life_years)
    return (math.expm1(slope * 365.25) * 100,
            *_deviation_stats_from_fit(selected, fitted_log, coverage, half_life_years))


def _deviation_stats_from_fit(selected, fitted_log, coverage, half_life_years):
    weights = _recency_weights(selected["market_date"], half_life_years)
    residuals = selected["close"].map(math.log) - fitted_log
    # exp(log(price/trend)) - 1 = (price - trend) / trend.
    percent_deviation = float((residuals.map(math.expm1).abs() * weights).sum() / weights.sum()) * 100
    if percent_deviation <= 1e-10:
        percent_deviation = 0.0
    width = _residual_envelope(residuals, coverage, None if half_life_years is None else weights)
    if width <= 1e-12:
        return None, None, percent_deviation, 0.0
    latest_residual = float(residuals.iloc[-1])
    width_percent = (math.exp(width - latest_residual) - math.exp(-width - latest_residual)) * 100
    average_position = float((residuals.abs() * weights).sum() / weights.sum() / width)
    return latest_residual / width, average_position, percent_deviation, width_percent


def annualized_logarithmic_regression_change(
    frame: pd.DataFrame, start_date: date | pd.Timestamp, minimum_observations: int = 30,
    half_life_years: float | None = None,
    end_date: date | pd.Timestamp | None = None,
) -> float:
    """Return the fitted logarithmic trend as an equivalent annual percentage change."""
    _, _, daily_slope = _fit_logarithmic_regression(frame, start_date, minimum_observations, half_life_years, end_date)
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

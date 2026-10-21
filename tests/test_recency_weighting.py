import math

import numpy as np
import pandas as pd
import pytest

from financial_dashboard.analytics import (
    _recency_weights,
    annualized_logarithmic_regression_change,
    logarithmic_regression_channel,
    logarithmic_regression_deviation_stats,
)


def sample():
    dates = pd.date_range("2000-01-01", periods=150, freq="31D")
    x = (dates - dates[0]).days.to_numpy()
    y = 4 + 0.0001 * x + 0.0006 * np.maximum(x - x[80], 0) + 0.15 * np.sin(np.arange(len(x)))
    return pd.DataFrame({"market_date": dates, "close": np.exp(y)})


def test_calendar_half_life_weights_use_latest_observation_not_wall_clock_or_rows():
    dates = pd.Series(pd.to_datetime(["2000-01-01", "2003-01-01", "2006-01-01"]))
    expected = 2 ** (-(dates.max() - dates).dt.total_seconds() / (365.25 * 86400 * 3))
    pd.testing.assert_series_equal(_recency_weights(dates, 3), expected)
    assert expected.iloc[0] == pytest.approx(0.25, abs=0.001)
    assert expected.iloc[1] == pytest.approx(0.5, abs=0.001)
    shifted = dates + pd.Timedelta(days=900)
    pd.testing.assert_series_equal(_recency_weights(dates, 3), _recency_weights(shifted, 3))


@pytest.mark.parametrize("half_life", [1 / 12, 0.25, 0.5, 1, 2, 3, 5])
def test_weighted_fit_corridor_and_means_match_independent_reference(half_life):
    frame = sample()
    x = (frame.market_date - frame.market_date.iloc[0]).dt.days.to_numpy()
    y = np.log(frame.close.to_numpy())
    w = 2 ** (-(x[-1] - x) / (365.25 * half_life))
    design = np.column_stack([np.ones(len(x)), x])
    coefficients = np.linalg.lstsq(design * np.sqrt(w[:, None]), y * np.sqrt(w), rcond=None)[0]
    fitted = design @ coefficients
    residuals = y - fitted
    order = np.argsort(abs(residuals))
    width = abs(residuals)[order][np.searchsorted(np.cumsum(w[order]), 0.95 * sum(w))]
    channel = logarithmic_regression_channel(frame, frame.market_date.iloc[0], coverage=0.95, half_life_years=half_life)
    assert channel.center.to_numpy() == pytest.approx(np.exp(fitted))
    assert channel.upper.to_numpy() == pytest.approx(np.exp(fitted + width))
    assert channel.lower.to_numpy() == pytest.approx(np.exp(fitted - width))
    expected = (residuals[-1] / width, np.average(abs(residuals), weights=w) / width,
                np.average(abs(np.expm1(residuals)), weights=w) * 100,
                (channel.upper.iloc[-1] - channel.lower.iloc[-1]) / frame.close.iloc[-1] * 100)
    actual = logarithmic_regression_deviation_stats(frame, frame.market_date.iloc[0], half_life_years=half_life)
    assert actual == pytest.approx(expected)
    assert annualized_logarithmic_regression_change(frame, frame.market_date.iloc[0], half_life_years=half_life) == pytest.approx(math.expm1(coefficients[1] * 365.25) * 100)


def test_recent_emphasis_responds_to_new_trend_and_full_corridor_encloses_every_point():
    frame = sample()
    start = frame.market_date.iloc[0]
    assert annualized_logarithmic_regression_change(frame, start, half_life_years=1) > annualized_logarithmic_regression_change(frame, start)
    channel = logarithmic_regression_channel(frame, start, half_life_years=1)
    assert (channel.upper >= frame.close - 1e-10).all()
    assert (channel.lower <= frame.close + 1e-10).all()


@pytest.mark.parametrize("half_life", [0, -1, float("nan"), float("inf")])
def test_invalid_half_life_is_rejected(half_life):
    frame = sample()
    with pytest.raises(ValueError, match="Half-life"):
        logarithmic_regression_deviation_stats(frame, frame.market_date.iloc[0], half_life_years=half_life)


def test_off_preserves_existing_equal_weight_regression():
    frame = sample()
    x = (frame.market_date - frame.market_date.iloc[0]).dt.days.to_numpy()
    coefficients = np.polyfit(x, np.log(frame.close), 1)
    channel = logarithmic_regression_channel(frame, frame.market_date.iloc[0])
    assert channel.center.to_numpy() == pytest.approx(np.exp(np.polyval(coefficients, x)))


def test_full_corridor_keeps_ancient_outlier_with_short_half_life():
    frame = sample()
    frame.loc[0, "close"] *= 1000
    channel = logarithmic_regression_channel(frame, frame.market_date.iloc[0], half_life_years=1 / 12)
    assert (channel.upper >= frame.close - 1e-8).all()
    assert (channel.lower <= frame.close + 1e-8).all()


def test_leaderboard_uses_weighting_but_preserves_drawdown(monkeypatch, tmp_path):
    from financial_dashboard import stocks
    monkeypatch.setattr(stocks, "STOCKS", stocks.STOCKS[:1])
    frame = sample().rename(columns={"close": "adjusted_close"})
    frame["quote_close"] = frame.adjusted_close * 2
    ticker = stocks.STOCKS[0]["ticker"]
    frame.to_parquet(tmp_path / f"{ticker}.parquet", index=False)
    off, on = stocks.leaderboard(tmp_path), stocks.leaderboard(tmp_path, half_life_years=3)
    assert off["Drawdown from ATH (%)"].iloc[0] == on["Drawdown from ATH (%)"].iloc[0]
    assert off["Trend/year (%)"].iloc[0] != pytest.approx(on["Trend/year (%)"].iloc[0])
    reference = logarithmic_regression_deviation_stats(frame.rename(columns={"adjusted_close": "close"}), frame.market_date.iloc[0], half_life_years=3)
    assert on["Corridor width / price (%)"].iloc[0] == pytest.approx(reference[3])

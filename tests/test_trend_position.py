import math

import pandas as pd
import pytest

from financial_dashboard.analytics import logarithmic_regression_channel, logarithmic_regression_position, logarithmic_regression_position_stats, logarithmic_regression_deviation_stats


def prices(last_residual=0.0):
    dates = pd.date_range("2020-01-01", periods=100)
    values = [math.exp(4 + 0.002 * i + 0.1 * math.sin(i)) for i in range(100)]
    values[-1] = math.exp(4 + 0.002 * 99 + last_residual)
    return pd.DataFrame({"market_date": dates, "close": values})


@pytest.mark.parametrize("last,expected", [(2.0, 1.0), (-2.0, -1.0)])
def test_extreme_latest_price_at_full_corridor_boundary(last, expected):
    frame = prices(last)
    assert logarithmic_regression_position(frame, frame.market_date.iloc[0], coverage=1) == pytest.approx(expected)


@pytest.mark.parametrize("last", [0.05, -0.05, 2.0, -2.0])
def test_position_matches_chart_95_percent_log_corridor_without_clipping(last):
    frame = prices(last)
    start = frame.market_date.iloc[0]
    row = logarithmic_regression_channel(frame, start, coverage=0.95).iloc[-1]
    expected = math.log(frame.close.iloc[-1] / row.center) / math.log(row.upper / row.center)
    assert logarithmic_regression_position(frame, start) == pytest.approx(expected)
    if abs(last) == 2:
        assert abs(expected) > 1


def test_perfect_regression_has_undefined_position_not_numeric_noise():
    frame = prices()
    frame["close"] = [math.exp(4 + 0.002 * i) for i in range(100)]
    assert logarithmic_regression_position(frame, frame.market_date.iloc[0]) is None
    with pytest.raises(ValueError):
        logarithmic_regression_position(frame.head(5), frame.market_date.iloc[0])


def test_price_on_center_is_zero_with_nonzero_corridor():
    frame = prices().iloc[:31].copy()
    residuals = [0.0] * 31
    for i, v in [(5, 0.1), (25, 0.1), (10, -0.1), (20, -0.1)]:
        residuals[i] = v
    frame["close"] = [math.exp(4 + v) for v in residuals]
    assert logarithmic_regression_position(frame, frame.market_date.iloc[0]) == pytest.approx(0, abs=1e-12)


def test_average_deviation_matches_mean_absolute_historical_corridor_positions():
    frame = prices(2)
    start = frame.market_date.iloc[0]
    channel = logarithmic_regression_channel(frame, start, coverage=0.95)
    positions = [math.log(price / center) / math.log(upper / center)
                 for price, center, upper in zip(frame.close, channel.center, channel.upper)]
    latest, average = logarithmic_regression_position_stats(frame, start)
    assert latest == pytest.approx(positions[-1])
    assert average == pytest.approx(sum(abs(v) for v in positions) / len(positions))
    assert average > 0
    assert average != pytest.approx(abs(latest))


def test_degenerate_corridor_has_no_average_deviation():
    frame = prices()
    frame["close"] = 100.0
    assert logarithmic_regression_position_stats(frame, frame.market_date.iloc[0]) == (None, None)


def test_percentage_deviation_matches_price_relative_to_trend():
    frame = prices(2)
    start = frame.market_date.iloc[0]
    channel = logarithmic_regression_channel(frame, start)
    expected = sum(abs(price / center - 1) for price, center in zip(frame.close, channel.center)) / len(frame) * 100
    assert logarithmic_regression_deviation_stats(frame, start)[2] == pytest.approx(expected)
    scaled = frame.assign(close=frame.close * 100)
    assert logarithmic_regression_deviation_stats(scaled, start)[2] == pytest.approx(expected)


def test_percentage_deviation_is_zero_for_perfect_fit_and_requires_history():
    frame = prices().assign(close=100.0)
    assert logarithmic_regression_deviation_stats(frame, frame.market_date.iloc[0])[2] == 0
    with pytest.raises(ValueError):
        logarithmic_regression_deviation_stats(frame.head(5), frame.market_date.iloc[0])


def test_percentage_deviation_does_not_depend_on_corridor_coverage():
    frame = prices(2)
    start = frame.market_date.iloc[0]
    assert logarithmic_regression_deviation_stats(frame, start, 0.95)[2] == logarithmic_regression_deviation_stats(frame, start, 1)[2]


@pytest.mark.parametrize("last", [-2.0, 0.05, 2.0])
def test_corridor_width_relative_to_latest_adjusted_price_matches_chart(last):
    frame = prices(last)
    start = frame.market_date.iloc[0]
    bounds = logarithmic_regression_channel(frame, start, coverage=0.95).iloc[-1]
    expected = (bounds.upper - bounds.lower) / frame.close.iloc[-1] * 100
    assert logarithmic_regression_deviation_stats(frame, start)[3] == pytest.approx(expected)
    scaled = frame.assign(close=frame.close * 100)
    assert logarithmic_regression_deviation_stats(scaled, start)[3] == pytest.approx(expected)


def test_perfect_fit_has_zero_relative_corridor_width():
    frame = prices().assign(close=100.0)
    assert logarithmic_regression_deviation_stats(frame, frame.market_date.iloc[0])[3] == 0

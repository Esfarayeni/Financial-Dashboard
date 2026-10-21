import math

import pandas as pd
import pytest

from financial_dashboard.analytics import annualized_logarithmic_regression_change, logarithmic_regression_channel


def prices():
    dates = pd.date_range("2015-01-01", periods=150, freq="31D")
    return pd.DataFrame({"market_date": dates,
                         "close": [math.exp(4 + 0.01 * i + 0.1 * math.sin(i)) for i in range(150)]})


@pytest.mark.parametrize("half_life", [None, 1, 3, 5])
def test_end_date_fits_only_selected_history_and_clips_projection(half_life):
    frame = prices()
    start, end = frame.market_date.iloc[10], frame.market_date.iloc[80]
    expected = frame[frame.market_date <= end]
    # Later extreme observations must not change the trend, envelope, or weights.
    frame.loc[frame.market_date > end, "close"] *= 1000
    channel = logarithmic_regression_channel(frame, start, coverage=0.95,
                                              half_life_years=half_life, end_date=end,
                                              output_dates=frame.market_date)
    reference = logarithmic_regression_channel(expected, start, coverage=0.95, half_life_years=half_life)
    pd.testing.assert_frame_equal(channel, reference)
    assert channel.market_date.min() == start
    assert channel.market_date.max() == end
    actual_trend = annualized_logarithmic_regression_change(frame, start, half_life_years=half_life, end_date=end)
    expected_trend = annualized_logarithmic_regression_change(expected, start, half_life_years=half_life)
    assert actual_trend == pytest.approx(expected_trend)


def test_latest_end_preserves_full_history_result():
    frame = prices()
    start = frame.market_date.iloc[0]
    pd.testing.assert_frame_equal(logarithmic_regression_channel(frame, start),
                                  logarithmic_regression_channel(frame, start, end_date=frame.market_date.iloc[-1]))


def test_end_before_start_or_insufficient_interval_is_rejected():
    frame = prices()
    start = frame.market_date.iloc[0]
    with pytest.raises(ValueError, match="Channel end"):
        logarithmic_regression_channel(frame, frame.market_date.iloc[40], end_date=start)
    with pytest.raises(ValueError, match="at least 30"):
        logarithmic_regression_channel(frame, start, end_date=frame.market_date.iloc[28])
    with pytest.raises(ValueError, match="at least 30"):
        annualized_logarithmic_regression_change(frame, start, end_date=frame.market_date.iloc[28])


def test_end_between_observations_does_not_include_next_observation():
    frame = prices()
    end = frame.market_date.iloc[60] + pd.Timedelta(days=5)
    channel = logarithmic_regression_channel(frame, frame.market_date.iloc[0], end_date=end)
    assert channel.market_date.iloc[-1] == frame.market_date.iloc[60]

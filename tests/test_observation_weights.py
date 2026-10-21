import pandas as pd
import pytest

from financial_dashboard.analytics import historical_corridor_crossings, regression_observation_weights


def prices():
    return pd.DataFrame({"market_date": pd.date_range("2020-01-01", periods=65), "close": 100.0})


@pytest.mark.parametrize("half_life", [1 / 12, 0.25, 0.5, 1, 2])
def test_displayed_weights_use_same_calendar_age_decay_as_fit(half_life):
    frame = prices()
    result = regression_observation_weights(frame, frame.market_date.iloc[0], half_life_years=half_life)
    age = (frame.market_date.iloc[-1] - frame.market_date).dt.total_seconds() / (365.25 * 86400)
    assert result.weight.tolist() == pytest.approx((2 ** (-age / half_life)).tolist())
    assert result.weight.iloc[-1] == 1
    assert result.weight.is_monotonic_increasing


def test_no_emphasis_is_flat_one_not_sum_normalized():
    frame = prices()
    result = regression_observation_weights(frame, frame.market_date.iloc[0])
    assert result.weight.eq(1).all()
    assert result.weight.sum() == len(frame)


def test_selected_window_and_actual_last_observation_set_anchor():
    frame = prices()
    frame = frame[frame.market_date != pd.Timestamp("2020-02-20")]
    result = regression_observation_weights(frame, pd.Timestamp("2020-01-10"), pd.Timestamp("2020-02-20"), 0.5)
    assert result.market_date.iloc[0] == pd.Timestamp("2020-01-10")
    assert result.market_date.iloc[-1] == pd.Timestamp("2020-02-19")
    assert result.weight.iloc[-1] == 1


def test_historical_weights_exclude_the_last_tested_close():
    frame = prices()
    study = historical_corridor_crossings(frame, frame.market_date.iloc[0], half_life_years=0.5)
    result = regression_observation_weights(frame, frame.market_date.iloc[0], study.training_end.iloc[-1], 0.5)
    assert result.market_date.iloc[-1] < study.market_date.iloc[-1]
    assert len(result) == study.training_observations.iloc[-1]
    assert result.weight.iloc[-1] == 1


def test_invalid_training_window_is_rejected():
    frame = prices()
    with pytest.raises(ValueError, match="at least 30"):
        regression_observation_weights(frame.head(29), frame.market_date.iloc[0])

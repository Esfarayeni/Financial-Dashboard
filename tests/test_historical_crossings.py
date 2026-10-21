import math

import pandas as pd
import pytest

from financial_dashboard.analytics import historical_corridor_crossings, logarithmic_regression_channel


def prices():
    dates = pd.date_range("2010-01-01", periods=70, freq="31D")
    return pd.DataFrame({"market_date": dates,
                         "close": [math.exp(4 + 0.008 * i + 0.15 * math.sin(i)) for i in range(len(dates))]})


@pytest.mark.parametrize("half_life", [None, 1 / 12, 0.25, 0.5, 1, 2, 3, 5])
@pytest.mark.parametrize("coverage", [0.95, 1.0])
def test_predictions_match_prior_only_reference_fit(half_life, coverage):
    frame = prices()
    result = historical_corridor_crossings(frame, frame.market_date.iloc[0], half_life_years=half_life, coverage=coverage)
    assert len(result) == len(frame) - 30
    assert (result.training_end < result.market_date).all()
    for i in (30, 40, 69):
        reference = logarithmic_regression_channel(frame.iloc[:i], frame.market_date.iloc[0], coverage=coverage,
                                                    half_life_years=half_life, output_dates=frame.market_date.iloc[i:i + 1]).iloc[0]
        actual = result[result.market_date == frame.market_date.iloc[i]].iloc[0]
        for column in ("center", "upper", "lower"):
            assert actual[column] == pytest.approx(reference[column])
        assert actual.training_observations == i


@pytest.mark.parametrize("half_life", [None, 3])
def test_current_and_future_prices_cannot_change_current_prediction_or_past_signals(half_life):
    frame = prices()
    start = frame.market_date.iloc[0]
    original = historical_corridor_crossings(frame, start, half_life_years=half_life)
    changed = frame.copy()
    changed.loc[45:, "close"] *= 10
    after = historical_corridor_crossings(changed, start, half_life_years=half_life)
    pd.testing.assert_frame_equal(original[original.market_date < frame.market_date.iloc[45]],
                                  after[after.market_date < frame.market_date.iloc[45]])
    at = original.market_date == frame.market_date.iloc[45]
    pd.testing.assert_frame_equal(original.loc[at, ["center", "upper", "lower", "training_end"]],
                                  after.loc[at, ["center", "upper", "lower", "training_end"]])


def test_marks_only_inside_to_outside_transitions_not_continued_exits_or_direct_flips():
    frame = pd.DataFrame({"market_date": pd.date_range("2020-01-01", periods=30),
                          "close": [100 * math.exp(0.001 * i) for i in range(30)]})
    desired_states = [0, 1, 1, 0, -1, -1, 1, 0, 1]
    for state in desired_states:
        next_date = frame.market_date.iloc[-1] + pd.Timedelta(days=1)
        bounds = logarithmic_regression_channel(frame, frame.market_date.iloc[0], coverage=0.95,
                                                 half_life_years=3, output_dates=pd.Series([next_date])).iloc[0]
        close = bounds.upper * 1.2 if state == 1 else bounds.lower / 1.2 if state == -1 else bounds.center
        frame = pd.concat([frame, pd.DataFrame({"market_date": [next_date], "close": [close]})], ignore_index=True)
    result = historical_corridor_crossings(frame, frame.market_date.iloc[0])
    assert result.state.tolist() == desired_states
    assert result.signal.tolist() == [0, 1, 0, 0, -1, 0, 0, 0, 1]


def test_selected_interval_and_prefix_result_are_independent_of_later_history():
    frame = prices()
    start, end = frame.market_date.iloc[5], frame.market_date.iloc[50]
    full = historical_corridor_crossings(frame, start, end)
    prefix = historical_corridor_crossings(frame[frame.market_date <= end], start)
    pd.testing.assert_frame_equal(full, prefix)
    assert full.training_observations.iloc[0] == 30
    assert full.market_date.iloc[-1] == end


def test_perfect_exponential_has_no_spurious_crossings():
    frame = prices()
    frame["close"] = [math.exp(4 + 0.005 * i) for i in range(len(frame))]
    result = historical_corridor_crossings(frame, frame.market_date.iloc[0])
    assert result.signal.eq(0).all()


@pytest.mark.parametrize("slope,multiplier,expected_state", [(-0.02, 0.99, 1), (0.02, 1.01, -1), (-0.02, 1.0, 1), (0.02, 1.0, -1)])
@pytest.mark.parametrize("half_life", [None, 1 / 12])
def test_opposite_or_flat_price_move_is_not_marked(slope, multiplier, expected_state, half_life):
    values = [100 * math.exp(slope * i) for i in range(30)]
    values.append(values[-1] * multiplier)
    frame = pd.DataFrame({"market_date": pd.date_range("2020-01-01", periods=31), "close": values})
    result = historical_corridor_crossings(frame, frame.market_date.iloc[0], half_life_years=half_life)
    assert result.state.iloc[0] == expected_state
    assert result.signal.iloc[0] == 0


@pytest.mark.parametrize("slope,multiplier,expected_signal", [(-0.02, 1.01, 1), (0.02, 0.99, -1)])
def test_matching_direction_exit_remains_marked(slope, multiplier, expected_signal):
    values = [100 * math.exp(slope * i) for i in range(30)]
    values.append(values[-1] * multiplier)
    frame = pd.DataFrame({"market_date": pd.date_range("2020-01-01", periods=31), "close": values})
    result = historical_corridor_crossings(frame, frame.market_date.iloc[0])
    assert result.signal.iloc[0] == expected_signal


@pytest.mark.parametrize("half_life", [0, -1, float("inf"), float("nan")])
def test_invalid_half_life_is_rejected(half_life):
    frame = prices()
    with pytest.raises(ValueError, match="Half-life"):
        historical_corridor_crossings(frame, frame.market_date.iloc[0], half_life_years=half_life)


def test_insufficient_history_and_duplicate_dates_are_rejected():
    frame = prices()
    with pytest.raises(ValueError, match="31 observations"):
        historical_corridor_crossings(frame.head(30), frame.market_date.iloc[0])
    with pytest.raises(ValueError, match="one close"):
        historical_corridor_crossings(pd.concat([frame, frame.tail(1)]), frame.market_date.iloc[0])

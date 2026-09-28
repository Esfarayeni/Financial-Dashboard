import math

import pandas as pd
import pytest

from financial_dashboard.analytics import (
    annualized_logarithmic_regression_change,
    logarithmic_regression_channel,
    period_change,
    rebased_price_level,
    year_over_year_change,
)


def test_period_changes_use_previous_and_calendar_targets():
    frame = pd.DataFrame(
        {
            "market_date": pd.to_datetime(
                ["2025-09-20", "2026-08-20", "2026-08-22", "2026-09-13", "2026-09-20"]
            ),
            "close": [55.0, 80.0, 90.0, 110.0, 121.0],
        }
    )

    assert period_change(frame, None) == (11.0, 10.0)
    assert period_change(frame, 7) == (11.0, 10.0)
    monthly_absolute, monthly_percentage = period_change(frame, 30)
    assert monthly_absolute == 41.0
    assert monthly_percentage == pytest.approx(51.25)
    assert period_change(frame, 365) == (66.0, 120.0)


def test_year_over_year_change_uses_the_same_month_a_year_earlier():
    frame = pd.DataFrame(
        {
            "market_date": pd.date_range("2024-01-01", periods=13, freq="MS"),
            "close": [100.0] * 12 + [103.5],
        }
    )

    result = year_over_year_change(frame)

    assert len(result) == 1
    assert result.iloc[0]["close"] == pytest.approx(3.5)


def test_rebased_price_level_sets_the_selected_start_to_one():
    frame = pd.DataFrame(
        {
            "market_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
            "close": [100.0, 102.0, 105.0],
        }
    )

    result = rebased_price_level(frame, pd.Timestamp("2024-02-01"))

    assert result["close"].tolist() == pytest.approx([1.0, 105 / 102])


def test_logarithmic_regression_channel_fits_exponential_prices():
    frame = pd.DataFrame(
        {
            "market_date": pd.date_range("2026-01-01", periods=31, freq="D"),
            "close": [100 * math.exp(day * 0.02) for day in range(31)],
        }
    )

    channel = logarithmic_regression_channel(frame, pd.Timestamp("2026-01-01"))

    assert channel["center"].tolist() == pytest.approx(frame["close"].tolist())
    assert channel["upper"].tolist() == pytest.approx(frame["close"].tolist())
    assert channel["lower"].tolist() == pytest.approx(frame["close"].tolist())


def test_logarithmic_regression_channel_encloses_each_close():
    frame = pd.DataFrame(
        {
            "market_date": pd.date_range("2026-01-01", periods=31, freq="D"),
            "close": [100 * math.exp(day * 0.02) for day in range(31)],
        }
    )
    frame.loc[15, "close"] *= 1.5

    channel = logarithmic_regression_channel(frame, pd.Timestamp("2026-01-01"))

    assert (frame["close"] <= channel["upper"]).all()
    assert (frame["close"] >= channel["lower"]).all()


def test_95_percent_logarithmic_corridor_is_tighter_than_full_envelope():
    frame = pd.DataFrame(
        {
            "market_date": pd.date_range("2026-01-01", periods=100, freq="D"),
            "close": [100 * math.exp(day * 0.01) for day in range(100)],
        }
    )
    frame.loc[50, "close"] *= 3

    full = logarithmic_regression_channel(frame, pd.Timestamp("2026-01-01"))
    corridor_95 = logarithmic_regression_channel(
        frame, pd.Timestamp("2026-01-01"), coverage=0.95
    )

    assert (corridor_95["upper"] - corridor_95["lower"]).mean() < (
        full["upper"] - full["lower"]
    ).mean()
    assert not (frame["close"] <= corridor_95["upper"]).all()


def test_annualized_logarithmic_regression_change_converts_daily_slope():
    daily_slope = 0.001
    frame = pd.DataFrame(
        {
            "market_date": pd.date_range("2026-01-01", periods=31, freq="D"),
            "close": [100 * math.exp(day * daily_slope) for day in range(31)],
        }
    )

    annualized = annualized_logarithmic_regression_change(frame, pd.Timestamp("2026-01-01"))

    assert annualized == pytest.approx(math.expm1(daily_slope * 365.25) * 100)

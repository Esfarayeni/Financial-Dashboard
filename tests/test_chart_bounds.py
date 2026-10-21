import math

import pandas as pd
import pytest

from financial_dashboard.analytics import chart_price_bounds


def test_linear_bounds_fit_prices_with_padding_and_include_comparison():
    prices = pd.DataFrame({"close": [100, 110]})
    assert chart_price_bounds(prices) == pytest.approx((99.5, 110.5))
    assert chart_price_bounds(prices, pd.DataFrame({"close": [90, 120]})) == pytest.approx((88.5, 121.5))


def test_log_bounds_pad_in_log_space_and_ignore_invalid_points():
    low, high = chart_price_bounds(pd.DataFrame({"close": [10, 100, 0, -1, math.nan, math.inf]}), logarithmic=True)
    assert math.log10(low) == pytest.approx(0.95)
    assert math.log10(high) == pytest.approx(2.05)


@pytest.mark.parametrize("logarithmic", [True, False])
def test_constant_and_single_points_have_nonzero_vertical_range(logarithmic):
    low, high = chart_price_bounds(pd.DataFrame({"close": [100]}), logarithmic=logarithmic)
    assert low < 100 < high
    assert chart_price_bounds(pd.DataFrame({"close": []}), logarithmic=logarithmic) is None


def test_channel_columns_cannot_affect_price_bounds():
    frame = pd.DataFrame({"close": [100, 110], "upper": [10000, 20000], "lower": [1, 2]})
    assert chart_price_bounds(frame) == pytest.approx((99.5, 110.5))

import math
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from financial_dashboard.analytics import (
    _fit_weights, annualized_logarithmic_regression_change,
    historical_corridor_crossings, logarithmic_regression_channel,
    logarithmic_regression_deviation_stats, regression_observation_weights,
)
from financial_dashboard.providers.databourse import jalali_to_gregorian
from financial_dashboard.usd_history import with_regression_weights


def test_annual_monthly_and_daily_coverage_have_equal_base_weight():
    # Persian 1399 is a leap year: annual, monthly and daily versions all cover 366 days.
    first = pd.Timestamp(jalali_to_gregorian(1399, 1, 1))
    end = pd.Timestamp(jalali_to_gregorian(1400, 1, 1) - timedelta(days=1))
    annual = pd.DataFrame({"market_date": [end], "close": [100], "unit": ["toman_annual_average"]})
    monthly_dates = [pd.Timestamp((jalali_to_gregorian(1400, 1, 1) if month == 12 else
                      jalali_to_gregorian(1399, month+1, 1)) - timedelta(days=1))
                     for month in range(1, 13)]
    monthly = pd.DataFrame({"market_date": monthly_dates, "close": 100, "unit": "toman_monthly_average"})
    daily = pd.DataFrame({"market_date": pd.date_range(first, end), "close": 100, "unit": "toman"})
    totals = [with_regression_weights(f).regression_weight.sum() for f in [annual, monthly, daily]]
    assert totals == pytest.approx([366/365.25]*3)
    assert with_regression_weights(monthly).regression_weight.iloc[-1] == pytest.approx(30/365.25)


def test_quote_gaps_use_only_prior_information_and_do_not_bridge_outages():
    f = pd.DataFrame({"market_date": pd.to_datetime(["2020-01-01", "2020-01-03", "2020-01-20"]),
                      "close": 100, "unit": "toman"})
    result = with_regression_weights(f)
    assert result.regression_weight.tolist() == pytest.approx(np.array([1, 2, 1])/365.25)
    pd.testing.assert_frame_equal(result.iloc[:2], with_regression_weights(f.iloc[:2]))


def sample():
    dates = pd.date_range("2000-01-01", periods=80, freq="31D")
    x = (dates-dates[0]).days.to_numpy()
    return pd.DataFrame({"market_date": dates, "close": np.exp(4 + .0002*x + .2*np.sin(np.arange(80))),
                         "regression_weight": np.r_[np.repeat(365.,10),np.repeat(30.,30),np.ones(40)]/365.25})


@pytest.mark.parametrize("half_life", [None, .5, 2])
def test_fit_corridor_deviations_and_display_use_combined_weights(half_life):
    frame = sample()
    x = (frame.market_date-frame.market_date.iloc[0]).dt.days.to_numpy()
    y = np.log(frame.close.to_numpy())
    w = frame.regression_weight.to_numpy() * (1 if half_life is None else np.exp2((x-x[-1])/(365.25*half_life)))
    design = np.column_stack([np.ones(len(x)), x])
    fit = np.linalg.lstsq(design*np.sqrt(w[:,None]), y*np.sqrt(w), rcond=None)[0]
    fitted = design@fit
    residual = y-fitted
    order = np.argsort(abs(residual))
    width = abs(residual)[order][np.searchsorted(np.cumsum(w[order]), .95*w.sum())]
    channel = logarithmic_regression_channel(frame, frame.market_date.iloc[0], coverage=.95, half_life_years=half_life)
    assert channel.center.to_numpy() == pytest.approx(np.exp(fitted))
    assert channel.upper.to_numpy() == pytest.approx(np.exp(fitted+width))
    stats = logarithmic_regression_deviation_stats(frame, frame.market_date.iloc[0], half_life_years=half_life)
    assert stats[1] == pytest.approx(np.average(abs(residual),weights=w)/width)
    assert stats[2] == pytest.approx(np.average(abs(np.expm1(residual)),weights=w)*100)
    assert annualized_logarithmic_regression_change(frame, frame.market_date.iloc[0], half_life_years=half_life) == pytest.approx(math.expm1(fit[1]*365.25)*100)
    display = regression_observation_weights(frame, frame.market_date.iloc[0], half_life_years=half_life)
    assert display.weight.to_numpy() == pytest.approx(w/w.max())
    full = logarithmic_regression_channel(frame, frame.market_date.iloc[0], half_life_years=half_life)
    assert (full.upper >= frame.close-1e-10).all() and (full.lower <= frame.close+1e-10).all()


@pytest.mark.parametrize("half_life", [None, 1])
def test_crossings_match_prior_only_weighted_fit_and_prefix_is_unchanged(half_life):
    frame = sample()
    result = historical_corridor_crossings(frame, frame.market_date.iloc[0], coverage=.95, half_life_years=half_life)
    for i in [30, 50, 79]:
        reference = logarithmic_regression_channel(frame.iloc[:i], frame.market_date.iloc[0], coverage=.95,
                        half_life_years=half_life, output_dates=frame.market_date.iloc[i:i+1]).iloc[0]
        actual = result[result.market_date == frame.market_date.iloc[i]].iloc[0]
        assert actual.center == pytest.approx(reference.center)
        assert actual.upper == pytest.approx(reference.upper)
    prefix = historical_corridor_crossings(frame.iloc[:60], frame.market_date.iloc[0], coverage=.95, half_life_years=half_life)
    pd.testing.assert_frame_equal(result.iloc[:30], prefix)


def test_selection_preserves_base_weights_and_unweighted_assets_are_unchanged():
    frame = sample()
    selected = frame.iloc[10:60]
    actual = regression_observation_weights(frame, selected.market_date.iloc[0], selected.market_date.iloc[-1])
    assert actual.weight.to_numpy() == pytest.approx(selected.regression_weight.to_numpy()/selected.regression_weight.max())
    plain = frame.drop(columns="regression_weight")
    ones = plain.assign(regression_weight=1.)
    assert annualized_logarithmic_regression_change(plain, plain.market_date.iloc[0]) == pytest.approx(annualized_logarithmic_regression_change(ones, ones.market_date.iloc[0]))
    assert _fit_weights(plain,None).eq(1).all()


@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf")])
def test_invalid_base_weights_are_rejected(invalid):
    f = sample()
    f.loc[0,"regression_weight"] = invalid
    with pytest.raises(ValueError,match="base weights"):
        logarithmic_regression_channel(f,f.market_date.iloc[0])

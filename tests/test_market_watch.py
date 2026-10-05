import pandas as pd
import pytest

from financial_dashboard.market_watch import latest_change


def frame(values, dates, source="fred"):
    return pd.DataFrame({"market_date": pd.to_datetime(dates), "close": values, "source": source})


def test_daily_change_uses_previous_available_date_not_calendar_day():
    result = latest_change(frame([100, 110], ["2026-09-25", "2026-09-28"]), "SP500")
    assert result["change"] == pytest.approx(10)
    assert result["previous_date"] == pd.Timestamp("2026-09-25")


def test_monthly_and_rate_units():
    result = latest_change(frame([100, 102], ["2026-07-31", "2026-08-31"]), "US_INFLATION")
    assert result["basis"] == "Monthly"
    assert result["unit"] == "%"
    result = latest_change(frame([4, 4.25], ["2026-09-25", "2026-09-28"]), "FED_FUNDS_TARGET")
    assert result["unit"] == "bp"
    assert result["change"] == 25


def test_missing_history_is_not_zero_change():
    assert latest_change(pd.DataFrame(), "SP500")["latest"] is None
    assert latest_change(frame([100], ["2026-09-25"]), "SP500")["change"] is None

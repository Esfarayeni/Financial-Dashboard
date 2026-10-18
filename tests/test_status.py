from datetime import date

from financial_dashboard.status import expected_cadence, freshness_status


def test_daily_freshness_uses_market_observation_date():
    status, label = freshness_status(date(2026, 9, 25), "bonbast", date(2026, 9, 28))
    assert status == "current"
    assert label == "Latest observation: Sep 25, 2026 (expected daily)"


def test_monthly_freshness_allows_publication_lag_and_missing_data_is_visible():
    assert expected_cadence("sci") == "monthly"
    assert freshness_status(date(2026, 8, 1), "sci", date(2026, 9, 28))[0] == "stale"
    assert freshness_status(None, "fred_cpi")[0] == "missing"


def test_macro_freshness_accounts_for_monthly_and_quarterly_publication_lags():
    assert expected_cadence("fred_unemployment") == "monthly"
    assert freshness_status(date(2026, 9, 1), "fred_unemployment", date(2026, 10, 14))[0] == "current"
    assert expected_cadence("fred_house_prices") == "quarterly"
    assert freshness_status(date(2026, 4, 1), "fred_house_prices", date(2026, 10, 14))[0] == "current"
    assert freshness_status(date(2025, 4, 1), "fred_house_prices", date(2026, 10, 14))[0] == "stale"

import json
import os

import numpy as np
import pandas as pd
import pytest

from financial_dashboard import analytics, leaderboard_cache as cache, stocks


@pytest.fixture
def universe(monkeypatch, tmp_path):
    monkeypatch.setattr(stocks, "STOCKS", [
        {"ticker": "A", "name": "Company A", "sector": "Industrials", "company_id": "a"},
        {"ticker": "B", "name": "Company B", "sector": "Industrials", "company_id": "b"},
    ])
    monkeypatch.setattr(stocks, "TICKERS", {"A", "B"})
    dates = pd.date_range("2010-01-01", periods=90)
    prices = np.exp(np.arange(90) * .002 + np.sin(np.arange(90)) * .05)
    frame = pd.DataFrame({"market_date": dates, "adjusted_close": prices, "quote_close": prices})
    frame.to_parquet(tmp_path / "A.parquet", index=False)
    (tmp_path / "metadata.json").write_text(json.dumps({"A": {"market_cap": 100, "listing_year": 2000}}))
    return tmp_path


@pytest.mark.parametrize("half_life", cache.HALF_LIVES)
def test_shared_fit_matches_existing_metrics_exactly_and_fits_once(monkeypatch, half_life):
    frame = pd.DataFrame({"market_date": pd.date_range("2000-01-01", periods=600, freq="7D"),
                          "close": np.exp(np.arange(600) * .005 + np.sin(np.arange(600)) * .1)})
    start = frame.market_date.iloc[0]
    expected = (analytics.annualized_logarithmic_regression_change(frame, start, half_life_years=half_life),
                *analytics.logarithmic_regression_deviation_stats(frame, start, half_life_years=half_life))
    original = analytics._fit_logarithmic_regression
    calls = []
    def fit(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(analytics, "_fit_logarithmic_regression", fit)
    assert analytics.logarithmic_regression_metrics(frame, start, half_life_years=half_life) == expected
    assert len(calls) == 1


def test_saved_snapshot_survives_restart_without_recalculating(universe, monkeypatch):
    expected = stocks.leaderboard(universe)
    result = cache.load(directory=universe)
    result.attrs = {}
    pd.testing.assert_frame_equal(result, expected)
    monkeypatch.setattr(stocks, "leaderboard", lambda *a, **kw: pytest.fail("Must read saved metrics"))
    cache._content_digest.cache_clear()
    loaded = cache.load(directory=universe)
    loaded.attrs = {}
    pd.testing.assert_frame_equal(loaded, expected)
    assert loaded.Logo.isna().all()


def test_data_and_metadata_changes_invalidate_saved_snapshots(universe, monkeypatch):
    original = stocks.leaderboard
    calls = []
    def calculate(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(stocks, "leaderboard", calculate)
    cache.load(directory=universe)
    cache.load(directory=universe)
    assert len(calls) == 1
    frame = pd.read_parquet(universe / "A.parquet")
    frame.loc[89, "adjusted_close"] *= 1.1
    frame.to_parquet(universe / "A.parquet", index=False)
    cache.load(directory=universe)
    assert len(calls) == 2
    (universe / "metadata.json").write_text(json.dumps({"A": {"market_cap": 200}}))
    result = cache.load(directory=universe)
    assert len(calls) == 3
    assert result.set_index("Ticker").loc["A", "Market cap (USD)"] == 200


def test_checkout_mtime_changes_do_not_invalidate_identical_contents(universe):
    original = cache.input_signature(universe)
    path = universe / "A.parquet"
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert cache.input_signature(universe) == original
    old = stocks.STOCKS[0]["name"]
    try:
        stocks.STOCKS[0]["name"] = "Renamed"
        assert cache.input_signature(universe) != original
    finally:
        stocks.STOCKS[0]["name"] = old


def test_market_cap_path_does_not_load_history_or_logos(universe, monkeypatch):
    monkeypatch.setattr(stocks, "load_prices", lambda *a, **kw: pytest.fail("No history needed"))
    monkeypatch.setattr(stocks, "logo_uri", lambda *a, **kw: pytest.fail("No logos needed"))
    result = stocks.market_cap_overview(universe)
    assert len(result) == 2
    assert result.set_index("Ticker").loc["A", "Market cap (USD)"] == 100
    assert "Trend/year (%)" not in result


def test_only_selected_rows_get_logos(universe, monkeypatch):
    calls = []
    monkeypatch.setattr(stocks, "logo_uri", lambda ticker, directory: calls.append(ticker) or "local-logo")
    frame = stocks.market_cap_overview(universe).head(1)
    result = stocks.with_logos(frame, universe)
    assert calls == ["A"]
    assert result.Logo.tolist() == ["local-logo"]
    assert frame.Logo.isna().all()


def test_precompute_builds_every_supported_half_life(monkeypatch):
    calls = []
    monkeypatch.setattr(cache, "load", lambda half_life, directory: calls.append(half_life) or pd.DataFrame())
    assert cache.precompute() == 8
    assert tuple(calls) == cache.HALF_LIVES


def test_corrupt_snapshot_is_rebuilt_and_concurrent_updates_not_published(universe, monkeypatch):
    path = cache._snapshot_path(universe, None)
    path.parent.mkdir()
    path.write_bytes(b"invalid parquet")
    assert len(cache.load(directory=universe)) == 2
    assert pd.read_parquet(path).attrs["input_signature"] == cache.input_signature(universe)
    signatures = iter(["before", "after"])
    monkeypatch.setattr(cache, "input_signature", lambda directory: next(signatures))
    with pytest.raises(RuntimeError, match="changed during calculation"):
        cache.load(1, universe)
    assert not cache._snapshot_path(universe, 1).exists()

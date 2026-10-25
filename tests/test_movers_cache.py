import json

import pandas as pd
import pytest

from financial_dashboard import leaderboard_cache, movers_cache as cache, stocks


@pytest.fixture
def universe(monkeypatch, tmp_path):
    monkeypatch.setattr(stocks, "STOCKS", [
        {"ticker": ticker, "name": ticker, "sector": "Industrials"} for ticker in ("A", "B", "C")])
    monkeypatch.setattr(stocks, "TICKERS", {"A", "B", "C"})
    dates = pd.to_datetime(["2024-10-21", "2025-10-21", "2026-09-22", "2026-10-15", "2026-10-21", "2026-10-22"])
    for ticker, values in [("A", [10, 20, 30, 40, 50, 60]), ("B", [80, 70, 60, 50, 40, 30]),
                           ("C", [5, 6, 7, 8, 9])]:
        pd.DataFrame({"market_date": dates[:len(values)], "quote_close": values}).to_parquet(tmp_path / f"{ticker}.parquet", index=False)
    return tmp_path


@pytest.mark.parametrize("period,expected_change", [("Daily", 20), ("Weekly", 50), ("Monthly", 100), ("Yearly", 200)])
def test_saved_rankings_match_existing_calculation_and_session_filter(universe, period, expected_change):
    expected = stocks.daily_movers(universe, period).reset_index(drop=True)
    actual = cache.load(period, universe)
    assert actual.iloc[0].Change == pytest.approx(expected_change)
    assert set(actual.Name) == {"A (A)", "B (B)"}
    actual.attrs = {}
    pd.testing.assert_frame_equal(actual.reset_index(drop=True), expected)


def test_all_four_periods_survive_restart_without_history_scans(universe, monkeypatch):
    assert cache.precompute(universe) == 4
    leaderboard_cache._content_digest.cache_clear()
    monkeypatch.setattr(stocks, "daily_movers", lambda *a, **kw: pytest.fail("No recalculation on snapshot read"))
    for period in cache.PERIODS:
        assert len(cache.load(period, universe)) == 2
    assert len(list((universe / "leaderboards").glob("movers_*.parquet"))) == 4


def test_changed_prices_invalidate_snapshot(universe):
    first = cache.load("Daily", universe)
    frame = pd.read_parquet(universe / "A.parquet")
    frame.loc[len(frame) - 1, "quote_close"] = 70
    frame.to_parquet(universe / "A.parquet", index=False)
    updated = cache.load("Daily", universe)
    assert updated.iloc[0].Change == pytest.approx(40)
    assert updated.attrs["input_signature"] != first.attrs["input_signature"]


def test_catalog_and_metadata_invalidation(universe, monkeypatch):
    first = cache.input_signature(universe)
    (universe / "metadata.json").write_text(json.dumps({"A": {"market_cap": 100}}))
    second = cache.input_signature(universe)
    assert second != first
    monkeypatch.setattr(stocks, "STOCKS", stocks.STOCKS[:2])
    assert cache.input_signature(universe) != second


def test_corrupt_snapshot_rebuild_and_concurrent_updates_not_published(universe, monkeypatch):
    path = universe / "leaderboards" / "movers_daily.parquet"
    path.parent.mkdir()
    path.write_bytes(b"invalid parquet")
    assert len(cache.load("Daily", universe)) == 2
    signatures = iter(["before", "after"])
    monkeypatch.setattr(cache, "input_signature", lambda _: next(signatures))
    with pytest.raises(RuntimeError, match="changed during calculation"):
        cache.load("Weekly", universe)
    assert not (path.parent / "movers_weekly.parquet").exists()


def test_empty_rankings_and_unsupported_period(universe, monkeypatch):
    monkeypatch.setattr(stocks, "STOCKS", [])
    assert cache.load("Daily", universe).empty
    assert cache.load("Daily", universe).columns.tolist() == ["Name", "Change", "Date"]
    with pytest.raises(ValueError, match="Unsupported"):
        cache.load("Invalid", universe)

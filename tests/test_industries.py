import json

import pandas as pd
import pytest

from financial_dashboard import industries


def test_bulk_industries_use_live_names_and_preserve_profiles(monkeypatch, tmp_path):
    monkeypatch.setattr(industries, "update_metadata", lambda *args, **kwargs: [])
    monkeypatch.setattr(industries, "TICKERS", {"ABC", "DEF"})
    monkeypatch.setattr(industries.time, "sleep", lambda _: None)
    monkeypatch.setattr(industries.yf, "Sector", lambda _: type("Sector", (), {
        "industries": pd.DataFrame({"name": ["Oil & Gas E&P"]})})())
    monkeypatch.setattr(industries.yf, "screen", lambda query, **kw: {
        "start": kw["offset"], "total": 1,
        "quotes": [{"symbol": "ABC"}, {"symbol": "NOT_SELECTED"}]})
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"ABC": {"business_summary": "Existing profile", "market_cap": 123}}))
    industries.synchronize(tmp_path)
    entry = json.loads(path.read_text())["ABC"]
    assert entry["business_summary"] == "Existing profile"
    assert entry["market_cap"] == 123
    assert entry["industry"] == "Oil & Gas E&P"
    assert entry["industry_source"] == "Yahoo Finance equity screener"
    assert "NOT_SELECTED" not in json.loads(path.read_text())


def test_bulk_import_stops_and_preserves_completed_groups_on_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(industries, "TICKERS", {"ABC"})
    monkeypatch.setattr(industries.time, "sleep", lambda _: None)
    monkeypatch.setattr(industries.yf, "Sector", lambda _: type("Sector", (), {
        "industries": pd.DataFrame({"name": ["Auto Manufacturers", "Semiconductors"]})})())
    calls = []
    def screen(query, **kw):
        calls.append(query)
        if len(calls) == 2:
            raise RuntimeError("Rate limited")
        return {"start": 0, "total": 1, "quotes": [{"symbol": "ABC"}]}
    monkeypatch.setattr(industries.yf, "screen", screen)
    with pytest.raises(RuntimeError, match="Rate limited"):
        industries.synchronize(tmp_path)
    assert len(calls) == 2
    assert json.loads((tmp_path / "metadata.json").read_text())["ABC"]["industry"] == "Auto Manufacturers"

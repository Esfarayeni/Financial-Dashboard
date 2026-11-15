from datetime import date

import pandas as pd
import pytest

from financial_dashboard import db
from financial_dashboard.providers import housing


def test_archive_dates_units_gaps_and_idempotent_import(tmp_path):
    rows = housing.fetch_history()
    assert len(rows) == 91
    assert rows[0].market_date == date(2016, 4, 19)
    assert rows[-1].market_date == date(2024, 8, 21)
    assert rows[-1].close == 88_500_000  # 885 million IRR / 10, not another /10
    assert {r.unit for r in rows} == {"toman_per_m2"}
    assert any((b.market_date - a.market_date).days > 40 for a, b in zip(rows, rows[1:]))
    path = tmp_path / "market.db"
    db.initialize(path)
    db.upsert_prices(rows, path)
    db.upsert_prices(rows, path)
    assert len(db.load_prices(housing.SYMBOL, path)) == 91


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_reject_invalid_prices(value):
    frame = pd.DataFrame([dict(jalali_year=1403, jalali_month=5,
                              price_per_m2_toman=value, source_url="https://example.org")])
    with pytest.raises(ValueError):
        housing.extract_rows(frame)


def test_reject_duplicate_months():
    frame = pd.read_csv(housing.ARCHIVE).iloc[:1]
    with pytest.raises(ValueError, match="Duplicate"):
        housing.extract_rows(pd.concat([frame, frame]))

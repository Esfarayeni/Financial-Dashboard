import csv
from datetime import date

import pytest

from financial_dashboard.config import DATA_DIR
from financial_dashboard.providers import tindex


def test_saved_public_table_and_date_not_headline_refresh():
    with (DATA_DIR / "housing/tindex_asking_snapshot.csv").open() as f:
        entries = list(csv.DictReader(f))
    html = '<p>آخرین به‌روزرسانی: ۱۰ آبان ۱۴۰۵</p><table><tr><th>تاریخ</th><th>بازگشایی</th><th>بیشترین</th><th>کمترین</th><th>پایانی</th></tr>'
    for r in entries:
        html += f'<tr><td>{r["persian_date"]}</td><td>—</td><td>—</td><td>—</td><td><b>{int(r["toman_per_m2"]):,}</b></td></tr>'
    rows = tindex.parse_history(html + '</table>')
    assert len(rows) == 18
    assert rows[0].market_date == date(2026, 7, 14)
    assert rows[-1].market_date == date(2026, 10, 27)
    assert rows[-1].close == 302_832_601
    assert {r.symbol for r in rows} == {"TEHRAN_HOUSING_ASKING"}


@pytest.mark.parametrize('html', ['<h1>302832601</h1>', '<table><tr><th>تاریخ</th><th>قیمت</th></tr></table>'])
def test_missing_table_is_failure_not_headline_fallback(html):
    with pytest.raises(ValueError):
        tindex.parse_history(html)


@pytest.mark.parametrize('price', ['NaN', 'inf', '-1', '0'])
def test_invalid_prices_rejected(price):
    with pytest.raises(ValueError):
        tindex.observation('۵ آبان ۱۴۰۵', price)

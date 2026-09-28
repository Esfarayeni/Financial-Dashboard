from datetime import datetime, timezone

import pytest

from financial_dashboard.providers.databourse import (
    DataBourseError,
    jalali_to_gregorian,
    parse_index_history,
)


HTML = '''
<script>
var dataArray = [
  {"date":"1403-01-01","value":2300000.5},
  {"date":"1403-01-02","value":2310000}
];
</script>
'''


def test_jalali_to_gregorian():
    assert jalali_to_gregorian(1403, 1, 1).isoformat() == "2024-03-20"
    assert jalali_to_gregorian(1405, 6, 30).isoformat() == "2026-09-21"


def test_parse_index_history_converts_and_sorts_dates():
    rows = parse_index_history(HTML, datetime(2024, 3, 22, tzinfo=timezone.utc))

    assert [row.market_date.isoformat() for row in rows] == ["2024-03-20", "2024-03-21"]
    assert [row.close for row in rows] == [2_300_000.5, 2_310_000]
    assert rows[0].source == "databourse"


def test_parse_index_history_rejects_missing_data():
    with pytest.raises(DataBourseError):
        parse_index_history("<html></html>")

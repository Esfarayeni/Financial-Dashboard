from datetime import datetime, timezone

import pytest

from financial_dashboard.providers.tsetmc import TSETMCError, parse_index_history


def test_parse_index_history_uses_official_close_and_sorts_dates():
    rows = parse_index_history(
        {
            "indexB2": [
                {"dEven": "20260920", "xNivInuClM": 2_000_100},
                {"dEven": "20260919", "xNivInuClM": "1,999,500".replace(",", "")},
            ]
        },
        datetime(2026, 9, 21, tzinfo=timezone.utc),
    )

    assert [row.market_date.isoformat() for row in rows] == ["2026-09-19", "2026-09-20"]
    assert [row.close for row in rows] == [1_999_500, 2_000_100]
    assert rows[0].symbol == "TEDPIX"
    assert rows[0].unit == "points"


def test_parse_index_history_rejects_unexpected_shape():
    with pytest.raises(TSETMCError):
        parse_index_history({"unexpected": []})

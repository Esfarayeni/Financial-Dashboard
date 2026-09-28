import pandas as pd

from financial_dashboard.providers.sci import _extract_rows


def test_extract_rows_reads_monthly_sci_cpi_and_converts_jalali_dates():
    rows = _extract_rows(
        pd.DataFrame(
            [
                {"source_id": "sci", "freq": "M", "period": "1400-01", "cpi_index": 100.0},
                {"source_id": "sci", "freq": "M", "period": "1400-02", "cpi_index": 102.0},
                {"source_id": "other", "freq": "M", "period": "1400-01", "cpi_index": 1.0},
            ]
        )
    )

    assert [row.market_date.isoformat() for row in rows] == ["2021-03-21", "2021-04-21"]
    assert [row.close for row in rows] == [100.0, 102.0]
    assert {row.symbol for row in rows} == {"IRAN_INFLATION"}

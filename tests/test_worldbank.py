from datetime import date

import pandas as pd

from financial_dashboard.providers.worldbank import _extract_rows


def test_extract_rows_reads_monthly_gold_and_silver_at_month_end():
    frame = pd.DataFrame(
        [
            ["World Bank Commodity Price Data", None, None],
            [None, "Gold", "Silver"],
            ["1960M01", 35.27, 0.91],
            ["1960M02", "…", 0.92],
            ["not a month", 999, 999],
        ]
    )

    rows = _extract_rows(frame)

    assert [(row.symbol, row.market_date, row.close) for row in rows] == [
        ("XAG/USD", date(1960, 1, 31), 0.91),
        ("XAG/USD", date(1960, 2, 29), 0.92),
        ("XAU/USD", date(1960, 1, 31), 35.27),
    ]
    assert {row.source for row in rows} == {"world_bank_pink_sheet"}

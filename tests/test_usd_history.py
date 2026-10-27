import ast
import csv
from datetime import date, datetime, timezone
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from financial_dashboard import db, usd_history
from financial_dashboard.analytics import chart_price_bounds


def csv_file(tmp_path, rows):
    path = tmp_path / "history.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date_pr", "date_gr", "source", "price_avg"])
        writer.writerows(rows)
    return path


def test_collapse_averages_at_period_end_and_convert_rials(tmp_path):
    path = csv_file(tmp_path, [
        ["1360/07/07", "9/29/1981", "bourseview", "270"],
        ["1360/07/08", "9/30/1981", "bourseview", "270"],
        ["1364/01/01", "3/21/1985", "bourseview", "596"],
        ["1364/01/02", "3/22/1985", "bourseview", "596"],
        ["1391/07/17", "10/8/2012", "tgju", "32,375"],
        ["1391/07/18", "10/9/2012", "tgju", "35,000"],
    ])
    rows, report = usd_history.prepare(path, date(2012, 10, 9))
    assert len(rows) == 3
    assert rows[0].market_date == date(1982, 3, 20)
    assert rows[0].close == 27
    assert rows[0].unit == "toman_annual_average"
    assert rows[1].market_date == date(1985, 4, 20)
    assert rows[2].close == 3237.5
    assert all(row.market_date < date(2012, 10, 9) for row in rows)
    assert report["excluded_at_or_after_bonbast"] == 1


def test_persian_dates_override_wrong_gregorian_and_deduplicate(tmp_path):
    path = csv_file(tmp_path, [["1405/07/16", "2026/10/7", "tgju", "2,667,000"]]*2)
    rows, report = usd_history.prepare(path, date(2027, 1, 1))
    assert len(rows) == 1 and rows[0].market_date == date(2026, 10, 8)
    assert report["duplicate_rows"] == 1
    assert report["gregorian_mismatches"] == 2


@pytest.mark.parametrize("prices", [[270, 271], [270, -1], [270, "nan"]])
def test_reject_inconsistent_period_or_invalid_prices(tmp_path, prices):
    path = csv_file(tmp_path, [["1360/07/07", "9/29/1981", "bourseview", prices[0]],
                               ["1360/07/08", "9/30/1981", "bourseview", prices[1]]])
    with pytest.raises(ValueError): usd_history.prepare(path, date(2012, 10, 9))


def test_import_idempotent_and_bonbast_precedence(tmp_path):
    database = tmp_path / "market.db"
    db.initialize(database)
    now = datetime.now(timezone.utc)
    original = db.Price("USD/IRT", date(2012, 10, 9), 3550, "IRT", "toman", "bonbast", now)
    db.upsert_prices([original], database)
    path = csv_file(tmp_path, [["1391/07/17", "10/8/2012", "tgju", "32,375"],
                               ["1391/07/18", "10/9/2012", "tgju", "35,000"]])
    for _ in range(2): usd_history.import_history(path, database, tmp_path / "archive")
    frame = db.load_prices("USD/IRT", database)
    assert frame.close.tolist() == [3237.5, 3550]
    assert frame.source.iloc[-1] == "bonbast"
    # A future, earlier Bonbast backfill supersedes the corresponding extension.
    db.upsert_prices([db.Price("USD/IRT", date(2012, 10, 8), 3400, "IRT", "toman", "bonbast_archive", now)], database)
    frame = db.load_prices("USD/IRT", database)
    assert frame.close.tolist() == [3400, 3550]


def test_import_requires_bonbast_cutoff(tmp_path):
    database = tmp_path / "empty.db"
    db.initialize(database)
    with pytest.raises(ValueError, match="Bonbast first"):
        usd_history.import_history(tmp_path / "missing.csv", database, tmp_path / "archive")


def test_chart_distinguishes_historical_extension_from_bonbast():
    module = ast.parse(Path("app.py").read_text())
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "build_chart")
    namespace = {"pd": pd, "go": go, "math": math, "chart_price_bounds": chart_price_bounds}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
    frame = pd.DataFrame({"market_date": pd.to_datetime(["1982-03-20", "1983-03-20", "2012-10-09", "2012-10-10"]),
                          "close": [27, 35, 3550, 3600],
                          "source": ["usd2rials_bourseview_annual_average"]*2 + ["bonbast"]*2})
    figure = namespace["build_chart"](frame, "USD / Toman", "blue", 0, True,
        {"chart_background": "white", "grid": "gray", "muted": "gray", "text": "black"})
    assert [trace.line.dash for trace in figure.data] == ["dot", "solid"]
    assert len(figure.data[0].x) == 2
    assert "annual average" in figure.data[0].name

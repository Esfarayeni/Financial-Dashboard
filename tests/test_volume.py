from datetime import date
import ast
import math
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from financial_dashboard import stocks, volume
from financial_dashboard.analytics import chart_price_bounds


def history():
    return pd.DataFrame({"Volume": [100, 200, 300], "Close": [10, 11, 12], "Adj Close": [9, 10, 11]},
                        index=pd.date_range("2020-01-01", periods=3, tz="America/New_York"))


def test_normalize_excludes_incomplete_and_invalid_volume_without_dropping_prices():
    raw = history()
    assert volume.normalize(raw, today=date(2020, 1, 3)).volume.tolist() == [100, 200]
    raw.loc[raw.index[0], "Volume"] = float("nan")
    assert len(stocks.normalize_history(raw)) == 3
    assert volume.normalize(raw).volume.tolist() == [200, 300]
    assert stocks.normalize_history(history()).volume.tolist() == [100, 200, 300]


def test_volume_updates_incrementally_and_preserves_snapshot_on_failure(monkeypatch, tmp_path):
    calls = []
    class Ticker:
        def history(self, **kwargs):
            calls.append(kwargs)
            return history()
    monkeypatch.setattr(volume.yf, "Ticker", lambda ticker: Ticker())
    volume.update("SP500", directory=tmp_path)
    assert calls[-1]["period"] == "max"
    volume.update("SP500", directory=tmp_path)
    assert "start" in calls[-1]
    expected = volume.load("SP500", tmp_path)
    monkeypatch.setattr(Ticker, "history", lambda self, **kwargs: pd.DataFrame())
    with pytest.raises(ValueError):
        volume.update("SP500", directory=tmp_path)
    pd.testing.assert_frame_equal(volume.load("SP500", tmp_path), expected)


def test_volume_rejects_unrelated_symbols_and_missing_volume_is_empty(tmp_path):
    assert volume.load("STOCK:AAPL", tmp_path).empty
    with pytest.raises(ValueError):
        volume.load("../../other", tmp_path)


def test_volume_aggregation_sums_all_reported_days_and_never_invents_zeroes():
    prices = pd.DataFrame({"market_date": pd.date_range("2000-01-01", "2007-01-01"),
                           "close": np.arange(2558)+10})
    volumes = prices[["market_date"]].copy()
    volumes["volume"] = 100.0
    volumes.loc[volumes.market_date < "2001-01-01", "volume"] = np.nan
    chart = volume.for_chart(prices, volumes)
    assert chart.volume.sum() == pytest.approx(volumes.volume.sum())
    assert set(chart.period) == {"Weekly total"}
    assert (chart.volume > 0).all()
    assert chart.market_date.is_monotonic_increasing
    expected = volumes.groupby(volumes.market_date.dt.to_period("W-FRI")).volume.sum(min_count=1).dropna()
    assert chart.volume.to_numpy() == pytest.approx(expected.to_numpy())
    assert chart.market_date.dt.to_period("W-FRI").is_unique


@pytest.mark.parametrize("weights", [False, True])
@pytest.mark.parametrize("logarithmic", [False, True])
def test_volume_chart_uses_separate_linear_axis_and_shared_dates(weights, logarithmic):
    # Compile just the pure figure builder, without executing Streamlit's app.
    module = ast.parse(Path("app.py").read_text())
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "build_chart")
    namespace = {"pd": pd, "go": go, "math": math, "chart_price_bounds": chart_price_bounds}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
    frame = pd.DataFrame({"market_date": pd.date_range("2020-01-01", periods=40), "close": np.arange(40)+10})
    vols = frame[["market_date"]].assign(volume=1000, period="Daily", color="green")
    observation_weights = frame[["market_date"]].assign(weight=1) if weights else None
    fig = namespace["build_chart"](frame, "Stock", "blue", 2, logarithmic,
           {"chart_background": "white", "grid": "gray", "muted": "gray", "text": "black"},
           observation_weights=observation_weights, weights_training_end=frame.market_date.iloc[-1],
           trade_volume=vols, fit_prices_only=True)
    assert fig.layout.yaxis.type == ("log" if logarithmic else "linear")
    assert fig.layout.yaxis3.type == "linear"
    assert fig.layout.yaxis3.overlaying == "y"
    assert list(fig.layout.yaxis3.range) == [0, 5000]
    assert fig.layout.yaxis3.showticklabels is False
    assert fig.data[-1].type == "bar" and fig.data[-1].yaxis == "y3"
    assert all(trace.xaxis in (None, "x") for trace in fig.data)
    assert tuple(fig.layout.yaxis3.domain) == tuple(fig.layout.yaxis.domain or [0, 1])
    assert fig.data[-1].zorder < (fig.data[0].zorder or 0)
    baseline = namespace["build_chart"](frame, "Stock", "blue", 2, logarithmic,
           {"chart_background": "white", "grid": "gray", "muted": "gray", "text": "black"},
           observation_weights=observation_weights, weights_training_end=frame.market_date.iloc[-1],
           fit_prices_only=True)
    assert fig.layout.yaxis.to_plotly_json() == baseline.layout.yaxis.to_plotly_json()
    assert fig.layout.xaxis.to_plotly_json() == baseline.layout.xaxis.to_plotly_json()
    assert fig.layout.height == baseline.layout.height
    if weights:
        assert fig.layout.yaxis3.domain[0] > fig.layout.yaxis2.domain[1]

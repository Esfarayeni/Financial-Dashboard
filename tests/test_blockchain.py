from financial_dashboard.providers.blockchain import _parse


def test_parse_reads_market_price_observations():
    rows = _parse({"values": [{"x": 1_278_307_200, "y": 0.08}]})

    assert len(rows) == 1
    assert rows[0].symbol == "BTC/USD"
    assert rows[0].market_date.isoformat() == "2010-07-05"
    assert rows[0].close == 0.08

from financial_dashboard.providers.coingecko import _parse


def test_parse_assigns_the_requested_crypto_symbol():
    rows = _parse(
        {"prices": [[1_577_836_800_000, 130.5], [1_577_923_200_000, 135.25]]},
        "binancecoin",
    )

    assert [row.market_date.isoformat() for row in rows] == ["2020-01-01", "2020-01-02"]
    assert [row.close for row in rows] == [130.5, 135.25]
    assert {row.symbol for row in rows} == {"BNB/USD"}
    assert {row.source for row in rows} == {"coingecko"}

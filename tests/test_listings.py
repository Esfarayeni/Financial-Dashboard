import json
import pytest
from financial_dashboard import listings


def test_nasdaq_filters_non_company_issues_but_keeps_adrs_and_reits():
    text = "Symbol|Security Name|Test Issue|ETF\n" + "\n".join([
        "AAPL|Apple Inc. - Common Stock|N|N",
        "ADR|Foreign Ltd - American Depositary Shares|N|N",
        "REIT|Example Trust - Common Shares|N|N",
        "ETF|Example ETF|N|Y", "TEST|Test Company - Common Stock|Y|N",
        "ACQU|Acquisition Corp - Units|N|N", "ACQW|Acquisition Corp - Warrants|N|N",
        "ACQR|Acquisition Corp - Rights|N|N", "PREF|Example Preferred Stock|N|N",
        "RIGHT|Acquisition Corp - Right|N|N",
        "DEBT|Example Senior Notes Due 2030|N|N", "File Creation Time: 10192026||||",
    ])
    assert [row["ticker"] for row in listings.parse_directory(text, "Nasdaq")] == ["AAPL", "ADR", "REIT"]


def test_nyse_filters_exchanges_and_converts_yahoo_share_classes():
    text = "ACT Symbol|Security Name|Exchange|Test Issue|ETF\nBRK.B|Berkshire Hathaway Class B|N|N|N\nOTHER|Other company|A|N|N\nBAD$A|Preferred shares|N|N|N\n"
    assert listings.parse_directory(text, "NYSE")[0]["ticker"] == "BRK-B"
    assert len(listings.parse_directory(text, "NYSE")) == 1


def test_failed_or_tiny_catalog_refresh_preserves_existing_file(monkeypatch, tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text('{"old": true}')
    class Response:
        text = "Symbol|Security Name|Test Issue|ETF\nAAPL|Apple|N|N"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(listings.requests, "get", lambda *a, **k: Response())
    with pytest.raises(ValueError, match="Suspiciously small"):
        listings.refresh(path)
    assert json.loads(path.read_text()) == {"old": True}


def test_bad_source_format_is_rejected():
    with pytest.raises(ValueError, match="Invalid"):
        listings.parse_directory("<html>Error</html>", "Nasdaq")


def test_company_name_omits_security_description_without_losing_source_text():
    text = "ACT Symbol|Security Name|Exchange|Test Issue|ETF\nBABA|Alibaba Group Holding Limited American Depositary Shares each representing eight Ordinary shares|N|N|N\n"
    row = listings.parse_directory(text, "NYSE")[0]
    assert row["name"] == "Alibaba Group Holding Limited"
    assert "American Depositary" in row["security_name"]

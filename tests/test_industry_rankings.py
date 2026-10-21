import pandas as pd

from financial_dashboard.stocks import industry_cap_groups
from financial_dashboard.market_cap_map import industry_bars_html


def test_each_industry_ranks_ten_largest_across_size_bands():
    rows = [{"Company ID": str(i), "Company": f"Company {i}", "Ticker": f"C{i}",
             "Sector": "Industrials", "Industry": "Machinery", "Market cap (USD)": (i + 1) * 1e9}
            for i in range(15)]
    rows += [{**rows[-1], "Ticker": "OTHER_CLASS"},
             {**rows[0], "Company ID": "invalid", "Market cap (USD)": -1},
             {**rows[0], "Company ID": "other_sector", "Sector": "Energy"},
             {**rows[0], "Company ID": "second_industry", "Industry": "Airlines"}]
    groups = {name: (frame, total) for name, frame, total in industry_cap_groups(pd.DataFrame(rows), "Industrials")}
    shown, total = groups["Machinery"]
    assert total == 15
    assert len(shown) == 10
    assert shown["Market cap (USD)"].tolist() == [i * 1e9 for i in range(15, 5, -1)]
    assert len(groups["Airlines"][0]) == 1


def test_unclassified_industry_is_explicit_and_empty_sector_has_no_charts():
    frame = pd.DataFrame([{"Company ID": "a", "Sector": "Energy", "Industry": None,
                           "Market cap (USD)": 10}])
    assert industry_cap_groups(frame, "Energy")[0][0] == "Industry unavailable"
    assert industry_cap_groups(frame, "Health Care") == []


def test_direct_industry_selection_includes_all_sectors():
    frame = pd.DataFrame([
        {"Company ID": "a", "Sector": "Energy", "Industry": "Oil & Gas Integrated", "Market cap (USD)": 10},
        {"Company ID": "b", "Sector": "Consumer Discretionary", "Industry": "Auto Manufacturers", "Market cap (USD)": 20},
    ])
    assert [name for name, _, _ in industry_cap_groups(frame)] == ["Auto Manufacturers", "Oil & Gas Integrated"]


def test_ranked_bars_show_exact_linear_ratios_logos_and_links():
    frame = pd.DataFrame([{"Company": "A & B", "Ticker": "AB", "Sector": "Industrials",
                           "Market cap (USD)": value, "Logo": "data:image/png;base64,AAAA"}
                          for value in [10e9, 5e9]])
    html = industry_bars_html(frame, "Tools & Machinery")
    assert "width:100.000000%" in html
    assert "width:50.000000%" in html
    assert '<figcaption>Tools &amp; Machinery</figcaption>' in html
    assert 'A &amp; B' in html
    assert html.count('<li>') == 2
    assert html.count('src="data:image/png;base64,AAAA"') == 2
    assert 'dashboard_section=Stocks' in html
    assert '$10B' in html and '$5.0B' in html
    assert 'title="$10,000,000,000"' in html
    assert '#e1e7ef' in industry_bars_html(frame, "Machinery", dark=True)

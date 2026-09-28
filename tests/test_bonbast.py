from datetime import datetime, timezone

import pytest

from financial_dashboard.providers.bonbast import BonbastFormatError, parse_graph_html


HTML = """
<script>
var chart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: [new Date('2026-09-18'), new Date('2026-09-19')],
    datasets: [{label: 'usd', data: [228600, 230700]}]
  },
  options: {}
});
</script>
"""


def test_parse_graph_html():
    fetched = datetime(2026, 9, 20, tzinfo=timezone.utc)
    rows = parse_graph_html(HTML, fetched)
    assert [row.close for row in rows] == [228600, 230700]
    assert rows[0].symbol == "USD/IRT"
    assert rows[0].unit == "toman"
    assert rows[1].market_date.isoformat() == "2026-09-19"


def test_parse_graph_html_rejects_missing_chart():
    with pytest.raises(BonbastFormatError):
        parse_graph_html("<html></html>")


def test_parse_graph_html_rejects_mismatched_lengths():
    with pytest.raises(BonbastFormatError):
        parse_graph_html(HTML.replace("228600, 230700", "228600"))


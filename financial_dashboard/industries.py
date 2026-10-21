"""Import industry membership in bulk; no network requests while rendering."""
import json
import time
from datetime import datetime, timezone

import yfinance as yf

from .stocks import STOCK_DIR, TICKERS, update_metadata


class IndustryQuery(yf.EquityQuery):
    """Validate against Yahoo's live labels, not the client's outdated static list."""
    industry_names = set()

    @property
    def valid_values(self):
        return {**super().valid_values, "industry": self.industry_names}


def synchronize(directory=STOCK_DIR):
    path = directory / "metadata.json"
    metadata = json.loads(path.read_text()) if path.exists() else {}
    sectors = yf.EquityQuery("eq", ["region", "us"]).valid_values["sector"]
    taxonomy = {}
    for sector in sorted(sectors):
        table = yf.Sector(sector.lower().replace(" ", "-")).industries
        if table is None or table.empty:
            raise ValueError(f"No current industry taxonomy for {sector}; preserving saved data")
        taxonomy[sector] = set(table["name"].dropna())
    IndustryQuery.industry_names = set().union(*taxonomy.values())
    updated = datetime.now(timezone.utc).isoformat()
    count = 0
    try:
        for sector, industries in sorted(taxonomy.items()):
            for industry in sorted(industries):
                offset = 0
                while True:
                    query = IndustryQuery("and", [
                        IndustryQuery("is-in", ["exchange", "NMS", "NGM", "NCM", "NYQ"]),
                        IndustryQuery("eq", ["industry", industry]),
                    ])
                    response = yf.screen(query, size=250, offset=offset,
                                         sortField="intradaymarketcap", sortAsc=False)
                    if response.get("start") != offset:
                        raise ValueError("Unexpected industry screener page")
                    rows = response.get("quotes", [])
                    for row in rows:
                        if row.get("symbol") in TICKERS:
                            metadata.setdefault(row["symbol"], {}).update(
                                industry=industry, industry_sector=sector,
                                industry_source="Yahoo Finance equity screener",
                                industry_updated=updated)
                            count += 1
                    offset += len(rows)
                    if offset >= response.get("total", offset):
                        break
                    if not rows:
                        raise ValueError("Industry screener ended before its reported total")
                    time.sleep(0.25)
                # Persist completed groups even if the next request is rate-limited.
                temporary = path.with_suffix(".json.tmp")
                temporary.write_text(json.dumps(metadata, indent=2) + "\n")
                temporary.replace(path)
                print(f"{industry}: {count} selected listings classified", flush=True)
                time.sleep(0.25)
    finally:
        print(f"Saved industry classifications for {count} selected listings", flush=True)
    # Yahoo's bulk screener omits some otherwise valid industry filters (for
    # example Banks - Diversified). Only these missing companies need profiles.
    results = update_metadata(directory, missing_industry=True, progress=True)
    print(f"Individual fallback: {sum(row['status'] == 'success' for row in results)} saved; "
          f"{sum(row['status'] != 'success' for row in results)} unavailable", flush=True)


if __name__ == "__main__":
    synchronize()

# Stocks extension

Mode: Operate. Preserve the existing Streamlit dashboard's white surfaces, blue controls, native table interactions, and current navigation.

Market Watch defaults to Stocks, followed by Markets. Markets retain compact cards in six desktop columns with responsive reductions. Stocks use semantic horizontal-scroll tables: white surfaces, separated rows without vertical gridlines, local logos, gray ticker labels, colored percentages, and same-tab chart links. The full leaderboard retains search and sorting and adds 25/50/100-row pagination; sector rankings don't paginate. Gainers and losers are compact bordered panels stacked in a right-hand column beside the main stock view, showing 12 logo/company/change rows each. Independent period selectors sit below their headings. The columns stack on mobile with the leaderboard first; no cap, date, price or sector fields appear in the mover panels. Missing values render as dashes; empty results are explicit. No new fundamental metrics or data requests were introduced.

## Direction contract

THESIS: Scan all current S&P 500 stocks, compare regression trends within sectors, and inspect company size without leaving Market Watch.

OWN-WORLD: Inherit white cards, dark readable text, blue selected controls and the existing dotted background; no replacement identity.

STORY: Search a company, review its trend and equal-weight sector average, open its chart, or switch to market-cap area by sector.

Market-cap map: largest 50 companies in the current S&P 500 snapshot, deduplicated before limiting. Search narrows that same set. Sector categorical colors replace trend colors; centered company names and dollar caps replace ticker-only labels. Tile area remains company cap, not index weight. The supplied poster guides composition and color grouping, not its historical/global universe or values.

Poster refinement: squarified semantic HTML links replace the Plotly market-cap renderer, with softer sector colors, dark readable text, corner dollar caps, and centered local PNG logos in larger tiles. The canvas retains a 900px minimum width and horizontal scrolling on narrow screens to preserve its information density. Sector headers reserve a narrow strip; within each sector body, company tile areas remain proportional to cap. Logos retain the FMP provenance above. No new data requests or imagery were generated.

Logo backgrounds are transparent, without white backing plates. Multiply blending suppresses baked-in white backgrounds in a few original PNGs; source assets are preserved.

Industry refinement: preserve the current five size-band figures, sector palette,
logos and chart links. Inside each sector, squarify contiguous industry groups
before laying out company tiles, so similar businesses sit together. Compact
industry headings occupy a reserved 22px strip only in sufficiently large groups;
small groups expose the industry in the company tooltip and accessible link name.
Unavailable classifications are labeled rather than inferred. Local industry
metadata comes from Yahoo's current sector taxonomy and bulk screener, with
individual-profile fallback; no network requests run during rendering. Existing
900px map minimum and horizontal-scroll regions preserve the dense map on mobile.

Industry rankings alternative: a native representation selector preserves the
size map and adds a direct searchable industry dropdown with horizontal rankings,
ten companies per industry across all size bands. The chosen industry's figure
uses the available width on desktop and mobile. The company's local
logo, ticker, truncated name, proportional bar and formatted cap share one linked
row; the accessible name includes its full name and cap. Bars are independently
scaled and captions disclose this. No data fetch runs during rendering.

Stock detail refinement: the price header shows a compact market-cap line below
the existing quote/date details. It uses the latest valid local USD cap, with a
source/retrieval-date tooltip, and Unavailable for missing caps. It does not follow
the chart's historical range. Existing descriptions are preserved; official
investor-relations summaries fill provider gaps with visible source links.

Performance refinement: keep the rendered leaderboard and market-cap layout
unchanged. Rankings load portable, data-versioned metric snapshots prepared by
daily sync for every half-life, and share one fit per company. Only selected
table rows/movers/tiles receive logo data. Market-cap browsing bypasses price
history and regression entirely. Missing snapshots have an honest loading label
and a locked, atomic one-time rebuild; no spinner-only concealment of the work.

FIRST VIEWPORT: Stocks heading and search above the left Leaderboard/Sectors/Market cap switch and right mover sidebar. Sort controls lead the logo-bearing table; its footer shows rows-per-page and range navigation. There is no checkbox or History from column. Alternatives are equal-weight sector rankings and a treemap. Each gainers/losers heading has its own Daily, Weekly, Monthly and Yearly selector showing a compact 12-stock list.

FORM: Precisely specified local extension; no concept seed. Company identifiers deduplicate share classes in sector averages and the size map. Metadata and imagery are local; unavailable logos are omitted.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Logo provenance: Financial Modeling Prep public PNG endpoint, https://images.financialmodelingprep.com/symbol/{ticker}.png. Existing design-system files are absent and this extension does not create a replacement world.

## Finish evidence

Disposition: ship; no material findings in the supplied desktop and mobile leaderboard/market-cap captures (`/private/tmp/financial-stock-review/{leaderboard,market-cap,leaderboard-mobile,market-cap-mobile}.jpg`). The stock surface retains the incumbent dotted background, white surfaces, blue selected controls, native table behavior, and existing watch-card styles and responsive breakpoints in `app.py`; the diff does not change their global tokens.

Documentation checked against `app.py`, `financial_dashboard/stocks.py`, and README: full-history adjusted-price trends, equal-weight company sector means, share-class deduplication, company-cap area, capped trend colors, hidden Price date/Cap updated columns, and local logo provenance are documented. The supplied captures verify the visible leaderboard and treemap at both sizes; interaction and data verification belong to the implementation checks.

For this ordinary extension, this task-local note completes documentation. No `DESIGN.md`, `PRODUCT.md`, or design sidecar existed, so there is no existing global-document drift to refresh; their absence does not authorize creating a new visual world or normative tokens. This narrows the earlier FINISH template's global-document requirement to the preserved incumbent scope.

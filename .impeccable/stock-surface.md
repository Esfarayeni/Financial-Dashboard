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

Mover-panel performance: preserve both independent period selectors and the
existing 12-row logo lists. Daily/Weekly/Monthly/Yearly results are precomputed
by daily sync into four data-versioned snapshots. The panels share the same
period result and memory cache, with no 15-minute expiry or history scans on a
valid cache hit. Empty rankings and stale-session exclusion keep existing behavior.

FIRST VIEWPORT: Stocks heading and search above the left Leaderboard/Sectors/Market cap switch and right mover sidebar. Sort controls lead the logo-bearing table; its footer shows rows-per-page and range navigation. There is no checkbox or History from column. Alternatives are equal-weight sector rankings and a treemap. Each gainers/losers heading has its own Daily, Weekly, Monthly and Yearly selector showing a compact 12-stock list.

FORM: Precisely specified local extension; no concept seed. Company identifiers deduplicate share classes in sector averages and the size map. Metadata and imagery are local; unavailable logos are omitted.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Logo provenance: Financial Modeling Prep public PNG endpoint, https://images.financialmodelingprep.com/symbol/{ticker}.png. Existing design-system files are absent and this extension does not create a replacement world.

## Finish evidence

Disposition: ship; no material findings in the supplied desktop and mobile leaderboard/market-cap captures (`/private/tmp/financial-stock-review/{leaderboard,market-cap,leaderboard-mobile,market-cap-mobile}.jpg`). The stock surface retains the incumbent dotted background, white surfaces, blue selected controls, native table behavior, and existing watch-card styles and responsive breakpoints in `app.py`; the diff does not change their global tokens.

Documentation checked against `app.py`, `financial_dashboard/stocks.py`, and README: full-history adjusted-price trends, equal-weight company sector means, share-class deduplication, company-cap area, capped trend colors, hidden Price date/Cap updated columns, and local logo provenance are documented. The supplied captures verify the visible leaderboard and treemap at both sizes; interaction and data verification belong to the implementation checks.

For this ordinary extension, this task-local note completes documentation. No `DESIGN.md`, `PRODUCT.md`, or design sidecar existed, so there is no existing global-document drift to refresh; their absence does not authorize creating a new visual world or normative tokens. This narrows the earlier FINISH template's global-document requirement to the preserved incumbent scope.

## Crypto extension

Market Watch → Market cap adds a native Stocks/Crypto selector. Crypto reuses the
existing area-map component, dotted dashboard background, white controls and chart
surface. Its saved CoinGecko snapshot contains the top 30 assets by circulating
USD market cap, including stablecoins and tokenized assets when ranked. Tile area
represents circulating cap; same-tab tile links open the corresponding Crypto
chart. The caption identifies the ranking source and snapshot time, and the map
retains horizontal scrolling on narrow screens.

All 30 saved histories were verified in the implementation handoff. Existing
BTC/ETH/BNB archive history is retained; Yahoo daily history is preferred for other
supported assets, with CoinGecko aggregated daily observations as fallback, limited
to the available past year. Chart source labels disclose that fallback and its
coverage. Daily sync refreshes the catalog and histories; viewing the map or charts
uses saved data. README documents sources and the crypto initialization command.

Logo provenance: 26 cached PNGs from the CoinGecko-supplied image URLs on
`coin-images.coingecko.com` or `assets.coingecko.com`; unavailable or unsupported
logos retain text identity. No generated imagery or new visual tokens were added.

Finish-review disposition: ship; the reviewer reported no material findings in
`/private/tmp/crypto-market-cap.png`, `/private/tmp/crypto-market-cap-mobile.png`,
`/private/tmp/crypto-chart.png`, and `/private/tmp/crypto-chart-mobile.png`. The
automated detector was unavailable because its engine was missing; this verdict
records the supplied visual review, not a successful detector run. Documentation
was checked against `app.py`, `financial_dashboard/crypto.py`,
`financial_dashboard/market_cap_map.py`, and README. This narrow extension updates
the surface brief only and does not create global design documents.

## USD/Toman historical extension

The user-supplied USD2Rials CSV extends the existing USD/Toman chart strictly
before Bonbast begins on October 9, 2012. The import adds 3,173 observations
from March 20, 1982 through October 8, 2012: four annual averages, 192 monthly
averages, 2,725 later BourseView observations, and 252 TGJU high/low midpoints.
The first point represents Persian year 1360's average at period end. All 5,121
Bonbast rows remain unchanged. Rials are divided by ten; Persian dates are
canonical, annual/monthly averages use period ends, and no daily interpolation
is created. The retained CSV, SHA-256 and import audit preserve provenance;
BourseView/TGJU are supplied source labels and early primary methodology remains
unverified.

Historical source groups reuse the chart's existing accent with dotted lines.
The source caption distinguishes these observations from Bonbast closes and
discloses mixed-frequency regression. The existing regression is retained; it
is not a frequency-balanced long-run estimate. Period-end labels are not
verified publication dates for backtests. Daily sync continues to update
Bonbast only. This extension preserves the incumbent dashboard and adds no
visual tokens or imagery.

Finish-review disposition: ship; the supplied review found no material fixes in
`/private/tmp/usd-toman-history.png` and
`/private/tmp/usd-toman-history-mobile.png`. The source caption was verified in
the DOM and code but falls below the captured viewport. The automated detector
was unavailable because its engine was absent; no detector pass is claimed.
The implementation handoff reports 278 passing tests. Documentation was checked
against `app.py` source grouping and source caption,
`financial_dashboard/usd_history.py`, and README's USD/Toman historical extension
section. This scoped note preserves the earlier brief's historical wording;
no global design-document refresh or GitHub push is authorized by this task.

USD/Toman frequency-balancing follow-up: the fit, residual percentile and
deviation means now combine represented calendar-duration base weights with
optional recency decay. Persian annual/monthly periods use their exact day
counts; daily observations cover a day or a preceding quote gap of at most
seven days. Long outages receive only a day. Historical predictions use prior
observations only. The weights plot normalizes combined weights to a 100% maximum.
Other instruments have no base-weight column and retain their calculations.
The source note and README describe the new method; existing layout and styling
are unchanged. The previously documented unbalanced fit is superseded by this
follow-up. No new visual-system decisions or assets are introduced.

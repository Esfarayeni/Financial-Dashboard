# Tehran transaction prices

Bundled source-linked secondary transcription of CBI monthly average residential
transaction prices, **Toman per square metre**, Tehran city only. This is not a
national or quality-adjusted house price index, and is not an asking-price series.

Downloaded 2026-11-02 from:
https://github.com/Milad-Shabani/Iran-housing-market-analytics/blob/0bda494d1c8ab26200016cfbcb1cf4d7dd33fa4d/data/raw/official/cbi_tehran_monthly.csv

The original CSV retains per-row source URLs and quality labels. 91 observations
cover Farvardin 1395–Mordad 1403; 10 reporting months are absent. Original prices
are already in Toman and are not divided by ten again. Missing months remain
missing. The parser labels each Persian reporting month at its Gregorian end;
these dates are not publication timestamps, so this is not release-time backtest data.

Validation: checked the last price, 88,500,000 Toman/m², against the linked
Mordad 1403 report (885.0 million IRR), and the meaning/units against an archived
CBI report. Not every historical transcription has been independently audited.

Official report archive: https://www.cbi.ir/category/16994.aspx
Latest value cross-check: https://sarmayesazan.com/blog/معاملات-مسکن-تهران-مرداد-1403/
CBI methodology/report mirror: https://iranopendata.org/res/get/datasets/IODS2/2022/iod515.pdf

No verified free live feed is configured. Initial import and backfills use this
local archive; daily sync imports it only if no housing observations exist.
Update the archive from verified reports before importing new periods. Do not
append listing-price estimates as transaction-price observations.

## Tindex asking-price series

`tindex_asking_snapshot.csv` contains the
18 actual dated table rows readable on 2026-11-02 at
https://tindex.app/indicators/housing/average-housing-price-in-tehranm/ .
They span 1405/04/23–1405/08/05 (2026-07-14–2026-10-27). Values are already
Toman/m². This is a mean of advertised asking prices from listing samples, not
CBI transactions, and it has a separate symbol `TEHRAN_HOUSING_ASKING`.
The page headline says updated 1405/08/10 while the last table observation is
1405/08/05; we use only the dated table rows. No prices are interpolated.

The initial snapshot was transcribed from the public page's readable history
because direct HTTPS requests from the development machine failed. The daily
sync attempts one page request, validates the dated closing-price table and
upserts new dates plus a possible revision on the last stored date. The page
may still transfer its entire compact table. A failed request or parser leaves
the existing database untouched and is reported as a source failure. This live
fetch integration has not yet been verified against a successful HTTP response.
Viewing charts never calls Tindex. The snapshot is retained for provenance;
normal sync does not silently fall back to it when the live source fails.

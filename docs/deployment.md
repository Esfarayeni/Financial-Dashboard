# Deployment design notes

This application is designed as a local-first dashboard: the SQLite database
and API keys remain on the operator's machine. A shareable deployment should
separate the web application from the data refresh job.

## Recommended shape

1. Run the Streamlit app in a small container or managed Python service.
2. Store `market.db` on a persistent volume, or migrate only the storage layer
   to a managed database when multiple app instances are needed.
3. Run `python -m financial_dashboard.sync --daily` once per day in a separate
   scheduled job. It must use the same persistent data store as the app.
4. Put API keys in the host's secret manager; never commit `.env` or the
   database.

## Hosting choices

- A private VM plus a cron/launchd-like scheduler is the simplest option and
  keeps scraper traffic and data local.
- A container host with a scheduled job works when a persistent volume and
  secrets are available.
- Streamlit Community Cloud is suitable only for a demonstrator unless an
  external persistent database and refresh service are configured.

## Data-source risks

Bonbast and DataBourse are public chart pages rather than contractual APIs.
They can alter their markup, rate-limit requests, or restrict access. Keep the
daily sync low frequency, retain the current parser validation, and monitor the
Data status panel. A failed refresh should preserve the last known observation,
not overwrite it.

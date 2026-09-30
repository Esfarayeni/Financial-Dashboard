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
- Streamlit Community Cloud is suitable for a public demonstrator. This
  repository includes a versioned SQLite snapshot so the app has chart history
  after each Cloud restart. A refresh updates only the running instance; use a
  scheduled external sync plus a managed database before treating it as a
  durable production service.

## Streamlit Community Cloud quick launch

1. Push the repository, including `data/market.db`, to GitHub.
2. In [share.streamlit.io](https://share.streamlit.io), choose **Create app**.
3. Select the `main` branch and `app.py` as the entrypoint.
4. Choose an available `streamlit.app` subdomain, such as
   `iran-market-dashboard`.
5. In **Advanced settings**, choose Python 3.12 and paste the values from
   `.streamlit/secrets.toml.example`, with your real Alpha Vantage and FRED
   keys substituted. Do not commit the real secret file.
6. Deploy, then use **Manage app → Cloud logs** for any build or provider
   errors.

## Data-source risks

Bonbast and DataBourse are public chart pages rather than contractual APIs.
They can alter their markup, rate-limit requests, or restrict access. Keep the
daily sync low frequency, retain the current parser validation, and monitor the
Data status panel. A failed refresh should preserve the last known observation,
not overwrite it.

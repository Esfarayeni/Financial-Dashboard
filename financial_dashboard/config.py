from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _setting(name: str) -> str:
    """Read a local environment value or a Community Cloud secret safely."""
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, "")).strip()
    except Exception:
        # The CLI sync process and test suite do not require Streamlit secrets.
        return ""

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(
    _setting("FINANCIAL_DASHBOARD_DB_PATH") or str(DATA_DIR / "market.db")
).expanduser()
LOCK_PATH = DATA_DIR / "sync.lock"

ALPHAVANTAGE_API_KEY = _setting("ALPHAVANTAGE_API_KEY")
COINGECKO_API_KEY = _setting("COINGECKO_API_KEY")
FRED_API_KEY = _setting("FRED_API_KEY")

REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "FinancialDashboard/0.1 (personal, low-frequency market data collector)"

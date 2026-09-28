from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(
    os.getenv("FINANCIAL_DASHBOARD_DB_PATH", str(DATA_DIR / "market.db"))
).expanduser()
LOCK_PATH = DATA_DIR / "sync.lock"

ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()

REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "FinancialDashboard/0.1 (personal, low-frequency market data collector)"

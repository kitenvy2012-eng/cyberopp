import os
from typing import List

class Settings:
    PROJECT_NAME: str = "CyberWatch: Cybersecurity Procurement Tracker"
    VERSION: str = "3.0.0"
    API_V1_STR: str = "/api"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./cyber_opp.db")
    # Comma-separated origins, e.g. "https://cyberwatch.netlify.app". Left as a
    # wildcard for local use; a deployment that calls the API cross-origin
    # should name its own origin so credentials can be allowed.
    CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "*").split(",")
        if origin.strip()
    ] or ["*"]
    SCAN_INTERVAL_MINUTES: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "30"))
    DATA_GO_TH_API_KEY: str = os.getenv("DATA_GO_TH_API_KEY", "").strip()
    # A fresh deployment starts with an empty database, which looks broken even
    # though nothing is wrong. With this on, the app fills it from the official
    # e-GP history once, in the background, the first time it finds no records.
    BACKFILL_ON_EMPTY: bool = os.getenv(
        "BACKFILL_ON_EMPTY", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    # Deliberately small. A first-run sweep competes with the web worker for
    # CPU and memory, and on a modest instance a 12-year sweep is killed
    # part-way — which, with no disk, restarts it from nothing in a loop. Two
    # years fills the dashboard in well under a minute; run
    # `backend/backfill_egp.py` for the full history once it is up.
    BACKFILL_YEARS_BACK: int = int(os.getenv("BACKFILL_YEARS_BACK", "2"))
    # Contract/winner lookups add one request per record. Off for the
    # unattended first run; the scheduled scan enriches later.
    BACKFILL_ENRICH_DETAILS: bool = os.getenv(
        "BACKFILL_ENRICH_DETAILS", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    # Which source types the scheduled scan visits. Empty means all of them.
    # The point of a routine scan is to keep the *biddable* list current, and
    # only sources that publish an invitation document carry a bid window —
    # re-sweeping the e-GP history every cycle adds no deadline and is what
    # makes a scan too long to finish on a small instance.
    SCAN_SOURCE_TYPES: List[str] = [
        item.strip().upper()
        for item in os.getenv("SCAN_SOURCE_TYPES", "").split(",")
        if item.strip()
    ]
    DEFAULT_RETRIES: int = 3
    DEFAULT_TIMEOUT: int = 15

settings = Settings()

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
    BACKFILL_YEARS_BACK: int = int(os.getenv("BACKFILL_YEARS_BACK", "12"))
    DEFAULT_RETRIES: int = 3
    DEFAULT_TIMEOUT: int = 15

settings = Settings()

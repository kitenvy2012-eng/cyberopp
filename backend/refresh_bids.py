"""Refresh current official invitation feeds without running the e-GP history sweep.

Usage: PYTHONPATH=. backend/venv/bin/python backend/refresh_bids.py
No external notifications are sent unless --notify is explicitly selected.
"""

import argparse
import asyncio
import json

from backend.app.core.database import Base, SessionLocal, engine, run_database_migrations
from backend.app.scrapers.manager import run_full_scan, seed_database_if_empty


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-types", nargs="+", default=["CORPORATE", "ONCB", "GOVERNMENT", "NCSA", "STATE_ENTERPRISE", "BOT"], help="Every invitation-publishing source; excludes only the e-GP contract history")
    parser.add_argument("--notify", action="store_true", help="Send matching configured notifications")
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    run_database_migrations()
    with SessionLocal() as db:
        seed_database_if_empty(db)
        result = await run_full_scan(db, source_types=args.source_types, notify=args.notify)
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

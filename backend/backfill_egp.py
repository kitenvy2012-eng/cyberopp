"""Deep historical sweep of the official e-GP / GovSpending record set.

The scheduled scan stays deliberately polite: it looks back a few budget years
so a run finishes quickly and the public service is not hammered every 30
minutes. This script is the other half of that trade-off — run it once (or
occasionally) to pull the full history the service holds.

    PYTHONPATH=. backend/venv/bin/python backend/backfill_egp.py
    PYTHONPATH=. backend/venv/bin/python backend/backfill_egp.py --years-back 12 --no-details

Nothing here fabricates data: it is the same adapter, the same first-party
endpoints, and the same evidence retention as a normal scan, only with a wider
year range.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime

from backend.app.core.database import Base, SessionLocal, engine, run_database_migrations
from backend.app.models.models import ScanLog, ScraperSource, Tender
from backend.app.scrapers.egp_scraper import EGPScraper
from backend.app.scrapers.manager import _normalize_raw_record, _upsert_tender

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill")

EGP_SOURCE_NAME = "e-GP กรมบัญชีกลาง (ระบบจัดซื้อจัดจ้างภาครัฐ)"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years-back",
        type=int,
        default=12,
        help="How many budget years to sweep, newest first (default: 12, the full range the service publishes).",
    )
    parser.add_argument(
        "--max-detail-requests",
        type=int,
        default=1500,
        help="Cap on contract/winner detail lookups (default: 1500).",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip contract/winner enrichment; much faster, fewer requests.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=6,
        help="Concurrent requests against the public API (default: 6).",
    )
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    Base.metadata.create_all(bind=engine)
    run_database_migrations()

    db = SessionLocal()
    try:
        return await run_backfill(
            db,
            years_back=args.years_back,
            max_detail_requests=args.max_detail_requests,
            enrich_details=not args.no_details,
            concurrency=args.concurrency,
        )
    finally:
        db.close()


async def run_backfill(
    db,
    *,
    years_back: int = 12,
    max_detail_requests: int = 1500,
    enrich_details: bool = True,
    concurrency: int = 6,
) -> int:
    """Sweep the official e-GP history into ``db``. Returns a process exit code."""
    started_at = datetime.utcnow()
    scan_log = ScanLog(started_at=started_at, status="RUNNING")
    db.add(scan_log)
    db.commit()

    try:
        source = (
            db.query(ScraperSource)
            .filter(ScraperSource.name == EGP_SOURCE_NAME)
            .first()
        )
        if source is None:
            logger.error(
                "e-GP source row is missing. Start the application once so the "
                "source catalogue is created, then re-run this script."
            )
            return 1

        config = json.dumps(
            {
                "years_back": max(1, years_back),
                "limit": 1000,
                "max_pages": 10,
                "max_concurrency": max(1, concurrency),
                "enrich_details": enrich_details,
                "max_detail_requests": max(0, max_detail_requests),
                "timeout_seconds": 60,
            },
            ensure_ascii=False,
        )
        logger.info(
            "Sweeping %s budget years of official e-GP data (details: %s)...",
            years_back,
            "on" if enrich_details else "off",
        )

        scraper = EGPScraper(source.name, source.url, config)
        result = await scraper.scrape()
        outcome = result.outcome
        logger.info(
            "Source returned %s cybersecurity records in %s requests (status %s).",
            len(result),
            outcome.pages_fetched,
            outcome.status.value,
        )
        for error in outcome.errors[:10]:
            logger.warning("Source error: %s - %s", error.code, error.message)

        observed_at = datetime.utcnow()
        created = 0
        updated = 0
        skipped = 0
        for index, raw in enumerate(result, start=1):
            try:
                normalized = _normalize_raw_record(raw, source, observed_at)
                if normalized is None:
                    skipped += 1
                    continue
                _, was_created = _upsert_tender(db, normalized, observed_at)
                created += int(was_created)
                updated += int(not was_created)
            except Exception:
                # One malformed row must not discard the rest of the sweep.
                db.rollback()
                skipped += 1
                continue
            if index % 200 == 0:
                db.commit()
                # Without this the identity map keeps every tender and its
                # provenance alive for the whole run, which is what exhausts a
                # small instance part-way through a large sweep.
                db.expunge_all()
                logger.info("Persisted %s/%s records...", index, len(result))
        db.commit()
        db.expunge_all()

        source.last_scanned_at = observed_at
        source.last_status = outcome.status.value
        source.tenders_count = (
            db.query(Tender)
            .filter(
                Tender.source_name == source.name,
                Tender.is_quarantined.is_(False),
            )
            .count()
        )

        details = (
            f"Backfill {years_back} budget years: found {len(result)}; "
            f"new {created}; updated {updated}; skipped {skipped}"
        )
        scan_log = db.query(ScanLog).filter(ScanLog.id == scan_log.id).first()
        scan_log.completed_at = datetime.utcnow()
        scan_log.total_scanned = len(result)
        scan_log.new_found = created
        scan_log.status = outcome.status.value
        scan_log.details = details[:12000]
        db.commit()
        logger.info(details)
        return 0
    except Exception:
        db.rollback()
        raise


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

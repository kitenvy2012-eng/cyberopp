import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.scrapers.manager import run_full_scan

logger = logging.getLogger("cyber_scheduler")
scheduler = AsyncIOScheduler()

async def scheduled_scan_job():
    logger.info("Executing periodic cybersecurity tender scan...")
    db = SessionLocal()
    try:
        result = await run_full_scan(db)
        logger.info(f"Scan finished: {result}")
    except Exception as e:
        logger.error(f"Error during periodic scan: {e}")
    finally:
        db.close()

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            scheduled_scan_job,
            "interval",
            minutes=settings.SCAN_INTERVAL_MINUTES,
            id="periodic_cyber_scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        logger.info(f"Background scanner scheduled every {settings.SCAN_INTERVAL_MINUTES} minutes.")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scanner stopped.")

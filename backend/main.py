import asyncio
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import settings
from backend.app.core.database import Base, engine, SessionLocal, run_database_migrations
from backend.app.core.scheduler import start_scheduler, stop_scheduler
from backend.app.models.models import Tender
from backend.app.scrapers.manager import (
    mark_awarded_from_stored_evidence,
    reconcile_interrupted_scans,
    seed_database_if_empty,
)
from backend.app.api.tenders import router as tenders_router
from backend.app.api.stats import router as stats_router
from backend.app.api.sources import router as sources_router
from backend.app.api.buyers import router as buyers_router
from backend.app.api.notifications import router as notifications_router
from backend.app.api.scan import router as scan_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cyber_app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and seed data
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    run_database_migrations()
    
    db = SessionLocal()
    try:
        seed_database_if_empty(db)
        # This process just started, so nothing can still be scanning. Any row
        # left RUNNING belongs to a scan a restart killed, and leaving it there
        # makes the dashboard show a scan that never finishes.
        interrupted = reconcile_interrupted_scans(db)
        if interrupted:
            logger.info("Closed %s scan(s) interrupted by a restart.", interrupted)
        awarded = mark_awarded_from_stored_evidence(db)
        if awarded:
            logger.info("Marked %s record(s) as already awarded from stored evidence.", awarded)
        logger.info("Initial data check and seeding completed.")
        needs_backfill = settings.BACKFILL_ON_EMPTY and db.query(Tender).count() == 0
    finally:
        db.close()

    # A first-boot sweep takes minutes, so it runs alongside the app rather than
    # inside startup — a host's health check must not wait for it.
    async def initial_refresh():
        # Public invitation/source discovery comes first after a cold start.
        # Archival contract backfill remains explicitly configurable.
        from backend.app.scrapers.manager import run_full_scan
        try:
            with SessionLocal() as refresh_db:
                await run_full_scan(refresh_db, source_types=settings.SCAN_SOURCE_TYPES
                    or ["CORPORATE", "ONCB", "GOVERNMENT", "NCSA", "STATE_ENTERPRISE", "BOT"], notify=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Initial public-source refresh failed; scheduled scans remain enabled.")
        if needs_backfill:
            await _backfill_empty_database()

    backfill_task = asyncio.create_task(initial_refresh())

    # Start background scanner
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    if backfill_task and not backfill_task.done():
        backfill_task.cancel()


async def _backfill_empty_database() -> None:
    """Populate a brand-new database from the official e-GP history, once."""
    from backend.backfill_egp import run_backfill

    logger.info("Database is empty; starting first-run e-GP backfill in the background...")
    db = SessionLocal()
    try:
        await run_backfill(
            db,
            years_back=settings.BACKFILL_YEARS_BACK,
            enrich_details=settings.BACKFILL_ENRICH_DETAILS,
            concurrency=3,
        )
        logger.info("First-run backfill finished.")
    except asyncio.CancelledError:
        logger.info("First-run backfill cancelled by shutdown.")
        raise
    except Exception:
        # The scheduled scan still runs, so a failed backfill is not fatal.
        logger.exception("First-run backfill failed; scheduled scans will still run.")
    finally:
        db.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS. A wildcard origin combined with credentials is rejected by every
# browser, so credentials stay off unless an explicit origin list is given.
# Deployments that proxy /api through the frontend host need no CORS at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME, "version": settings.VERSION}

# Include API Routers
app.include_router(tenders_router, prefix=settings.API_V1_STR)
app.include_router(stats_router, prefix=settings.API_V1_STR)
app.include_router(sources_router, prefix=settings.API_V1_STR)
app.include_router(buyers_router, prefix=settings.API_V1_STR)
app.include_router(notifications_router, prefix=settings.API_V1_STR)
app.include_router(scan_router, prefix=settings.API_V1_STR)

# Serve Frontend static if built (Mounted LAST so /api routes take priority)
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

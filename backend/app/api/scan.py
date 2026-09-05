import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, get_db
from backend.app.models.models import ScanLog
from backend.app.models.schemas import ScanLogResponse
from backend.app.scrapers.manager import is_scan_running, run_full_scan

logger = logging.getLogger("cyber_app")

router = APIRouter(prefix="/scan", tags=["Scanner"])


async def _run_scan_detached(source_types) -> None:
    """Own the session: the request that started this has already returned."""
    db = SessionLocal()
    try:
        result = await run_full_scan(db, source_types=source_types)
        logger.info("On-demand scan finished: %s", result.get("status"))
    except asyncio.CancelledError:
        logger.info("On-demand scan cancelled by shutdown.")
        raise
    except Exception:
        logger.exception("On-demand scan failed.")
    finally:
        db.close()


@router.post("", status_code=202)
async def trigger_scan(full: bool = False, db: Session = Depends(get_db)):
    """Start a scan and return immediately.

    A full scan takes minutes — longer than any proxy or browser will hold a
    request open. Returning as soon as it is accepted means a slow scan is no
    longer indistinguishable from a failed one; progress is read from
    ``GET /api/scan/logs``.

    By default this honours ``SCAN_SOURCE_TYPES`` like the scheduled run, so
    the button refreshes the biddable list rather than re-sweeping the whole
    e-GP history. ``?full=true`` asks for every source regardless.
    """
    if is_scan_running():
        return {
            "status": "ALREADY_RUNNING",
            "detail": "มีรอบสแกนกำลังทำงานอยู่ ดูความคืบหน้าที่ /api/scan/logs",
        }

    source_types = None if full else (settings.SCAN_SOURCE_TYPES or None)
    asyncio.create_task(_run_scan_detached(source_types))
    return {
        "status": "STARTED",
        "scope": "ALL_SOURCES" if source_types is None else ",".join(source_types),
        "detail": "เริ่มสแกนแล้ว ผลลัพธ์จะปรากฏใน /api/scan/logs เมื่อรอบนี้จบ",
    }


@router.get("/logs", response_model=List[ScanLogResponse])
def get_scan_logs(limit: int = 10, db: Session = Depends(get_db)):
    return db.query(ScanLog).order_by(desc(ScanLog.id)).limit(limit).all()

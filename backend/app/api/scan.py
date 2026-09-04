from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List

from backend.app.core.database import get_db
from backend.app.models.models import ScanLog
from backend.app.models.schemas import ScanLogResponse
from backend.app.scrapers.manager import run_full_scan

router = APIRouter(prefix="/scan", tags=["Scanner"])

@router.post("")
async def trigger_scan(db: Session = Depends(get_db)):
    """
    Triggers an on-demand scan across all active sources.
    """
    result = await run_full_scan(db)
    return result

@router.get("/logs", response_model=List[ScanLogResponse])
def get_scan_logs(limit: int = 10, db: Session = Depends(get_db)):
    return db.query(ScanLog).order_by(desc(ScanLog.id)).limit(limit).all()

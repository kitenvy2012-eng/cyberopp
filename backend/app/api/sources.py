from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.app.core.database import get_db
from backend.app.models.models import ScraperSource, Tender
from backend.app.models.schemas import ScraperSourceResponse, ScraperSourceCreate
from backend.app.scrapers.base import URLValidationError, canonicalize_url

router = APIRouter(prefix="/sources", tags=["Sources"])

@router.get("", response_model=List[ScraperSourceResponse])
def get_sources(db: Session = Depends(get_db)):
    sources = db.query(ScraperSource).all()
    # Count only records that can appear in the normal trusted view.
    for s in sources:
        s.tenders_count = db.query(Tender).filter(
            Tender.source_name == s.name,
            Tender.is_demo.is_(False),
            Tender.is_quarantined.is_(False),
        ).count()
    return sources

@router.post("", response_model=ScraperSourceResponse)
def create_source(data: ScraperSourceCreate, db: Session = Depends(get_db)):
    try:
        safe_url = canonicalize_url(data.url)
    except URLValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    source = ScraperSource(**data.model_dump(exclude={"url"}), url=safe_url)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source

@router.patch("/{source_id}/toggle", response_model=ScraperSourceResponse)
def toggle_source(source_id: int, db: Session = Depends(get_db)):
    source = db.query(ScraperSource).filter(ScraperSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="ไม่พบแหล่งข้อมูลนี้")
    source.is_active = not source.is_active
    # Turning on a source the application had disabled for itself is a
    # deliberate override. Clearing the marker stops startup from reverting it.
    if source.is_active and str(source.last_status or "").startswith("DISABLED_"):
        source.last_status = "IDLE"
    db.commit()
    db.refresh(source)
    return source

@router.delete("/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.query(ScraperSource).filter(ScraperSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="ไม่พบแหล่งข้อมูลนี้")
    db.delete(source)
    db.commit()
    return {"message": "ลบแหล่งข้อมูลสำเร็จ"}

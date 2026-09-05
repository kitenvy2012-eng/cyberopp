import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.app.core.database import get_db
from backend.app.models.models import ScraperSource, Tender
from backend.app.models.schemas import (
    ScraperSourceResponse,
    ScraperSourceCreate,
    SourceTestRequest,
    SourceTestResponse,
    SourceTestSampleItem,
)
from backend.app.scrapers.base import URLValidationError, canonicalize_url
from backend.app.scrapers.custom_scraper import CustomWebScraper
from backend.app.services.classifier import detect_agency_type, is_cyber_relevant

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.post("/test", response_model=SourceTestResponse)
async def test_source(req: SourceTestRequest):
    try:
        safe_url = canonicalize_url(req.url)
    except URLValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    config = {}
    if req.config_json:
        try:
            config = json.loads(req.config_json)
        except Exception:
            pass
    if req.item_selector:
        config["item_selector"] = req.item_selector
    if req.agency_type:
        config["agency_type"] = req.agency_type

    suggested_agency = req.agency_type or detect_agency_type(req.name or "")
    config["preview_mode"] = True
    config["max_pages"] = 1
    config["discover_sitemaps"] = False

    scraper = CustomWebScraper(req.name or "Preview Source", safe_url, json.dumps(config, ensure_ascii=False))
    try:
        result = await asyncio.wait_for(scraper.scrape(), timeout=12.0)
    except asyncio.TimeoutError:
        return SourceTestResponse(
            status="TIMEOUT",
            errors=["การเชื่อมต่อไปยังเว็บไซต์เป้าหมายหมดเวลา (Timeout 12s) เว็บอาจมีการป้องกันหรือตอบสนองช้า"],
            suggested_agency_type=suggested_agency,
        )
    except Exception as exc:
        return SourceTestResponse(
            status="FAILED",
            errors=[f"เกิดข้อผิดพลาดในการดึงข้อมูล: {type(exc).__name__} - {str(exc)}"],
            suggested_agency_type=suggested_agency,
        )

    outcome = getattr(result, "outcome", None)
    error_messages = [err.message for err in (getattr(outcome, "errors", []) or [])]
    pages_fetched = getattr(outcome, "pages_fetched", 0) or 0
    status_str = getattr(outcome, "status", None)
    status_val = status_str.value if hasattr(status_str, "value") else str(status_str or "SUCCESS")

    sample_items = []
    for item in result[:5]:
        item_title = item.get("title", "")
        item_desc = item.get("description", "")
        sample_items.append(
            SourceTestSampleItem(
                title=item_title,
                agency=item.get("agency") or req.name or "",
                agency_type=item.get("agency_type") or suggested_agency,
                announcement_date=item.get("announcement_date"),
                submission_deadline=item.get("submission_deadline"),
                budget=item.get("budget"),
                tor_url=item.get("tor_url"),
                source_url=item.get("source_url"),
                is_cyber_relevant=is_cyber_relevant(item_title, item_desc),
            )
        )

    return SourceTestResponse(
        status=status_val,
        pages_fetched=pages_fetched,
        total_items_found=len(result),
        sample_items=sample_items,
        errors=error_messages,
        suggested_agency_type=suggested_agency,
    )

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

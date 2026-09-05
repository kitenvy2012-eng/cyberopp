import csv
import hashlib
import io
import json
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, asc
from typing import List, Optional

from backend.app.core.database import get_db
from backend.app.models.models import Tender, TenderProvenance
from backend.app.models.schemas import TenderResponse, TenderCreate, TenderUpdate
from backend.app.services.classifier import classify_tender, extract_requirements, calculate_status, detect_agency_type
from backend.app.scrapers.base import URLValidationError, canonicalize_url
from backend.app.services.bidding import is_actionable

router = APIRouter(prefix="/tenders", tags=["Tenders"])


DEFAULT_MAX_AGE_DAYS = 365


def apply_trust_scope(query, include_quarantined: bool = False):
    """Hide fabricated/rejected records from normal reads and exports."""
    if not include_quarantined:
        query = query.filter(
            Tender.is_demo.is_(False),
            Tender.is_quarantined.is_(False),
        )
    return query


def apply_recency_window(query, max_age_days: Optional[int] = DEFAULT_MAX_AGE_DAYS):
    """Keep only notices announced within the window, newest usable first.

    A record whose source never published an announcement date has no provable
    age, so it cannot satisfy "no older than a year" and is left out rather than
    shown on the assumption that it is recent. Pass 0 to lift the window.
    """
    if not max_age_days or max_age_days <= 0:
        return query
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    return query.filter(
        Tender.announcement_date.isnot(None),
        Tender.announcement_date != "",
        Tender.announcement_date >= cutoff,
    )

@router.get("", response_model=List[TenderResponse])
def get_tenders(
    q: Optional[str] = None,
    category: Optional[str] = None,
    agency_type: Optional[str] = None,
    status: Optional[str] = None,
    min_budget: Optional[float] = None,
    max_budget: Optional[float] = None,
    pipeline_stage: Optional[str] = None,
    is_bookmarked: Optional[bool] = None,
    verification_status: Optional[str] = None,
    data_origin: Optional[str] = None,
    verified_only: bool = False,
    official_only: bool = False,
    open_for_bidding: bool = False,
    opportunity_scope: Optional[str] = None,
    include_quarantined: bool = False,
    max_age_days: int = Query(DEFAULT_MAX_AGE_DAYS, ge=0, le=36500),
    sort_by: Optional[str] = "newest",
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    query = apply_trust_scope(db.query(Tender), include_quarantined)
    query = apply_recency_window(query, max_age_days)

    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(
                Tender.title.ilike(search_pattern),
                Tender.description.ilike(search_pattern),
                Tender.agency.ilike(search_pattern),
                Tender.tender_code.ilike(search_pattern),
                Tender.sub_categories.ilike(search_pattern)
            )
        )

    if category and category != "ALL":
        query = query.filter(Tender.category == category)

    if agency_type and agency_type != "ALL":
        query = query.filter(Tender.agency_type == agency_type)

    if status and status != "ALL":
        query = query.filter(Tender.status == status)

    if pipeline_stage and pipeline_stage != "ALL":
        query = query.filter(Tender.pipeline_stage == pipeline_stage)

    if is_bookmarked is not None:
        query = query.filter(Tender.is_bookmarked == is_bookmarked)

    if verification_status and verification_status != "ALL":
        query = query.filter(Tender.verification_status == verification_status.upper())

    if data_origin and data_origin != "ALL":
        query = query.filter(Tender.data_origin == data_origin.upper())

    if verified_only:
        query = query.filter(Tender.verification_status == "VERIFIED")

    if official_only:
        query = query.filter(Tender.is_official_source.is_(True))

    if min_budget is not None and min_budget > 0:
        query = query.filter(Tender.budget >= min_budget)

    if max_budget is not None and max_budget > 0:
        query = query.filter(Tender.budget <= max_budget)

    if opportunity_scope == "ACTIVE_ONLY":
        query = query.filter(
            Tender.bid_notice_status.notin_(["AWARDED", "CANCELLED"]),
            Tender.status != "CLOSED",
        )
    elif opportunity_scope == "AWARDED":
        query = query.filter(
            or_(
                Tender.bid_notice_status == "AWARDED",
                Tender.status == "CLOSED",
            )
        )

    # Sorting
    if sort_by == "deadline":
        query = query.order_by(asc(Tender.bid_deadline_at if open_for_bidding else Tender.submission_deadline).nullslast(), Tender.id)
    elif sort_by == "budget_desc":
        query = query.order_by(desc(Tender.budget))
    elif sort_by == "budget_asc":
        query = query.order_by(asc(Tender.budget))
    else: # newest
        query = query.order_by(desc(Tender.announcement_date).nullslast(), desc(Tender.id))

    if open_for_bidding:
        # Filter before pagination. A stored project status cannot establish
        # eligibility, and stale evidence must expire even between scans.
        candidates = query.filter(Tender.bid_deadline_at.isnot(None)).all()
        results = [item for item in candidates if is_actionable(item)][offset:offset + limit]
    else:
        results = query.offset(offset).limit(limit).all()
    return results

@router.get("/export/csv")
def export_tenders_csv(
    q: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    agency_type: Optional[str] = None,
    verification_status: Optional[str] = None,
    data_origin: Optional[str] = None,
    verified_only: bool = False,
    official_only: bool = False,
    min_budget: Optional[float] = None,
    max_budget: Optional[float] = None,
    pipeline_stage: Optional[str] = None,
    is_bookmarked: Optional[bool] = None,
    sort_by: Optional[str] = "newest",
    open_for_bidding: bool = False,
    opportunity_scope: Optional[str] = None,
    include_quarantined: bool = False,
    max_age_days: int = Query(DEFAULT_MAX_AGE_DAYS, ge=0, le=36500),
    db: Session = Depends(get_db)
):
    query = apply_trust_scope(db.query(Tender), include_quarantined)
    query = apply_recency_window(query, max_age_days)
    if q:
        search = f"%{q}%"
        query = query.filter(or_(Tender.title.ilike(search), Tender.description.ilike(search), Tender.agency.ilike(search), Tender.tender_code.ilike(search), Tender.sub_categories.ilike(search)))
    if category and category != "ALL":
        query = query.filter(Tender.category == category)
    if status and status != "ALL":
        query = query.filter(Tender.status == status)
    if agency_type and agency_type != "ALL":
        query = query.filter(Tender.agency_type == agency_type)
    if verification_status and verification_status != "ALL":
        query = query.filter(Tender.verification_status == verification_status.upper())
    if data_origin and data_origin != "ALL":
        query = query.filter(Tender.data_origin == data_origin.upper())
    if verified_only:
        query = query.filter(Tender.verification_status == "VERIFIED")
    if official_only:
        query = query.filter(Tender.is_official_source.is_(True))
    if min_budget is not None and min_budget > 0:
        query = query.filter(Tender.budget >= min_budget)
    if max_budget is not None and max_budget > 0:
        query = query.filter(Tender.budget <= max_budget)
    if pipeline_stage and pipeline_stage != "ALL":
        query = query.filter(Tender.pipeline_stage == pipeline_stage)
    if is_bookmarked is not None:
        query = query.filter(Tender.is_bookmarked == is_bookmarked)
    if opportunity_scope == "ACTIVE_ONLY":
        query = query.filter(
            Tender.bid_notice_status.notin_(["AWARDED", "CANCELLED"]),
            Tender.status != "CLOSED",
        )
    elif opportunity_scope == "AWARDED":
        query = query.filter(
            or_(
                Tender.bid_notice_status == "AWARDED",
                Tender.status == "CLOSED",
            )
        )
    if sort_by == "deadline":
        query = query.order_by(asc(Tender.bid_deadline_at if open_for_bidding else Tender.submission_deadline).nullslast(), Tender.id)
    elif sort_by == "budget_desc":
        query = query.order_by(desc(Tender.budget))
    elif sort_by == "budget_asc":
        query = query.order_by(asc(Tender.budget))
    else:
        query = query.order_by(desc(Tender.announcement_date).nullslast(), desc(Tender.id))
    tenders = query.all()
    if open_for_bidding:
        tenders = [item for item in tenders if is_actionable(item)]

    output = io.StringIO()
    output.write('\ufeff') # UTF-8 BOM
    writer = csv.writer(output)
    writer.writerow([
        "เลขที่โครงการ", "ชื่อโครงการ", "หน่วยงาน", "ประเภทหน่วยงาน", "หมวดหมู่งานไซเบอร์",
        "งบประมาณ (บาท)", "ราคากลาง (บาท)", "วิธีการจัดหา", "วันที่ประกาศ",
        "กำหนดยื่นซอง", "สถานะ", "ลิงก์ TOR ต้นฉบับ", "ที่มา", "URL แหล่งข้อมูล",
        "ที่มาของเรคอร์ด", "สถานะการตรวจสอบ", "แหล่งทางการ", "คะแนนความมั่นใจ",
        "พบครั้งแรก", "ตรวจสอบล่าสุด", "Quarantine", "เหตุผล Quarantine",
        "สถานะการยื่นข้อเสนอ", "เริ่มรับข้อเสนอ", "ปิดรับข้อเสนอ (เวลาไทย)",
        "หลักฐานกำหนดรับข้อเสนอ", "ตรวจกำหนดรับล่าสุด"
    ])

    for t in tenders:
        writer.writerow([
            t.tender_code, t.title, t.agency, t.agency_type, t.category,
            f"{t.budget:.2f}" if t.budget is not None else "",
            f"{t.median_price:.2f}" if t.median_price is not None else "",
            t.procurement_method or "",
            t.announcement_date or "", t.submission_deadline or "",
            t.status, t.tor_url or "", t.source_name, t.source_url or "",
            t.data_origin, t.verification_status, t.is_official_source,
            t.confidence_score if t.confidence_score is not None else "",
            t.first_seen_at.isoformat() if t.first_seen_at else "",
            t.last_verified_at.isoformat() if t.last_verified_at else "",
            t.is_quarantined, t.quarantine_reason or "",
            t.bidding_state, t.bid_start_date or "", t.bid_deadline_at or "",
            t.bid_evidence_url or "",
            t.bidding_checked_at.isoformat() if t.bidding_checked_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cyber_tenders.csv"}
    )

@router.get("/{tender_id}/tor-doc")
def get_tender_tor_document(
    tender_id: int,
    include_quarantined: bool = False,
    db: Session = Depends(get_db),
):
    """Redirect to the original TOR; never generate a synthetic document."""
    tender = apply_trust_scope(
        db.query(Tender).filter(Tender.id == tender_id), include_quarantined
    ).first()
    if not tender:
        raise HTTPException(status_code=404, detail="ไม่พบโครงการนี้")
    if tender.is_demo or tender.is_quarantined:
        raise HTTPException(
            status_code=410,
            detail="TOR จำลองถูกปิดใช้งาน; record นี้อยู่ใน quarantine",
        )
    if not tender.tor_url or not tender.tor_url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=404, detail="ไม่พบ URL ของ TOR ต้นฉบับ")
    return RedirectResponse(url=tender.tor_url, status_code=307)

@router.get("/{tender_id}/source-snapshot")
def get_tender_source_snapshot(
    tender_id: int,
    include_quarantined: bool = False,
    db: Session = Depends(get_db),
):
    """Redirect to the real source page; never render a simulated snapshot."""
    tender = apply_trust_scope(
        db.query(Tender).filter(Tender.id == tender_id), include_quarantined
    ).first()
    if not tender:
        raise HTTPException(status_code=404, detail="ไม่พบโครงการนี้")
    if tender.is_demo or tender.is_quarantined:
        raise HTTPException(
            status_code=410,
            detail="Snapshot จำลองถูกปิดใช้งาน; record นี้อยู่ใน quarantine",
        )
    if not tender.source_url or not tender.source_url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=404, detail="ไม่พบ URL ของแหล่งต้นทาง")
    return RedirectResponse(url=tender.source_url, status_code=307)

@router.get("/{tender_id}", response_model=TenderResponse)
def get_tender(
    tender_id: int,
    include_quarantined: bool = False,
    db: Session = Depends(get_db),
):
    tender = apply_trust_scope(
        db.query(Tender).filter(Tender.id == tender_id), include_quarantined
    ).first()
    if not tender:
        raise HTTPException(status_code=404, detail="ไม่พบประกาศโครงการนี้")
    return tender

@router.patch("/{tender_id}", response_model=TenderResponse)
def update_tender(tender_id: int, data: TenderUpdate, db: Session = Depends(get_db)):
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        raise HTTPException(status_code=404, detail="ไม่พบประกาศโครงการนี้")

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        setattr(tender, field, val)

    db.commit()
    db.refresh(tender)
    return tender

@router.post("", response_model=TenderResponse)
def create_manual_tender(data: TenderCreate, db: Session = Depends(get_db)):
    evidence_input = data.source_url or data.tor_url
    if not evidence_input:
        raise HTTPException(
            status_code=422,
            detail="Manual entry ต้องมี URL หลักฐานต้นทางหรือเอกสารต้นฉบับ",
        )
    try:
        source_url = canonicalize_url(evidence_input)
        tor_url = canonicalize_url(data.tor_url) if data.tor_url else None
    except URLValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cat, tags = classify_tender(data.title, data.description or "")
    status = (
        calculate_status(data.submission_deadline)
        if data.submission_deadline
        else (data.status if data.status in {"IN_PROGRESS", "CLOSED"} else "UNKNOWN")
    )
    reqs = extract_requirements(f"{data.title} {data.description or ''}")
    agency_type = data.agency_type or detect_agency_type(data.agency)

    source_payload = data.model_dump()
    source_payload.update({"source_url": source_url, "tor_url": tor_url})
    raw_payload_json = json.dumps(
        source_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    evidence_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()

    tender = Tender(
        **data.model_dump(exclude={
            "category", "sub_categories", "status", "requirements_summary",
            "agency_type", "source_url", "tor_url",
        }),
        source_url=source_url,
        tor_url=tor_url,
        agency_type=agency_type,
        category=data.category or cat,
        sub_categories=data.sub_categories or ", ".join(tags),
        status=status,
        requirements_summary=reqs,
        data_origin="MANUAL",
        verification_status="PENDING",
        verification_method="MANUAL_ENTRY",
        confidence_score=0.0,
        is_official_source=False,
        source_record_id=data.tender_code,
        evidence_hash=evidence_hash,
        raw_payload_json=raw_payload_json,
    )
    tender.provenance.append(TenderProvenance(
        source_name=data.source_name or "Manual entry",
        source_type="MANUAL",
        source_url=source_url,
        document_url=tor_url,
        source_record_id=data.tender_code,
        published_at=data.announcement_date,
        verification_status="PENDING",
        verification_notes="Awaiting independent source verification.",
        content_sha256=evidence_hash,
        raw_payload_json=raw_payload_json,
        is_primary=True,
    ))
    db.add(tender)
    db.commit()
    db.refresh(tender)
    return tender

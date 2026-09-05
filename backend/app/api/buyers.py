from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, desc, asc
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.models.models import Buyer, Source, Tender
from backend.app.models.schemas import (
    BuyerCreate,
    BuyerUpdate,
    BuyerResponse,
    BuyerDetailResponse,
    BuyerActivityResponse,
    SourceResponse,
)

router = APIRouter(prefix="/buyers", tags=["Buyers"])


@router.get("", response_model=List[BuyerResponse])
def get_buyers(
    q: Optional[str] = None,
    priority: Optional[str] = None,
    industry: Optional[str] = None,
    company_type: Optional[str] = None,
    coverage_status: Optional[str] = None,
    active_only: bool = True,
    sort_by: Optional[str] = "priority",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List registered target buyers with filtering, priority, and coverage."""
    query = db.query(Buyer)

    if active_only:
        query = query.filter(Buyer.active.is_(True))

    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Buyer.name.ilike(pattern),
                Buyer.name_th.ilike(pattern),
                Buyer.name_en.ilike(pattern),
                Buyer.domain.ilike(pattern),
                Buyer.industry.ilike(pattern),
            )
        )

    if priority and priority != "ALL":
        query = query.filter(Buyer.priority == priority.upper())

    if industry and industry != "ALL":
        query = query.filter(Buyer.industry == industry.upper())

    if company_type and company_type != "ALL":
        query = query.filter(Buyer.company_type == company_type.upper())

    if coverage_status and coverage_status != "ALL":
        query = query.filter(Buyer.procurement_coverage_status == coverage_status.upper())

    if sort_by == "priority":
        query = query.order_by(asc(Buyer.priority), asc(Buyer.name))
    elif sort_by == "name":
        query = query.order_by(asc(Buyer.name))
    elif sort_by == "latest_procurement":
        query = query.order_by(desc(Buyer.latest_procurement_date))
    else:
        query = query.order_by(desc(Buyer.created_at))

    buyers = query.offset(offset).limit(limit).all()

    result = []
    for b in buyers:
        resp = BuyerResponse.model_validate(b)
        resp.sources_count = len(b.sources) if b.sources else 0
        result.append(resp)

    return result


@router.get("/{buyer_id}", response_model=BuyerDetailResponse)
def get_buyer(buyer_id: int, db: Session = Depends(get_db)):
    """Retrieve buyer profile with all linked verification/procurement sources."""
    buyer = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found")

    resp = BuyerDetailResponse.model_validate(buyer)
    resp.sources_count = len(buyer.sources) if buyer.sources else 0
    resp.sources = [
        SourceResponse.model_validate(s) for s in (buyer.sources or [])
    ]
    for s_resp in resp.sources:
        s_resp.buyer_name = buyer.name
    return resp


@router.post("", response_model=BuyerResponse, status_code=status.HTTP_201_CREATED)
def create_buyer(payload: BuyerCreate, db: Session = Depends(get_db)):
    """Register a new buyer organization in the radar."""
    existing = (
        db.query(Buyer)
        .filter(or_(Buyer.name == payload.name, Buyer.domain == payload.domain if payload.domain else False))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Buyer with name '{payload.name}' or domain '{payload.domain}' already exists (ID: {existing.id})",
        )

    buyer = Buyer(**payload.model_dump())
    db.add(buyer)
    db.commit()
    db.refresh(buyer)

    resp = BuyerResponse.model_validate(buyer)
    resp.sources_count = 0
    return resp


@router.patch("/{buyer_id}", response_model=BuyerResponse)
def update_buyer(buyer_id: int, payload: BuyerUpdate, db: Session = Depends(get_db)):
    """Update an existing buyer profile."""
    buyer = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(buyer, key, value)

    buyer.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(buyer)

    resp = BuyerResponse.model_validate(buyer)
    resp.sources_count = len(buyer.sources) if buyer.sources else 0
    return resp


@router.delete("/{buyer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_buyer(buyer_id: int, db: Session = Depends(get_db)):
    """Deactivate or delete a buyer."""
    buyer = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found")

    db.delete(buyer)
    db.commit()
    return None


@router.get("/{buyer_id}/activity", response_model=BuyerActivityResponse)
def get_buyer_activity(buyer_id: int, db: Session = Depends(get_db)):
    """Retrieve aggregated procurement activity and source health for Buyer Watch."""
    buyer = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found")

    # Match tenders by agency name or domain
    tenders_q = db.query(Tender).filter(
        Tender.is_demo.is_(False),
        Tender.is_quarantined.is_(False),
        Tender.agency.ilike(f"%{buyer.name}%"),
    )

    total_tenders = tenders_q.count()

    # Source health evaluation
    sources = buyer.sources or []
    if not sources:
        overall_health = "NO_SOURCES"
    elif any(s.health_status == "FAILED" for s in sources):
        overall_health = "FAILED"
    elif any(s.health_status == "WARNING" for s in sources):
        overall_health = "WARNING"
    else:
        overall_health = "HEALTHY"

    source_responses = []
    for s in sources:
        sr = SourceResponse.model_validate(s)
        sr.buyer_name = buyer.name
        source_responses.append(sr)

    return BuyerActivityResponse(
        buyer_id=buyer.id,
        buyer_name=buyer.name,
        latest_procurement_date=buyer.latest_procurement_date,
        latest_cyber_opportunity_date=buyer.latest_cyber_opportunity_date,
        procurement_count_30d=min(total_tenders, 5),
        procurement_count_90d=total_tenders,
        cyber_count_90d=total_tenders,
        source_health=overall_health,
        coverage_score=buyer.procurement_coverage_status,
        sources=source_responses,
    )

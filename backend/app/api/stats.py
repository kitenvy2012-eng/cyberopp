from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, noload
from sqlalchemy import func, desc, or_
from collections import Counter
from datetime import datetime, timedelta

from backend.app.core.database import get_db
from backend.app.models.models import Tender, ScanLog
from backend.app.models.schemas import StatsResponse, ScanLogResponse
from backend.app.services.bidding import BANGKOK, ACTIONABLE_STATES, bidding_state, parse_bid_datetime

router = APIRouter(prefix="/stats", tags=["Statistics"])

@router.get("", response_model=StatsResponse)
def get_dashboard_stats(
    include_quarantined: bool = False,
    db: Session = Depends(get_db),
):
    visible_filters = [] if include_quarantined else [
        Tender.is_demo.is_(False),
        Tender.is_quarantined.is_(False),
    ]

    total = db.query(Tender).filter(*visible_filters).count()
    now = datetime.now(BANGKOK)
    rows = db.query(Tender).options(noload(Tender.provenance)).filter(*visible_filters).all()
    bid_counts = Counter(bidding_state(row, now) for row in rows)
    active = bid_counts["OPEN_NOW"]
    closing_soon = sum(
        1 for row in rows
        if bidding_state(row, now) in ACTIONABLE_STATES
        and parse_bid_datetime(row.bid_deadline_at) <= now + timedelta(days=7)
    )
    pipeline = db.query(Tender).filter(
        *visible_filters, Tender.pipeline_stage.notin_(["NONE", None])
    ).count()
    verified = db.query(Tender).filter(
        *visible_filters, Tender.verification_status == "VERIFIED"
    ).count()
    pending = db.query(Tender).filter(
        *visible_filters, Tender.verification_status == "PENDING"
    ).count()
    quarantined = db.query(Tender).filter(or_(
        Tender.is_demo.is_(True),
        Tender.is_quarantined.is_(True),
    )).count()
    
    total_budget_row = db.query(func.sum(Tender.budget)).filter(*visible_filters).scalar()
    # SQLite stores this legacy column as FLOAT; round away binary floating
    # point noise before serializing a monetary aggregate.
    total_budget = round(float(total_budget_row), 2) if total_budget_row else 0.0

    # Category counts
    cat_rows = db.query(Tender.category, func.count(Tender.id)).filter(
        *visible_filters
    ).group_by(Tender.category).all()
    category_counts = {cat: count for cat, count in cat_rows}

    # Agency type counts
    agency_rows = db.query(Tender.agency_type, func.count(Tender.id)).filter(
        *visible_filters
    ).group_by(Tender.agency_type).all()
    agency_type_counts = {atype: count for atype, count in agency_rows if atype}

    # Latest scan log
    latest_scan = db.query(ScanLog).order_by(desc(ScanLog.id)).first()

    return StatsResponse(
        total_tenders=total,
        active_tenders=active,
        closing_soon_tenders=closing_soon,
        actionable_tenders=bid_counts["OPEN_NOW"] + bid_counts["UPCOMING"],
        open_now_tenders=bid_counts["OPEN_NOW"],
        upcoming_tenders=bid_counts["UPCOMING"],
        unconfirmed_deadline_tenders=bid_counts["UNCONFIRMED"],
        stale_bidding_tenders=bid_counts["STALE"],
        verified_tenders=verified,
        pending_tenders=pending,
        quarantined_tenders=quarantined,
        total_budget=total_budget,
        pipeline_count=pipeline,
        category_counts=category_counts,
        agency_type_counts=agency_type_counts,
        latest_scan=latest_scan
    )

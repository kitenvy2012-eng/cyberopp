from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class TenderBase(BaseModel):
    tender_code: str
    title: str
    description: Optional[str] = None
    agency: str
    agency_type: Optional[str] = "ส่วนราชการ"
    category: str
    sub_categories: Optional[str] = None
    budget: Optional[float] = None
    median_price: Optional[float] = None
    procurement_method: Optional[str] = None
    announcement_date: Optional[str] = None
    submission_deadline: Optional[str] = None
    tor_url: Optional[str] = None
    source_name: Optional[str] = "e-GP กรมบัญชีกลาง"
    source_url: Optional[str] = None
    status: Optional[str] = "UNKNOWN"
    requirements_summary: Optional[str] = None
    is_bookmarked: Optional[bool] = False
    pipeline_stage: Optional[str] = "NONE"
    notes: Optional[str] = None

class TenderCreate(TenderBase):
    # A manually created record must not implicitly claim to come from e-GP.
    source_name: Optional[str] = "Manual entry"

class TenderUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    sub_categories: Optional[str] = None
    budget: Optional[float] = None
    median_price: Optional[float] = None
    status: Optional[str] = None
    is_bookmarked: Optional[bool] = None
    pipeline_stage: Optional[str] = None
    notes: Optional[str] = None


class TenderProvenanceResponse(BaseModel):
    id: int
    source_name: str
    source_type: str
    source_url: Optional[str] = None
    document_url: Optional[str] = None
    source_record_id: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    published_at: Optional[str] = None
    http_status: Optional[int] = None
    content_sha256: Optional[str] = None
    verification_status: str = "PENDING"
    verification_notes: Optional[str] = None
    is_primary: bool = False

    class Config:
        from_attributes = True


class TenderResponse(TenderBase):
    id: int
    data_origin: str = "UNKNOWN"
    verification_status: str = "PENDING"
    verification_method: Optional[str] = None
    confidence_score: Optional[float] = None
    is_official_source: bool = False
    source_record_id: Optional[str] = None
    evidence_hash: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    last_verified_at: Optional[datetime] = None
    is_demo: bool = False
    is_quarantined: bool = False
    quarantine_reason: Optional[str] = None
    provenance: List[TenderProvenanceResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ScraperSourceBase(BaseModel):
    name: str
    source_type: str
    url: str
    is_active: bool = True
    config_json: Optional[str] = None

class ScraperSourceCreate(ScraperSourceBase):
    pass

class ScraperSourceResponse(ScraperSourceBase):
    id: int
    last_scanned_at: Optional[datetime] = None
    last_status: Optional[str] = "IDLE"
    tenders_count: int = 0

    class Config:
        from_attributes = True

class NotificationChannelBase(BaseModel):
    name: str
    channel_type: str # LINE_NOTIFY, DISCORD, TELEGRAM, WEBHOOK, IN_APP
    target_url: Optional[str] = None
    token: Optional[str] = None
    chat_id: Optional[str] = None
    is_enabled: bool = True
    min_budget: float = 0.0
    categories_filter: Optional[str] = None
    keywords_filter: Optional[str] = None

class NotificationChannelCreate(NotificationChannelBase):
    pass

class NotificationChannelResponse(NotificationChannelBase):
    id: int

    class Config:
        from_attributes = True

class NotificationLogResponse(BaseModel):
    id: int
    tender_id: Optional[int] = None
    channel_type: str
    title: str
    message: str
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ScanLogResponse(BaseModel):
    id: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_scanned: int = 0
    new_found: int = 0
    status: str
    details: Optional[str] = None

    class Config:
        from_attributes = True

class StatsResponse(BaseModel):
    total_tenders: int
    active_tenders: int
    closing_soon_tenders: int
    verified_tenders: int = 0
    pending_tenders: int = 0
    quarantined_tenders: int = 0
    total_budget: float
    pipeline_count: int
    category_counts: dict
    agency_type_counts: dict
    latest_scan: Optional[ScanLogResponse] = None

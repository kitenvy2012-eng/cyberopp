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
    bidding_state: str = "UNCONFIRMED"
    bid_start_date: Optional[str] = None
    bid_deadline_at: Optional[str] = None
    bid_notice_status: str = "UNKNOWN"
    bid_evidence_url: Optional[str] = None
    bid_evidence_hash: Optional[str] = None
    bid_evidence_excerpt: Optional[str] = None
    bidding_checked_at: Optional[datetime] = None
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


class SourceTestRequest(BaseModel):
    url: str
    name: Optional[str] = None
    config_json: Optional[str] = None
    item_selector: Optional[str] = None
    agency_type: Optional[str] = None


class SourceTestSampleItem(BaseModel):
    title: str
    agency: Optional[str] = None
    agency_type: Optional[str] = None
    announcement_date: Optional[str] = None
    submission_deadline: Optional[str] = None
    budget: Optional[float] = None
    tor_url: Optional[str] = None
    source_url: Optional[str] = None
    is_cyber_relevant: bool = True


class SourceTestResponse(BaseModel):
    status: str
    pages_fetched: int = 0
    total_items_found: int = 0
    sample_items: List[SourceTestSampleItem] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    suggested_agency_type: Optional[str] = None

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
    actionable_tenders: int = 0
    open_now_tenders: int = 0
    upcoming_tenders: int = 0
    unconfirmed_deadline_tenders: int = 0
    stale_bidding_tenders: int = 0
    verified_tenders: int = 0
    pending_tenders: int = 0
    quarantined_tenders: int = 0
    total_budget: float
    pipeline_count: int
    category_counts: dict
    agency_type_counts: dict
    latest_scan: Optional[ScanLogResponse] = None


# ===========================================================================
# Buyer & Source Registry Schemas (Cyber Opportunity Radar)
# ===========================================================================

class SourceBase(BaseModel):
    buyer_id: Optional[int] = None
    name: str
    source_type: str
    url: str
    adapter_type: str = "STATIC_HTML"
    configuration_json: Optional[str] = None
    is_official: bool = True
    requires_browser: bool = False
    requires_authentication: bool = False
    is_active: bool = True
    source_confidence: str = "A_OFFICIAL"
    health_status: str = "HEALTHY"


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    buyer_id: Optional[int] = None
    name: Optional[str] = None
    source_type: Optional[str] = None
    url: Optional[str] = None
    adapter_type: Optional[str] = None
    configuration_json: Optional[str] = None
    is_official: Optional[bool] = None
    requires_browser: Optional[bool] = None
    requires_authentication: Optional[bool] = None
    is_active: Optional[bool] = None
    source_confidence: Optional[str] = None
    health_status: Optional[str] = None


class SourceResponse(SourceBase):
    id: int
    last_checked_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_content_change_at: Optional[datetime] = None
    latest_post_date: Optional[str] = None
    consecutive_failures: int = 0
    tenders_count: int = 0
    buyer_name: Optional[str] = None
    last_status: Optional[str] = "IDLE"
    config_json: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BuyerBase(BaseModel):
    name: str
    name_th: Optional[str] = None
    name_en: Optional[str] = None
    domain: Optional[str] = None
    industry: str
    company_type: str = "PRIVATE"
    country: str = "TH"
    priority: str = "TIER_2"
    active: bool = True
    procurement_coverage_status: str = "UNKNOWN"
    latest_procurement_date: Optional[str] = None
    latest_cyber_opportunity_date: Optional[str] = None


class BuyerCreate(BuyerBase):
    pass


class BuyerUpdate(BaseModel):
    name: Optional[str] = None
    name_th: Optional[str] = None
    name_en: Optional[str] = None
    domain: Optional[str] = None
    industry: Optional[str] = None
    company_type: Optional[str] = None
    country: Optional[str] = None
    priority: Optional[str] = None
    active: Optional[bool] = None
    procurement_coverage_status: Optional[str] = None


class BuyerResponse(BuyerBase):
    id: int
    sources_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BuyerDetailResponse(BuyerResponse):
    sources: List[SourceResponse] = Field(default_factory=list)


class BuyerActivityResponse(BaseModel):
    buyer_id: int
    buyer_name: str
    latest_procurement_date: Optional[str] = None
    latest_cyber_opportunity_date: Optional[str] = None
    procurement_count_30d: int = 0
    procurement_count_90d: int = 0
    cyber_count_90d: int = 0
    source_health: str = "HEALTHY"
    coverage_score: str = "UNKNOWN"
    sources: List[SourceResponse] = Field(default_factory=list)


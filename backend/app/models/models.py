from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class Tender(Base):
    __tablename__ = "tenders"

    id = Column(Integer, primary_key=True, index=True)
    tender_code = Column(String(100), unique=True, index=True, nullable=False)
    title = Column(String(500), index=True, nullable=False)
    description = Column(Text, nullable=True)
    agency = Column(String(255), index=True, nullable=False)
    agency_type = Column(String(100), index=True, default="ส่วนราชการ")
    
    # Categories: VA_PENTEST, AUDIT_COMPLIANCE, SOC_MSSP, SOLUTION_IMPLEMENTATION, INCIDENT_RESPONSE, TRAINING_DRILL, OTHER
    category = Column(String(100), index=True, nullable=False)
    sub_categories = Column(Text, nullable=True) # JSON list or comma separated
    
    # Unknown numeric/source fields stay NULL. Zero is a real value and must
    # not be used as a synthetic "not supplied" placeholder.
    budget = Column(Float, nullable=True, default=None) # งบประมาณโครงการ (บาท)
    median_price = Column(Float, nullable=True, default=None) # ราคากลาง (บาท)
    procurement_method = Column(String(100), nullable=True, default=None) # วิธีการจัดซื้อจัดจ้าง
    
    announcement_date = Column(String(50), nullable=True) # YYYY-MM-DD
    submission_deadline = Column(String(50), nullable=True) # YYYY-MM-DD

    # Explicit bid invitation evidence. Delivery/contract dates never populate
    # these fields. Eligibility is derived on every read in Thailand time.
    bid_start_date = Column(String(50), nullable=True)
    bid_deadline_at = Column(String(50), nullable=True, index=True)
    bid_notice_status = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    bid_evidence_url = Column(String(2000), nullable=True)
    bid_evidence_hash = Column(String(64), nullable=True)
    bid_evidence_excerpt = Column(Text, nullable=True)
    bidding_checked_at = Column(DateTime, nullable=True)
    
    tor_url = Column(String(1000), nullable=True)
    source_name = Column(String(255), default="e-GP กรมบัญชีกลาง")
    source_url = Column(String(1000), nullable=True)

    # Data trust & provenance. A record remains PENDING until its source evidence
    # has been checked; demo records are always quarantined from normal queries.
    # data_origin: SCRAPED, MANUAL, IMPORTED, DEMO, UNKNOWN
    data_origin = Column(String(32), nullable=False, default="SCRAPED", server_default="UNKNOWN", index=True)
    # verification_status: PENDING, VERIFIED, REJECTED, DEMO
    verification_status = Column(String(32), nullable=False, default="PENDING", server_default="PENDING", index=True)
    verification_method = Column(String(100), nullable=True)
    confidence_score = Column(Float, nullable=True)
    is_official_source = Column(Boolean, nullable=False, default=False, server_default="0")
    source_record_id = Column(String(255), nullable=True, index=True)
    evidence_hash = Column(String(128), nullable=True)
    raw_payload_json = Column(Text, nullable=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    is_demo = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    is_quarantined = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    quarantine_reason = Column(Text, nullable=True)
    
    # Status: OPEN, CLOSING_SOON, CLOSED, IN_PROGRESS, UNKNOWN
    status = Column(String(50), default="UNKNOWN", index=True)
    requirements_summary = Column(Text, nullable=True)
    
    # Pipeline & tracking
    is_bookmarked = Column(Boolean, default=False)
    pipeline_stage = Column(String(50), default="NONE") # NONE, SAVED, REVIEWING_TOR, PREPARING_PROPOSAL, BIDDING, WON, LOST
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    provenance = relationship(
        "TenderProvenance",
        back_populates="tender",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def bidding_state(self):
        from backend.app.services.bidding import bidding_state
        return bidding_state(self)


class TenderProvenance(Base):
    """One observation/evidence item for a tender, preserving all source trails."""

    __tablename__ = "tender_provenance"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    source_name = Column(String(255), nullable=False)
    # OFFICIAL, AGGREGATOR, WEB, MANUAL, DEMO, UNKNOWN
    source_type = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN", index=True)
    source_url = Column(String(1000), nullable=True)
    document_url = Column(String(1000), nullable=True)
    source_record_id = Column(String(255), nullable=True)
    retrieved_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(String(50), nullable=True)
    http_status = Column(Integer, nullable=True)
    content_sha256 = Column(String(64), nullable=True)
    raw_payload_json = Column(Text, nullable=True)
    verification_status = Column(String(32), nullable=False, default="PENDING", server_default="PENDING")
    verification_notes = Column(Text, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow)

    tender = relationship("Tender", back_populates="provenance")


class ScraperSource(Base):
    __tablename__ = "scraper_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False) # EGP, NCSA, REGULATOR, STATE_ENTERPRISE, CUSTOM_WEB, RSS
    url = Column(String(1000), nullable=False)
    is_active = Column(Boolean, default=True)
    last_scanned_at = Column(DateTime, nullable=True)
    last_status = Column(String(50), default="IDLE") # IDLE, SUCCESS, FAILED
    tenders_count = Column(Integer, default=0)
    config_json = Column(Text, nullable=True) # JSON config for custom crawler selectors


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    channel_type = Column(String(50), nullable=False) # LINE_NOTIFY, DISCORD, TELEGRAM, WEBHOOK, IN_APP
    target_url = Column(String(1000), nullable=True) # Webhook URL
    token = Column(String(500), nullable=True) # LINE Token or Telegram Bot Token
    chat_id = Column(String(100), nullable=True) # Telegram Chat ID
    is_enabled = Column(Boolean, default=True)
    min_budget = Column(Float, default=0.0) # Filter: Only notify if >= min_budget
    categories_filter = Column(Text, nullable=True) # Comma separated categories or empty for all
    keywords_filter = Column(Text, nullable=True) # Comma separated keywords or empty for all


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, nullable=True)
    channel_type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default="SENT") # SENT, FAILED, READ, UNREAD
    created_at = Column(DateTime, default=datetime.utcnow)


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    total_scanned = Column(Integer, default=0)
    new_found = Column(Integer, default=0)
    status = Column(String(50), default="RUNNING") # RUNNING, COMPLETED, FAILED
    details = Column(Text, nullable=True)


class Buyer(Base):
    __tablename__ = "buyers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    name_th = Column(String(255), nullable=True)
    name_en = Column(String(255), nullable=True)
    domain = Column(String(255), nullable=True, index=True)
    industry = Column(String(100), nullable=False, index=True) # TELECOM, BANKING, ENERGY, RETAIL, HEALTHCARE, TECH, GOV, etc.
    company_type = Column(String(50), nullable=False, default="PRIVATE") # PRIVATE, PUBLIC, STATE_ENTERPRISE, GOVERNMENT, UNIVERSITY, OTHER
    country = Column(String(10), default="TH")
    priority = Column(String(20), default="TIER_2", index=True) # TIER_1, TIER_2, TIER_3
    active = Column(Boolean, default=True)

    procurement_coverage_status = Column(String(50), default="UNKNOWN") # HIGH, MEDIUM, LOW, UNKNOWN
    latest_procurement_date = Column(String(50), nullable=True)
    latest_cyber_opportunity_date = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sources = relationship(
        "Source",
        back_populates="buyer",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    # PROCUREMENT_PAGE, TENDER_PAGE, SUPPLIER_PORTAL, VENDOR_PORTAL, RSS, SITEMAP, SEARCH_DISCOVERY, MANUAL, OTHER
    source_type = Column(String(50), nullable=False)
    url = Column(String(2000), nullable=False)
    # STATIC_HTML, RSS, XML, SITEMAP, BROWSER, PDF, SEARCH, CUSTOM
    adapter_type = Column(String(50), nullable=False, default="STATIC_HTML")
    configuration_json = Column(Text, nullable=True)

    is_official = Column(Boolean, default=True)
    requires_browser = Column(Boolean, default=False)
    requires_authentication = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # A_OFFICIAL, B_PLATFORM, C_DISCOVERED, D_SIGNAL
    source_confidence = Column(String(50), default="A_OFFICIAL")
    # HEALTHY, WARNING, FAILED, DISABLED, STALE_SOURCE
    health_status = Column(String(50), default="HEALTHY", index=True)

    last_checked_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_content_change_at = Column(DateTime, nullable=True)
    latest_post_date = Column(String(50), nullable=True)
    consecutive_failures = Column(Integer, default=0)
    tenders_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    buyer = relationship("Buyer", back_populates="sources")


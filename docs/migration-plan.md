# Cyber Opportunity Radar — Migration Plan

## 1. Migration Strategy and Principles

1. **Non-Destructive Transition**: Existing tables (`tenders`, `tender_provenance`, `scraper_sources`) remain functional throughout early phases. New tables are created alongside them.
2. **Dual-Read / Dual-Write during Migration**: Existing API endpoints (`/api/tenders`, `/api/stats`, `/api/sources`) continue to serve the current frontend until the new `Opportunity` feed and `Buyer Watch` frontend components are activated.
3. **Database Portability**: Schema designs use standard SQL types and declarative constraints that operate seamlessly on both SQLite (local development / free tier) and PostgreSQL (production / enterprise).
4. **Zero Downtime**: Each phase is independently testable, backward-compatible, and immediately deployable to Render and Netlify without downtime.

---

## 2. Target Entity Architecture

```
[ Buyer Registry ] 1 ─── * [ Source Registry ]
        │                           │
        │ 1                         │ 1
        ▼                           ▼
[ Procurement Events ] 1 ─── * [ Raw Documents ]
        │
        ├── 1 ─── * [ Event Versions ]
        ├── 1 ─── 0..1 [ Procurement Awards ]
        │
        ▼
[ Actionable Opportunities ] (Scored & Classified)
```

---

## 3. Detailed Schema Specifications

### 3.1 `buyers` Table
```sql
CREATE TABLE buyers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    domain VARCHAR(255),
    industry VARCHAR(100) NOT NULL,            -- TELECOM, BANKING, ENERGY, RETAIL, HEALTHCARE, TECH, GOV, etc.
    company_type VARCHAR(50) NOT NULL,         -- PRIVATE, PUBLIC, STATE_ENTERPRISE, GOVERNMENT, UNIVERSITY, OTHER
    country VARCHAR(10) DEFAULT 'TH',
    priority VARCHAR(20) DEFAULT 'TIER_2',      -- TIER_1, TIER_2, TIER_3
    active BOOLEAN DEFAULT TRUE,
    
    procurement_coverage_status VARCHAR(50) DEFAULT 'UNKNOWN', -- HIGH, MEDIUM, LOW, UNKNOWN
    latest_procurement_date VARCHAR(50),
    latest_cyber_opportunity_date VARCHAR(50),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_buyers_priority ON buyers(priority);
CREATE INDEX ix_buyers_industry ON buyers(industry);
CREATE INDEX ix_buyers_domain ON buyers(domain);
```

### 3.2 `sources` Table (Replacing `scraper_sources`)
```sql
CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    buyer_id INTEGER REFERENCES buyers(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,          -- PROCUREMENT_PAGE, TENDER_PAGE, SUPPLIER_PORTAL, VENDOR_PORTAL, RSS, SITEMAP, SEARCH_DISCOVERY, MANUAL, OTHER
    url VARCHAR(2000) NOT NULL,
    adapter_type VARCHAR(50) NOT NULL,         -- STATIC_HTML, RSS, XML, SITEMAP, BROWSER, PDF, SEARCH, CUSTOM
    configuration_json TEXT,
    
    is_official BOOLEAN DEFAULT TRUE,
    requires_browser BOOLEAN DEFAULT FALSE,
    requires_authentication BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    
    source_confidence VARCHAR(50) DEFAULT 'A_OFFICIAL', -- A_OFFICIAL, B_PLATFORM, C_DISCOVERED, D_SIGNAL
    health_status VARCHAR(50) DEFAULT 'HEALTHY',       -- HEALTHY, WARNING, FAILED, DISABLED, STALE_SOURCE
    
    last_checked_at TIMESTAMP,
    last_success_at TIMESTAMP,
    last_content_change_at TIMESTAMP,
    latest_post_date VARCHAR(50),
    consecutive_failures INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_sources_buyer_id ON sources(buyer_id);
CREATE INDEX ix_sources_health_status ON sources(health_status);
```

### 3.3 `raw_documents` Table
```sql
CREATE TABLE raw_documents (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    buyer_id INTEGER REFERENCES buyers(id) ON DELETE SET NULL,
    url VARCHAR(2000) NOT NULL,
    canonical_url VARCHAR(2000),
    external_document_id VARCHAR(255),
    content_type VARCHAR(100),
    title VARCHAR(500),
    content_hash VARCHAR(64) NOT NULL,
    raw_text TEXT,
    storage_url VARCHAR(2000),
    http_status INTEGER,
    published_date_candidate VARCHAR(50),
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_status VARCHAR(50) DEFAULT 'DISCOVERED', -- DISCOVERED, FETCHED, EXTRACTED, FAILED, IGNORED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_raw_docs_hash ON raw_documents(content_hash);
CREATE INDEX ix_raw_docs_source ON raw_documents(source_id);
```

### 3.4 `procurement_events` Table
```sql
CREATE TABLE procurement_events (
    id SERIAL PRIMARY KEY,
    buyer_id INTEGER REFERENCES buyers(id) ON DELETE RESTRICT,
    external_reference VARCHAR(255),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    
    announcement_date VARCHAR(50),
    announcement_date_source VARCHAR(50),      -- PAGE_EXPLICIT, DOCUMENT_EXPLICIT, STRUCTURED_METADATA, FIRST_SEEN
    announcement_date_confidence VARCHAR(20),  -- HIGH, MEDIUM, LOW, UNKNOWN
    
    submission_deadline VARCHAR(50),
    budget NUMERIC(15, 2),
    currency VARCHAR(10) DEFAULT 'THB',
    
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(100),
    submission_method VARCHAR(100),
    registration_required BOOLEAN DEFAULT FALSE,
    
    source_confidence VARCHAR(50) DEFAULT 'A_OFFICIAL',
    status VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN', -- DISCOVERED, OPEN, CLOSING_SOON, CLOSED, AWARDED, CANCELLED, UNKNOWN
    status_confidence VARCHAR(20) DEFAULT 'MEDIUM',
    
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_pe_status ON procurement_events(status);
CREATE INDEX ix_pe_buyer ON procurement_events(buyer_id);
CREATE INDEX ix_pe_deadline ON procurement_events(submission_deadline);
```

### 3.5 `procurement_event_versions` Table
```sql
CREATE TABLE procurement_event_versions (
    id SERIAL PRIMARY KEY,
    procurement_event_id INTEGER REFERENCES procurement_events(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    change_reason VARCHAR(255),                 -- DEADLINE_EXTENSION, TOR_UPDATED, BUDGET_REVISED, CLARIFICATION
    previous_deadline VARCHAR(50),
    new_deadline VARCHAR(50),
    diff_summary TEXT,
    raw_document_id INTEGER REFERENCES raw_documents(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_pev_event ON procurement_event_versions(procurement_event_id);
```

### 3.6 `procurement_awards` Table
```sql
CREATE TABLE procurement_awards (
    id SERIAL PRIMARY KEY,
    procurement_event_id INTEGER UNIQUE REFERENCES procurement_events(id) ON DELETE CASCADE,
    winner_name VARCHAR(255) NOT NULL,
    winner_company_id VARCHAR(100),
    award_date VARCHAR(50),
    award_amount NUMERIC(15, 2),
    source_document_id INTEGER REFERENCES raw_documents(id),
    confidence VARCHAR(20) DEFAULT 'HIGH',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_pa_event ON procurement_awards(procurement_event_id);
CREATE INDEX ix_pa_winner ON procurement_awards(winner_name);
```

### 3.7 `opportunities` Table
```sql
CREATE TABLE opportunities (
    id SERIAL PRIMARY KEY,
    procurement_event_id INTEGER UNIQUE REFERENCES procurement_events(id) ON DELETE CASCADE,
    buyer_id INTEGER REFERENCES buyers(id) ON DELETE CASCADE,
    
    cyber_relevance_score NUMERIC(5, 2) NOT NULL,
    opportunity_score NUMERIC(5, 2) NOT NULL,
    actionability_score NUMERIC(5, 2) NOT NULL,
    
    summary TEXT,
    categories TEXT,                            -- JSON array of taxonomy keys
    status VARCHAR(50) NOT NULL,                -- OPEN, CLOSING_SOON, CLOSED, AWARDED, UNKNOWN
    submission_possible BOOLEAN DEFAULT TRUE,
    
    source_confidence VARCHAR(50) NOT NULL,
    classification_confidence NUMERIC(5, 2),
    is_visible BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_opp_score ON opportunities(opportunity_score DESC);
CREATE INDEX ix_opp_status ON opportunities(status);
CREATE INDEX ix_opp_visible ON opportunities(is_visible);
```

### 3.8 `crawl_jobs` Table
```sql
CREATE TABLE crawl_jobs (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    job_type VARCHAR(50) DEFAULT 'SCHEDULED',   -- SCHEDULED, MANUAL, DISCOVERY, RECHECK
    status VARCHAR(50) DEFAULT 'PENDING',       -- PENDING, RUNNING, COMPLETED, FAILED, RETRYING
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    attempts INTEGER DEFAULT 0,
    error_message TEXT,
    documents_discovered INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_crawl_jobs_status ON crawl_jobs(status);
```

---

## 4. Implementation Phases

```
Phase 0: Architecture Audit & Documentation [DONE]
Phase 1: Foundation — Buyer Registry & Source Registry [NEXT]
Phase 2: Source Registry Management & Initial 25 Tier-1 Buyers
Phase 3: Source Adapter Framework (HTML, RSS, Sitemap, PDF)
Phase 4: Observable Crawler Jobs & Worker Pipeline
Phase 5: Normalization, Event Matching, Lifecycle & Award Engine
Phase 6: Cyber Intelligence & Strict Taxonomy Classification
Phase 7: Opportunity Dashboard & Details UI
Phase 8: Buyer Watch & Coverage Tracking
Phase 9: Search Discovery Engine
Phase 10: Private Sector Scale-Up (50-100 Buyers)
```

---

## 5. Phase 1 Implementation Details: Buyer Registry & Source Registry

### Scope
1. Define SQLAlchemy models for `Buyer` and `Source` in `backend/app/models/models.py`.
2. Add Pydantic validation schemas in `backend/app/models/schemas.py`.
3. Add migration in `backend/app/core/database.py` (idempotent table creation).
4. Create `BuyerService` and `SourceService` in `backend/app/services/`.
5. Expose REST endpoints:
   - `GET /api/buyers`
   - `GET /api/buyers/{id}`
   - `POST /api/buyers`
   - `PATCH /api/buyers/{id}`
   - `GET /api/buyers/{id}/activity`
   - `GET /api/sources` (upgraded to support buyer linkage)
   - `POST /api/sources`
   - `PATCH /api/sources/{id}`
6. Seed initial 25 Tier-1 corporate and state-owned buyers with verified domains, company types, and procurement portal metadata.
7. Preserve 100% test compatibility with all existing unit tests.


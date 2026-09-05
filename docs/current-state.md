# Cyber Opportunity Radar — Current State Audit

## 1. Current Architecture

The system operates as a decoupled single-page application (SPA) with a FastAPI backend and a relational database, architected as follows:

```
[ Browser (User) ]
       │
       ▼
[ Netlify Edge CDN ] (React 18 SPA, static hosting + _redirects proxy)
       │  /api/* proxy
       ▼
[ Render Web Service ] (Docker container running FastAPI + Uvicorn)
       │
       ├── SQLite Database (`cyber_opp.db`, accessed via SQLAlchemy 2.0)
       ├── In-process APScheduler (Background crawler runs every 30-180 min)
       └── Scrapers / Ingestion Adapters (HTTPX, BeautifulSoup4, PyPDF)
              │
              ├── Official APIs (e-GP GovSpending, NCSA JSON feed)
              ├── Semi-structured Listings (BOT JSON endpoint)
              ├── Custom Web Scrapers (PEA, EGAT, DGA, ETDA HTML tables)
              └── Corporate Scrapers (CustomWebScraper with preview support)
```

Data flows strictly unidirectionally from external procurement portals into `tenders` and `tender_provenance` tables, with the frontend fetching serialized JSON via `/api/tenders`, `/api/stats`, and `/api/sources`.

---

## 2. Frontend Framework and Deployment Config

- **Framework**: React 18.3.1 SPA with Vite 6.1.0 build tool.
- **Styling**: Tailwind CSS 3.4.17 with `@tailwindcss/forms` and Lucide React icons (`lucide-react` 0.474.0).
- **Font Stack**: Kanit and Inter (Google Fonts) with dark theme by default (`bg-[#0B0F17]`).
- **State & Communication**: Pure React functional components with hooks (`useState`, `useEffect`, `useCallback`). Native `fetch` wrapper in `frontend/src/services/api.js`.
- **Hosting & Deployment**:
  - Hosted on **Netlify** (`https://cyberopps.netlify.app`).
  - Configured via `netlify.toml` (`base = "frontend"`, `publish = "dist"`, `command = "npm run build:netlify"`).
  - API requests to `/api/*` are routed through Netlify's reverse proxy using `_redirects`:
    `/api/*  https://cyberwatch-api-r6p8.onrender.com/api/:splat  200`
    This ensures single-origin security in the browser, eliminating CORS preflight overhead and avoiding backend URL leakage in client bundles.

---

## 3. Backend Framework and Deployment Config

- **Framework**: FastAPI (>=0.110.0) running on Python 3.11 with Uvicorn (>=0.28.0).
- **Asynchronous Execution**: `asyncio` for non-blocking I/O in scrapers (`httpx` >=0.27.0). Single worker (`--workers 1`) to preserve SQLite file locking and in-memory scan synchronization (`asyncio.Lock`).
- **Configuration**: `backend/app/core/config.py` using environment variables with safe defaults.
- **Hosting & Deployment**:
  - Hosted on **Render** (`https://cyberwatch-api-r6p8.onrender.com`) via Docker.
  - Specified via `render.yaml` (free plan, web service, `dockerfilePath: ./Dockerfile`, `healthCheckPath: /api/health`).
  - Environment flags:
    - `DATABASE_URL=sqlite:////data/cyber_opp.db`
    - `BACKFILL_ON_EMPTY=true` (automatically bootstraps 2 budget years of e-GP history on clean boot in ~45 seconds)
    - `SCAN_SOURCE_TYPES=ONCB,GOVERNMENT,CORPORATE,CUSTOM_WEB`

---

## 4. Database Technology and Schema

- **Engine**: SQLite 3 accessed via SQLAlchemy 2.0 (`SessionLocal`, declarative base).
- **Migration Mechanism**: Idempotent column injection and cleanup in `backend/app/core/database.py:run_database_migrations()`.
- **Existing Tables**:
  1. `tenders`: Primary record table combining tender metadata, procurement status, classification, bidding window, and verification trust fields.
  2. `tender_provenance`: Audit trail of observations per tender, tracking source URL, HTTP status, SHA-256 content hashes, and retrieval timestamps.
  3. `scraper_sources`: Registry of crawler targets (name, source_type, URL, active state, config JSON).
  4. `notification_channels`: Alert destinations (Discord, Telegram, Webhook, in-app).
  5. `notification_logs`: Delivery history of outbound alerts.
  6. `scan_logs`: Execution logs of crawl cycles (started_at, completed_at, total_scanned, new_found, status, details).

---

## 5. Existing Procurement / Tender Models

The current domain is conflated into a single monolithic model: `Tender` (`backend/app/models/models.py`).

```python
class Tender(Base):
    id: int
    tender_code: str (unique, generated from hash or source ID)
    title: str
    description: str
    agency: str               # Conflates Buyer name and emitting department
    agency_type: str          # "ส่วนราชการ", "รัฐวิสาหกิจ", "บริษัทเอกชนชั้นนำ", etc.
    category: str             # VA_PENTEST, AUDIT_COMPLIANCE, SOC_MSSP, etc.
    sub_categories: str       # JSON list
    budget: float             # Stored as raw float or NULL
    median_price: float
    procurement_method: str
    announcement_date: str    # YYYY-MM-DD
    submission_deadline: str  # YYYY-MM-DD
    bid_start_date: str
    bid_deadline_at: str
    bid_notice_status: str    # UNKNOWN, INVITATION, DRAFT, AWARDED, CANCELLED
    bid_evidence_url: str
    bid_evidence_hash: str
    bid_evidence_excerpt: str
    bidding_checked_at: datetime
    tor_url: str
    source_name: str
    source_url: str
    data_origin: str          # SCRAPED, MANUAL, IMPORTED, DEMO, UNKNOWN
    verification_status: str  # PENDING, VERIFIED, REJECTED
    confidence_score: float
    is_official_source: bool
    source_record_id: str
    evidence_hash: str
    raw_payload_json: str
    first_seen_at: datetime
    last_seen_at: datetime
    is_demo: bool
    is_quarantined: bool
    quarantine_reason: str
    status: str               # OPEN, CLOSING_SOON, CLOSED, IN_PROGRESS, UNKNOWN
    requirements_summary: str
    is_bookmarked: bool
    pipeline_stage: str
    notes: str
    created_at, updated_at: datetime
```

**Key Observation**: The `Tender` table currently serves four distinct roles simultaneously:
1. Buyer identity (`agency`, `agency_type`).
2. Raw document reference (`source_url`, `tor_url`, `raw_payload_json`).
3. Procurement event & lifecycle (`status`, `bid_notice_status`, `announcement_date`, `submission_deadline`).
4. Commercial sales opportunity (`pipeline_stage`, `is_bookmarked`, `notes`).

---

## 6. Existing Crawler Implementations

Located in `backend/app/scrapers/`:
1. `base.py`: Abstract `BaseScraper` class with rate limiting, retry backoff, robots.txt compliance, URL canonicalization, and SSRF validation.
2. `egp_scraper.py`: Queries Thai Open Government Data API (`api-govspending.data.go.th`) for e-GP records across budget years. Handles project details and contract winner enrichment.
3. `bot_scraper.py`: Scrapes Bank of Thailand procurement API, paging by page index with CDN cache-warming backoff.
4. `ncsa_scraper.py`: Scrapes National Cyber Security Agency (NCSA) JSON announcement feed.
5. `oncb_scraper.py`: Scrapes Office of the Narcotics Control Board procurement tables, detecting invitation periods from HTML.
6. `custom_scraper.py`: Generic CSS/XPath/Regex HTML crawler for PEA, EGAT, DGA, ETDA, and corporate websites. Supports test preview mode (`preview_mode=True`) for live URL validation.
7. `bid_document.py` & `bid_refresh.py`: Deep inspection of linked PDFs and invitation pages using PyPDF and regular expressions to extract submission deadlines and bid start dates.

---

## 7. Existing Scheduled Jobs

- **Scheduler**: APScheduler (`AsyncIOScheduler`) in `backend/app/core/scheduler.py`.
- **Frequency**: Configurable via `SCAN_INTERVAL_MINUTES` (defaults to 30 mins, set to 60-180 mins in production).
- **Concurrency Control**: Protected by `_SCAN_LOCK = asyncio.Lock()` in `backend/app/scrapers/manager.py`. If a scan is already running, concurrent requests return HTTP 202 / `SKIPPED`.
- **Lifecycle Recovery**: At startup, `reconcile_interrupted_scans()` marks any dangling `RUNNING` scan logs as `INTERRUPTED`.

---

## 8. Existing AI Integrations

- **Current State**: **Zero external AI API calls are active in the current production loop.**
- All classification (`backend/app/services/classifier.py`) is handled deterministically via regex token matching (`CATEGORY_KEYWORDS`, `CYBER_RELEVANCE_PHRASES`).
- Requirements extraction (`extract_requirements`) uses deterministic Thai/English regex patterns.
- This design decision was made to ensure low operational cost, deterministic reproducibility, and high throughput on free-tier infrastructure.

---

## 9. Existing API Endpoints

### Tenders API (`/api/tenders`)
- `GET /api/tenders`: List tenders with filtering (`q`, `category`, `agency_type`, `status`, `opportunity_scope`, `max_age_days`, `pipeline_stage`, `verified_only`, `official_only`, `include_awarded`, `include_quarantined`).
- `GET /api/tenders/{id}`: Single tender detail.
- `PATCH /api/tenders/{id}`: Update user metadata (bookmark, pipeline_stage, notes).
- `POST /api/tenders`: Create manual tender.
- `GET /api/tenders/{id}/tor-doc`: Redirect to source TOR document (307 redirect, no synthetic documents).
- `GET /api/tenders/{id}/source-snapshot`: Redirect to raw source URL.
- `GET /api/tenders/export/csv`: Export filtered dataset to CSV.

### Sources API (`/api/sources`)
- `GET /api/sources`: List configured scraper sources.
- `POST /api/sources`: Add custom web source.
- `PATCH /api/sources/{id}`: Update source.
- `POST /api/sources/{id}/toggle`: Toggle active/inactive.
- `DELETE /api/sources/{id}`: Delete source.
- `POST /api/sources/test`: Test a target URL live, returning extracted sample items and detected agency type with SSRF protection.

### Scan API (`/api/scan`)
- `POST /api/scan`: Trigger scan asynchronously (returns 202 Accepted).
- `GET /api/scan/logs`: Get scan execution history.

### Stats API (`/api/stats`)
- `GET /api/stats`: Aggregate counts (total, open, active opportunities, closing soon, total budget, category breakdown, pipeline counts).

### Notifications API (`/api/notifications`)
- `GET /api/notifications/channels`: List notification channels.
- `POST /api/notifications/channels`: Create channel.
- `PATCH /api/notifications/channels/{id}`: Update channel.
- `POST /api/notifications/test/{id}`: Send test notification.
- `GET /api/notifications/logs`: List alert logs.

---

## 10. Existing Search / Filter Logic

- Free-text query (`q`) uses SQL `LIKE %q%` against `title`, `description`, `agency`, `tender_code`, and `sub_categories`.
- Default recency filter: `max_age_days = 365` against `announcement_date` (records with null/empty announcement dates are omitted from default feed).
- Default opportunity scope filter: `opportunity_scope = 'ACTIVE_ONLY'` hides awarded contracts (`bid_notice_status == 'AWARDED'`) and closed projects.
- Sorting: Newest `announcement_date DESC` with `nullslast()`.

---

## 11. Reusable Components

1. `backend/app/scrapers/base.py`:
   - Robust `BaseScraper` class with retry logic, exponential backoff, rate limiting, and timeout handling.
   - SSRF protection validator (`validate_safe_url`), blocking internal/private IP ranges (127.0.0.1, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, link-local, file://).
   - Content hash generator (`stable_tender_id`, SHA-256 payload digest).
2. `backend/app/scrapers/bid_document.py`:
   - PDF text extraction (`pypdf.PdfReader`) and regex date parser for Thai official notices (`BE` Buddhist Era conversion to Gregorian).
3. `backend/app/services/classifier.py`:
   - Comprehensive Thai/English keyword taxonomy for cybersecurity disciplines (`VA_PENTEST`, `SOC_MSSP`, `AUDIT_COMPLIANCE`, `SOLUTION_IMPLEMENTATION`, `INCIDENT_RESPONSE`, `TRAINING_DRILL`).
   - Strict false-positive elimination rules (weeding out medical, COVID-19, road construction, physical security).
   - Corporate markers detection (`detect_agency_type`).
4. `frontend/src/utils/bidding.js`:
   - Bangkok timezone date math and relative date formatting (`ประกาศเมื่อวาน`, `ประกาศเมื่อ 3 วันที่แล้ว`).

---

## 12. Technical Debt Affecting Data Freshness

1. **Monolithic Crawl Jobs**: Crawls are executed sequentially or in large batches inside a single process, meaning a slow source delays subsequent source checks.
2. **Lack of Incremental Change Detection**: Few sources implement `If-Modified-Since` or `ETag`. The scrapers download the whole page/listing on every run.
3. **No Event-Driven Webhooks**: Everything relies on scheduled polling.

---

## 13. Technical Debt Affecting Procurement Status Accuracy

1. **Absence of a Dedicated Award Entity**: An awarded contract is currently indicated only by setting `bid_notice_status = "AWARDED"` on the `Tender` record. There is no `procurement_awards` table capturing who won, winning amount, or award announcement dates.
2. **Lack of Lifecycle State Machine**: Status transitions (`DISCOVERED` -> `OPEN` -> `CLOSING_SOON` -> `CLOSED` -> `AWARDED`) are computed on-the-fly in multiple places (`calculate_status`, `bidding_state`, `exclude_awarded`) rather than governed by a centralized deterministic lifecycle engine.
3. **Missing Event Matching / Deduplication**: When an agency publishes a revised TOR, an announcement extension, or a winner notice, the system risks creating a new tender row or misinterpreting the update because there is no parent `procurement_events` container.

---

## 14. Technical Debt Affecting Private-Sector Coverage

1. **Government-Centric Data Model**: The model assumes every record has a `tender_code`, `budget`, and `announcement_date` characteristic of Thai public procurement (e-GP).
2. **Missing Buyer Entity**: There is no `buyers` table. Organizations are merely string names in `tenders.agency`. This makes it impossible to track buyer coverage, buyer procurement portals, or buyer-level health monitoring.
3. **No Distinction Between Supplier Portals and Tender Boards**: Private companies predominantly operate Approved Vendor Lists (AVL) and supplier registration portals rather than public bidding boards. The current system lacks a model to track supplier registration URLs vs. live tender boards.

---

## 15. Proposed Migration Mapping

To fulfill the architectural specification without breaking existing production behavior:

| New Entity | Purpose | Mapped From Existing System |
|---|---|---|
| `buyers` | First-class corporate/government organization registry | Normalized distinct values of `tenders.agency` + Seeded Target Buyers (AIS, SCG, PTT, KBANK, etc.) |
| `sources` | Verification & adapter registry attached to buyers | `scraper_sources` migrated & linked to `buyer_id` + custom discovery URLs |
| `raw_documents` | Immutable store of downloaded HTML/PDF payloads with content hashes | `tender_provenance` payloads + new adapter outputs |
| `procurement_events` | Canonical procurement record with deterministic lifecycle | Core procurement fields of `tenders` |
| `procurement_event_versions` | History of TOR updates, deadline extensions, and amendments | Provenance changes & deadline extension diffs |
| `opportunities` | Actionable sales opportunities with scoring & cyber taxonomy | Verified, non-awarded cyber tenders with computed `opportunity_score` |
| `procurement_awards` | Historical contract award data (winner name, price, award date) | Stored contract payloads from `tenders.raw_payload_json` |
| `crawl_jobs` | Observable background crawler task execution | Replaces and upgrades `scan_logs` |


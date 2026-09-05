"""Source orchestration, persistence, and trust/provenance handling."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.app.data.seed_data import DEFAULT_CHANNELS, DEFAULT_SOURCES
from backend.app.models.models import (
    NotificationChannel,
    NotificationLog,
    ScanLog,
    ScraperSource,
    Tender,
    TenderProvenance,
)
from backend.app.scrapers.base import (
    ScrapeError,
    ScrapeStatus,
    canonicalize_url,
    is_probable_document_url,
    stable_tender_id,
)
from backend.app.scrapers.bot_scraper import BOTScraper
from backend.app.scrapers.bid_refresh import refresh_bid_evidence
from backend.app.scrapers.custom_scraper import CustomWebScraper
from backend.app.scrapers.egp_scraper import EGPScraper
from backend.app.scrapers.ncsa_scraper import NCSAScraper
from backend.app.scrapers.oncb_scraper import ONCBScraper
from backend.app.services.bidding import BID_FIELDS, is_actionable, parse_bid_datetime
from backend.app.services.classifier import (
    calculate_status,
    classify_tender,
    detect_agency_type,
    extract_requirements,
    is_procurement_relevant,
)
from backend.app.services.notifier import dispatch_tender_notification


_VALID_RECORD_STATUSES = {"OPEN", "CLOSING_SOON", "CLOSED", "IN_PROGRESS", "UNKNOWN"}
_VALID_VERIFICATION_STATUSES = {"PENDING", "VERIFIED", "REJECTED"}
_NO_REQUIREMENT_DETAIL = "ดูรายละเอียดคุณสมบัติในเอกสาร TOR"
_GENERIC_FALSE_POSITIVE_REASON = (
    "Generic crawler matched cyber content but the record title is not a procurement notice"
)
# Statuses the application itself assigns when it disables a source. A user who
# re-enables one of these by hand gets a different status, so their choice is
# never silently reverted.
_AUTO_DISABLED_STATUSES = {
    "DISABLED_UNVERIFIED",
    "DISABLED_BLOCKED_BY_SOURCE",
    "DISABLED_JS_RENDERED",
    "DISABLED_NO_PUBLIC_BOARD",
}
_CURATED_GENERIC_SOURCE_NAMES = {
    item["name"] for item in DEFAULT_SOURCES if item["source_type"] != "EGP"
}
_SCAN_LOCK = asyncio.Lock()


def seed_database_if_empty(db: Session) -> None:
    """Synchronize the live source catalogue and notification channels."""
    for src_data in DEFAULT_SOURCES:
        existing_src = (
            db.query(ScraperSource)
            .filter(ScraperSource.name == src_data["name"])
            .first()
        )
        if not existing_src:
            db.add(ScraperSource(**src_data))
            continue

        # URL/parser fixes are application metadata and always applied.
        existing_src.source_type = src_data["source_type"]
        existing_src.url = src_data["url"]
        existing_src.config_json = src_data.get("config_json")
        # A source the catalogue ships as disabled is one we established cannot
        # be fetched lawfully or parsed at all. Turn it off once, and record the
        # reason, rather than letting it report a permanent failure. Turning it
        # back on by hand clears the marker, and this never overrides that.
        default_status = src_data.get("last_status")
        if src_data.get("is_active") is False and default_status:
            if existing_src.last_scanned_at is None or (
                existing_src.last_status in _AUTO_DISABLED_STATUSES
            ):
                existing_src.is_active = False
                existing_src.last_status = default_status
        elif src_data.get("is_active") and existing_src.last_status in _AUTO_DISABLED_STATUSES:
            # The catalogue now has a working URL/parser for a source that had
            # been switched off automatically before.
            existing_src.is_active = True
            existing_src.last_status = "IDLE"
    db.commit()

    # Quarantine false positives created by older generic sitemap traversal.
    # A curated procurement source is not enough: the individual record title
    # must itself describe a purchase/contract notice.
    pending_generic = (
        db.query(Tender)
        .filter(
            Tender.source_name.in_(_CURATED_GENERIC_SOURCE_NAMES),
            Tender.data_origin == "SCRAPED",
            Tender.verification_status == "PENDING",
            Tender.is_quarantined.is_(False),
        )
        .all()
    )
    for tender in pending_generic:
        if not is_procurement_relevant(tender.title):
            tender.verification_status = "REJECTED"
            tender.is_quarantined = True
            tender.quarantine_reason = _GENERIC_FALSE_POSITIVE_REASON
            for evidence in tender.provenance:
                evidence.verification_status = "REJECTED"
                evidence.verification_notes = (
                    "Quarantined during QA: cybersecurity content was news/policy/navigation, "
                    "not an individual procurement notice."
                )

    # If a parser/QA rule is corrected, recover only records quarantined by
    # that exact automated rule. Demo or manually rejected data is untouched.
    recoverable = (
        db.query(Tender)
        .filter(
            Tender.source_name.in_(_CURATED_GENERIC_SOURCE_NAMES),
            Tender.verification_status == "REJECTED",
            Tender.quarantine_reason == _GENERIC_FALSE_POSITIVE_REASON,
        )
        .all()
    )
    for tender in recoverable:
        if is_procurement_relevant(tender.title):
            tender.verification_status = "PENDING"
            tender.is_quarantined = False
            tender.quarantine_reason = None
            for evidence in tender.provenance:
                evidence.verification_status = "PENDING"
                evidence.verification_notes = (
                    "Source-specific procurement selector matched; field mapping awaits review."
                )

    # Older generic parsing treated the first detail-page link as a TOR. Keep
    # only URLs whose path actually resembles a source document.
    for tender in pending_generic + recoverable:
        if (
            tender.tor_url
            and tender.tor_url == tender.source_url
            and not is_probable_document_url(tender.tor_url)
        ):
            tender.tor_url = None
            for evidence in tender.provenance:
                if evidence.document_url == evidence.source_url:
                    evidence.document_url = None

    # ETDA's fourth table column is a document publication date, not a numeric
    # median price. Clear values produced by the old generic number parser.
    for tender in pending_generic:
        if tender.source_name == "สำนักงานพัฒนาธุรกรรมทางอิเล็กทรอนิกส์ (ETDA)":
            tender.median_price = None

    # ETDA replaces document links as a project advances from median-price
    # publication to invitation/winner. Use source+title as the stable record
    # identity and quarantine earlier duplicate rows without deleting audit data.
    etda_name = "สำนักงานพัฒนาธุรกรรมทางอิเล็กทรอนิกส์ (ETDA)"
    etda_root = next(
        (item["url"] for item in DEFAULT_SOURCES if item["name"] == etda_name),
        "https://www.etda.or.th/th/newsevents/announce/etda-procurement.aspx",
    )
    etda_rows = (
        db.query(Tender)
        .filter(
            Tender.source_name == etda_name,
            Tender.is_demo.is_(False),
            Tender.is_quarantined.is_(False),
        )
        .all()
    )
    etda_groups: Dict[str, List[Tender]] = {}
    for tender in etda_rows:
        title_key = _clean(tender.title).casefold()
        etda_groups.setdefault(title_key, []).append(tender)
    for title_key, group in etda_groups.items():
        expected_code = stable_tender_id(f"source:{etda_root}|title:{title_key}")
        canonical = max(
            group,
            key=lambda row: (row.announcement_date or "", row.id or 0),
        )
        code_owner = (
            db.query(Tender)
            .filter(Tender.tender_code == expected_code)
            .first()
        )
        if code_owner and code_owner in group:
            canonical = code_owner
        elif not code_owner:
            canonical.tender_code = expected_code
            canonical.source_record_id = expected_code
        for duplicate in group:
            if duplicate is canonical:
                continue
            duplicate.verification_status = "REJECTED"
            duplicate.is_quarantined = True
            duplicate.quarantine_reason = (
                f"Superseded duplicate of tender {canonical.id}; source document URL changed"
            )
            for evidence in duplicate.provenance:
                evidence.verification_status = "REJECTED"
                evidence.verification_notes = (
                    f"Superseded by canonical tender {canonical.id}; retained for audit."
                )

    # A tender can accumulate multiple historical observations as a source
    # updates its page. Keep all of them for audit, but designate exactly one
    # current primary observation. Prefer evidence from the tender's owning
    # source so a corroborating source can never take ownership accidentally.
    _repair_primary_provenance(db)
    db.commit()

    if db.query(NotificationChannel).count() == 0:
        for channel_data in DEFAULT_CHANNELS:
            db.add(NotificationChannel(**channel_data))
        db.commit()

    # LINE Notify was retired. Never leave a legacy channel looking usable.
    db.query(NotificationChannel).filter(
        NotificationChannel.channel_type == "LINE_NOTIFY"
    ).update({"is_enabled": False}, synchronize_session=False)
    db.commit()


def is_scan_running() -> bool:
    """Whether a scan holds the lock right now, in this process."""
    return _SCAN_LOCK.locked()


def mark_awarded_from_stored_evidence(db: Session) -> int:
    """Flag records whose retained evidence already names a contract winner.

    The e-GP detail payload is kept per record, so this reads what was already
    fetched rather than asking the source again. A project with a signed
    contract is not an opportunity, and leaving it in the list is what makes the
    dashboard look full of work that was decided months ago.
    """
    candidates = (
        db.query(Tender)
        .filter(
            Tender.raw_payload_json.isnot(None),
            Tender.raw_payload_json.like('%"project_detail"%'),
            Tender.bid_notice_status != "AWARDED",
        )
        .all()
    )
    changed = 0
    for tender in candidates:
        try:
            payload = json.loads(tender.raw_payload_json or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        contracts = (payload.get("project_detail") or {}).get("contract")
        if not isinstance(contracts, list):
            continue
        has_winner = any(
            isinstance(contract, dict)
            and isinstance(contract.get("winner"), dict)
            and _clean(contract["winner"].get("name"))
            for contract in contracts
        )
        if has_winner:
            tender.bid_notice_status = "AWARDED"
            changed += 1
    if changed:
        db.commit()
    return changed


def reconcile_interrupted_scans(db: Session) -> int:
    """Close out scan rows left RUNNING by a process that died mid-scan.

    A restart means nothing is running any more, so a row still marked RUNNING
    can only be a scan that was killed. Left alone it makes the dashboard report
    a scan that never finishes, which reads as a permanent failure.
    """
    stale = db.query(ScanLog).filter(ScanLog.status == "RUNNING").all()
    for log in stale:
        log.status = "INTERRUPTED"
        log.completed_at = datetime.utcnow()
        note = "เซิร์ฟเวอร์รีสตาร์ทระหว่างสแกน รอบนี้จึงไม่จบ"
        log.details = f"{log.details} | {note}" if log.details else note
    if stale:
        db.commit()
    return len(stale)


async def run_full_scan(db: Session, *, source_types=None, notify: bool = True) -> Dict[str, Any]:
    """Serialize scans inside the app so manual and scheduled runs cannot race."""
    if _SCAN_LOCK.locked():
        return {
            "status": "SKIPPED",
            "total_scanned": 0,
            "new_found": 0,
            "details": "มีรอบสแกนอื่นกำลังทำงานอยู่",
            "completed_at": datetime.utcnow().isoformat(),
        }
    async with _SCAN_LOCK:
        return await _run_full_scan_unlocked(db, source_types=source_types, notify=notify)


async def _run_full_scan_unlocked(db: Session, *, source_types=None, notify: bool = True) -> Dict[str, Any]:
    """Scan all enabled sources and persist only evidence-backed observations."""
    scan_log = ScanLog(started_at=datetime.utcnow(), status="RUNNING")
    db.add(scan_log)
    db.commit()

    active_sources = (
        db.query(ScraperSource)
        .filter(ScraperSource.is_active.is_(True))
        .order_by(ScraperSource.id)
        .all()
    )
    # Current invitation feeds must not wait behind the large historical sweep.
    active_sources.sort(key=lambda source: (source.source_type.upper() != "ONCB", source.source_type.upper() == "EGP", source.id))
    if source_types is not None:
        allowed_types = {item.upper() for item in source_types}
        active_sources = [source for source in active_sources if source.source_type.upper() in allowed_types]
    total_found = 0
    new_found = 0
    details: List[str] = []
    source_statuses: List[str] = []
    new_tenders: List[Tender] = []

    for source in active_sources:
        source_now = datetime.utcnow()
        try:
            if source.source_type.upper() == "EGP":
                scraper = EGPScraper(source.name, source.url, source.config_json)
            elif source.source_type.upper() == "NCSA":
                scraper = NCSAScraper(source.name, source.url)
            elif source.source_type.upper() == "BOT":
                scraper = BOTScraper(source.name, source.url, source.config_json)
            elif source.source_type.upper() == "ONCB":
                config = json.loads(source.config_json or "{}")
                config["recheck_urls"] = [
                    tender.source_url for tender in db.query(Tender).filter(
                        Tender.source_name == source.name,
                        Tender.bid_notice_status == "INVITATION",
                        Tender.is_quarantined.is_(False),
                    ).order_by(Tender.bidding_checked_at.asc()).all()
                    if parse_bid_datetime(tender.bid_deadline_at)
                    and parse_bid_datetime(tender.bid_deadline_at) > parse_bid_datetime(source_now, utc_naive=True)
                ][:50]
                scraper = ONCBScraper(source.name, source.url, json.dumps(config))
            else:
                scraper = CustomWebScraper(
                    source.name, source.url, source.config_json
                )

            result = await scraper.scrape()
            if source.source_type.upper() not in {"ONCB", "EGP", "NCSA"}:
                result[:] = await refresh_bid_evidence(result, source_url=source.url)
            outcome = getattr(result, "outcome", None)
            outcome_status = _outcome_status(outcome)
            source_statuses.append(outcome_status)
            source.last_scanned_at = source_now
            source.last_status = outcome_status
            total_found += len(result)
            source_new = 0
            source_invalid = 0

            for raw in result:
                try:
                    normalized = _normalize_raw_record(raw, source, source_now)
                    if normalized is None:
                        source_invalid += 1
                        continue
                    tender, created = _upsert_tender(db, normalized, source_now)
                    if created:
                        source_new += 1
                        new_found += 1
                        new_tenders.append(tender)
                    elif is_actionable(tender):
                        # A previously unconfirmed row can gain its first
                        # verified window on a later scan.
                        new_tenders.append(tender)
                except Exception:
                    # One malformed source row must not make other independently
                    # evidenced rows disappear. The count remains visible in
                    # scan details without leaking raw payloads or credentials.
                    source_invalid += 1

            db.flush()
            source.tenders_count = (
                db.query(Tender)
                .filter(
                    Tender.source_name == source.name,
                    Tender.is_demo.is_(False),
                    Tender.is_quarantined.is_(False),
                )
                .count()
            )
            db.commit()

            errors = list(getattr(outcome, "errors", []) or [])
            error_note = _safe_error_summary(errors)
            details.append(
                f"{source.name}: {outcome_status}; พบ {len(result)}; "
                f"ใหม่ {source_new}; ข้าม {source_invalid}"
                + (f"; {error_note}" if error_note else "")
            )
        except Exception as exc:
            db.rollback()
            source = (
                db.query(ScraperSource)
                .filter(ScraperSource.id == source.id)
                .first()
            )
            if source:
                source.last_scanned_at = source_now
                source.last_status = "FAILED"
                db.commit()
            source_statuses.append("FAILED")
            details.append(
                f"{source.name if source else 'Unknown source'}: FAILED; "
                f"{type(exc).__name__}"
            )

    # Recalculate only tenders whose status is explicitly deadline-driven.
    deadline_tenders = (
        db.query(Tender)
        .filter(
            Tender.is_demo.is_(False),
            Tender.is_quarantined.is_(False),
            Tender.status.in_(["OPEN", "CLOSING_SOON"]),
            Tender.submission_deadline.isnot(None),
        )
        .all()
    )
    for tender in deadline_tenders:
        tender.status = calculate_status(tender.submission_deadline or "")
    db.commit()

    _reconcile_terminal_notices(db)
    db.commit()

    # Old contracts and unconfirmed dates are useful history, not new bid alerts.
    alert_candidates = {
        tender.id: tender for tender in new_tenders
        if is_actionable(tender)
        and not db.query(NotificationLog.id).filter(NotificationLog.tender_id == tender.id).first()
    }
    for tender in alert_candidates.values():
        if notify:
            try:
                await dispatch_tender_notification(tender, db)
            except Exception:
                db.rollback()

    final_status = _overall_scan_status(source_statuses)
    completed_at = datetime.utcnow()
    scan_log = db.query(ScanLog).filter(ScanLog.id == scan_log.id).first()
    scan_log.completed_at = completed_at
    scan_log.total_scanned = total_found
    scan_log.new_found = new_found
    scan_log.status = final_status
    scan_log.details = " | ".join(details)[:12000]
    db.commit()

    return {
        "status": final_status,
        "total_scanned": total_found,
        "new_found": new_found,
        "actionable_new_found": len(alert_candidates),
        "sources": {
            "total": len(active_sources),
            "success": source_statuses.count("SUCCESS"),
            "partial": source_statuses.count("PARTIAL"),
            "failed": source_statuses.count("FAILED"),
            "skipped": source_statuses.count("SKIPPED"),
        },
        "details": scan_log.details,
        "completed_at": completed_at.isoformat(),
    }


def _normalize_raw_record(
    raw: Any, source: ScraperSource, observed_at: datetime
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    title = _clean(raw.get("title"))
    code = _clean(raw.get("tender_code"))
    agency = _clean(raw.get("agency"))
    source_url = _http_url(raw.get("source_url") or source.url)
    if not title or not code or not agency or not source_url:
        return None

    tor_url = _http_url(raw.get("tor_url"))
    verification_status = _clean(raw.get("verification_status")).upper()
    if verification_status not in _VALID_VERIFICATION_STATUSES:
        verification_status = "PENDING"
    data_origin = _clean(raw.get("data_origin")).upper() or "SCRAPED"
    if data_origin == "DEMO":
        return None

    raw_payload_json = raw.get("raw_payload_json")
    if not isinstance(raw_payload_json, str) or not raw_payload_json.strip():
        safe_payload = {
            key: value
            for key, value in raw.items()
            if key not in {"api_key", "token", "password", "secret"}
            and key != "provenance"
        }
        raw_payload_json = json.dumps(
            safe_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    evidence_hash = _clean(raw.get("evidence_hash")) or hashlib.sha256(
        raw_payload_json.encode("utf-8")
    ).hexdigest()
    confidence = _as_float(raw.get("confidence_score"))
    if confidence is not None:
        confidence = min(1.0, max(0.0, confidence))

    deadline = _clean(raw.get("submission_deadline")) or None
    raw_status = _clean(raw.get("status")).upper()
    status = (
        raw_status
        if raw_status in _VALID_RECORD_STATUSES
        else calculate_status(deadline)
        if deadline
        else "UNKNOWN"
    )
    is_official = bool(raw.get("is_official_source"))
    last_verified = raw.get("last_verified_at")
    if not isinstance(last_verified, datetime):
        last_verified = observed_at if verification_status == "VERIFIED" else None

    normalized = dict(raw)
    normalized.update(
        {
            "tender_code": code[:100],
            "title": title[:500],
            "agency": agency[:255],
            "source_name": _clean(raw.get("source_name"))[:255] or source.name,
            "source_url": source_url,
            "tor_url": tor_url,
            "source_record_id": _clean(raw.get("source_record_id"))[:255] or code,
            "description": _clean(raw.get("description"))[:4000] or None,
            "procurement_method": _clean(raw.get("procurement_method"))[:100] or None,
            "announcement_date": _clean(raw.get("announcement_date"))[:50] or None,
            "submission_deadline": deadline[:50] if deadline else None,
            "budget": _as_float(raw.get("budget")),
            "median_price": _as_float(raw.get("median_price")),
            "status": status,
            "data_origin": data_origin,
            "verification_status": verification_status,
            "verification_method": _clean(raw.get("verification_method"))[:100] or None,
            "confidence_score": confidence,
            "is_official_source": is_official,
            "evidence_hash": evidence_hash[:128],
            "raw_payload_json": raw_payload_json,
            "last_verified_at": last_verified,
        }
    )
    # A contract/winner or withdrawal can disqualify an opportunity even when
    # the source does not supply an invitation window. Publication dates alone
    # never establish when submissions begin or end.
    notice_status = _clean(raw.get("bid_notice_status")).upper()
    if notice_status not in {"INVITATION", "DRAFT", "AWARDED", "CANCELLED"}:
        if re.search(r"ยกเลิก(?:ประกาศ|การประกวดราคา|โครงการ|การจัดซื้อ)", title):
            notice_status = "CANCELLED"
        elif "ผู้ชนะ" in title or "ผู้ได้รับการคัดเลือก" in title:
            notice_status = "AWARDED"
        elif "ร่าง" in title or "รับฟังความคิดเห็น" in title:
            notice_status = "DRAFT"
        else:
            notice_status = "UNKNOWN"
        try:
            payload = json.loads(raw_payload_json)
            if isinstance(payload, dict) and (payload.get("project_detail") or {}).get("contract"):
                notice_status = "AWARDED"
        except (ValueError, TypeError, AttributeError):
            pass
    normalized["bid_notice_status"] = notice_status
    if notice_status in {"AWARDED", "CANCELLED", "DRAFT"}:
        normalized["bid_start_date"] = None
        normalized["bid_deadline_at"] = None
    return normalized


def _upsert_tender(
    db: Session, raw: Dict[str, Any], observed_at: datetime
) -> tuple[Tender, bool]:
    source_record_id = raw["source_record_id"]
    source_name = raw["source_name"]
    existing = (
        db.query(Tender)
        .filter(
            or_(
                Tender.tender_code == raw["tender_code"],
                and_(
                    Tender.source_record_id == source_record_id,
                    Tender.source_name == source_name,
                ),
            )
        )
        .first()
    )

    category, tags = classify_tender(raw["title"], raw.get("description") or "")
    requirements = extract_requirements(
        f"{raw['title']} {raw.get('description') or ''}"
    )
    if requirements == _NO_REQUIREMENT_DETAIL:
        requirements = None

    if existing:
        if existing.is_demo or existing.is_quarantined:
            # Never turn a known prototype into a trusted record merely because
            # an identifier happens to collide.
            return existing, False
        same_primary_source = existing.source_name == raw["source_name"]
        for field in (
            "title",
            "description",
            "agency",
            "budget",
            "median_price",
            "procurement_method",
            "announcement_date",
            "submission_deadline",
            "tor_url",
            "source_url",
            "status",
            "raw_payload_json",
            "evidence_hash",
        ):
            value = raw.get(field)
            current_value = getattr(existing, field)
            if value is not None and value != "" and (
                same_primary_source or current_value is None or current_value == ""
            ):
                setattr(existing, field, value)
        if same_primary_source:
            existing.agency_type = raw.get("agency_type") or detect_agency_type(raw["agency"])
            existing.category = category
            existing.sub_categories = ", ".join(tags) or None
            existing.requirements_summary = requirements
        # Replace the whole evidence bundle, including nulls, on a successful
        # reread. Otherwise removed/changed dates could survive indefinitely.
        if raw.get("bidding_checked_at") and (same_primary_source or not existing.bid_evidence_url):
            for field in BID_FIELDS:
                setattr(existing, field, raw.get(field))
        elif raw.get("bid_notice_status") in {"AWARDED", "CANCELLED", "DRAFT"}:
            existing.bid_notice_status = raw["bid_notice_status"]
            existing.bid_start_date = None
            existing.bid_deadline_at = None
        existing.data_origin = raw["data_origin"]
        existing.source_record_id = source_record_id
        existing.last_seen_at = observed_at
        existing.is_official_source = (
            existing.is_official_source or raw["is_official_source"]
        )
        if raw["verification_status"] == "VERIFIED":
            existing.verification_status = "VERIFIED"
            if same_primary_source or not existing.verification_method:
                existing.verification_method = raw.get("verification_method")
            existing.last_verified_at = raw.get("last_verified_at") or observed_at
            if same_primary_source or existing.confidence_score is None:
                existing.confidence_score = raw.get("confidence_score")
        elif existing.verification_status != "VERIFIED":
            existing.verification_status = raw["verification_status"]
            existing.verification_method = raw.get("verification_method")
            existing.confidence_score = raw.get("confidence_score")
        _append_provenance_if_new(
            existing,
            raw,
            observed_at,
            make_primary=same_primary_source,
        )
        return existing, False

    tender = Tender(
        tender_code=raw["tender_code"],
        title=raw["title"],
        description=raw.get("description"),
        agency=raw["agency"],
        agency_type=raw.get("agency_type") or detect_agency_type(raw["agency"]),
        category=category,
        sub_categories=", ".join(tags) or None,
        budget=raw.get("budget"),
        median_price=raw.get("median_price"),
        procurement_method=raw.get("procurement_method"),
        announcement_date=raw.get("announcement_date"),
        submission_deadline=raw.get("submission_deadline"),
        **{field: raw.get(field) for field in BID_FIELDS if field in raw},
        tor_url=raw.get("tor_url"),
        source_name=raw["source_name"],
        source_url=raw["source_url"],
        status=raw["status"],
        requirements_summary=requirements,
        data_origin=raw["data_origin"],
        verification_status=raw["verification_status"],
        verification_method=raw.get("verification_method"),
        confidence_score=raw.get("confidence_score"),
        is_official_source=raw["is_official_source"],
        source_record_id=source_record_id,
        evidence_hash=raw["evidence_hash"],
        raw_payload_json=raw["raw_payload_json"],
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        last_verified_at=raw.get("last_verified_at"),
        is_demo=False,
        is_quarantined=raw["verification_status"] == "REJECTED",
        quarantine_reason=(
            "Source parser rejected this record"
            if raw["verification_status"] == "REJECTED"
            else None
        ),
    )
    _append_provenance_if_new(tender, raw, observed_at, make_primary=True)
    db.add(tender)
    db.flush()
    return tender, True


def _notice_project_key(title: str) -> str:
    """Exact project-title matching only; never fuzzy-match unrelated tenders."""
    title = title.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")).lower()
    title = re.sub(r"^ประกาศ(?:ยกเลิก(?:ประกาศ)?(?:ประกวดราคา)?|ผู้ชนะการเสนอราคา|รายชื่อผู้ชนะการเสนอราคา|ประกวดราคา)", "", title)
    title = re.split(r"ด้วยวิธี", title, maxsplit=1)[0]
    return re.sub(r"[\s\W_]+", "", title)


def _reconcile_terminal_notices(db: Session) -> None:
    """A newer exact-match award/cancellation overrides the earlier invitation."""
    notices = db.query(Tender).filter(
        Tender.bid_notice_status.in_(["INVITATION", "AWARDED", "CANCELLED"]),
        Tender.is_demo.is_(False), Tender.is_quarantined.is_(False),
        Tender.is_official_source.is_(True),
    ).all()
    terminal = {}
    for row in notices:
        if row.bid_notice_status not in {"AWARDED", "CANCELLED"} or not row.announcement_date:
            continue
        key = (row.source_name, row.agency, _notice_project_key(row.title))
        if key not in terminal or row.announcement_date > terminal[key].announcement_date:
            terminal[key] = row
    for invitation in notices:
        if invitation.bid_notice_status != "INVITATION" or not invitation.announcement_date:
            continue
        end = terminal.get((invitation.source_name, invitation.agency, _notice_project_key(invitation.title)))
        if not end or end.announcement_date < invitation.announcement_date:
            continue
        invitation.bid_notice_status = end.bid_notice_status
        invitation.bid_start_date = None
        invitation.bid_deadline_at = None
        invitation.bid_evidence_url = end.bid_evidence_url or end.source_url
        invitation.bid_evidence_hash = end.bid_evidence_hash or end.evidence_hash
        invitation.bid_evidence_excerpt = end.bid_evidence_excerpt or end.title
        invitation.bidding_checked_at = end.bidding_checked_at or end.last_seen_at
        _append_provenance_if_new(invitation, {
            "source_name": end.source_name, "source_url": end.source_url,
            "source_record_id": end.source_record_id, "evidence_hash": end.evidence_hash,
            "raw_payload_json": end.raw_payload_json, "is_official_source": True,
            "verification_status": end.verification_status,
            "announcement_date": end.announcement_date,
            "provenance": {"verification_notes": "Newer exact-title award/cancellation supersedes invitation."},
        }, end.last_seen_at or datetime.utcnow(), make_primary=False)


def _append_provenance_if_new(
    tender: Tender,
    raw: Dict[str, Any],
    observed_at: datetime,
    *,
    make_primary: bool,
) -> None:
    provenance = raw.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    content_hash = _clean(
        provenance.get("content_sha256") or raw.get("evidence_hash")
    )[:64]
    source_url = _http_url(provenance.get("source_url") or raw.get("source_url"))
    existing_evidence = next(
        (
            item
            for item in tender.provenance
            if item.content_sha256 == content_hash and item.source_url == source_url
        ),
        None,
    )
    if existing_evidence is not None:
        if make_primary:
            for item in tender.provenance:
                item.is_primary = item is existing_evidence
        return
    if make_primary:
        for item in tender.provenance:
            item.is_primary = False
    tender.provenance.append(
        TenderProvenance(
            source_name=_clean(provenance.get("source_name"))[:255]
            or raw["source_name"],
            source_type=_clean(provenance.get("source_type"))[:32]
            or ("OFFICIAL" if raw["is_official_source"] else "WEB"),
            source_url=source_url,
            document_url=_http_url(
                provenance.get("document_url") or raw.get("tor_url")
            ),
            source_record_id=_clean(
                provenance.get("source_record_id") or raw.get("source_record_id")
            )[:255]
            or None,
            retrieved_at=observed_at,
            published_at=_clean(
                provenance.get("published_at") or raw.get("announcement_date")
            )[:50]
            or None,
            http_status=_as_int(provenance.get("http_status")),
            content_sha256=content_hash or None,
            raw_payload_json=(
                provenance.get("raw_payload_json")
                if isinstance(provenance.get("raw_payload_json"), str)
                else raw.get("raw_payload_json")
            ),
            verification_status=raw["verification_status"],
            verification_notes=_clean(provenance.get("verification_notes"))[:2000]
            or None,
            # Primary ownership is a relationship-level decision made by the
            # manager, not a claim accepted from an individual scraper row.
            is_primary=make_primary,
        )
    )


def _repair_primary_provenance(db: Session) -> None:
    """Make primary provenance deterministic for existing databases."""
    for tender in db.query(Tender).all():
        evidence = list(tender.provenance)
        if not evidence:
            continue
        owning_source = [
            item for item in evidence if item.source_name == tender.source_name
        ]
        candidates = owning_source or evidence
        chosen = max(
            candidates,
            key=lambda item: (
                item.retrieved_at or datetime.min,
                item.id or 0,
            ),
        )
        for item in evidence:
            should_be_primary = item is chosen
            if item.is_primary != should_be_primary:
                item.is_primary = should_be_primary


def _outcome_status(outcome: Any) -> str:
    value = getattr(outcome, "status", ScrapeStatus.SUCCESS)
    if isinstance(value, ScrapeStatus):
        return value.value
    value = str(value).upper()
    return value if value in {item.value for item in ScrapeStatus} else "FAILED"


def _overall_scan_status(statuses: Iterable[str]) -> str:
    statuses = list(statuses)
    if not statuses or all(status in {"FAILED", "SKIPPED"} for status in statuses):
        return "FAILED"
    if any(status in {"PARTIAL", "FAILED", "SKIPPED"} for status in statuses):
        return "PARTIAL"
    return "COMPLETED"


def _safe_error_summary(errors: List[ScrapeError]) -> str:
    if not errors:
        return ""
    codes = list(dict.fromkeys(_clean(error.code) for error in errors if error.code))
    return f"ข้อผิดพลาด {len(errors)} ({', '.join(codes[:5])})"


def _http_url(value: Any) -> Optional[str]:
    text = _clean(value)
    if not text:
        return None
    try:
        return canonicalize_url(text)
    except Exception:
        return None


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

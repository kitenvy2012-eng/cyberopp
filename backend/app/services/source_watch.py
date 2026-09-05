"""Evidence-backed source activity; never substitute discovery for publication."""
import hashlib
import json
import re
from datetime import datetime, timedelta

from backend.app.models.models import Source, PublicNotice, Tender
from backend.app.services.bidding import BANGKOK, is_actionable
from backend.app.services.classifier import is_cyber_relevant


def source_access_note(source):
    try:
        config = json.loads(source.configuration_json or "{}")
        return config.get("access_note", "") if isinstance(config, dict) else ""
    except (ValueError, TypeError):
        return ""


def notice_kind(title):
    if re.search(r"ยกเลิก(?:ประกาศ|การประกวดราคา|โครงการ)|ประกาศยกเลิก", title):
        return "CANCELLED"
    if "ผู้ชนะ" in title or "ผู้ได้รับการคัดเลือก" in title:
        return "AWARDED"
    if "ร่าง" in title or "รับฟัง" in title:
        return "DRAFT"
    if re.search(r"ประกวดราคา|เชิญชวน|ยื่นแบบ|request for proposal|request for quotation", title, re.I):
        return "INVITATION"
    return "UNKNOWN"


def record_source_scan(db, legacy, outcome, records, checked_at):
    source = db.query(Source).filter(Source.name == legacy.name).first()
    if not source:
        return
    source.last_checked_at = checked_at
    if legacy.is_active is not None:
        source.is_active = legacy.is_active
    status = legacy.last_status
    source.tenders_count = legacy.tenders_count or 0
    if status not in {"SUCCESS", "PARTIAL"}:
        source.health_status = "FAILED"
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        return
    access = getattr(outcome, "access_status", "PUBLIC_LISTING")
    source.health_status = "WARNING" if status == "PARTIAL" else access if access != "PUBLIC_LISTING" else "HEALTHY"
    source.last_success_at = checked_at
    source.consecutive_failures = 0
    # Some adapters expose all posts; older adapters only expose cyber rows.
    observations = getattr(outcome, "public_notices", []) or [
        {"title": r["title"], "url": r["source_url"], "published_date": r.get("announcement_date"),
         "publication_evidence": r.get("announcement_date")} for r in records
    ]
    changed = False
    seen = set()
    for raw in observations[:500]:
        title, url = raw.get("title"), raw.get("url")
        if not title or not url:
            continue
        identity = hashlib.sha256(f"{source.id}|{url}|{title}".encode()).hexdigest()
        if identity in seen:
            continue
        seen.add(identity)
        payload_hash = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        notice = db.query(PublicNotice).filter(PublicNotice.identity == identity).first()
        if not notice:
            notice = PublicNotice(source_id=source.id, identity=identity, first_seen_at=checked_at)
            db.add(notice)
            changed = True
        changed = changed or notice.content_hash != payload_hash
        notice.title, notice.url = title, url
        # A successful reread may remove a previously stated date.
        notice.published_date = raw.get("published_date")
        notice.publication_evidence = raw.get("publication_evidence")
        notice.notice_status = notice_kind(title)
        notice.is_cyber = is_cyber_relevant(title)
        notice.content_hash, notice.last_seen_at = payload_hash, checked_at
    db.flush()
    dates = [n.published_date for n in db.query(PublicNotice).filter(PublicNotice.source_id == source.id).all() if n.published_date]
    source.latest_post_date = max(dates) if dates else None
    if changed:
        source.last_content_change_at = checked_at
    if source.buyer:
        dates = [s.latest_post_date for s in source.buyer.sources if s.latest_post_date]
        source.buyer.latest_procurement_date = max(dates) if dates else None


def buyer_watch(db, buyer):
    now = datetime.now(BANGKOK)
    sources = list(buyer.sources or [])
    ids = [s.id for s in sources]
    notices = db.query(PublicNotice).filter(PublicNotice.source_id.in_(ids)).order_by(PublicNotice.published_date.desc().nullslast(), PublicNotice.first_seen_at.desc()).all() if ids else []
    tenders = db.query(Tender).filter(Tender.source_name.in_([s.name for s in sources]), Tender.is_demo.is_(False), Tender.is_quarantined.is_(False)).all() if sources else []
    def recent(n, days):
        return bool(n.published_date and (now.date() - timedelta(days=days)).isoformat() <= n.published_date <= now.date().isoformat())
    dated = [n for n in notices if n.published_date]
    cyber = [n for n in dated if n.is_cyber and n.notice_status not in {"AWARDED", "CANCELLED"}]
    actionable = [t for t in tenders if is_actionable(t)]
    def health(s):
        if not s.is_active:
            return "DISABLED"
        if not s.last_checked_at:
            return "NOT_CHECKED"
        if datetime.utcnow() - s.last_checked_at > timedelta(hours=24):
            return "STALE_SOURCE"
        return s.health_status
    return {
        "id": buyer.id, "name": buyer.name, "name_en": buyer.name_en, "domain": buyer.domain,
        "company_type": buyer.company_type, "industry": buyer.industry,
        "latest_procurement_date": dated[0].published_date if dated else None,
        "latest_cyber_opportunity_date": cyber[0].published_date if cyber else None,
        "procurement_count_30d": sum(recent(n, 30) for n in notices),
        "procurement_count_90d": sum(recent(n, 90) for n in notices),
        "cyber_count_90d": sum(recent(n, 90) for n in cyber),
        "actionable_count": len(actionable), "undated_count": sum(not n.published_date for n in notices),
        "sources": [{"id": s.id, "name": s.name, "url": s.url, "source_type": s.source_type,
                     "health": health(s), "checked_at": s.last_checked_at, "latest_post_date": s.latest_post_date,
                     "requires_authentication": s.requires_authentication,
                     "notes": source_access_note(s)}
                    for s in sources],
        "notices": [{"title": n.title, "url": n.url, "published_date": n.published_date,
                     "first_seen_at": n.first_seen_at, "last_seen_at": n.last_seen_at,
                     "publication_evidence": n.publication_evidence, "notice_status": n.notice_status,
                     "is_cyber": n.is_cyber} for n in notices[:10]],
    }

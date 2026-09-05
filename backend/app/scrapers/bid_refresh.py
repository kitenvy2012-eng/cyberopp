"""Bounded re-checking of bid evidence for recent official records.

Discovery adapters deliberately do not infer a submission deadline from a
project status or a publication date.  This helper is the small network-facing
bridge between those adapters and :mod:`backend.app.scrapers.bid_document`: it
re-checks at most twelve recent invitation records, follows at most two PDF
attachments from one official detail page, and copies bid fields back only
when an actually fetched document can be classified by the evidence parser.

The helper is intentionally not a general crawler.  Hosts are exact, curated
values; links may not leave the source host; old records and non-invitation
notices are never fetched.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from backend.app.scrapers.base import BaseScraper, URLValidationError, canonicalize_url
from backend.app.scrapers.bid_document import (
    BidDocumentEnrichment,
    BidNoticeStatus,
    extract_bid_document_evidence,
)
from backend.app.scrapers.web_fetcher import FetchFailure, FetchedDocument, SafeWebClient
from backend.app.services.bidding import BID_FIELDS


BANGKOK = ZoneInfo("Asia/Bangkok")
ALLOWED_SOURCE_HOSTS = frozenset(
    {
        "www.dga.or.th",
        "www.etda.or.th",
        "www.bot.or.th",
        "bidding.pea.co.th",
    }
)
MAX_REFRESH_RECORDS = 12
MAX_PDF_ATTACHMENTS = 2
RECENT_DAYS = 90

_INVITATION = re.compile(
    r"(?:ประกาศ\s*(?:เชิญชวน|ประกวดราคา)|ประกวดราคา|เอกสาร\s*ประกวดราคา|"
    r"e[- ]?bidding|invitation\s+to\s+bid)",
    re.IGNORECASE,
)
_NOT_AN_INVITATION = re.compile(
    r"(?:ประชา(?:วิจารณ์|พิจารณ์)|รับฟังคำ(?:วิจารณ์|คิดเห็น)|"
    r"(?:^|\s)ร่าง\s*(?:ประกาศ|เอกสาร|ขอบเขต)|ประกาศ(?:ผล)?\s*ผู้ชนะ|"
    r"ผลการคัดเลือกผู้ชนะ|ประกาศ\s*ยกเลิก|ยกเลิก\s*(?:ประกาศ|การประกวดราคา)|"
    r"notice\s+of\s+award|\bawarded\b|\bcancell?ed\b)",
    re.IGNORECASE,
)
_PDF_PATH = re.compile(r"\.pdf(?:$|[./])", re.IGNORECASE)


async def refresh_bid_evidence(
    records: Iterable[Mapping[str, Any]],
    *,
    source_url: Optional[str] = None,
    fetcher: Optional[SafeWebClient] = None,
    now: Optional[datetime] = None,
    max_records: int = MAX_REFRESH_RECORDS,
) -> list[dict[str, Any]]:
    """Return copies of ``records`` with conservatively refreshed bid fields.

    ``records`` is expected to be one adapter's raw result set.  ``source_url``
    may be supplied by the manager to pin that set to its configured source;
    otherwise the first eligible record establishes the exact source host.
    An injected ``fetcher`` and ``now`` keep tests deterministic.  An external
    fetcher remains owned by its caller.

    A network failure, unsupported document, title/document mismatch, or other
    unclassified evidence leaves every existing bid field untouched -- most
    importantly, it does not make an old ``bidding_checked_at`` look fresh.
    """

    output = [dict(record) for record in records]
    if not output:
        return output

    limit = max(0, min(MAX_REFRESH_RECORDS, int(max_records)))
    if limit == 0:
        return output

    current = _as_bangkok(now)
    pinned_host = _allowed_host(source_url)
    candidates = _recent_invitation_indices(output, current.date(), pinned_host)
    candidates = candidates[:limit]
    if not candidates:
        return output

    if fetcher is not None:
        await _refresh_selected(output, candidates, fetcher, pinned_host, current)
        return output

    async with SafeWebClient(
        timeout_seconds=25.0,
        max_response_bytes=25 * 1024 * 1024,
        max_retries=1,
        request_delay_seconds=0.25,
    ) as managed_fetcher:
        await _refresh_selected(output, candidates, managed_fetcher, pinned_host, current)
    return output


async def _refresh_selected(
    output: list[dict[str, Any]],
    indices: Sequence[int],
    fetcher: SafeWebClient,
    pinned_host: Optional[str],
    current: datetime,
) -> None:
    source_host = pinned_host
    for index in indices:
        record = output[index]
        record_host = _record_source_host(record)
        if source_host is None:
            source_host = record_host
        if record_host is None or record_host != source_host:
            continue

        primary_url = _primary_evidence_url(record, source_host)
        if primary_url is None:
            continue
        enrichment = await _fetch_and_parse_record(
            fetcher,
            primary_url=primary_url,
            source_host=source_host,
            title=str(record.get("title") or ""),
            checked_at=current,
        )
        if enrichment is None:
            continue

        parsed = enrichment.to_dict()
        # reason_code is diagnostic and is intentionally not a persisted model
        # field.  Null dates are copied: a fresh document that cannot prove a
        # window must not preserve a formerly inferred/actionable window.
        for field in BID_FIELDS:
            record[field] = parsed[field]


async def _fetch_and_parse_record(
    fetcher: SafeWebClient,
    *,
    primary_url: str,
    source_host: str,
    title: str,
    checked_at: datetime,
) -> Optional[BidDocumentEnrichment]:
    try:
        primary = await fetcher.fetch(primary_url)
    except FetchFailure:
        return None
    if _host(primary.url) != source_host:
        return None

    primary_evidence = _parse_fetched(primary, title, source_host, checked_at)
    evidence = [primary_evidence] if primary_evidence is not None else []
    # A detail page that is itself a draft or terminal notice is authoritative
    # for this record.  Its linked files must not promote it back into an
    # actionable invitation.
    if primary_evidence is not None and primary_evidence.bid_notice_status in {
        BidNoticeStatus.DRAFT,
        BidNoticeStatus.AWARDED,
        BidNoticeStatus.CANCELLED,
    }:
        return primary_evidence

    # A direct PDF/document is the end of this bounded branch.  Only an HTML
    # detail page may contribute attachment links, and only its first two
    # same-host PDF links are considered.
    for attachment_url in _same_site_pdf_links(primary, source_host)[:MAX_PDF_ATTACHMENTS]:
        try:
            attachment = await fetcher.fetch(attachment_url)
        except FetchFailure:
            continue
        if _host(attachment.url) != source_host:
            continue
        candidate = _parse_fetched(attachment, title, source_host, checked_at)
        if candidate is not None:
            evidence.append(candidate)
        # Draft/terminal evidence dominates any invitation window already seen.
        # Once found, later attachments cannot make the record actionable.
        if candidate is not None and candidate.bid_notice_status in {
            BidNoticeStatus.DRAFT,
            BidNoticeStatus.AWARDED,
            BidNoticeStatus.CANCELLED,
        }:
            break
    return _resolve_evidence(evidence)


def _parse_fetched(
    document: FetchedDocument,
    title: str,
    source_host: str,
    checked_at: datetime,
) -> Optional[BidDocumentEnrichment]:
    evidence = extract_bid_document_evidence(
        content=document.content,
        content_type=document.content_type,
        evidence_url=document.url,
        title=title,
        checked_at=checked_at,
        allowed_hosts={source_host},
    )
    # UNKNOWN covers unsupported/unreadable content, a title mismatch, and a
    # page that is not a bid notice.  Treating any of those as a successful
    # check would incorrectly refresh the freshness clock.
    if evidence.bid_notice_status is BidNoticeStatus.UNKNOWN:
        return None
    return evidence


def _recent_invitation_indices(
    records: Sequence[Mapping[str, Any]],
    current_date: date,
    pinned_host: Optional[str],
) -> list[int]:
    dated: list[tuple[date, int]] = []
    established_host = pinned_host
    for index, record in enumerate(records):
        if record.get("is_demo") or record.get("is_quarantined"):
            continue
        if not _looks_like_invitation(record):
            continue
        published = _record_date(record)
        if published is None:
            continue
        age = (current_date - published).days
        if age < 0 or age > RECENT_DAYS:
            continue
        host = _record_source_host(record)
        if host is None:
            continue
        if established_host is None:
            established_host = host
        if host != established_host:
            continue
        dated.append((published, index))

    # Newest notices get the finite refresh budget.  Original order breaks ties
    # deterministically, while the returned output itself remains in input order.
    dated.sort(key=lambda pair: (-pair[0].toordinal(), pair[1]))
    return [index for _, index in dated]


def _looks_like_invitation(record: Mapping[str, Any]) -> bool:
    explicit_status = str(record.get("bid_notice_status") or "").strip().upper()
    if explicit_status in {"DRAFT", "AWARDED", "CANCELLED"}:
        return False
    title = BaseScraper.clean_text(record.get("title"))
    description = BaseScraper.clean_text(record.get("description"))
    method = BaseScraper.clean_text(record.get("procurement_method"))
    scope = f"{title} {description} {method}".strip()
    if not title or _NOT_AN_INVITATION.search(scope):
        return False
    return bool(_INVITATION.search(scope))


def _record_date(record: Mapping[str, Any]) -> Optional[date]:
    for key in ("announcement_date", "published_at", "publication_date"):
        value = record.get(key)
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value.astimezone(BANGKOK).date()
            return value.date()
        if isinstance(value, date):
            return value
        parsed = BaseScraper.parse_source_date(value)
        if parsed:
            try:
                return date.fromisoformat(parsed)
            except ValueError:
                continue
    return None


def _record_source_host(record: Mapping[str, Any]) -> Optional[str]:
    for key in ("source_url", "detail_url", "announcement_url", "tor_url"):
        host = _allowed_host(record.get(key))
        if host:
            return host
    return None


def _primary_evidence_url(record: Mapping[str, Any], source_host: str) -> Optional[str]:
    # Prefer the scraper's already-resolved document.  When it is an off-site
    # e-GP link, do not follow it here; fall back to one official detail page.
    tor_url = _same_host_url(record.get("tor_url"), source_host)
    if tor_url:
        return tor_url
    for key in ("detail_url", "announcement_url", "source_record_url", "source_url"):
        detail_url = _same_host_url(record.get(key), source_host)
        if detail_url:
            return detail_url
    return None


def _same_site_pdf_links(document: FetchedDocument, source_host: str) -> list[str]:
    if document.content_type not in {"text/html", "application/xhtml+xml"}:
        return []
    soup = BeautifulSoup(document.text, "html.parser")
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        try:
            url = canonicalize_url(href, document.url)
        except (URLValidationError, TypeError, ValueError):
            continue
        if _host(url) != source_host:
            continue
        path = unquote(urlsplit(url).path)
        if not _PDF_PATH.search(path):
            continue
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def _same_host_url(value: Any, source_host: str) -> Optional[str]:
    try:
        url = canonicalize_url(value)
    except (URLValidationError, TypeError, ValueError):
        return None
    if _host(url) != source_host:
        return None
    return url


def _allowed_host(value: Any) -> Optional[str]:
    try:
        url = canonicalize_url(value)
    except (URLValidationError, TypeError, ValueError):
        return None
    host = _host(url)
    return host if host in ALLOWED_SOURCE_HOSTS else None


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").rstrip(".").lower()


def _as_bangkok(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(BANGKOK)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BANGKOK)


def _resolve_evidence(
    evidence: Sequence[BidDocumentEnrichment],
) -> Optional[BidDocumentEnrichment]:
    if not evidence:
        return None

    # A final lifecycle document can only close/suppress a bid.  It must never
    # lose to an older invitation merely because that invitation has dates.
    for status in (
        BidNoticeStatus.CANCELLED,
        BidNoticeStatus.AWARDED,
        BidNoticeStatus.DRAFT,
    ):
        terminal = next((item for item in evidence if item.bid_notice_status is status), None)
        if terminal is not None:
            return terminal

    invitations = [
        item for item in evidence if item.bid_notice_status is BidNoticeStatus.INVITATION
    ]
    if not invitations:
        return None

    with_windows = [
        item for item in invitations if item.bid_start_date and item.bid_deadline_at
    ]
    windows = {
        (item.bid_start_date, item.bid_deadline_at)
        for item in with_windows
    }
    if len(windows) > 1:
        # Two official documents that assert different windows require human or
        # source-specific resolution.  Keep evidence that the notice was read,
        # but clear both dates so the bidding policy remains UNCONFIRMED.
        base = with_windows[0]
        excerpts = " | ".join(
            dict.fromkeys(
                item.bid_evidence_excerpt
                for item in with_windows
                if item.bid_evidence_excerpt
            )
        )[:700] or base.bid_evidence_excerpt
        return replace(
            base,
            bid_start_date=None,
            bid_deadline_at=None,
            bid_evidence_excerpt=excerpts,
            reason_code="AMBIGUOUS_DOCUMENT_WINDOWS",
        )
    if with_windows:
        return with_windows[0]
    return invitations[0]


__all__ = [
    "ALLOWED_SOURCE_HOSTS",
    "MAX_REFRESH_RECORDS",
    "refresh_bid_evidence",
]

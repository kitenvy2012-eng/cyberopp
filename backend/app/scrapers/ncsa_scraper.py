"""Structured first-party NCSA procurement feed adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

from backend.app.scrapers.base import (
    BaseScraper,
    ScrapeError,
    ScrapeResult,
    ScrapeStatus,
    canonicalize_url,
    stable_tender_id,
)
from backend.app.scrapers.web_fetcher import FetchFailure, SafeWebClient
from backend.app.services.classifier import is_cyber_relevant, is_procurement_relevant


NCSA_FEED_URL = "https://www.ncsa.or.th/data/output/egp.json"


class NCSAScraper(BaseScraper):
    """Read the JSON feed used by the official NCSA procurement page."""

    async def scrape(self) -> ScrapeResult:
        outcome = self.new_outcome()
        fetcher = SafeWebClient(timeout_seconds=30, max_retries=2, request_delay_seconds=0.3)
        async with fetcher:
            try:
                document = await fetcher.fetch(NCSA_FEED_URL)
                payload = json.loads(document.text)
            except FetchFailure as exc:
                outcome.errors.append(exc.to_scrape_error())
                outcome.pages_fetched = fetcher.pages_fetched
                outcome.pages_skipped = fetcher.pages_skipped
                status = ScrapeStatus.SKIPPED if exc.code == "ROBOTS_DENIED" else ScrapeStatus.FAILED
                return self.finish_outcome(outcome, status=status)
            except (json.JSONDecodeError, ValueError) as exc:
                outcome.errors.append(
                    ScrapeError(
                        code="INVALID_NCSA_JSON",
                        message=f"NCSA feed could not be parsed ({type(exc).__name__})",
                        url=NCSA_FEED_URL,
                    )
                )
                outcome.pages_fetched = fetcher.pages_fetched
                return self.finish_outcome(outcome, status=ScrapeStatus.FAILED)

        if not isinstance(payload, list):
            outcome.errors.append(
                ScrapeError(
                    code="INVALID_NCSA_SCHEMA",
                    message="NCSA feed root is not a list",
                    url=NCSA_FEED_URL,
                )
            )
            outcome.pages_fetched = fetcher.pages_fetched
            return self.finish_outcome(outcome, status=ScrapeStatus.FAILED)

        latest_date: Optional[date] = None
        for group in payload:
            if not isinstance(group, dict):
                continue
            group_type = self.clean_text(group.get("anounceType"))
            group_name = self.clean_text(group.get("anounceTypeName"))
            items = group.get("item")
            if not isinstance(items, list):
                continue
            for record in items:
                if not isinstance(record, dict):
                    continue
                normalized = self._normalize_record(record, group_type, group_name)
                if normalized:
                    outcome.items.append(normalized)
                    parsed_date = self.parse_source_date(record.get("pubDate"))
                    if parsed_date:
                        observed_date = date.fromisoformat(parsed_date)
                        latest_date = max(latest_date, observed_date) if latest_date else observed_date

        outcome.pages_fetched = fetcher.pages_fetched
        outcome.pages_skipped = fetcher.pages_skipped
        if latest_date and (date.today() - latest_date).days > 365:
            outcome.errors.append(
                ScrapeError(
                    code="STALE_SOURCE",
                    message=f"Latest NCSA feed publication is {latest_date.isoformat()}",
                    url=NCSA_FEED_URL,
                )
            )
            return self.finish_outcome(outcome, status=ScrapeStatus.PARTIAL)
        return self.finish_outcome(outcome)

    def _normalize_record(
        self, record: Dict[str, Any], group_type: str, group_name: str
    ) -> Optional[Dict[str, Any]]:
        title = self.clean_text(record.get("title"))
        if not title or not is_cyber_relevant(title) or not is_procurement_relevant(title):
            return None

        raw_link = self.clean_text(record.get("link"))
        try:
            record_url = canonicalize_url(raw_link) if raw_link else NCSA_FEED_URL
        except Exception:
            record_url = NCSA_FEED_URL
        project_id = _extract_project_id(raw_link)
        identity = (
            f"egp:{project_id}"
            if project_id
            else f"ncsa:{group_type}|{record.get('pubDate')}|{title}|{record_url}"
        )
        tender_code = f"EGP-{project_id}" if project_id else stable_tender_id(identity)
        source_record_id = project_id or tender_code
        published_at = self.parse_source_date(record.get("pubDate"))
        source_status = _status_from_announcement_type(group_type)

        evidence_payload = {
            "group_type": group_type,
            "group_name": group_name,
            "record": record,
        }
        raw_payload_json = json.dumps(
            evidence_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        evidence_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
        return {
            "tender_code": tender_code,
            "title": title[:500],
            "description": f"ประเภทประกาศจาก สกมช.: {group_name or group_type}",
            "agency": "สำนักงานคณะกรรมการการรักษาความมั่นคงปลอดภัยไซเบอร์แห่งชาติ",
            "agency_type": "องค์การมหาชน",
            "budget": None,
            "median_price": None,
            "procurement_method": None,
            "announcement_date": published_at,
            "submission_deadline": None,
            "tor_url": None,
            "source_name": self.source_name,
            "source_url": record_url,
            "source_record_id": source_record_id,
            "status": source_status,
            "data_origin": "SCRAPED",
            "verification_status": "VERIFIED",
            "verification_method": "OFFICIAL_NCSA_JSON_FEED",
            "confidence_score": 1.0,
            "is_official_source": True,
            "evidence_hash": evidence_hash,
            "raw_payload_json": raw_payload_json,
            "last_verified_at": datetime.utcnow(),
            "provenance": {
                "source_name": self.source_name,
                "source_type": "OFFICIAL",
                "source_url": NCSA_FEED_URL,
                "document_url": record_url if record_url != NCSA_FEED_URL else None,
                "source_record_id": source_record_id,
                "published_at": published_at,
                "http_status": 200,
                "content_sha256": evidence_hash,
                "raw_payload_json": raw_payload_json,
                "verification_status": "VERIFIED",
                "verification_notes": (
                    f"Structured record from the JSON feed used by the official NCSA site; "
                    f"announcement type {group_type or 'unknown'}."
                ),
                "is_primary": True,
            },
        }


def _extract_project_id(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        values = parse_qs(urlsplit(url).query)
    except ValueError:
        return None
    for key in ("projectId", "project_id"):
        candidates = values.get(key) or []
        for candidate in candidates:
            candidate = "".join(character for character in str(candidate) if character.isdigit())
            if len(candidate) >= 8:
                return candidate[:32]
    return None


def _status_from_announcement_type(value: str) -> str:
    if value in {"W0", "W1", "W2", "D1"}:
        return "CLOSED"
    return "UNKNOWN"

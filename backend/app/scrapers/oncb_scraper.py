"""Latest procurement notices and explicit bid windows from the ONCB website."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from backend.app.scrapers.base import BaseScraper, ScrapeError, ScrapeStatus, canonicalize_url
from backend.app.scrapers.bid_document import extract_bid_document_evidence
from backend.app.scrapers.web_fetcher import FetchFailure, SafeWebClient
from backend.app.services.bidding import BANGKOK
from backend.app.services.classifier import is_cyber_relevant


class ONCBScraper(BaseScraper):
    def __init__(self, source_name="สำนักงาน ป.ป.ส. (ONCB) — ประกาศจัดซื้อจัดจ้าง", url="https://www.oncb.go.th/procurement", config_json=None):
        super().__init__(source_name, url)
        self.config = json.loads(config_json) if config_json else {}

    async def scrape(self):
        outcome = self.new_outcome()
        max_pages = max(1, min(int(self.config.get("max_pages", 8)), 20))
        cutoff = (datetime.now(BANGKOK) - timedelta(days=90)).date().isoformat()
        seen = set()
        detail_seen = set()
        next_url = self.url
        async with SafeWebClient(timeout_seconds=20, max_retries=1, request_delay_seconds=0.4) as fetcher:
            for _ in range(max_pages):
                if not next_url or next_url in seen:
                    break
                seen.add(next_url)
                try:
                    page = await fetcher.fetch(next_url)
                except FetchFailure as exc:
                    outcome.errors.append(exc.to_scrape_error())
                    break
                soup = BeautifulSoup(page.text, "html.parser")
                rows = soup.select(".list-content .list-group-item")
                if not rows:
                    outcome.errors.append(ScrapeError(code="LISTING_EMPTY", message="ONCB listing selector returned no rows", url=next_url))
                    break
                older_count = 0
                for row in rows:
                    anchor = row.select_one(".news-title a")
                    if not anchor:
                        continue
                    date_node = row.select_one(".news-date")
                    published = self.parse_source_date(date_node.get_text(" ", strip=True)) if date_node else None
                    if published and published < cutoff:
                        older_count += 1
                        continue
                    title = self.clean_text(anchor.get_text(" ", strip=True))
                    if not is_cyber_relevant(title):
                        continue
                    url = canonicalize_url(anchor.get("href"), page.url)
                    if not re.fullmatch(r"/procurement/\d+", urlsplit(url).path):
                        continue
                    try:
                        detail = await fetcher.fetch(url)
                        detail_seen.add(url)
                        item = self.normalize_detail(detail, published)
                        if item:
                            outcome.items.append(item)
                    except FetchFailure as exc:
                        outcome.errors.append(exc.to_scrape_error())
                if older_count == len(rows):
                    break
                next_anchor = soup.select_one('a[aria-label="pagination-btn-next"]:not(.disabled)')
                next_url = canonicalize_url(next_anchor["href"], page.url) if next_anchor else None
            # Active invitations may move beyond the first listing pages. Fetch
            # their own official notice again; failures do not renew freshness.
            for url in self.config.get("recheck_urls", [])[:50]:
                if url in detail_seen or urlsplit(url).hostname != "www.oncb.go.th" or not re.fullmatch(r"/procurement/\d+", urlsplit(url).path):
                    continue
                try:
                    detail = await fetcher.fetch(url)
                    item = self.normalize_detail(detail)
                    if item:
                        outcome.items.append(item)
                except FetchFailure as exc:
                    outcome.errors.append(exc.to_scrape_error())
            outcome.pages_fetched = fetcher.pages_fetched
            outcome.pages_skipped = fetcher.pages_skipped
        status = ScrapeStatus.PARTIAL if outcome.errors and outcome.pages_fetched else ScrapeStatus.FAILED if outcome.errors else ScrapeStatus.SUCCESS
        return self.finish_outcome(outcome, status=status)

    def normalize_detail(self, document, published=None):
        soup = BeautifulSoup(document.text, "html.parser")
        heading = soup.select_one("h1.content-title")
        body = soup.select_one(".content-description")
        if not heading or not body:
            return None
        title = self.clean_text(heading.get_text(" ", strip=True))
        if not is_cyber_relevant(title):
            return None
        if not published:
            date_node = heading.find_next_sibling("div")
            published = self.parse_source_date(date_node.get_text(" ", strip=True)) if date_node else None
        text = self.clean_text(body.get_text(" ", strip=True))
        now = datetime.utcnow()
        # Hash the actual response. The parser extracts dates solely from the
        # invitation's content, without navigation or other notice cards.
        evidence = extract_bid_document_evidence(
            content=document.content,
            content_type=document.content_type,
            evidence_url=document.url,
            title=title,
            checked_at=now,
        )
        bid = asdict(evidence)
        bid.pop("reason_code", None)
        bid["bid_notice_status"] = evidence.bid_notice_status.value
        notice_id = urlsplit(document.url).path.rstrip("/").split("/")[-1]
        document_url = None
        for anchor in soup.select(".content-download a[href]"):
            label = anchor.get_text(" ", strip=True)
            if "ขอบเขต" not in label and "TOR" not in label.upper():
                continue
            href = canonicalize_url(anchor["href"], document.url)
            file_url = (parse_qs(urlsplit(href).query).get("file") or [None])[0]
            document_url = canonicalize_url(file_url, document.url) if file_url else href
            break
        raw_payload = json.dumps({"title": title, "description": text, "announcement_date": published, "tor_url": document_url}, ensure_ascii=False, sort_keys=True)
        payload_hash = hashlib.sha256(raw_payload.encode()).hexdigest()
        return {
            "tender_code": f"ONCB-{notice_id}", "source_record_id": notice_id,
            "title": title, "description": text,
            "agency": "สำนักงานคณะกรรมการป้องกันและปราบปรามยาเสพติด",
            "agency_type": "ส่วนราชการ", "category": "OTHER",
            "budget": None, "median_price": None,
            "procurement_method": "e-bidding" if "e-bidding" in title.lower() else None,
            "announcement_date": published,
            "submission_deadline": evidence.bid_deadline_at[:10] if evidence.bid_deadline_at else None,
            "tor_url": document_url, "source_url": document.url, "source_name": self.source_name,
            "status": "CLOSED" if bid["bid_notice_status"] in {"AWARDED", "CANCELLED"} else "UNKNOWN",
            "data_origin": "SCRAPED", "verification_status": "VERIFIED",
            "verification_method": "OFFICIAL_ONCB_NOTICE_HTML", "is_official_source": True,
            "confidence_score": 1.0, "last_verified_at": now,
            "evidence_hash": payload_hash, "raw_payload_json": raw_payload,
            **bid,
            "provenance": {
                "source_name": self.source_name, "source_type": "OFFICIAL", "source_url": document.url,
                "document_url": document_url, "source_record_id": notice_id, "published_at": published,
                "http_status": document.status_code, "content_sha256": hashlib.sha256(document.content).hexdigest(),
                "raw_payload_json": raw_payload, "verification_status": "VERIFIED", "is_primary": True,
                "verification_notes": "Official ONCB invitation title, date and explicit bid-submission clause. " + (evidence.reason_code or ""),
            },
        }

"""Bank of Thailand procurement adapter.

The public procurement page renders its rows from an AEM listing component. This
adapter reads that same first-party JSON endpoint instead of trying to parse a
client-rendered page, so every record it stores is the exact row the public page
shows, together with the announcement document the row links to.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple

from backend.app.scrapers.base import (
    BaseScraper,
    ScrapeError,
    ScrapeResult,
    ScrapeStatus,
    canonicalize_url,
    stable_tender_id,
)
from backend.app.scrapers.web_fetcher import FetchFailure, SafeWebClient
from backend.app.services.classifier import is_cyber_relevant


BOT_ORIGIN = "https://www.bot.or.th"
# `.superListingResults.<pageSize>.<pageIndex>.<sortOrder>.json` is the selector
# chain the public page itself requests. The third segment is a *page index*,
# not a row offset: at page size 20 the page after 0 is 1, not 20. Treating it
# as an offset silently skips 380 rows per step.
BOT_LISTING_TEMPLATE = (
    BOT_ORIGIN
    + "/content/bot/th/news-and-media/procurement-list/jcr:content/root/container"
    + "/superlist.superListingResults.{page_size}.{page}.descending.json"
    + "/sortOrderMap/ascending"
)
_HREF_PATTERN = re.compile(r'href="([^"]+)"', re.I)


class BOTScraper(BaseScraper):
    """Read the JSON listing behind the official BOT procurement page."""

    def __init__(
        self,
        source_name: str = "ธนาคารแห่งประเทศไทย (BOT)",
        url: str = f"{BOT_ORIGIN}/th/news-and-media/procurement-list.html",
        config_json: Optional[str] = None,
    ):
        super().__init__(source_name, url)
        self.config: Dict[str, Any] = {}
        self._config_error: Optional[ScrapeError] = None
        if config_json:
            try:
                loaded = json.loads(config_json)
                if not isinstance(loaded, dict):
                    raise ValueError("configuration must be a JSON object")
                self.config = loaded
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                self._config_error = ScrapeError(
                    code="INVALID_CONFIG",
                    message=f"BOT configuration is invalid: {exc}",
                )

        # A large page is no slower than a small one: what costs time is a page
        # the CDN has not cached yet, not the number of rows in it. Twelve pages
        # of 1000 covers the whole listing (10,862 rows when this was written).
        self.page_size = _bounded_int(self.config.get("page_size"), 1000, 1, 2000)
        self.max_pages = _bounded_int(self.config.get("max_pages"), 12, 1, 200)
        self.timeout_seconds = _bounded_float(
            self.config.get("timeout_seconds"), 30.0, 5.0, 180.0
        )
        # An uncached page never answers in time, however long the wait, but the
        # request still makes the CDN build and store it. Retrying after a pause
        # is what turns a cold page into a fast hit, so the retry delays are
        # measured in seconds rather than milliseconds.
        self.warm_attempts = _bounded_int(self.config.get("warm_attempts"), 3, 0, 10)
        self.warm_delay_seconds = _bounded_float(
            self.config.get("warm_delay_seconds"), 10.0, 1.0, 120.0
        )
        # Total time this source may spend waiting for cold pages in one scan.
        # Whatever is still cold is left for the next scan, which finds it warm.
        self.max_warm_seconds = _bounded_float(
            self.config.get("max_warm_seconds"), 300.0, 0.0, 1800.0
        )

    async def scrape(self) -> ScrapeResult:
        outcome = self.new_outcome()
        if self._config_error:
            outcome.errors.append(self._config_error)

        fetcher = SafeWebClient(
            timeout_seconds=self.timeout_seconds,
            # Warming is handled here, with delays long enough to matter; the
            # client's own sub-second retries cannot help a cold page.
            max_retries=0,
            max_response_bytes=12 * 1024 * 1024,
            request_delay_seconds=float(self.config.get("request_delay_seconds") or 0.4),
        )
        seen_identities: set[str] = set()
        pages_read = 0
        total_results: Optional[int] = None
        warm_deadline = time.monotonic() + self.max_warm_seconds

        async with fetcher:
            for page in range(self.max_pages):
                payload, error = await self._fetch_page(fetcher, page, warm_deadline)
                if error is not None:
                    outcome.errors.append(error)
                    if error.code == "ROBOTS_DENIED":
                        outcome.pages_fetched = fetcher.pages_fetched
                        outcome.pages_skipped = fetcher.pages_skipped
                        return self.finish_outcome(outcome, status=ScrapeStatus.SKIPPED)
                    # Pages are addressed independently, so one that stayed cold
                    # must not hide the pages after it. Move on unless the whole
                    # warming budget for this scan is gone.
                    if time.monotonic() >= warm_deadline:
                        break
                    continue

                results = payload.get("results")
                results = results if isinstance(results, list) else []
                pages_read += 1
                if isinstance(payload.get("totalResults"), int):
                    total_results = payload["totalResults"]

                for entry in results:
                    row = entry.get("rowData") if isinstance(entry, dict) else None
                    if not isinstance(row, dict):
                        continue
                    item = self._build_item(row, page)
                    if item and item["tender_code"] not in seen_identities:
                        seen_identities.add(item["tender_code"])
                        outcome.items.append(item)

                if not results or not payload.get("hasLoadmore"):
                    break
                if total_results is not None and (page + 1) * self.page_size >= total_results:
                    break

        outcome.pages_fetched = fetcher.pages_fetched
        outcome.pages_skipped = fetcher.pages_skipped
        if pages_read == 0:
            return self.finish_outcome(outcome, status=ScrapeStatus.FAILED)
        if outcome.errors:
            return self.finish_outcome(outcome, status=ScrapeStatus.PARTIAL)
        return self.finish_outcome(outcome, status=ScrapeStatus.SUCCESS)

    async def _fetch_page(
        self, fetcher: SafeWebClient, page: int, warm_deadline: float
    ) -> Tuple[Optional[Dict[str, Any]], Optional[ScrapeError]]:
        """Fetch one listing page, retrying a timeout long enough to let it cache."""
        url = BOT_LISTING_TEMPLATE.format(page_size=self.page_size, page=page)
        delay = self.warm_delay_seconds
        last_error: Optional[ScrapeError] = None

        for attempt in range(self.warm_attempts + 1):
            try:
                document = await fetcher.fetch(url)
                payload = json.loads(document.text)
            except FetchFailure as exc:
                last_error = exc.to_scrape_error()
                if exc.code != "TIMEOUT":
                    return None, last_error
            except (json.JSONDecodeError, ValueError) as exc:
                return None, ScrapeError(
                    code="INVALID_BOT_JSON",
                    message=f"BOT listing could not be parsed ({type(exc).__name__})",
                    url=url,
                )
            else:
                if not isinstance(payload, dict) or payload.get("success") is not True:
                    return None, ScrapeError(
                        code="BOT_LISTING_UNSUCCESSFUL",
                        message="BOT listing endpoint reported an unsuccessful response",
                        url=url,
                    )
                return payload, None

            if attempt >= self.warm_attempts or time.monotonic() + delay >= warm_deadline:
                break
            await asyncio.sleep(delay)
            delay *= 2

        return None, last_error

    def _build_item(self, row: Mapping[str, Any], page: int) -> Optional[Dict[str, Any]]:
        title = self.clean_text(row.get("procurementtitle"))
        if not title:
            return None
        announce_type = self.clean_text(row.get("announceType"))
        category = self.clean_text(row.get("category"))
        # The listing mixes announcements with contract summaries and appeal
        # notices. Only cybersecurity-related rows are stored, and the row's own
        # announcement type is preserved verbatim in the description.
        if not is_cyber_relevant(title, f"{announce_type} {category}"):
            return None

        document_url = _first_document_url(row.get("link"))
        announcement_date = self.parse_source_date(row.get("publishstart"))
        # BOT rows carry no procurement identifier, so identity is derived from
        # the source plus the title and publication date the source published.
        identity = stable_tender_id(
            f"source:{BOT_ORIGIN}|title:{title.casefold()}|published:{announcement_date or ''}"
        )
        raw_payload_json = json.dumps(
            dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
        evidence_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
        description_parts = [
            f"ประเภทประกาศ: {announce_type}" if announce_type else None,
            f"วิธีการจัดซื้อจัดจ้าง: {category}" if category else None,
        ]
        now = datetime.utcnow()
        return {
            "tender_code": identity,
            "title": title[:500],
            "agency": "ธนาคารแห่งประเทศไทย",
            "agency_type": None,
            "description": " | ".join(part for part in description_parts if part) or None,
            # The listing publishes no budget, median price, or submission
            # deadline; those stay missing rather than being guessed.
            "budget": None,
            "median_price": None,
            "procurement_method": category or None,
            "announcement_date": announcement_date,
            "submission_deadline": None,
            "tor_url": document_url,
            "source_name": self.source_name,
            "source_url": self.url,
            "source_record_id": identity,
            "status": "UNKNOWN",
            "data_origin": "SCRAPED",
            "verification_status": "VERIFIED",
            "verification_method": "OFFICIAL_BOT_LISTING_JSON",
            "confidence_score": 1.0,
            "is_official_source": True,
            "evidence_hash": evidence_hash,
            "raw_payload_json": raw_payload_json,
            "last_verified_at": now,
            "provenance": {
                "source_name": self.source_name,
                "source_type": "OFFICIAL",
                "source_url": self.url,
                "document_url": document_url,
                "source_record_id": identity,
                "published_at": announcement_date,
                "http_status": 200,
                "content_sha256": evidence_hash,
                "raw_payload_json": raw_payload_json,
                "verification_status": "VERIFIED",
                "verification_notes": (
                    "Row returned by the first-party AEM listing endpoint that renders "
                    f"the public BOT procurement page (listing page {page})."
                ),
                "is_primary": True,
            },
        }


def _first_document_url(link_html: Any) -> Optional[str]:
    """Pull the announcement document out of the row's HTML link fragment."""
    if not isinstance(link_html, str) or not link_html.strip():
        return None
    match = _HREF_PATTERN.search(link_html)
    if not match:
        return None
    url = canonicalize_url(match.group(1), base_url=BOT_ORIGIN)
    return url or None


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))

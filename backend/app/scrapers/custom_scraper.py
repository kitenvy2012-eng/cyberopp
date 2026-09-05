"""Generic live-source crawler for HTML, RSS/Atom, and XML sitemaps."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from bs4 import BeautifulSoup, Tag

from backend.app.scrapers.base import (
    BaseScraper,
    ScrapeError,
    ScrapeOutcome,
    ScrapeResult,
    ScrapeStatus,
    URLValidationError,
    canonicalize_url,
    is_probable_document_url,
    stable_tender_id,
)
from backend.app.scrapers.web_fetcher import FetchFailure, FetchedDocument, SafeWebClient
from backend.app.services.classifier import is_cyber_relevant, is_procurement_relevant


_DEFAULT_ITEM_SELECTOR = ", ".join(
    (
        "article",
        "tr",
        "li",
        ".item",
        ".card",
        ".news-item",
        ".procurement-item",
        ".tender-item",
        ".views-row",
    )
)
_FEED_CONTENT_TYPES = {
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
}
_XML_CONTENT_TYPES = {"application/xml", "text/xml"}
_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml", ""}
_TOR_LABEL_PATTERN = re.compile(r"(?:\btor\b|ขอบเขต(?:ของ)?งาน|เอกสาร(?:ประกวด|แนบ|ดาวน์โหลด)|ดาวน์โหลด)", re.I)


class CustomWebScraper(BaseScraper):
    """Crawl a configured public source without inventing missing tender fields.

    Existing callers still receive a list-like object. Structured status, errors,
    and fetch counts are available through ``result.outcome``.
    """

    def __init__(
        self,
        source_name: str,
        url: str,
        config_json: Optional[str] = None,
        *,
        _client: Optional[httpx.AsyncClient] = None,
        _resolve_dns: bool = True,
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
                    message=f"Crawler configuration is invalid: {exc}",
                )

        self.max_items = _bounded_int(self.config.get("max_items"), default=250, minimum=1, maximum=2000)
        self.max_pages = _bounded_int(self.config.get("max_pages"), default=30, minimum=1, maximum=500)
        self.max_sitemaps = _bounded_int(self.config.get("max_sitemaps"), default=10, minimum=0, maximum=100)
        self.discover_feeds = _as_bool(self.config.get("discover_feeds"), default=True)
        self.discover_sitemaps = _as_bool(self.config.get("discover_sitemaps"), default=True)
        self._injected_client = _client
        self._resolve_dns = _resolve_dns
        self._processed_urls: set[str] = set()
        self._queued_sitemaps: set[str] = set()
        self._detail_pages_processed = 0
        self._pagination_pages_processed = 0
        # Some listings page purely by query string and render no page links at
        # all. `page_url_template` lets such a source declare its own paging,
        # e.g. "https://host/list?page={page}".
        template = self.config.get("page_url_template")
        self.page_url_template = str(template) if isinstance(template, str) and "{page}" in template else None
        self.page_start = _bounded_int(self.config.get("page_start"), default=1, minimum=0, maximum=10)
        self.page_count = _bounded_int(self.config.get("page_count"), default=0, minimum=0, maximum=200)
        self._templated_pages_queued = False
        # A source row is named for the feed ("Agency X — bid announcements"),
        # which is not the agency name a record should carry. `agency_name`
        # supplies the organisation itself when a row does not name it.
        agency_name = self.clean_text(self.config.get("agency_name"))
        self.default_agency = agency_name or source_name
        self._extra_keyword_patterns = _compile_keyword_patterns(
            _extra_keywords(self.config.get("keywords"))
        )

    async def scrape(self) -> ScrapeResult:
        outcome = self.new_outcome()
        if self._config_error:
            outcome.errors.append(self._config_error)

        fetcher = SafeWebClient(
            client=self._injected_client,
            timeout_seconds=_bounded_float(self.config.get("timeout_seconds"), 20.0, 2.0, 120.0),
            max_response_bytes=_bounded_int(
                self.config.get("max_response_bytes"),
                default=8 * 1024 * 1024,
                minimum=64 * 1024,
                maximum=50 * 1024 * 1024,
            ),
            max_retries=_bounded_int(self.config.get("max_retries"), default=2, minimum=0, maximum=5),
            request_delay_seconds=_bounded_float(
                self.config.get("request_delay_seconds"), 0.25, 0.0, 60.0
            ),
            # Fail closed by default; a source owner may explicitly opt into a
            # fail-open policy for a temporarily unavailable robots endpoint.
            robots_fail_open=_as_bool(self.config.get("robots_fail_open"), default=False),
            resolve_dns=self._resolve_dns,
        )

        async with fetcher:
            try:
                root = await fetcher.fetch(self.url)
            except FetchFailure as exc:
                outcome.errors.append(exc.to_scrape_error())
                outcome.pages_fetched = fetcher.pages_fetched
                outcome.pages_skipped = fetcher.pages_skipped
                status = ScrapeStatus.SKIPPED if exc.code == "ROBOTS_DENIED" else ScrapeStatus.FAILED
                return self.finish_outcome(outcome, status=status)

            try:
                await self._consume_document(root, fetcher, outcome, is_detail=False)
            except Exception as exc:  # Parser isolation; HTTP errors remain structured above.
                _append_error(
                    outcome,
                    ScrapeError(
                        code="PARSE_ERROR",
                        message=f"Could not parse source document ({type(exc).__name__})",
                        url=root.url,
                    ),
                )

            if self.discover_sitemaps and self.max_sitemaps:
                try:
                    declared = await fetcher.sitemaps_for(root.url)
                except (FetchFailure, URLValidationError) as exc:
                    error = exc.to_scrape_error() if isinstance(exc, FetchFailure) else ScrapeError(
                        code="INVALID_SITEMAP_URL", message=str(exc), url=root.url
                    )
                    _append_error(outcome, error)
                else:
                    for sitemap_url in declared[: self.max_sitemaps]:
                        await self._fetch_secondary(
                            sitemap_url,
                            fetcher,
                            outcome,
                            is_detail=False,
                            expected_kind="sitemap",
                        )

        outcome.pages_fetched = fetcher.pages_fetched
        outcome.pages_skipped = fetcher.pages_skipped
        if not self._processed_urls:
            return self.finish_outcome(outcome, status=ScrapeStatus.FAILED)
        return self.finish_outcome(outcome)

    async def _consume_document(
        self,
        document: FetchedDocument,
        fetcher: SafeWebClient,
        outcome: ScrapeOutcome,
        *,
        is_detail: bool,
        expected_kind: Optional[str] = None,
    ) -> None:
        if document.url in self._processed_urls:
            return
        self._processed_urls.add(document.url)

        content = _maybe_decompress(document.content)
        kind, soup = _classify_document(content, document.content_type)
        if expected_kind and kind != expected_kind:
            _append_error(
                outcome,
                ScrapeError(
                    code="UNEXPECTED_CONTENT",
                    message=f"Expected {expected_kind} content but received {kind}",
                    url=document.url,
                ),
            )

        if kind == "feed":
            outcome.items.extend(self._parse_feed(soup, document.url))
            return
        if kind == "sitemap":
            await self._consume_sitemap(soup, document.url, fetcher, outcome)
            return
        if kind == "html":
            if is_detail:
                detail = self._parse_detail_page(soup, document.url)
                if detail:
                    outcome.items.append(detail)
                else:
                    outcome.items.extend(self._parse_html(soup, document.url))
            else:
                outcome.items.extend(self._parse_html(soup, document.url))
            await self._discover_from_html(soup, document.url, fetcher, outcome)
            return

        _append_error(
            outcome,
            ScrapeError(
                code="UNSUPPORTED_CONTENT",
                message=f"Unsupported source content type: {document.content_type or 'unknown'}",
                url=document.url,
            ),
        )

    def _parse_feed(self, soup: BeautifulSoup, feed_url: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for entry in soup.find_all(["item", "entry"])[: self.max_items]:
            title = self.clean_text(_tag_text(entry.find("title")))
            description = self.clean_text(
                _tag_text(entry.find(["description", "summary", "content", "content:encoded"]))
            )
            if not title or not self._matches_keywords(f"{title} {description}"):
                continue

            raw_link = _feed_link(entry)
            item_url = _safe_url(raw_link, feed_url) if raw_link else feed_url
            if not item_url:
                continue
            guid = self.clean_text(_tag_text(entry.find(["guid", "id"])))
            identity = f"feed:{feed_url}|{guid}" if guid else f"url:{item_url}"
            published = _tag_text(entry.find(["published", "pubdate", "updated", "dc:date", "date"]))

            tor_url = None
            enclosure = entry.find("enclosure")
            if enclosure and enclosure.get("url"):
                candidate = _safe_url(enclosure.get("url"), feed_url)
                if candidate and is_probable_document_url(candidate):
                    tor_url = candidate
            if tor_url is None and is_probable_document_url(item_url):
                tor_url = item_url

            items.append(
                self._raw_item(
                    identity=identity,
                    title=title,
                    description=description,
                    source_url=item_url,
                    tor_url=tor_url,
                    announcement_date=self.parse_source_date(published),
                    provenance_format="rss/atom",
                    source_record_id=guid or None,
                    verification_status="PENDING",
                    verification_method="RSS_ATOM_FEED",
                )
            )
        return items

    def _parse_html(self, soup: BeautifulSoup, page_url: str) -> List[Dict[str, Any]]:
        item_selector = self.config.get("item_selector") or _DEFAULT_ITEM_SELECTOR
        try:
            elements = soup.select(str(item_selector))
        except Exception as exc:
            raise ValueError(f"invalid item_selector ({type(exc).__name__})") from exc

        results: List[Dict[str, Any]] = []
        for element in elements:
            if len(results) >= self.max_items:
                break
            source_text = self.clean_text(element.get_text(" ", strip=True))
            if len(source_text) < 8 or not self._matches_keywords(source_text):
                continue

            title = _selected_text(element, self.config.get("title_selector"))
            if not title:
                anchor = element if element.name == "a" else element.find("a", href=True)
                title = self.clean_text(anchor.get_text(" ", strip=True)) if anchor else source_text
            if not title:
                continue

            raw_link = _selected_link(element, self.config.get("link_selector"))
            item_url = _safe_url(raw_link, page_url) if raw_link else page_url
            if not item_url:
                continue

            description = _selected_text(element, self.config.get("description_selector")) or source_text
            agency = _selected_text(element, self.config.get("agency_selector")) or self.default_agency
            budget = self.parse_price(_selected_text(element, self.config.get("budget_selector")))
            median_price = self.parse_price(
                _selected_text(element, self.config.get("median_price_selector"))
            )
            method = _selected_text(element, self.config.get("method_selector")) or None
            announcement_date = self.parse_source_date(
                _selected_text(element, self.config.get("announcement_date_selector"))
            )
            deadline = self.parse_source_date(
                _selected_text(element, self.config.get("deadline_selector"))
            )
            source_record_id = _selected_text(element, self.config.get("code_selector")) or None
            tor_url = self._extract_tor_url(element, page_url, item_url)
            if _as_bool(self.config.get("identity_from_title"), default=False):
                identity = f"source:{self.url}|title:{self.clean_text(title).casefold()}"
            else:
                identity = (
                    f"url:{item_url}"
                    if item_url != page_url
                    else f"page:{page_url}|title:{self.clean_text(title).casefold()}"
                )

            results.append(
                self._raw_item(
                    identity=identity,
                    title=title,
                    description=description,
                    agency=agency,
                    source_url=item_url,
                    tor_url=tor_url,
                    budget=budget,
                    median_price=median_price,
                    procurement_method=method,
                    announcement_date=announcement_date,
                    submission_deadline=deadline,
                    provenance_format="html",
                    source_record_id=source_record_id,
                    verification_status="PENDING",
                    verification_method="HTML_DISCOVERY",
                )
            )
        return results

    def _parse_detail_page(self, soup: BeautifulSoup, page_url: str) -> Optional[Dict[str, Any]]:
        title_element = soup.select_one("h1") or soup.select_one("main h2") or soup.find("title")
        title = self.clean_text(title_element.get_text(" ", strip=True)) if title_element else ""
        body_element = soup.select_one("main") or soup.select_one("article") or soup.body
        body = self.clean_text(body_element.get_text(" ", strip=True)) if body_element else ""
        if not title or not self._matches_keywords(f"{title} {body}"):
            return None

        agency = _selected_text(body_element, self.config.get("agency_selector")) or self.default_agency
        return self._raw_item(
            identity=f"url:{page_url}",
            title=title,
            description=body,
            agency=agency,
            source_url=page_url,
            tor_url=self._extract_tor_url(body_element, page_url, page_url),
            budget=self.parse_price(_selected_text(body_element, self.config.get("budget_selector"))),
            median_price=self.parse_price(
                _selected_text(body_element, self.config.get("median_price_selector"))
            ),
            procurement_method=_selected_text(body_element, self.config.get("method_selector")) or None,
            announcement_date=self.parse_source_date(
                _selected_text(body_element, self.config.get("announcement_date_selector"))
            ),
            submission_deadline=self.parse_source_date(
                _selected_text(body_element, self.config.get("deadline_selector"))
            ),
            provenance_format="html-detail",
            source_record_id=_selected_text(body_element, self.config.get("code_selector")) or None,
            # Fetching a page proves the evidence URL exists, but a generic
            # parser can still attach the wrong heading/body. Keep the record
            # pending until a source-specific adapter or human review verifies
            # the field mapping.
            verification_status="PENDING",
            verification_method="FETCHED_SOURCE_RECORD_PENDING_REVIEW",
        )

    async def _consume_sitemap(
        self,
        soup: BeautifulSoup,
        sitemap_url: str,
        fetcher: SafeWebClient,
        outcome: ScrapeOutcome,
    ) -> None:
        root = soup.find()
        root_name = _local_name(root.name) if root else ""
        if root_name == "sitemapindex":
            sitemap_urls = []
            for node in soup.find_all(lambda tag: _local_name(getattr(tag, "name", "")) == "sitemap"):
                loc = node.find(lambda tag: _local_name(getattr(tag, "name", "")) == "loc")
                candidate = _safe_url(_tag_text(loc), sitemap_url)
                if candidate:
                    sitemap_urls.append(candidate)
            for candidate in sitemap_urls:
                if len(self._queued_sitemaps) >= self.max_sitemaps:
                    break
                if candidate in self._queued_sitemaps:
                    continue
                self._queued_sitemaps.add(candidate)
                await self._fetch_secondary(
                    candidate,
                    fetcher,
                    outcome,
                    is_detail=False,
                    expected_kind="sitemap",
                )
            return

        page_entries: List[Tuple[str, str]] = []
        for node in soup.find_all(lambda tag: _local_name(getattr(tag, "name", "")) == "url"):
            loc = node.find(lambda tag: _local_name(getattr(tag, "name", "")) == "loc")
            lastmod = node.find(lambda tag: _local_name(getattr(tag, "name", "")) == "lastmod")
            candidate = _safe_url(_tag_text(loc), sitemap_url)
            if candidate:
                # lastmod affects crawl priority only; it is not treated as an
                # announcement date because the semantics are different.
                page_entries.append((candidate, self.clean_text(_tag_text(lastmod))))
        page_entries.sort(key=lambda pair: pair[1], reverse=True)
        for candidate, _lastmod in page_entries:
            if self._detail_pages_processed >= self.max_pages:
                break
            self._detail_pages_processed += 1
            await self._fetch_secondary(candidate, fetcher, outcome, is_detail=True)

    async def _discover_from_html(
        self,
        soup: BeautifulSoup,
        page_url: str,
        fetcher: SafeWebClient,
        outcome: ScrapeOutcome,
    ) -> None:
        if self.page_url_template and self.page_count and not self._templated_pages_queued:
            # Queue every declared page once, from the first document only, so a
            # generated page cannot generate the series again.
            self._templated_pages_queued = True
            for offset in range(self.page_count):
                if self._pagination_pages_processed >= self.max_pages:
                    break
                candidate = _safe_url(
                    self.page_url_template.format(page=self.page_start + offset), page_url
                )
                if not candidate or candidate in self._processed_urls:
                    continue
                self._pagination_pages_processed += 1
                await self._fetch_secondary(candidate, fetcher, outcome, is_detail=False)

        pagination_selector = self.config.get("pagination_selector")
        if pagination_selector:
            try:
                pagination_links = soup.select(str(pagination_selector))
            except Exception as exc:
                _append_error(
                    outcome,
                    ScrapeError(
                        code="INVALID_PAGINATION_SELECTOR",
                        message=f"Pagination selector is invalid ({type(exc).__name__})",
                        url=page_url,
                    ),
                )
                pagination_links = []
            for link in pagination_links:
                if self._pagination_pages_processed >= self.max_pages:
                    break
                candidate = _safe_url(link.get("href"), page_url) if link.get("href") else None
                if not candidate or candidate in self._processed_urls:
                    continue
                self._pagination_pages_processed += 1
                await self._fetch_secondary(
                    candidate,
                    fetcher,
                    outcome,
                    is_detail=False,
                )

        if self.discover_feeds:
            feed_urls = []
            for link in soup.find_all("link", href=True):
                rel = " ".join(link.get("rel") or []).lower()
                media_type = str(link.get("type") or "").lower()
                if "alternate" in rel and ("rss" in media_type or "atom" in media_type):
                    candidate = _safe_url(link.get("href"), page_url)
                    if candidate:
                        feed_urls.append(candidate)
            for feed_url in list(dict.fromkeys(feed_urls))[:5]:
                await self._fetch_secondary(
                    feed_url,
                    fetcher,
                    outcome,
                    is_detail=False,
                    expected_kind="feed",
                )

        if self.discover_sitemaps and self.max_sitemaps:
            for link in soup.find_all("link", href=True):
                rel = " ".join(link.get("rel") or []).lower()
                if "sitemap" not in rel:
                    continue
                candidate = _safe_url(link.get("href"), page_url)
                if not candidate or candidate in self._queued_sitemaps:
                    continue
                if len(self._queued_sitemaps) >= self.max_sitemaps:
                    break
                self._queued_sitemaps.add(candidate)
                await self._fetch_secondary(
                    candidate,
                    fetcher,
                    outcome,
                    is_detail=False,
                    expected_kind="sitemap",
                )

    async def _fetch_secondary(
        self,
        url: str,
        fetcher: SafeWebClient,
        outcome: ScrapeOutcome,
        *,
        is_detail: bool,
        expected_kind: Optional[str] = None,
    ) -> None:
        if url in self._processed_urls:
            return
        try:
            document = await fetcher.fetch(url)
            await self._consume_document(
                document,
                fetcher,
                outcome,
                is_detail=is_detail,
                expected_kind=expected_kind,
            )
        except FetchFailure as exc:
            _append_error(outcome, exc.to_scrape_error())
        except Exception as exc:
            _append_error(
                outcome,
                ScrapeError(
                    code="PARSE_ERROR",
                    message=f"Could not parse discovered document ({type(exc).__name__})",
                    url=url,
                ),
            )

    def _extract_tor_url(self, element: Optional[Tag], page_url: str, item_url: str) -> Optional[str]:
        tor_selector = self.config.get("tor_selector")
        configured = _selected_link(element, tor_selector) if tor_selector else None
        if configured:
            return _safe_url(configured, page_url)
        if is_probable_document_url(item_url):
            return item_url
        if element:
            for anchor in element.find_all("a", href=True):
                label = self.clean_text(anchor.get_text(" ", strip=True))
                candidate = _safe_url(anchor.get("href"), page_url)
                if candidate and is_probable_document_url(candidate) and _TOR_LABEL_PATTERN.search(label):
                    return candidate
        return None

    def _raw_item(
        self,
        *,
        identity: str,
        title: str,
        description: Optional[str],
        source_url: str,
        tor_url: Optional[str],
        agency: Optional[str] = None,
        budget: Optional[float] = None,
        median_price: Optional[float] = None,
        procurement_method: Optional[str] = None,
        announcement_date: Optional[str] = None,
        submission_deadline: Optional[str] = None,
        provenance_format: str,
        source_record_id: Optional[str] = None,
        verification_status: str,
        verification_method: str,
    ) -> Dict[str, Any]:
        official = _as_bool(self.config.get("is_official_source"), default=False)
        payload = {
            "source_record_id": source_record_id,
            "title": self.clean_text(title),
            "agency": self.clean_text(agency or self.default_agency),
            "description": self.truncate_source_text(description),
            "budget": budget,
            "median_price": median_price,
            "procurement_method": self.clean_text(procurement_method) or None,
            "announcement_date": announcement_date,
            "submission_deadline": submission_deadline,
            "source_url": source_url,
            "tor_url": tor_url,
        }
        raw_payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        evidence_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
        verification_notes = (
            "Record URL fetched and cybersecurity-relevant content matched."
            if verification_status == "VERIFIED"
            else "Discovered in a source listing/feed; record URL has not yet been independently fetched."
        )
        item = {
            "tender_code": stable_tender_id(identity),
            "title": payload["title"][:500],
            "agency": payload["agency"][:255],
            "agency_type": self.config.get("agency_type") or None,
            "description": payload["description"],
            "budget": budget,
            "median_price": median_price,
            "procurement_method": payload["procurement_method"],
            "announcement_date": announcement_date,
            "submission_deadline": submission_deadline,
            "tor_url": tor_url,
            "source_name": self.source_name,
            "source_url": source_url,
            "source_record_id": source_record_id,
            "data_origin": "SCRAPED",
            "verification_status": verification_status,
            "verification_method": verification_method,
            "confidence_score": 0.9 if verification_status == "VERIFIED" else 0.6,
            "is_official_source": official,
            "evidence_hash": evidence_hash,
            "raw_payload_json": raw_payload_json,
        }
        item["provenance"] = {
            "source_name": self.source_name,
            "source_type": "OFFICIAL" if official else "WEB",
            "source_url": source_url,
            "document_url": tor_url,
            "source_record_id": source_record_id,
            "published_at": announcement_date,
            "content_sha256": evidence_hash,
            "raw_payload_json": raw_payload_json,
            "verification_status": verification_status,
            "verification_notes": f"{verification_notes} Parsed as {provenance_format}.",
            "is_primary": True,
        }
        return item

    def _matches_keywords(self, text: str) -> bool:
        if _as_bool(self.config.get("preview_mode"), default=False):
            return True
        normalized = self.clean_text(text).casefold()
        cyber_match = is_cyber_relevant(normalized) or any(
            pattern.search(normalized) for pattern in self._extra_keyword_patterns
        )
        require_procurement = _as_bool(
            self.config.get("require_procurement_context"), default=True
        )
        return cyber_match and (
            not require_procurement or is_procurement_relevant(normalized)
        )


def _extra_keywords(value: Any) -> List[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _compile_keyword_patterns(keywords: Sequence[str]) -> List[re.Pattern[str]]:
    patterns = []
    seen = set()
    for raw_keyword in keywords:
        keyword = BaseScraper.clean_text(raw_keyword).casefold()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        escaped = re.escape(keyword)
        if keyword.isascii() and len(keyword) <= 4 and re.fullmatch(r"[a-z0-9+#.\-]+", keyword):
            patterns.append(re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.I))
        else:
            patterns.append(re.compile(escaped, re.I))
    return patterns


def _classify_document(content: bytes, content_type: str) -> Tuple[str, BeautifulSoup]:
    stripped = content.lstrip()
    looks_xml = stripped.startswith(b"<?xml") or stripped[:100].lower().startswith(
        (b"<rss", b"<feed", b"<urlset", b"<sitemapindex", b"<rdf:rdf")
    )
    if content_type in _FEED_CONTENT_TYPES or content_type in _XML_CONTENT_TYPES or looks_xml:
        soup = BeautifulSoup(content, "xml")
        root = soup.find()
        root_name = _local_name(root.name) if root else ""
        if root_name in {"rss", "feed", "rdf"}:
            return "feed", soup
        if root_name in {"urlset", "sitemapindex"}:
            return "sitemap", soup
        return "xml", soup
    if content_type in _HTML_CONTENT_TYPES or b"<html" in stripped[:1000].lower():
        return "html", BeautifulSoup(content, "lxml")
    return "binary", BeautifulSoup("", "html.parser")


def _maybe_decompress(content: bytes) -> bytes:
    if content.startswith(b"\x1f\x8b"):
        try:
            return gzip.decompress(content)
        except (OSError, EOFError):
            return content
    return content


def _local_name(name: Any) -> str:
    return str(name or "").split(":")[-1].lower()


def _tag_text(tag: Optional[Tag]) -> str:
    return tag.get_text(" ", strip=True) if tag else ""


def _feed_link(entry: Tag) -> Optional[str]:
    links = entry.find_all("link")
    for link in links:
        rel = " ".join(link.get("rel") or []).lower()
        if link.get("href") and (not rel or "alternate" in rel):
            return str(link.get("href"))
    for link in links:
        if link.get("href"):
            return str(link.get("href"))
        text = _tag_text(link)
        if text:
            return text
    return None


def _selected_text(element: Optional[Tag], selector: Any) -> str:
    if element is None or not selector:
        return ""
    selected = element.select_one(str(selector))
    return BaseScraper.clean_text(selected.get_text(" ", strip=True)) if selected else ""


def _selected_link(element: Optional[Tag], selector: Any) -> Optional[str]:
    if element is None:
        return None
    selected = element.select_one(str(selector)) if selector else None
    if selected is not None:
        if selected.get("href"):
            return str(selected.get("href"))
        nested = selected.find("a", href=True)
        return str(nested.get("href")) if nested else None
    if element.name == "a" and element.get("href"):
        return str(element.get("href"))
    anchor = element.find("a", href=True)
    return str(anchor.get("href")) if anchor else None


def _safe_url(raw_url: Any, base_url: str) -> Optional[str]:
    if raw_url is None:
        return None
    try:
        return canonicalize_url(raw_url, base_url)
    except URLValidationError:
        return None


def _append_error(outcome: ScrapeOutcome, error: ScrapeError) -> None:
    # Keep scan logs bounded on a broken large sitemap.
    if len(outcome.errors) < 100:
        outcome.errors.append(error)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.strip().lower() in {"true", "1", "yes", "on"}:
            return True
        if value.strip().lower() in {"false", "0", "no", "off"}:
            return False
    return default

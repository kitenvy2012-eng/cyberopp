"""Official Thai government procurement adapter.

Every Thai public body — ministries, departments, state enterprises, public
organisations, universities, hospitals and local government — is required to
publish its procurement through e-GP, so this one adapter is the widest lawful
net available. It sweeps the first-party GovSpending service across many budget
years and a large cybersecurity keyword set, then optionally enriches each
project with its contract and winner from the same first-party service.

The adapter prefers the documented data.go.th service when an API key is
configured. Without a key it uses the public first-party GovSpending endpoints.
Both paths return source-backed records only: missing deadlines, TOR documents,
prices, and announcement dates remain missing.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlencode

import httpx

from backend.app.scrapers.base import (
    BaseScraper,
    ScrapeError,
    ScrapeResult,
    ScrapeStatus,
)


API_ROOT = "https://api-govspending.data.go.th/api/"
PUBLIC_SEARCH_ENDPOINT = f"{API_ROOT}get/egp/search"
PUBLIC_DETAIL_ENDPOINT = f"{API_ROOT}get/egp/project_detail"
PUBLIC_YEARS_ENDPOINT = f"{API_ROOT}get/egp/years"
DOCUMENTED_API_ENDPOINT = "https://opend.data.go.th/govspending/service/egp-contract"
PUBLIC_PROJECT_URL = "https://govspending.data.go.th/search"

# The search endpoint matches substrings, so a broad root term subsumes every
# narrower phrase built on it: "ความมั่นคงปลอดภัย" already returns every
# "ความมั่นคงปลอดภัยไซเบอร์ / สารสนเทศ / เครือข่าย" project. Querying broad roots
# and letting `_is_cyber_record` judge relevance covers strictly more ground than
# a long list of narrow phrases, using far fewer requests.
DEFAULT_KEYWORDS: Sequence[str] = (
    # --- Thai roots ---
    "ความมั่นคงปลอดภัย",
    "ไซเบอร์",
    "ภัยคุกคาม",
    "ช่องโหว่",
    "เจาะระบบ",
    "มัลแวร์",
    "แรนซัมแวร์",
    "ป้องกันไวรัส",
    "แอนตี้ไวรัส",
    "ไฟร์วอลล์",
    "พิสูจน์หลักฐานดิจิทัล",
    "คุ้มครองข้อมูลส่วนบุคคล",
    "ยืนยันตัวตน",
    "เข้ารหัส",
    "ตระหนักรู้",
    # --- English roots that appear inside Thai project titles ---
    "security",
    "cyber",
    "penetration",
    "vulnerability",
    "forensic",
    "firewall",
    "antivirus",
    "ransomware",
    "malware",
    "threat",
    "encryption",
    "authentication",
    "zero trust",
    "ISO 27001",
    "PCI DSS",
    "PDPA",
    # --- Product acronyms; `_is_cyber_record` re-checks these as whole tokens ---
    "SIEM",
    "SOAR",
    "MSSP",
    "MDR",
    "XDR",
    "NDR",
    "WAF",
    "EDR",
    "DLP",
    "NGFW",
    "CASB",
)


class EGPScraper(BaseScraper):
    """Fetch cybersecurity-related projects from official government data."""

    def __init__(
        self,
        source_name: str = "e-GP / GovSpending",
        url: str = "https://govspending.data.go.th/",
        config_json: Optional[str] = None,
        *,
        _client: Optional[httpx.AsyncClient] = None,
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
                    message=f"e-GP configuration is invalid: {exc}",
                )

        self.api_key = str(
            self.config.get("api_key") or os.getenv("DATA_GO_TH_API_KEY", "")
        ).strip()
        self.keywords = _configured_keywords(self.config.get("keywords")) or list(DEFAULT_KEYWORDS)
        # Explicit years win. Otherwise the adapter asks the service which
        # budget years exist and takes the most recent `years_back` of them.
        self.years = _configured_years(self.config.get("years"))
        self.all_years = _as_bool(self.config.get("all_years"), default=False)
        self.years_back = _bounded_int(self.config.get("years_back"), 5, 1, 30)
        self.limit = _bounded_int(self.config.get("limit"), 1000, 1, 1000)
        self.max_pages = _bounded_int(self.config.get("max_pages"), 3, 1, 50)
        self.max_concurrency = _bounded_int(self.config.get("max_concurrency"), 6, 1, 12)
        self.timeout_seconds = _bounded_float(
            self.config.get("timeout_seconds"), 30.0, 3.0, 180.0
        )
        self.enrich_details = _as_bool(self.config.get("enrich_details"), default=True)
        self.max_detail_requests = _bounded_int(
            self.config.get("max_detail_requests"), 120, 0, 5000
        )
        self._injected_client = _client

    async def scrape(self) -> ScrapeResult:
        outcome = self.new_outcome()
        if self._config_error:
            outcome.errors.append(self._config_error)

        owns_client = self._injected_client is None
        client = self._injected_client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=True,
            headers={
                "User-Agent": "CyberOppBot/1.0 (official public-procurement data client)",
                "Accept": "application/json",
                "Accept-Language": "th-TH,th;q=0.9,en;q=0.7",
            },
        )
        try:
            if self.api_key:
                items, errors, requests_made = await self._scrape_documented_api(client)
                # A configured key may expire or the versioned service may move.
                # Preserve that error and use the public first-party fallback.
                if errors and not items:
                    fallback_items, fallback_errors, fallback_requests = (
                        await self._scrape_public_api(client)
                    )
                    items.extend(fallback_items)
                    errors.extend(fallback_errors)
                    requests_made += fallback_requests
            else:
                items, errors, requests_made = await self._scrape_public_api(client)

            if items and self.enrich_details and self.max_detail_requests:
                enriched_requests, enrich_errors = await self._enrich_with_details(
                    client, items
                )
                requests_made += enriched_requests
                errors.extend(enrich_errors)
        finally:
            if owns_client:
                await client.aclose()

        outcome.items.extend(items)
        outcome.errors.extend(errors)
        outcome.pages_fetched = max(0, requests_made - len(errors))

        if requests_made and outcome.pages_fetched == 0:
            return self.finish_outcome(outcome, status=ScrapeStatus.FAILED)
        if outcome.errors:
            return self.finish_outcome(outcome, status=ScrapeStatus.PARTIAL)
        return self.finish_outcome(outcome, status=ScrapeStatus.SUCCESS)

    # ----------------------------- public API -----------------------------

    async def _resolve_years(
        self, client: httpx.AsyncClient
    ) -> Tuple[List[int], Optional[ScrapeError], int]:
        """Ask the service which budget years it holds, newest first."""
        if self.years:
            return list(self.years), None, 0
        try:
            response = await _request_with_retries(client, "GET", PUBLIC_YEARS_ENDPOINT)
            payload = response.json()
            rows = payload.get("data") if isinstance(payload, dict) else None
            years = sorted(
                {
                    year
                    for year in (_as_int(row.get("budget_year")) for row in rows or [] if isinstance(row, dict))
                    if year and 2500 <= year <= 2700
                },
                reverse=True,
            )
            if not years:
                raise ValueError("year list was empty")
            selected = years if self.all_years else years[: self.years_back]
            return selected, None, 1
        except (httpx.HTTPError, json.JSONDecodeError, ValueError, AttributeError) as exc:
            # Losing the year list must not disable the whole sweep. Fall back to
            # the Buddhist-era years derived from the clock.
            return (
                _default_budget_years(self.years_back),
                ScrapeError(
                    code="YEAR_LIST_UNAVAILABLE",
                    message=(
                        "Budget year list could not be read "
                        f"({type(exc).__name__}); used calendar-derived years instead"
                    ),
                    url=PUBLIC_YEARS_ENDPOINT,
                    retryable=isinstance(exc, httpx.HTTPError),
                ),
                1,
            )

    async def _scrape_public_api(
        self, client: httpx.AsyncClient
    ) -> Tuple[List[Dict[str, Any]], List[ScrapeError], int]:
        years, year_error, requests_made = await self._resolve_years(client)
        semaphore = asyncio.Semaphore(self.max_concurrency)
        tasks = [
            self._public_query_series(client, semaphore, year, keyword)
            for year in years
            for keyword in self.keywords
        ]
        responses = await asyncio.gather(*tasks)
        items: List[Dict[str, Any]] = []
        errors: List[ScrapeError] = [year_error] if year_error else []
        for series_items, series_errors, series_requests in responses:
            items.extend(series_items)
            errors.extend(series_errors)
            requests_made += series_requests
        return _deduplicate(items), _deduplicate_errors(errors), requests_made

    async def _public_query_series(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        year: int,
        keyword: str,
    ) -> Tuple[List[Dict[str, Any]], List[ScrapeError], int]:
        """Page one (year, keyword) query until the source stops filling a page.

        The endpoint returns a whole result set when `limit` is large enough, so
        additional requests are only made when a page comes back full.
        """
        items: List[Dict[str, Any]] = []
        errors: List[ScrapeError] = []
        requests_made = 0
        for page in range(self.max_pages):
            page_items, row_count, error = await self._public_query(
                client, semaphore, year, keyword, page
            )
            requests_made += 1
            if error:
                errors.append(error)
                break
            items.extend(page_items)
            if row_count < self.limit:
                break
        return items, errors, requests_made

    async def _public_query(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        year: int,
        keyword: str,
        page: int,
    ) -> Tuple[List[Dict[str, Any]], int, Optional[ScrapeError]]:
        data = {
            "year": str(year),
            "name": keyword,
            "offset": str(page * self.limit),
            "limit": str(self.limit),
            "sort": "DESC",
        }
        try:
            async with semaphore:
                response = await _request_with_retries(
                    client, "POST", PUBLIC_SEARCH_ENDPOINT, data=data
                )
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise ValueError("official endpoint returned an unsuccessful payload")
            rows = payload.get("data")
            if rows is None:
                rows = []
            if not isinstance(rows, list):
                raise ValueError("official endpoint returned no data list")
            items = [
                self._normalize_public_record(row, year)
                for row in rows
                if isinstance(row, dict) and _is_cyber_record(row)
            ]
            return [item for item in items if item], len(rows), None
        except httpx.HTTPStatusError as exc:
            return [], 0, ScrapeError(
                code="HTTP_ERROR",
                message=f"GovSpending request failed with HTTP {exc.response.status_code}",
                url=PUBLIC_SEARCH_ENDPOINT,
                retryable=exc.response.status_code in {408, 425, 429, 500, 502, 503, 504},
                http_status=exc.response.status_code,
            )
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            return [], 0, ScrapeError(
                code="OFFICIAL_API_ERROR",
                message=f"GovSpending response could not be used ({type(exc).__name__})",
                url=PUBLIC_SEARCH_ENDPOINT,
                retryable=isinstance(exc, httpx.HTTPError),
            )

    # --------------------------- detail enrichment ---------------------------

    async def _enrich_with_details(
        self, client: httpx.AsyncClient, items: List[Dict[str, Any]]
    ) -> Tuple[int, List[ScrapeError]]:
        """Attach contract, winner, and location from the project detail service.

        Enrichment is capped and best-effort: a project whose detail call fails
        keeps exactly the fields the search endpoint supplied.
        """
        ordered = sorted(
            items,
            key=lambda item: (item.get("announcement_date") or "", item.get("tender_code") or ""),
            reverse=True,
        )[: self.max_detail_requests]
        if not ordered:
            return 0, []

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def one(item: Dict[str, Any]) -> Optional[ScrapeError]:
            params = {
                "project_id": item["source_record_id"],
                "year": str(item.get("_budget_year") or ""),
            }
            try:
                async with semaphore:
                    response = await _request_with_retries(
                        client, "GET", PUBLIC_DETAIL_ENDPOINT, params=params
                    )
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("success") is not True:
                    raise ValueError("detail endpoint returned an unsuccessful payload")
                detail = payload.get("data")
                if not isinstance(detail, dict):
                    raise ValueError("detail endpoint returned no data object")
            except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
                return ScrapeError(
                    code="OFFICIAL_DETAIL_ERROR",
                    message=f"Project detail could not be used ({type(exc).__name__})",
                    url=PUBLIC_DETAIL_ENDPOINT,
                    retryable=isinstance(exc, httpx.HTTPError),
                )
            self._apply_detail(item, detail)
            return None

        results = await asyncio.gather(*[one(item) for item in ordered])
        errors = _deduplicate_errors([error for error in results if error])
        return len(ordered), errors

    def _apply_detail(self, item: Dict[str, Any], detail: Mapping[str, Any]) -> None:
        project = detail.get("project") if isinstance(detail.get("project"), dict) else {}
        contracts = detail.get("contract")
        contracts = contracts if isinstance(contracts, list) else []

        notes: List[str] = []
        province = self.clean_text(project.get("province"))
        if province and "จังหวัด" not in (item.get("description") or ""):
            notes.append(f"จังหวัด: {province}")

        awarded_to: List[str] = []
        for contract in contracts:
            if not isinstance(contract, dict):
                continue
            winner = contract.get("winner")
            winner_name = self.clean_text(winner.get("name")) if isinstance(winner, dict) else ""
            contract_no = self.clean_text(contract.get("contract_no_formatted") or contract.get("contract_no"))
            price = self.parse_price(contract.get("price_agree"))
            parts = [part for part in (winner_name, contract_no) if part]
            if price is not None:
                parts.append(f"{price:,.2f} บาท")
            if parts:
                awarded_to.append(" / ".join(parts))
        if awarded_to:
            notes.append("ผู้ได้รับการคัดเลือกตามข้อมูลสัญญา: " + "; ".join(awarded_to[:3]))
            # A signed contract with a named winner means this competition is
            # over. Recording it lets the dashboard stop offering the project as
            # something to bid on; `bidding.py` already reads AWARDED as closed.
            item["bid_notice_status"] = "AWARDED"

        if notes:
            existing = item.get("description")
            item["description"] = self.truncate_source_text(
                " | ".join(part for part in ([existing] if existing else []) + notes)
            )

        # The detail response is itself evidence. Store it beside the search row
        # so the hash covers everything the record actually claims.
        merged = {"search_row": json.loads(item["raw_payload_json"]), "project_detail": dict(detail)}
        raw_payload_json = json.dumps(
            merged, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
        evidence_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
        item["raw_payload_json"] = raw_payload_json
        item["evidence_hash"] = evidence_hash
        item["verification_method"] = "OFFICIAL_GOVSPENDING_API_WITH_DETAIL"
        provenance = item.get("provenance")
        if isinstance(provenance, dict):
            provenance["raw_payload_json"] = raw_payload_json
            provenance["content_sha256"] = evidence_hash
            provenance["verification_notes"] = (
                provenance.get("verification_notes", "")
                + " Project detail and contract records retrieved from the same first-party service."
            ).strip()

    # -------------------------- documented data.go.th --------------------------

    async def _scrape_documented_api(
        self, client: httpx.AsyncClient
    ) -> Tuple[List[Dict[str, Any]], List[ScrapeError], int]:
        years, year_error, requests_made = await self._resolve_years(client)
        semaphore = asyncio.Semaphore(self.max_concurrency)
        tasks = [
            self._documented_query(client, semaphore, year, keyword, page)
            for year in years
            for keyword in self.keywords
            for page in range(self.max_pages)
        ]
        responses = await asyncio.gather(*tasks)
        items: List[Dict[str, Any]] = []
        errors: List[ScrapeError] = [year_error] if year_error else []
        for page_items, error in responses:
            items.extend(page_items)
            if error:
                errors.append(error)
        return _deduplicate(items), _deduplicate_errors(errors), requests_made + len(tasks)

    async def _documented_query(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        year: int,
        keyword: str,
        page: int,
    ) -> Tuple[List[Dict[str, Any]], Optional[ScrapeError]]:
        params = {
            "year": str(year),
            "keyword": keyword,
            "offset": str(page * self.limit),
            "limit": str(self.limit),
        }
        try:
            async with semaphore:
                response = await _request_with_retries(
                    client,
                    "GET",
                    DOCUMENTED_API_ENDPOINT,
                    params=params,
                    headers={"api-key": self.api_key},
                )
            payload = response.json()
            rows = _extract_rows(payload)
            if rows is None:
                raise ValueError("documented endpoint returned no record list")
            items = [
                self._normalize_documented_record(row, year)
                for row in rows
                if isinstance(row, dict) and _is_cyber_record(row)
            ]
            return [item for item in items if item], None
        except httpx.HTTPStatusError as exc:
            return [], ScrapeError(
                code="DATA_GO_TH_HTTP_ERROR",
                message=f"data.go.th request failed with HTTP {exc.response.status_code}",
                url=DOCUMENTED_API_ENDPOINT,
                retryable=exc.response.status_code in {408, 425, 429, 500, 502, 503, 504},
                http_status=exc.response.status_code,
            )
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            return [], ScrapeError(
                code="DATA_GO_TH_API_ERROR",
                message=f"data.go.th response could not be used ({type(exc).__name__})",
                url=DOCUMENTED_API_ENDPOINT,
                retryable=isinstance(exc, httpx.HTTPError),
            )

    # ------------------------------ normalization ------------------------------

    def _normalize_public_record(
        self, record: Mapping[str, Any], requested_year: int
    ) -> Optional[Dict[str, Any]]:
        project_id = self.clean_text(record.get("project_id"))
        title = self.clean_text(record.get("project_name"))
        if not project_id or not title:
            return None

        budget_year = _as_int(record.get("budget_year")) or requested_year
        source_url = f"{PUBLIC_PROJECT_URL}?{urlencode({'project_id': project_id, 'year': budget_year})}"
        agency = _nested_name(record.get("dept")) or _nested_name(record.get("dept_sub"))
        agency = agency or "หน่วยงานภาครัฐ (ไม่ระบุชื่อในผล API)"
        method = _nested_name(record.get("purchase_method"))
        project_type = _nested_name(record.get("project_type"))
        source_status = _nested_name(record.get("project_status"))
        province = _nested_name(record.get("province"))
        announcement_date = self.parse_source_date(record.get("announce_date_en"))
        if not announcement_date:
            announcement_date = self.parse_source_date(record.get("announce_date"))

        description_parts = [
            f"ประเภทโครงการ: {project_type}" if project_type else None,
            f"สถานะจากต้นทาง: {source_status}" if source_status else None,
            f"จังหวัด: {province}" if province else None,
            (
                f"วันที่ทำรายการจากต้นทาง: {self.clean_text(record.get('transaction_date'))}"
                if self.clean_text(record.get("transaction_date")) not in {"", "-"}
                else None
            ),
        ]
        return self._build_item(
            record=record,
            project_id=project_id,
            title=title,
            agency=agency,
            budget_year=budget_year,
            source_url=source_url,
            description=" | ".join(part for part in description_parts if part) or None,
            budget=self.parse_price(record.get("project_money") or record.get("budget_price")),
            median_price=self.parse_price(record.get("price_build")),
            procurement_method=method,
            announcement_date=announcement_date,
            status=_map_project_status(source_status),
            verification_method="OFFICIAL_GOVSPENDING_API",
        )

    def _normalize_documented_record(
        self, record: Mapping[str, Any], requested_year: int
    ) -> Optional[Dict[str, Any]]:
        project_id = self.clean_text(
            record.get("project_id") or record.get("projectId") or record.get("project_no")
        )
        title = self.clean_text(
            record.get("project_name") or record.get("projectName") or record.get("name")
        )
        if not project_id or not title:
            return None
        budget_year = _as_int(record.get("budget_year") or record.get("year")) or requested_year
        source_url = f"{PUBLIC_PROJECT_URL}?{urlencode({'project_id': project_id, 'year': budget_year})}"
        agency = self.clean_text(
            record.get("dept_name")
            or record.get("department_name")
            or _nested_name(record.get("dept"))
            or record.get("agency")
        ) or "หน่วยงานภาครัฐ (ไม่ระบุชื่อในผล API)"
        source_status = self.clean_text(
            record.get("project_status_name")
            or record.get("status_name")
            or _nested_name(record.get("project_status"))
            or record.get("status")
        )
        method = self.clean_text(
            record.get("purchase_method_name")
            or _nested_name(record.get("purchase_method"))
            or record.get("method")
        ) or None
        announcement_date = self.parse_source_date(
            record.get("announce_date") or record.get("announcement_date")
        )
        return self._build_item(
            record=record,
            project_id=project_id,
            title=title,
            agency=agency,
            budget_year=budget_year,
            source_url=source_url,
            description=(f"สถานะจากต้นทาง: {source_status}" if source_status else None),
            budget=self.parse_price(
                record.get("project_money") or record.get("budget_price") or record.get("budget")
            ),
            median_price=self.parse_price(
                record.get("price_build") or record.get("median_price")
            ),
            procurement_method=method,
            announcement_date=announcement_date,
            status=_map_project_status(source_status),
            verification_method="DOCUMENTED_DATA_GO_TH_API",
        )

    def _build_item(
        self,
        *,
        record: Mapping[str, Any],
        project_id: str,
        title: str,
        agency: str,
        budget_year: int,
        source_url: str,
        description: Optional[str],
        budget: Optional[float],
        median_price: Optional[float],
        procurement_method: Optional[str],
        announcement_date: Optional[str],
        status: str,
        verification_method: str,
    ) -> Dict[str, Any]:
        raw_payload_json = json.dumps(
            dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
        evidence_hash = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
        now = datetime.utcnow()
        return {
            "tender_code": f"EGP-{project_id}",
            "title": title[:500],
            "agency": agency[:255],
            "agency_type": None,
            "description": self.truncate_source_text(description),
            "budget": budget,
            "median_price": median_price,
            "procurement_method": procurement_method,
            "announcement_date": announcement_date,
            # This project/contract feed does not expose a bid submission
            # deadline or TOR document.
            "submission_deadline": None,
            "tor_url": None,
            "source_name": self.source_name,
            "source_url": source_url,
            "source_record_id": project_id,
            "status": status,
            "data_origin": "SCRAPED",
            "verification_status": "VERIFIED",
            "verification_method": verification_method,
            "confidence_score": 1.0,
            "is_official_source": True,
            "evidence_hash": evidence_hash,
            "raw_payload_json": raw_payload_json,
            "last_verified_at": now,
            # Carried for the detail lookup; the manager ignores unknown keys.
            "_budget_year": budget_year,
            "provenance": {
                "source_name": self.source_name,
                "source_type": "OFFICIAL",
                "source_url": source_url,
                "document_url": None,
                "source_record_id": project_id,
                "published_at": announcement_date,
                "http_status": 200,
                "content_sha256": evidence_hash,
                "raw_payload_json": raw_payload_json,
                "verification_status": "VERIFIED",
                "verification_notes": (
                    f"Record returned by a first-party Thai government procurement API; "
                    f"budget year {budget_year}. Missing fields were not inferred."
                ),
                "is_primary": True,
            },
        }


async def _request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    last_error: Optional[Exception] = None
    for attempt in range(3):
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code not in {408, 425, 429, 500, 502, 503, 504}:
                raise
        except httpx.HTTPError as exc:
            last_error = exc
        if attempt < 2:
            await asyncio.sleep(0.5 * (2**attempt))
    assert last_error is not None
    raise last_error


def _default_budget_years(count: int = 2) -> List[int]:
    current_be = datetime.now().year + 543
    return [current_be - offset for offset in range(max(1, count))]


def _configured_keywords(value: Any) -> List[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        return []
    cleaned = [BaseScraper.clean_text(item) for item in values]
    return list(dict.fromkeys(item for item in cleaned if item))


def _configured_years(value: Any) -> List[int]:
    if isinstance(value, str):
        values: Iterable[Any] = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        return []
    years = []
    for item in values:
        try:
            year = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if 2500 <= year <= 2700 and year not in years:
            years.append(year)
    return years


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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


def _nested_name(value: Any) -> str:
    if isinstance(value, dict):
        return BaseScraper.clean_text(
            value.get("name") or value.get("name_th") or value.get("name_en")
        )
    return BaseScraper.clean_text(value)


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _map_project_status(value: Any) -> str:
    text = BaseScraper.clean_text(value).casefold()
    if not text:
        return "UNKNOWN"
    if any(term in text for term in ("ระหว่างดำเนินการ", "in progress", "อยู่ระหว่าง")):
        return "IN_PROGRESS"
    if any(term in text for term in ("เสร็จสิ้น", "complete", "completed", "สิ้นสุด", "ยกเลิก", "cancel")):
        return "CLOSED"
    if any(term in text for term in ("เปิดรับ", "open", "ประกาศเชิญชวน")):
        return "OPEN"
    return "UNKNOWN"


def _extract_rows(payload: Any) -> Optional[List[Mapping[str, Any]]]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in ("data", "result", "records", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_rows(value)
            if nested is not None:
                return nested
    return None


_STRONG_CYBER_TERMS = (
    "ความมั่นคงปลอดภัยไซเบอร์",
    "ความมั่นคงปลอดภัยสารสนเทศ",
    "ความมั่นคงปลอดภัยระบบสารสนเทศ",
    "ความมั่นคงปลอดภัยทางไซเบอร์",
    "ความมั่นคงปลอดภัยด้านเทคโนโลยีสารสนเทศ",
    "ความมั่นคงปลอดภัยเครือข่าย",
    "รักษาความปลอดภัยไซเบอร์",
    "ภัยคุกคามทางไซเบอร์",
    "ภัยคุกคามไซเบอร์",
    "ทดสอบเจาะระบบ",
    "ทดสอบการเจาะระบบ",
    "ตรวจสอบช่องโหว่",
    "ประเมินช่องโหว่",
    "สแกนช่องโหว่",
    "หาช่องโหว่",
    "ตรวจจับภัยคุกคาม",
    "เฝ้าระวังภัยคุกคาม",
    "ป้องกันภัยคุกคาม",
    "เผชิญเหตุภัยคุกคาม",
    "ป้องกันมัลแวร์",
    "ป้องกันแรนซัมแวร์",
    "โปรแกรมป้องกันไวรัส",
    "ระบบป้องกันไวรัส",
    "ซอฟต์แวร์ป้องกันไวรัส",
    "ป้องกันไวรัสคอมพิวเตอร์",
    "ป้องกันไวรัสสำหรับเครื่องคอมพิวเตอร์",
    "พิสูจน์หลักฐานดิจิทัล",
    "คุ้มครองข้อมูลส่วนบุคคล",
    "ไฟร์วอลล์",
    "cybersecurity",
    "cyber security",
    "penetration test",
    "vulnerability assessment",
    "security operations center",
    "network security",
    "endpoint security",
    "information security",
    "threat intelligence",
    "digital forensic",
    "incident response",
    "security awareness",
    "zero trust",
    "data loss prevention",
    "identity and access management",
    "privileged access management",
    "multi-factor authentication",
    "multifactor authentication",
    "two-factor authentication",
    "ยืนยันตัวตนแบบหลายปัจจัย",
    "ยืนยันตัวตนหลายชั้น",
    "ยืนยันตัวตนหลายปัจจัย",
    "พิสูจน์และยืนยันตัวตนทางดิจิทัล",
    "digital id",
    "web application firewall",
    "iso 27001",
    "iso/iec 27001",
    "pci dss",
    "firewall",
    "แอนตี้ไวรัส",
    "antivirus",
    "ransomware",
    "malware",
)

# Acronyms are only accepted as standalone tokens, so "ZOLEDRONIC" (which
# contains "edr") or "WAFER" cannot pull an unrelated project into the results.
_CYBER_ACRONYM_PATTERN = re.compile(
    r"(?<![a-z0-9])(siem|soar|mssp|mdr|xdr|waf|edr|dlp|ngfw|ndr|casb|mfa)(?![a-z0-9])"
)

# Many genuine notices phrase the subject generically — "ระบบวิเคราะห์ภัยคุกคาม",
# "ความมั่นคงปลอดภัยด้านดิจิทัล" — and name no listed product. Those are accepted
# when a security cue and a digital/IT cue appear together, which is what makes
# them procurement of information security rather than physical safety.
_SECURITY_CUES = (
    "ความมั่นคงปลอดภัย",
    "ภัยคุกคาม",
    "ช่องโหว่",
    "เจาะระบบ",
    "security",
)
_DIGITAL_CUES = (
    "ไซเบอร์",
    "สารสนเทศ",
    "ดิจิทัล",
    "เครือข่าย",
    "คอมพิวเตอร์",
    "ซอฟต์แวร์",
    "โปรแกรม",
    "คลาวด์",
    "เซิร์ฟเวอร์",
    "ข้อมูล",
    "cyber",
    "information",
    "digital",
    "network",
    "computer",
    "software",
    "cloud",
    "server",
    "endpoint",
    "application",
)
# Domains where the same words mean something else entirely: medicine, roads,
# fuel, buildings, and physical guarding. A title carrying any of these is never
# admitted by the contextual rule (an explicit strong term still wins).
_NON_CYBER_CONTEXT = (
    "covid",
    "โควิด",
    "โคโรนา",
    "โคโรน่า",
    "หน้ากากอนามัย",
    "เจลแอลกอฮอล์",
    "แอลกอฮอล์",
    "เจลล้างมือ",
    "ไวรัสตับ",
    "ต้านไวรัส",
    "วัคซีน",
    "เวชภัณฑ์",
    "สัญญาณชีพ",
    "โลหิต",
    "ผู้โดยสาร",
    "ถนน",
    "ชีวิตและทรัพย์สิน",
    "เชื้อเพลิง",
    "หล่อลื่น",
    "ก่อสร้าง",
    "สิ่งปลูกสร้าง",
    "รักษาความปลอดภัยอาคาร",
    "พนักงานรักษาความปลอดภัย",
    "เวรยาม",
    "ดับเพลิง",
    "อากาศยานไร้คนขับ",
    "โดรน",
    # Goods bought *for* a cyber project (catering, projectors) are not a
    # cybersecurity contract, and the source puts the project name in the title.
    "อาหารกลางวัน",
    "อาหารว่าง",
    "เครื่องดื่ม",
    "โปรเจคเตอร์",
    "โปรเจ็คเตอร์",
    # "DLP" is also Digital Light Processing, the projector technology.
    "projector",
    "เครื่องฉาย",
    "รถตู้",
    "ยาต้าน",
    "น้ำยาตรวจ",
)


def _is_cyber_record(record: Mapping[str, Any]) -> bool:
    title = BaseScraper.clean_text(
        record.get("project_name")
        or record.get("projectName")
        or record.get("name")
        or record.get("title")
    ).casefold()
    if not title:
        return False
    # Checked first: these words place a notice in medicine, public health,
    # construction, or physical guarding, where the same vocabulary means
    # something else entirely.
    if any(term in title for term in _NON_CYBER_CONTEXT):
        return False
    if any(term in title for term in _STRONG_CYBER_TERMS):
        return True
    if _CYBER_ACRONYM_PATTERN.search(title):
        return True
    return any(cue in title for cue in _SECURITY_CUES) and any(
        cue in title for cue in _DIGITAL_CUES
    )


def _deduplicate(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[str, Dict[str, Any]] = {}
    for item in items:
        project_id = str(item.get("source_record_id") or item.get("tender_code") or "")
        if project_id and project_id not in unique:
            unique[project_id] = item
    return list(unique.values())


def _deduplicate_errors(errors: List[ScrapeError]) -> List[ScrapeError]:
    unique: Dict[tuple[Any, ...], ScrapeError] = {}
    for error in errors:
        key = (error.code, error.http_status, error.url, error.message)
        unique.setdefault(key, error)
    return list(unique.values())

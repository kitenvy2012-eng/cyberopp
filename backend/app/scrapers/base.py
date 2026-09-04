"""Shared contracts and conservative normalization for live scrapers.

Scrapers intentionally keep their return value list-compatible because the existing
scan manager iterates over it. The same value also exposes a structured ``outcome``
so callers can distinguish "no matching tenders" from a failed crawl.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "mc_cid",
    "mc_eid",
    "ref_src",
}
_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}
_BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".test")
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_THAI_MONTHS = {
    "ม.ค.": 1,
    "มค": 1,
    "มกราคม": 1,
    "ก.พ.": 2,
    "กพ": 2,
    "กุมภาพันธ์": 2,
    "มี.ค.": 3,
    "มีค": 3,
    "มีนาคม": 3,
    "เม.ย.": 4,
    "เมย": 4,
    "เมษายน": 4,
    "พ.ค.": 5,
    "พค": 5,
    "พฤษภาคม": 5,
    "มิ.ย.": 6,
    "มิย": 6,
    "มิถุนายน": 6,
    "ก.ค.": 7,
    "กค": 7,
    "กรกฎาคม": 7,
    "ส.ค.": 8,
    "สค": 8,
    "สิงหาคม": 8,
    "ก.ย.": 9,
    "กย": 9,
    "กันยายน": 9,
    "ต.ค.": 10,
    "ตค": 10,
    "ตุลาคม": 10,
    "พ.ย.": 11,
    "พย": 11,
    "พฤศจิกายน": 11,
    "ธ.ค.": 12,
    "ธค": 12,
    "ธันวาคม": 12,
}
_ENGLISH_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


class ScrapeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class ScrapeError:
    """A machine-readable, safe-to-log crawl error."""

    code: str
    message: str
    url: Optional[str] = None
    retryable: bool = False
    http_status: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "url": self.url,
            "retryable": self.retryable,
            "http_status": self.http_status,
        }


@dataclass
class ScrapeOutcome:
    source_name: str
    source_url: str
    status: ScrapeStatus = ScrapeStatus.SUCCESS
    items: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[ScrapeError] = field(default_factory=list)
    pages_fetched: int = 0
    pages_skipped: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_url": self.source_url,
            "status": self.status.value,
            "items": self.items,
            "errors": [error.to_dict() for error in self.errors],
            "pages_fetched": self.pages_fetched,
            "pages_skipped": self.pages_skipped,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ScrapeResult(list):
    """List-compatible result with structured crawl metadata."""

    def __init__(self, outcome: ScrapeOutcome):
        super().__init__(outcome.items)
        self.outcome = outcome

    @property
    def status(self) -> ScrapeStatus:
        return self.outcome.status

    @property
    def errors(self) -> List[ScrapeError]:
        return self.outcome.errors


class URLValidationError(ValueError):
    pass


class BaseScraper(ABC):
    def __init__(self, source_name: str, url: str):
        self.source_name = self.clean_text(source_name)
        self.url = self.clean_text(url)
        self.last_outcome: Optional[ScrapeOutcome] = None

    @abstractmethod
    async def scrape(self) -> ScrapeResult:
        """Fetch live source data and return a list-compatible structured result."""
        raise NotImplementedError

    def new_outcome(self) -> ScrapeOutcome:
        return ScrapeOutcome(source_name=self.source_name, source_url=redact_url(self.url))

    def finish_outcome(
        self,
        outcome: ScrapeOutcome,
        *,
        status: Optional[ScrapeStatus] = None,
    ) -> ScrapeResult:
        # Defend against feed/sitemap overlap and repeated DOM selectors.
        unique: Dict[str, Dict[str, Any]] = {}
        for item in outcome.items:
            identity = str(item.get("tender_code") or "")
            if identity and identity not in unique:
                unique[identity] = item
        outcome.items = list(unique.values())

        if status is not None:
            outcome.status = status
        elif outcome.errors and outcome.pages_fetched:
            outcome.status = ScrapeStatus.PARTIAL
        elif outcome.errors:
            outcome.status = ScrapeStatus.FAILED
        else:
            outcome.status = ScrapeStatus.SUCCESS
        outcome.completed_at = datetime.now(timezone.utc)
        self.last_outcome = outcome
        return ScrapeResult(outcome)

    @staticmethod
    def clean_text(text: Any) -> str:
        if text is None:
            return ""
        return re.sub(r"\s+", " ", str(text)).strip()

    @staticmethod
    def truncate_source_text(text: Any, max_length: int = 4000) -> Optional[str]:
        cleaned = BaseScraper.clean_text(text)
        if not cleaned:
            return None
        return cleaned[:max_length]

    @staticmethod
    def parse_price(price_value: Any) -> Optional[float]:
        """Parse an explicitly supplied amount; unavailable values stay ``None``."""
        if price_value is None or isinstance(price_value, bool):
            return None
        if isinstance(price_value, (int, float)):
            return float(price_value)
        text = BaseScraper.clean_text(price_value).translate(_THAI_DIGITS)
        if not text or text in {"-", "n/a", "N/A", "null", "None"}:
            return None
        match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0).replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def parse_source_date(value: Any) -> Optional[str]:
        """Normalize only a date that the source actually supplied.

        Supports ISO/RFC dates, numeric Thai dates, and Thai month names. It
        deliberately has no "today" fallback.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()

        text = BaseScraper.clean_text(value).translate(_THAI_DIGITS)
        if not text or text in {"-", "n/a", "N/A", "null", "None"}:
            return None

        iso_match = re.search(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", text)
        if iso_match:
            return _validated_iso_date(*map(int, iso_match.groups()))

        numeric_match = re.search(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})(?!\d)", text)
        if numeric_match:
            day, month, year = map(int, numeric_match.groups())
            return _validated_iso_date(_gregorian_year(year), month, day)

        month_pattern = "|".join(sorted((re.escape(key) for key in _THAI_MONTHS), key=len, reverse=True))
        thai_match = re.search(rf"(?<!\d)(\d{{1,2}})\s*({month_pattern})\s*(\d{{2,4}})(?!\d)", text)
        if thai_match:
            day = int(thai_match.group(1))
            month = _THAI_MONTHS[thai_match.group(2)]
            year = _gregorian_year(int(thai_match.group(3)))
            return _validated_iso_date(year, month, day)

        english_month_pattern = "|".join(
            sorted((re.escape(key) for key in _ENGLISH_MONTHS), key=len, reverse=True)
        )
        english_match = re.search(
            rf"(?<!\d)(\d{{1,2}})\s+({english_month_pattern})\s+(\d{{2,4}})(?!\d)",
            text,
            re.I,
        )
        if english_match:
            day = int(english_match.group(1))
            month = _ENGLISH_MONTHS[english_match.group(2).lower()]
            raw_year = int(english_match.group(3))
            # Thai agency pages sometimes render a two-digit Buddhist year
            # beside an English month ("8 Jul 69" = 8 July 2026). RFC-style
            # years below 60 retain their normal 2000-based interpretation.
            year = raw_year + 1957 if 60 <= raw_year <= 99 else raw_year
            if 0 <= raw_year <= 59:
                year = raw_year + 2000
            return _validated_iso_date(year, month, day)

        try:
            parsed = parsedate_to_datetime(text)
            if parsed:
                return parsed.date().isoformat()
        except (TypeError, ValueError, OverflowError):
            return None
        return None


def _gregorian_year(year: int) -> int:
    if year >= 2400:
        return year - 543
    # Thai government feeds commonly abbreviate Buddhist years ("67" = 2567).
    if 0 <= year <= 99:
        return year + 1957
    return year


def _validated_iso_date(year: int, month: int, day: int) -> Optional[str]:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def canonicalize_url(url: Any, base_url: Optional[str] = None) -> str:
    """Resolve and canonicalize an HTTP(S) URL for validation and deduplication."""
    raw = BaseScraper.clean_text(url)
    if base_url:
        raw = urljoin(base_url, raw)
    if not raw:
        raise URLValidationError("URL is empty")

    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise URLValidationError("URL contains an invalid port or host") from exc
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise URLValidationError("Only http and https URLs are allowed")
    if not parts.hostname:
        raise URLValidationError("URL has no hostname")
    if parts.username is not None or parts.password is not None:
        raise URLValidationError("Credentials embedded in URLs are not allowed")

    try:
        hostname = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise URLValidationError("URL hostname is invalid") from exc
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(_BLOCKED_HOST_SUFFIXES):
        raise URLValidationError("Local and internal hostnames are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise URLValidationError("Non-public IP addresses are not allowed")

    host_display = f"[{hostname}]" if ":" in hostname else hostname
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host_display if port is None or default_port else f"{host_display}:{port}"
    path = parts.path or "/"

    query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key.startswith("utm_") or lower_key in _TRACKING_QUERY_KEYS:
            continue
        query_pairs.append((key, value))
    query_pairs.sort(key=lambda pair: (pair[0], pair[1]))
    return urlunsplit((scheme, netloc, path, urlencode(query_pairs, doseq=True), ""))


def redact_url(url: Any, sensitive_keys: Iterable[str] = ("api-key", "api_key", "token", "key")) -> str:
    """Remove credentials and common secret query values before logging."""
    raw = BaseScraper.clean_text(url)
    if not raw:
        return raw
    try:
        parts = urlsplit(raw)
        sensitive = {key.lower() for key in sensitive_keys}
        pairs = [
            (key, "[REDACTED]" if key.lower() in sensitive else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        hostname = parts.hostname or ""
        host_display = f"[{hostname}]" if ":" in hostname else hostname
        port = parts.port
        netloc = host_display if port is None else f"{host_display}:{port}"
        return urlunsplit((parts.scheme, netloc, parts.path, urlencode(pairs), ""))
    except (TypeError, ValueError):
        return "[invalid URL]"


def stable_tender_id(identity: str) -> str:
    """Create a deterministic full SHA-256 identifier (71 chars)."""
    normalized = BaseScraper.clean_text(identity)
    if not normalized:
        raise ValueError("A non-empty source identity is required")
    return f"SHA256-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def is_probable_document_url(url: str) -> bool:
    try:
        path = urlsplit(url).path.lower()
    except ValueError:
        return False
    extensions = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt")
    return path.endswith(extensions) or any(f"{extension}." in path for extension in extensions)

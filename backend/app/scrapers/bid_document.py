"""Conservative extraction of explicit bid windows from official evidence.

The discovery crawlers intentionally leave submission deadlines empty.  This
module is the narrower trust boundary used when an official detail page or bid
document has been fetched: it accepts a window only when a single clause names
the bid submission/price action, a calendar date, and both start and end times.

It never turns publication ranges, public-comment periods, presentation times,
question deadlines, delivery dates, or price-validity periods into bid dates.
Draft, award, and cancellation notices are classified before any dates are
considered and therefore always return a null window.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional, Set, Tuple
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from backend.app.scrapers.base import BaseScraper, URLValidationError, canonicalize_url


BANGKOK = ZoneInfo("Asia/Bangkok")
MAX_CONTENT_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 4
MAX_EXTRACTED_CHARS = 60_000
MAX_OCR_PAGES = 2

# Exact hosts only.  Callers may replace this set with the exact host(s) from a
# curated source configuration; suffix matching is deliberately not supported.
DEFAULT_ALLOWED_HOSTS = frozenset(
    {
        "dga.or.th",
        "www.dga.or.th",
        "etda.or.th",
        "www.etda.or.th",
        "bot.or.th",
        "www.bot.or.th",
        "oncb.go.th",
        "www.oncb.go.th",
    }
)

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_PRIVATE_USE = re.compile(r"[\ue000-\uf8ff]")
_SPACE = re.compile(r"\s+")

_THAI_MONTHS = {
    "มกราคม": 1,
    "ม.ค.": 1,
    "มค": 1,
    "กุมภาพันธ์": 2,
    "ก.พ.": 2,
    "กพ": 2,
    "มีนาคม": 3,
    "มี.ค.": 3,
    "มีค": 3,
    "เมษายน": 4,
    "เม.ย.": 4,
    "เมย": 4,
    "พฤษภาคม": 5,
    "พ.ค.": 5,
    "พค": 5,
    "มิถุนายน": 6,
    "มิ.ย.": 6,
    "มิย": 6,
    "กรกฎาคม": 7,
    "ก.ค.": 7,
    "กค": 7,
    "สิงหาคม": 8,
    "ส.ค.": 8,
    "สค": 8,
    "กันยายน": 9,
    "ก.ย.": 9,
    "กย": 9,
    "ตุลาคม": 10,
    "ต.ค.": 10,
    "ตค": 10,
    "พฤศจิกายน": 11,
    "พ.ย.": 11,
    "พย": 11,
    "ธันวาคม": 12,
    "ธ.ค.": 12,
    "ธค": 12,
}
_MONTH_PATTERN = "|".join(
    sorted((re.escape(month) for month in _THAI_MONTHS), key=len, reverse=True)
)
_DATE_PATTERN = rf"(?:\d{{1,2}}\s*(?:{_MONTH_PATTERN})\s*(?:พ\.?\s*ศ\.?\s*)?\d{{2,4}}|\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{2,4}})"


def _time_pattern(prefix: str) -> str:
    return rf"(?P<{prefix}_hour>\d{{1,2}})\s*[:.]\s*(?P<{prefix}_minute>\d{{2}})"

# A match must begin with an actual submission/price action.  In particular,
# "นำเสนอ Presentation" and "กำหนดยืนราคา" do not satisfy this anchor.
_BID_WINDOW_PATTERN = re.compile(
    rf"(?P<clause>"
    # Do not start inside the bidder noun "ผู้ยื่นข้อเสนอ" or inside
    # "ข้อเสนอราคา".  A real action later in the sentence ("ต้องเสนอราคา" or
    # "ต้องยื่นข้อเสนอ") still matches independently.
    rf"(?:(?<!ผู้)ยื่น\s*ข้อเสนอ(?:\s*ราคา)?|(?<!ข้อ)เสนอ\s*ราคา(?:\s*ทาง\s*ระบบ)?)"
    rf".{{0,240}}?"
    rf"(?:ใน\s*)?วันที่\s*(?P<date>{_DATE_PATTERN})"
    rf".{{0,90}}?"
    rf"(?:ระหว่าง\s*|ตั้งแต่\s*)?เวลา\s*"
    + _time_pattern("start")
    + rf"\s*(?:น\.?|นาฬิกา)?\s*(?:ถึง|จนถึง|[-–—])\s*(?:เวลา\s*)?"
    + _time_pattern("end")
    + rf"\s*(?:น\.?|นาฬิกา)?)",
    re.IGNORECASE,
)

_DRAFT_PATTERN = re.compile(
    r"(?:ประชา(?:วิจารณ์|พิจารณ์)|รับฟังคำ(?:วิจารณ์|คิดเห็น)|ร่าง\s*(?:ประกาศ|เอกสาร|ขอบเขต)|\(\s*ร่าง\s*\)|\bdraft\b)",
    re.IGNORECASE,
)
_AWARD_PATTERN = re.compile(
    r"(?:ประกาศ(?:ผล)?\s*ผู้ชนะ(?:การเสนอราคา)?|ผลการคัดเลือกผู้ชนะ|\bnotice\s+of\s+award\b|\bawarded\b)",
    re.IGNORECASE,
)
_CANCEL_PATTERN = re.compile(
    r"(?:ประกาศ\s*ยกเลิก|ยกเลิก\s*(?:การประกวดราคา|ประกาศ|โครงการ)|\bcancell?ed\b|\bcancellation\b)",
    re.IGNORECASE,
)
_INVITATION_PATTERN = re.compile(
    r"(?:ประกาศ\s*(?:เชิญชวน|ประกวดราคา)|ประกวดราคา(?:อิเล็กทรอนิกส์)?|เอกสาร\s*ประกวดราคา|\be[- ]?bidding\b|\binvitation\s+to\s+bid\b)",
    re.IGNORECASE,
)

_PROJECT_CODE = re.compile(r"\b(?:DGA|ETDA)[-/]\d{2,4}[-/]\d{2,5}\b", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9._/+\-]{3,}|[ก-๙]{5,}", re.IGNORECASE)
_GENERIC_TOKENS = {
    "ประกาศ",
    "ประกาศประกวดราคา",
    "ประกวดราคา",
    "อิเล็กทรอนิกส์",
    "สำนักงาน",
    "โครงการ",
    "รายละเอียด",
    "จัดซื้อจัดจ้าง",
    "e-bidding",
    "bidding",
    "procurement",
}
_GENERIC_THAI_PREFIX = re.compile(
    r"^(?:ประกาศ)?(?:เชิญชวน|ประกวดราคา)(?:อิเล็กทรอนิกส์)?(?:จ้าง|ซื้อ|เช่า)?(?:งาน|ระบบ)?"
)


class BidNoticeStatus(str, Enum):
    INVITATION = "INVITATION"
    DRAFT = "DRAFT"
    AWARDED = "AWARDED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BidDocumentEnrichment:
    bid_start_date: Optional[str]
    bid_deadline_at: Optional[str]
    bid_evidence_url: Optional[str]
    bid_evidence_hash: Optional[str]
    bid_evidence_excerpt: Optional[str]
    bid_notice_status: BidNoticeStatus
    bidding_checked_at: datetime
    # Diagnostic only.  Integrations may log it but need not persist it.
    reason_code: str

    def to_dict(self) -> dict:
        result = asdict(self)
        result["bid_notice_status"] = self.bid_notice_status.value
        return result


def extract_bid_document_evidence(
    *,
    content: bytes,
    content_type: str,
    evidence_url: str,
    title: str = "",
    checked_at: Optional[datetime] = None,
    allowed_hosts: Optional[Set[str]] = None,
) -> BidDocumentEnrichment:
    """Extract an explicit bid window from one already-fetched official source.

    Fetching is intentionally outside this module so the caller retains the
    existing robots, redirect, DNS, response-size, and throttling controls.
    ``allowed_hosts`` replaces (rather than extends) the defaults and performs
    exact normalized hostname matching.
    """

    checked = _utc_naive(checked_at)
    empty = _empty_result(checked)

    try:
        canonical_url = canonicalize_url(evidence_url)
    except URLValidationError:
        return empty(reason_code="INVALID_EVIDENCE_URL")

    host = (urlsplit(canonical_url).hostname or "").rstrip(".").lower()
    try:
        trusted_hosts = _normalize_allowed_hosts(
            DEFAULT_ALLOWED_HOSTS if allowed_hosts is None else allowed_hosts
        )
    except ValueError:
        return empty(reason_code="INVALID_ALLOWED_HOSTS")
    if host not in trusted_hosts:
        return empty(reason_code="HOST_NOT_ALLOWED")

    if not isinstance(content, bytes) or not content:
        return empty(bid_evidence_url=canonical_url, reason_code="CONTENT_EMPTY")

    digest = hashlib.sha256(content).hexdigest()
    evidence_fields = {
        "bid_evidence_url": canonical_url,
        "bid_evidence_hash": digest,
    }
    if len(content) > MAX_CONTENT_BYTES:
        return empty(**evidence_fields, reason_code="CONTENT_TOO_LARGE")
    if not BaseScraper.clean_text(title):
        return empty(**evidence_fields, reason_code="MISSING_RECORD_TITLE")

    text, extraction_kind = _extract_text(content, content_type)
    if not text:
        return empty(**evidence_fields, reason_code="TEXT_UNAVAILABLE")
    if not _title_matches_document(title, text):
        return empty(**evidence_fields, reason_code="TITLE_DOCUMENT_MISMATCH")

    notice_status, status_excerpt = _classify_notice(title, canonical_url, text)
    if notice_status in {
        BidNoticeStatus.DRAFT,
        BidNoticeStatus.AWARDED,
        BidNoticeStatus.CANCELLED,
    }:
        return empty(
            **evidence_fields,
            bid_notice_status=notice_status,
            bid_evidence_excerpt=status_excerpt,
            reason_code=f"NOTICE_{notice_status.value}",
        )
    if notice_status is not BidNoticeStatus.INVITATION:
        return empty(
            **evidence_fields,
            bid_evidence_excerpt=status_excerpt,
            reason_code="NOTICE_NOT_INVITATION",
        )

    # OCR is useful for classification and triage, but it is not sufficiently
    # reliable for Thai dates/digits to establish an actionable deadline by
    # itself.  Store the official evidence and leave the window unconfirmed.
    if extraction_kind == "ocr":
        return empty(
            **evidence_fields,
            bid_notice_status=notice_status,
            bid_evidence_excerpt=status_excerpt,
            reason_code="OCR_ONLY_UNCONFIRMED",
        )

    windows = _extract_explicit_windows(text, checked)
    if not windows:
        return empty(
            **evidence_fields,
            bid_notice_status=notice_status,
            bid_evidence_excerpt=status_excerpt,
            reason_code="NO_EXPLICIT_BID_WINDOW",
        )

    unique = {(start, end): excerpt for start, end, excerpt in windows}
    if len(unique) != 1:
        excerpts = " | ".join(list(unique.values())[:2])
        return empty(
            **evidence_fields,
            bid_notice_status=notice_status,
            bid_evidence_excerpt=_truncate(excerpts),
            reason_code="AMBIGUOUS_BID_WINDOWS",
        )

    (start, end), excerpt = next(iter(unique.items()))
    return BidDocumentEnrichment(
        bid_start_date=start,
        bid_deadline_at=end,
        bid_evidence_url=canonical_url,
        bid_evidence_hash=digest,
        bid_evidence_excerpt=_truncate(excerpt),
        bid_notice_status=notice_status,
        bidding_checked_at=checked,
        reason_code="OK_EXPLICIT_BID_WINDOW",
    )


def _empty_result(checked: datetime):
    def build(
        *,
        bid_evidence_url: Optional[str] = None,
        bid_evidence_hash: Optional[str] = None,
        bid_evidence_excerpt: Optional[str] = None,
        bid_notice_status: BidNoticeStatus = BidNoticeStatus.UNKNOWN,
        reason_code: str,
    ) -> BidDocumentEnrichment:
        return BidDocumentEnrichment(
            bid_start_date=None,
            bid_deadline_at=None,
            bid_evidence_url=bid_evidence_url,
            bid_evidence_hash=bid_evidence_hash,
            bid_evidence_excerpt=bid_evidence_excerpt,
            bid_notice_status=bid_notice_status,
            bidding_checked_at=checked,
            reason_code=reason_code,
        )

    return build


def _utc_naive(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.utcnow()
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_allowed_hosts(hosts: Iterable[str]) -> frozenset[str]:
    normalized = set()
    for raw in hosts:
        host = str(raw).strip().rstrip(".").lower()
        if not host or ":" in host or "/" in host or "*" in host:
            raise ValueError("allowed_hosts entries must be exact hostnames")
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("invalid hostname") from exc
        normalized.add(host)
    if not normalized:
        raise ValueError("allowed_hosts cannot be empty")
    return frozenset(normalized)


def _extract_text(content: bytes, content_type: str) -> Tuple[str, str]:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type in {"text/html", "application/xhtml+xml"}:
        decoded = _decode_text(content)
        soup = BeautifulSoup(decoded, "html.parser")
        for unwanted in soup.select("script, style, noscript, nav, footer, header"):
            unwanted.decompose()
        preferred = soup.select_one(
            ".content-description, article, main, .entry-content, .post-content"
        )
        heading = soup.select_one("h1.content-title, article h1, main h1, h1")
        parts = []
        if heading:
            parts.append(heading.get_text(" ", strip=True))
        if preferred:
            parts.append(preferred.get_text(" ", strip=True))
        elif soup.body:
            parts.append(soup.body.get_text(" ", strip=True))
        return _normalize_text(" ".join(parts))[:MAX_EXTRACTED_CHARS], "html"

    if media_type in {"text/plain", "application/json", "application/xml", "text/xml"}:
        return _normalize_text(_decode_text(content))[:MAX_EXTRACTED_CHARS], "text"

    if media_type == "application/pdf" or content.startswith(b"%PDF-"):
        text = _extract_pdf_text(content)
        normalized = _normalize_text(text)[:MAX_EXTRACTED_CHARS]
        if _contains_bid_language(normalized):
            return normalized, "pdf_text"
        ocr_text = _ocr_pdf_first_pages(content)
        if ocr_text:
            return _normalize_text(ocr_text)[:MAX_EXTRACTED_CHARS], "ocr"
        return normalized, "pdf_text"

    return "", "unsupported"


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "tis-620", "cp874"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            return ""
        parts = []
        for page in reader.pages[:MAX_PDF_PAGES]:
            parts.append(page.extract_text() or "")
            if sum(len(part) for part in parts) >= MAX_EXTRACTED_CHARS:
                break
        return "\n".join(parts)
    except Exception:
        return ""


def _ocr_pdf_first_pages(content: bytes) -> str:
    """Best-effort bounded OCR used for classification, never for bid dates."""

    renderer = shutil.which("pdftoppm")
    tesseract = shutil.which("tesseract")
    if not renderer or not tesseract:
        return ""
    try:
        with tempfile.TemporaryDirectory(prefix="cyber-opp-bid-") as tmp:
            root = Path(tmp)
            pdf_path = root / "evidence.pdf"
            pdf_path.write_bytes(content)
            prefix = root / "page"
            rendered = subprocess.run(
                [
                    renderer,
                    "-f",
                    "1",
                    "-l",
                    str(MAX_OCR_PAGES),
                    "-scale-to",
                    "1800",
                    "-png",
                    "-q",
                    str(pdf_path),
                    str(prefix),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=25,
                check=False,
            )
            if rendered.returncode != 0:
                return ""
            parts = []
            for image_path in sorted(root.glob("page-*.png"))[:MAX_OCR_PAGES]:
                ocr = subprocess.run(
                    [tesseract, str(image_path), "stdout", "-l", "tha+eng", "--psm", "3"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=20,
                    check=False,
                )
                if ocr.returncode == 0:
                    parts.append(ocr.stdout.decode("utf-8", errors="replace"))
            return "\n".join(parts)
    except (OSError, subprocess.SubprocessError):
        return ""


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.translate(_THAI_DIGITS)
    # Some Thai PDFs map combining marks to a private-use font.  Removing those
    # glyphs makes surrounding anchor words searchable without inventing text.
    text = _PRIVATE_USE.sub("", text)
    return _SPACE.sub(" ", text).strip()


def _contains_bid_language(text: str) -> bool:
    return bool(
        re.search(r"(?:เสนอ\s*ราคา|ยื่น\s*ข้อเสนอ|ประกวด\s*ราคา|e[- ]?bidding)", text, re.I)
    )


def _title_matches_document(title: str, text: str) -> bool:
    title_norm = _normalize_text(title).casefold()
    text_norm = _normalize_text(text).casefold()
    if not title_norm or not text_norm:
        return False

    title_codes = {code.upper() for code in _PROJECT_CODE.findall(title_norm)}
    text_codes = {code.upper() for code in _PROJECT_CODE.findall(text_norm)}
    if title_codes and text_codes:
        return bool(title_codes & text_codes)

    title_tokens = _distinctive_title_tokens(title_norm)
    text_tokens = {token.casefold() for token in _TOKEN.findall(text_norm)}
    title_ascii = {
        token for token in title_tokens if re.fullmatch(r"[a-z0-9][a-z0-9._/+\-]{3,}", token)
    }
    if title_ascii and not (title_ascii & text_tokens):
        return False
    matches = title_tokens & text_tokens
    if len(matches) >= 2:
        return True
    if any(len(token) >= 14 for token in matches):
        return True

    # Thai headings sometimes wrap at different word boundaries.  Compare a
    # compact form only when it is long enough to be genuinely distinctive.
    compact_text = re.sub(r"[^a-z0-9ก-๙]", "", text_norm)
    for token in title_tokens:
        compact = re.sub(r"[^a-z0-9ก-๙]", "", token)
        if len(compact) >= 18 and compact in compact_text:
            return True
    return False


def _distinctive_title_tokens(title: str) -> set[str]:
    tokens = set()
    for raw in _TOKEN.findall(title):
        token = raw.casefold()
        if token in _GENERIC_TOKENS:
            continue
        if re.fullmatch(r"[ก-๙]{5,}", token):
            token = _GENERIC_THAI_PREFIX.sub("", token)
            if len(token) < 5:
                continue
        tokens.add(token)
    return tokens


def _classify_notice(
    title: str, evidence_url: str, text: str
) -> Tuple[BidNoticeStatus, Optional[str]]:
    decoded_path = unquote(urlsplit(evidence_url).path)
    title_scope = _normalize_text(f"{title} {decoded_path}")
    # Body classification is limited to the heading area so boilerplate such
    # as "if the bidder is the winner" cannot turn an invitation into an award.
    body_scope = text[:1800]

    for status, pattern in (
        (BidNoticeStatus.CANCELLED, _CANCEL_PATTERN),
        (BidNoticeStatus.AWARDED, _AWARD_PATTERN),
        (BidNoticeStatus.DRAFT, _DRAFT_PATTERN),
    ):
        match = pattern.search(title_scope) or pattern.search(body_scope)
        if match:
            return status, _excerpt_around(title_scope if pattern.search(title_scope) else body_scope, match)

    invitation = _INVITATION_PATTERN.search(title_scope) or _INVITATION_PATTERN.search(body_scope)
    if invitation:
        scope = title_scope if _INVITATION_PATTERN.search(title_scope) else body_scope
        return BidNoticeStatus.INVITATION, _excerpt_around(scope, invitation)
    return BidNoticeStatus.UNKNOWN, None


def _extract_explicit_windows(
    text: str, checked_at: datetime
) -> list[Tuple[str, str, str]]:
    windows = []
    for match in _BID_WINDOW_PATTERN.finditer(text):
        clause = match.group("clause")
        lowered = clause.casefold()
        if any(
            rejected in lowered
            for rejected in ("นำเสนอ presentation", "กำหนดยืนราคา", "ส่งมอบ", "สอบถาม")
        ):
            continue
        # The shared parser handles Thai month names, while procurement PDFs
        # commonly insert the explicit Buddhist-era marker between month/year.
        date_text = re.sub(r"พ\.?\s*ศ\.?", "", match.group("date"), flags=re.I)
        date_iso = BaseScraper.parse_source_date(date_text)
        if not date_iso:
            continue
        try:
            year, month, day = (int(part) for part in date_iso.split("-"))
            start_hour = int(match.group("start_hour"))
            start_minute = int(match.group("start_minute"))
            end_hour = int(match.group("end_hour"))
            end_minute = int(match.group("end_minute"))
            start = datetime(year, month, day, start_hour, start_minute, tzinfo=BANGKOK)
            end = datetime(year, month, day, end_hour, end_minute, tzinfo=BANGKOK)
        except (TypeError, ValueError):
            continue
        if end <= start or (end - start).total_seconds() > 24 * 60 * 60:
            continue

        # Avoid accepting obvious OCR/date corruption.  Procurement sources in
        # scope are current feeds; archival dates more than ten years behind or
        # more than three years ahead require independent handling.
        checked_year = checked_at.replace(tzinfo=timezone.utc).astimezone(BANGKOK).year
        if not checked_year - 10 <= year <= checked_year + 3:
            continue
        windows.append(
            (
                start.isoformat(timespec="seconds"),
                end.isoformat(timespec="seconds"),
                clause,
            )
        )
    return windows


def _excerpt_around(text: str, match: re.Match[str], radius: int = 180) -> str:
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return _truncate(text[start:end]) or ""


def _truncate(text: Optional[str], limit: int = 700) -> Optional[str]:
    cleaned = BaseScraper.clean_text(text)
    if not cleaned:
        return None
    return cleaned[:limit]

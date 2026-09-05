"""Time-sensitive bid eligibility, separate from a project's delivery status."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


BANGKOK = ZoneInfo("Asia/Bangkok")
BID_FRESHNESS_HOURS = 24
ACTIONABLE_STATES = frozenset({"OPEN_NOW", "UPCOMING"})
BID_FIELDS = (
    "bid_start_date", "bid_deadline_at", "bid_notice_status",
    "bid_evidence_url", "bid_evidence_hash", "bid_evidence_excerpt",
    "bidding_checked_at",
)


def _value(record: Any, name: str, default=None):
    return record.get(name, default) if isinstance(record, dict) else getattr(record, name, default)


def parse_bid_datetime(value: Any, *, utc_naive: bool = False) -> datetime | None:
    """A date without a time ends at its start, never at an invented 23:59."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc if utc_naive else BANGKOK)
    return parsed.astimezone(BANGKOK)


def bidding_state(record: Any, now: datetime | None = None) -> str:
    """Only independently evidenced invitation windows can be actionable."""
    current = parse_bid_datetime(now or datetime.now(BANGKOK))
    notice_status = str(_value(record, "bid_notice_status", "UNKNOWN") or "UNKNOWN").upper()
    if (
        _value(record, "is_demo", False)
        or _value(record, "is_quarantined", False)
        or _value(record, "verification_status") in {"REJECTED", "DEMO"}
        or notice_status in {"AWARDED", "CANCELLED"}
        or _value(record, "status") == "CLOSED"
    ):
        return "CLOSED"
    if notice_status != "INVITATION":
        return "UNCONFIRMED"

    start = parse_bid_datetime(_value(record, "bid_start_date"))
    deadline = parse_bid_datetime(_value(record, "bid_deadline_at"))
    if deadline is not None and current >= deadline:
        return "EXPIRED"
    if not start or not deadline or start >= deadline:
        return "UNCONFIRMED"
    if not (
        _value(record, "is_official_source", False)
        and _value(record, "bid_evidence_url")
        and _value(record, "bid_evidence_hash")
        and _value(record, "bid_evidence_excerpt")
    ):
        return "UNCONFIRMED"
    checked = parse_bid_datetime(_value(record, "bidding_checked_at"), utc_naive=True)
    if not checked:
        return "UNCONFIRMED"
    if checked > current + timedelta(minutes=5):
        return "UNCONFIRMED"
    if current - checked > timedelta(hours=BID_FRESHNESS_HOURS):
        return "STALE"
    return "UPCOMING" if current < start else "OPEN_NOW"


def is_actionable(record: Any, now: datetime | None = None) -> bool:
    return bidding_state(record, now) in ACTIONABLE_STATES

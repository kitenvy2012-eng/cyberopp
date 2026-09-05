import csv
import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.stats import router as stats_router
from backend.app.api.tenders import router as tenders_router
from backend.app.core.database import Base, get_db
from backend.app.models.models import Tender
from backend.app.services.bidding import (
    ACTIONABLE_STATES,
    BANGKOK,
    bidding_state,
    is_actionable,
    parse_bid_datetime,
)


class BiddingPolicyUnitTests(unittest.TestCase):
    NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=BANGKOK)

    def valid_record(self, **overrides):
        record = {
            "bid_start_date": "2026-09-05T09:00:00+07:00",
            "bid_deadline_at": "2026-09-05T17:00:00+07:00",
            "bid_notice_status": "INVITATION",
            "bid_evidence_url": "https://example.go.th/procurement/invitation.pdf",
            "bid_evidence_hash": "a" * 64,
            "bid_evidence_excerpt": "ยื่นข้อเสนอวันที่ 5 กันยายน เวลา 09.00-17.00 น.",
            "bidding_checked_at": self.NOW - timedelta(hours=1),
            "is_official_source": True,
            "is_demo": False,
            "is_quarantined": False,
            "verification_status": "VERIFIED",
            "status": "UNKNOWN",
        }
        record.update(overrides)
        return record

    def test_datetime_parsing_uses_asia_bangkok_consistently(self):
        self.assertEqual(
            datetime(2026, 9, 5, 12, 0, tzinfo=BANGKOK),
            parse_bid_datetime("2026-09-05T05:00:00Z"),
        )
        # A naive bid-window value is local Thailand time.
        self.assertEqual(
            datetime(2026, 9, 5, 12, 0, tzinfo=BANGKOK),
            parse_bid_datetime("2026-09-05T12:00:00"),
        )
        # A naive SQLAlchemy DateTime used for checked_at is stored as UTC.
        self.assertEqual(
            datetime(2026, 9, 5, 12, 0, tzinfo=BANGKOK),
            parse_bid_datetime(datetime(2026, 9, 5, 5, 0), utc_naive=True),
        )

    def test_upcoming_open_now_and_expired_boundaries(self):
        start = datetime(2026, 9, 5, 9, 0, tzinfo=BANGKOK)
        deadline = datetime(2026, 9, 5, 17, 0, tzinfo=BANGKOK)
        record = self.valid_record(bidding_checked_at=start - timedelta(minutes=1))

        self.assertEqual("UPCOMING", bidding_state(record, start - timedelta(microseconds=1)))
        self.assertEqual("OPEN_NOW", bidding_state(record, start))
        self.assertEqual("OPEN_NOW", bidding_state(record, deadline - timedelta(microseconds=1)))
        self.assertEqual("EXPIRED", bidding_state(record, deadline))

    def test_date_only_deadline_expires_at_start_of_that_day(self):
        record = self.valid_record(
            bid_start_date="2026-09-04",
            bid_deadline_at="2026-09-05",
            bidding_checked_at=datetime(2026, 9, 4, 23, 0, tzinfo=BANGKOK),
        )

        self.assertEqual(
            "OPEN_NOW",
            bidding_state(
                record,
                datetime(2026, 9, 4, 23, 59, 59, 999999, tzinfo=BANGKOK),
            ),
        )
        # No 23:59 cutoff is invented when the official source only gives a date.
        self.assertEqual(
            "EXPIRED",
            bidding_state(record, datetime(2026, 9, 5, 0, 0, tzinfo=BANGKOK)),
        )

    def test_evidence_is_fresh_through_24_hours_then_becomes_stale(self):
        exactly_fresh = self.valid_record(
            bid_start_date="2026-09-01T00:00:00+07:00",
            bid_deadline_at="2026-09-10T00:00:00+07:00",
            bidding_checked_at=self.NOW - timedelta(hours=24),
        )
        just_stale = self.valid_record(
            bid_start_date="2026-09-01T00:00:00+07:00",
            bid_deadline_at="2026-09-10T00:00:00+07:00",
            bidding_checked_at=self.NOW - timedelta(hours=24, microseconds=1),
        )

        self.assertEqual("OPEN_NOW", bidding_state(exactly_fresh, self.NOW))
        self.assertEqual("STALE", bidding_state(just_stale, self.NOW))
        self.assertTrue(is_actionable(exactly_fresh, self.NOW))
        self.assertFalse(is_actionable(just_stale, self.NOW))

    def test_non_invitation_and_terminal_records_are_never_actionable(self):
        cases = {
            "unknown notice": ({"bid_notice_status": "UNKNOWN"}, "UNCONFIRMED"),
            "draft notice": ({"bid_notice_status": "DRAFT"}, "UNCONFIRMED"),
            "awarded notice": ({"bid_notice_status": "AWARDED"}, "CLOSED"),
            "cancelled notice": ({"bid_notice_status": "CANCELLED"}, "CLOSED"),
            "closed project": ({"status": "CLOSED"}, "CLOSED"),
            "demo record": ({"is_demo": True}, "CLOSED"),
            "quarantined record": ({"is_quarantined": True}, "CLOSED"),
            "demo verification": ({"verification_status": "DEMO"}, "CLOSED"),
            "rejected verification": ({"verification_status": "REJECTED"}, "CLOSED"),
        }

        for label, (overrides, expected_state) in cases.items():
            with self.subTest(label=label):
                record = self.valid_record(**overrides)
                self.assertEqual(expected_state, bidding_state(record, self.NOW))
                self.assertFalse(is_actionable(record, self.NOW))

    def test_every_evidence_field_and_valid_window_are_required(self):
        missing_cases = (
            "bid_start_date",
            "bid_deadline_at",
            "bid_evidence_url",
            "bid_evidence_hash",
            "bid_evidence_excerpt",
            "bidding_checked_at",
        )
        for field in missing_cases:
            with self.subTest(field=field):
                record = self.valid_record(**{field: None})
                self.assertEqual("UNCONFIRMED", bidding_state(record, self.NOW))
                self.assertFalse(is_actionable(record, self.NOW))

        unofficial = self.valid_record(is_official_source=False)
        reversed_window = self.valid_record(
            bid_start_date="2026-09-06T17:00:00+07:00",
            bid_deadline_at="2026-09-06T09:00:00+07:00",
        )
        invalid_timestamp = self.valid_record(bid_start_date="not-a-date")
        for label, record in (
            ("unofficial source", unofficial),
            ("reversed window", reversed_window),
            ("invalid timestamp", invalid_timestamp),
        ):
            with self.subTest(label=label):
                self.assertEqual("UNCONFIRMED", bidding_state(record, self.NOW))
                self.assertFalse(is_actionable(record, self.NOW))

    def test_future_checked_timestamp_honors_only_five_minute_clock_skew(self):
        within_tolerance = self.valid_record(
            bidding_checked_at=self.NOW + timedelta(minutes=5),
        )
        beyond_tolerance = self.valid_record(
            bidding_checked_at=self.NOW + timedelta(minutes=5, microseconds=1),
        )

        self.assertEqual("OPEN_NOW", bidding_state(within_tolerance, self.NOW))
        self.assertEqual("UNCONFIRMED", bidding_state(beyond_tolerance, self.NOW))
        self.assertEqual(frozenset({"OPEN_NOW", "UPCOMING"}), ACTIONABLE_STATES)


def _stored_tender(code, *, now, state):
    checked = now - timedelta(minutes=10)
    values = {
        "bid_start_date": (now - timedelta(hours=1)).isoformat(),
        "bid_deadline_at": (now + timedelta(hours=2)).isoformat(),
        "bid_notice_status": "INVITATION",
        "bid_evidence_url": f"https://example.go.th/procurement/{code}.pdf",
        "bid_evidence_hash": (code.lower() * 64)[:64],
        "bid_evidence_excerpt": "กำหนดวันและเวลายื่นข้อเสนอ",
        # SQLite drops tzinfo; the service deliberately interprets this column
        # as a naive UTC timestamp on read.
        "bidding_checked_at": checked.astimezone(timezone.utc).replace(tzinfo=None),
        "is_demo": False,
        "is_quarantined": False,
        "verification_status": "VERIFIED",
        "data_origin": "SCRAPED",
    }
    if state == "UPCOMING":
        values.update(
            bid_start_date=(now + timedelta(hours=1)).isoformat(),
            bid_deadline_at=(now + timedelta(hours=3)).isoformat(),
        )
    elif state == "EXPIRED":
        values.update(
            bid_start_date=(now - timedelta(days=2)).isoformat(),
            bid_deadline_at=(now - timedelta(hours=1)).isoformat(),
        )
    elif state == "STALE":
        stale_checked = now - timedelta(hours=25)
        values.update(
            bid_start_date=(now - timedelta(days=1)).isoformat(),
            bid_deadline_at=(now + timedelta(days=2)).isoformat(),
            bidding_checked_at=stale_checked.astimezone(timezone.utc).replace(tzinfo=None),
        )
    elif state == "UNCONFIRMED":
        values["bid_evidence_hash"] = None
    elif state == "DEMO":
        values.update(
            is_demo=True,
            is_quarantined=True,
            verification_status="DEMO",
            data_origin="DEMO",
        )
    elif state == "REJECTED":
        values.update(
            is_quarantined=True,
            verification_status="REJECTED",
        )

    return Tender(
        tender_code=code,
        title=f"Cybersecurity procurement {code}",
        agency="Test agency",
        agency_type="ส่วนราชการ",
        category="OTHER",
        status="UNKNOWN",
        source_name="Official test source",
        source_url=f"https://example.go.th/procurement/{code}",
        is_official_source=True,
        announcement_date=now.date().isoformat(),
        **values,
    )


class BiddingApiConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{self.temp_dir.name}/bidding-policy.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.now = datetime.now(BANGKOK).replace(microsecond=0)

        with self.Session() as session:
            for state in (
                "OPEN_NOW",
                "UPCOMING",
                "EXPIRED",
                "STALE",
                "UNCONFIRMED",
                "DEMO",
                "REJECTED",
            ):
                session.add(_stored_tender(f"BID-{state}", now=self.now, state=state))
            session.commit()

        app = FastAPI()
        app.include_router(tenders_router, prefix="/api")
        app.include_router(stats_router, prefix="/api")

        def test_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_list_csv_and_stats_share_the_same_actionable_policy(self):
        listing = self.client.get("/api/tenders?open_for_bidding=true")
        self.assertEqual(200, listing.status_code)
        listed = {row["tender_code"]: row["bidding_state"] for row in listing.json()}
        self.assertEqual(
            {"BID-OPEN_NOW": "OPEN_NOW", "BID-UPCOMING": "UPCOMING"},
            listed,
        )

        csv_response = self.client.get("/api/tenders/export/csv?open_for_bidding=true")
        self.assertEqual(200, csv_response.status_code)
        csv_text = csv_response.content.decode("utf-8-sig").lstrip("\ufeff")
        exported = {
            row["เลขที่โครงการ"]: row["สถานะการยื่นข้อเสนอ"]
            for row in csv.DictReader(io.StringIO(csv_text))
        }
        self.assertEqual(listed, exported)

        stats_response = self.client.get("/api/stats")
        self.assertEqual(200, stats_response.status_code)
        stats = stats_response.json()
        self.assertEqual(len(listed), stats["actionable_tenders"])
        self.assertEqual(1, stats["open_now_tenders"])
        self.assertEqual(1, stats["upcoming_tenders"])
        self.assertEqual(1, stats["unconfirmed_deadline_tenders"])
        self.assertEqual(1, stats["stale_bidding_tenders"])
        self.assertEqual(5, stats["total_tenders"])
        self.assertEqual(2, stats["quarantined_tenders"])

    def test_unfiltered_list_exposes_states_but_hides_quarantined_rows(self):
        response = self.client.get("/api/tenders")
        self.assertEqual(200, response.status_code)
        states = {row["tender_code"]: row["bidding_state"] for row in response.json()}

        self.assertEqual(
            {
                "BID-OPEN_NOW": "OPEN_NOW",
                "BID-UPCOMING": "UPCOMING",
                "BID-EXPIRED": "EXPIRED",
                "BID-STALE": "STALE",
                "BID-UNCONFIRMED": "UNCONFIRMED",
            },
            states,
        )
        self.assertNotIn("BID-DEMO", states)
        self.assertNotIn("BID-REJECTED", states)


if __name__ == "__main__":
    unittest.main()

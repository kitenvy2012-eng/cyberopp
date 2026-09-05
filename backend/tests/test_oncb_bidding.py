import json
import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.models import ScraperSource, Tender
from backend.app.scrapers.manager import _normalize_raw_record, _upsert_tender, _reconcile_terminal_notices
from backend.app.scrapers.oncb_scraper import ONCBScraper
from backend.app.scrapers.web_fetcher import FetchedDocument
from backend.app.services.bidding import bidding_state


class ONCBBiddingTests(unittest.TestCase):
    TITLE = "ประกาศประกวดราคาจ้างบำรุงรักษาระบบ Client Zone Firewall ประจำปีงบประมาณ พ.ศ. 2570 ด้วยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    CLAUSE = "ยื่นข้อเสนอราคาในวันที่ 14 กันยายน 2569 ระหว่างเวลา 09.00 น. ถึง 12.00 น."

    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.scraper = ONCBScraper()
        self.source = ScraperSource(name=self.scraper.source_name, url=self.scraper.url, source_type="ONCB")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def raw(self, title=None, clause=None, number="6198"):
        html = f'<nav>ประกาศผู้ชนะการเสนอราคา</nav><h1 class="content-title">{title or self.TITLE}</h1><div class="content-description">{self.CLAUSE if clause is None else clause}</div>'
        url = f"https://www.oncb.go.th/procurement/{number}"
        doc = FetchedDocument(url, url, 200, {"content-type": "text/html"}, html.encode())
        return self.scraper.normalize_detail(doc, "2026-09-04")

    def save(self, raw):
        normalized = _normalize_raw_record(raw, self.source, datetime.utcnow())
        tender, created = _upsert_tender(self.db, normalized, datetime.utcnow())
        self.db.commit()
        return tender, created

    def test_official_clause_not_navigation_establishes_window_and_persists(self):
        raw = self.raw()
        self.assertEqual("INVITATION", raw["bid_notice_status"])
        self.assertEqual("2026-09-14T09:00:00+07:00", raw["bid_start_date"])
        self.assertEqual("2026-09-14T12:00:00+07:00", raw["bid_deadline_at"])
        tender, created = self.save(raw)
        self.assertTrue(created)
        self.assertEqual(raw["bid_evidence_hash"], tender.bid_evidence_hash)
        self.assertEqual(raw["bid_evidence_url"], tender.bid_evidence_url)
        self.assertEqual(1, len(tender.provenance))
        self.assertIsNone(tender.budget)
        self.assertIsNone(tender.tor_url)

    def test_successful_reread_without_window_clears_previous_dates(self):
        tender, _ = self.save(self.raw())
        original_check = tender.bidding_checked_at
        tender, created = self.save(self.raw(clause="โปรดอ่านประกาศล่าสุด ยังไม่ระบุกำหนดเวลา"))
        self.assertFalse(created)
        self.assertIsNone(tender.bid_start_date)
        self.assertIsNone(tender.bid_deadline_at)
        self.assertEqual("UNCONFIRMED", tender.bidding_state)
        self.assertGreaterEqual(tender.bidding_checked_at, original_check)

    def test_listing_observation_alone_does_not_renew_document_check(self):
        raw = self.raw()
        raw["bidding_checked_at"] = datetime.utcnow() - timedelta(days=2)
        tender, _ = self.save(raw)
        old_check = tender.bidding_checked_at
        raw = self.raw()
        raw.pop("bidding_checked_at")
        tender, _ = self.save(raw)
        self.assertEqual(old_check, tender.bidding_checked_at)

    def test_newer_exact_match_cancellation_closes_invitation_without_changing_pipeline(self):
        invitation, _ = self.save(self.raw())
        invitation.pipeline_stage = "BIDDING"
        cancelled_title = self.TITLE.replace("ประกาศประกวดราคา", "ประกาศยกเลิกประกวดราคา")
        raw = self.raw(title=cancelled_title, clause="ประกาศยกเลิกโครงการ", number="6200")
        raw["announcement_date"] = "2026-09-05"
        cancelled, _ = self.save(raw)
        _reconcile_terminal_notices(self.db)
        self.db.commit()
        self.assertEqual("CANCELLED", invitation.bid_notice_status)
        self.assertEqual("CLOSED", invitation.bidding_state)
        self.assertEqual("BIDDING", invitation.pipeline_stage)
        self.assertEqual(cancelled.source_url, invitation.bid_evidence_url)
        self.assertEqual(2, len(invitation.provenance))
        self.assertEqual(1, sum(p.is_primary for p in invitation.provenance))

    def test_contract_payload_is_awarded_not_an_open_project(self):
        raw = self.raw()
        raw.pop("bid_notice_status")
        raw["raw_payload_json"] = json.dumps({"project_detail": {"contract": [{"contract_no": "1/2569"}]}})
        normalized = _normalize_raw_record(raw, self.source, datetime.utcnow())
        self.assertEqual("AWARDED", normalized["bid_notice_status"])
        self.assertIsNone(normalized["bid_deadline_at"])


if __name__ == "__main__":
    unittest.main()

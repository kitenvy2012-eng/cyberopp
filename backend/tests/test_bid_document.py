import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.app.scrapers.bid_document import (
    BidNoticeStatus,
    extract_bid_document_evidence,
)


CHECKED_AT = datetime(2026, 9, 5, 3, 0, 0)
TITLE = "ประกาศประกวดราคาจ้างระบบ Client Zone Firewall ด้วยวิธี e-bidding"


def extract(text, **overrides):
    kwargs = {
        "content": text.encode("utf-8"),
        "content_type": "text/plain",
        "evidence_url": "https://www.oncb.go.th/procurement/6198",
        "title": TITLE,
        "checked_at": CHECKED_AT,
    }
    kwargs.update(overrides)
    return extract_bid_document_evidence(**kwargs)


class BidDocumentEvidenceTests(unittest.TestCase):
    def test_extracts_explicit_thai_buddhist_bid_window(self):
        text = (
            f"{TITLE} ผู้ยื่นข้อเสนอต้องเสนอราคาทางระบบจัดซื้อจัดจ้างภาครัฐ"
            "ด้วยอิเล็กทรอนิกส์ในวันที่ ๑๗ กันยายน พ.ศ. ๒๕๖๙ "
            "ระหว่างเวลา ๑๓.๐๐ น. ถึง ๑๖.๐๐ น."
        )

        result = extract(text)

        self.assertEqual(BidNoticeStatus.INVITATION, result.bid_notice_status)
        self.assertEqual("2026-09-17T13:00:00+07:00", result.bid_start_date)
        self.assertEqual("2026-09-17T16:00:00+07:00", result.bid_deadline_at)
        self.assertEqual("OK_EXPLICIT_BID_WINDOW", result.reason_code)
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), result.bid_evidence_hash)
        self.assertIn("เสนอราคา", result.bid_evidence_excerpt)

    def test_extracts_oncb_html_content_without_navigation(self):
        html = f"""
        <html><body>
          <nav>ประกาศผู้ชนะ ข่าวอื่นที่ไม่เกี่ยวข้อง</nav>
          <h1 class="content-title">{TITLE}</h1>
          <div class="content-description">
            ผู้สนใจสามารถดูรายละเอียดได้ที่เว็บไซต์ทางการ
            และยื่นข้อเสนอราคาในวันที่ 14 กันยายน 2569
            ระหว่างเวลา 09.00 น. ถึง 12.00 น.
          </div>
        </body></html>
        """

        result = extract(
            html,
            content=html.encode(),
            content_type="text/html; charset=utf-8",
        )

        self.assertEqual(BidNoticeStatus.INVITATION, result.bid_notice_status)
        self.assertEqual("2026-09-14T09:00:00+07:00", result.bid_start_date)
        self.assertEqual("2026-09-14T12:00:00+07:00", result.bid_deadline_at)

    def test_draft_rejects_even_an_explicit_looking_window(self):
        title = "ประกาศประชาวิจารณ์ร่างประกวดราคาจ้างระบบ Client Zone Firewall"
        text = (
            f"{title} ผู้ยื่นข้อเสนอต้องเสนอราคาในวันที่ 17 กันยายน 2569 "
            "เวลา 09.00 น. ถึง 12.00 น."
        )

        result = extract(text, title=title)

        self.assertEqual(BidNoticeStatus.DRAFT, result.bid_notice_status)
        self.assertIsNone(result.bid_start_date)
        self.assertIsNone(result.bid_deadline_at)
        self.assertEqual("NOTICE_DRAFT", result.reason_code)

    def test_terminal_notice_types_never_return_dates(self):
        cases = (
            ("ประกาศผลผู้ชนะการเสนอราคา Client Zone Firewall", BidNoticeStatus.AWARDED),
            ("ประกาศยกเลิกการประกวดราคา Client Zone Firewall", BidNoticeStatus.CANCELLED),
        )
        for title, expected in cases:
            with self.subTest(expected=expected):
                text = (
                    f"{title} ผู้ยื่นข้อเสนอต้องเสนอราคาในวันที่ 17 กันยายน 2569 "
                    "เวลา 09.00 น. ถึง 12.00 น."
                )
                result = extract(text, title=title)
                self.assertEqual(expected, result.bid_notice_status)
                self.assertIsNone(result.bid_start_date)
                self.assertIsNone(result.bid_deadline_at)

    def test_listing_publication_range_is_not_a_bid_window(self):
        text = f"{TITLE} (ระหว่างวันที่ 8-15/7/69) วันที่ประกาศ 8 กรกฎาคม 2569"

        result = extract(text)

        self.assertEqual(BidNoticeStatus.INVITATION, result.bid_notice_status)
        self.assertIsNone(result.bid_start_date)
        self.assertIsNone(result.bid_deadline_at)
        self.assertEqual("NO_EXPLICIT_BID_WINDOW", result.reason_code)

    def test_presentation_and_delivery_dates_are_not_bid_windows(self):
        text = (
            f"{TITLE} กำหนดนำเสนอ Presentation ในวันที่ 18 กันยายน 2569 "
            "ระหว่างเวลา 09.00 น. ถึง 12.00 น. ผู้ขายต้องส่งมอบภายในวันที่ 30 กันยายน 2569"
        )

        result = extract(text)

        self.assertIsNone(result.bid_start_date)
        self.assertIsNone(result.bid_deadline_at)
        self.assertEqual("NO_EXPLICIT_BID_WINDOW", result.reason_code)

    def test_bidder_noun_does_not_turn_other_appointments_into_bid_windows(self):
        activities = (
            "ดาวน์โหลดเอกสารประกวดราคา",
            "ซื้อเอกสารประกวดราคา",
            "เข้าดูสถานที่ปฏิบัติงาน",
        )
        for activity in activities:
            with self.subTest(activity=activity):
                text = (
                    f"{TITLE} ผู้ยื่นข้อเสนอต้อง{activity}ในวันที่ 12 กันยายน 2569 "
                    "ระหว่างเวลา 09.00 น. ถึง 12.00 น."
                )
                result = extract(text)
                self.assertIsNone(result.bid_start_date)
                self.assertIsNone(result.bid_deadline_at)
                self.assertEqual("NO_EXPLICIT_BID_WINDOW", result.reason_code)

    def test_cancelled_old_window_followed_by_new_window_fails_ambiguous(self):
        text = (
            f"{TITLE} ผู้ยื่นข้อเสนอต้องเสนอราคาในวันที่ 14 กันยายน 2569 "
            "เวลา 09.00 น. ถึง 12.00 น. ต่อมายกเลิกกำหนดวันดังกล่าว "
            "และกำหนดใหม่ให้ผู้ยื่นข้อเสนอต้องเสนอราคาในวันที่ 21 กันยายน 2569 "
            "เวลา 09.00 น. ถึง 12.00 น."
        )

        result = extract(text)

        self.assertIsNone(result.bid_start_date)
        self.assertIsNone(result.bid_deadline_at)
        self.assertEqual("AMBIGUOUS_BID_WINDOWS", result.reason_code)

    def test_multiple_distinct_submission_windows_are_ambiguous(self):
        text = (
            f"{TITLE} ผู้ยื่นข้อเสนอต้องเสนอราคาในวันที่ 17 กันยายน 2569 "
            "เวลา 09.00 น. ถึง 12.00 น. และยื่นข้อเสนอราคาในวันที่ 18 กันยายน 2569 "
            "ระหว่างเวลา 13.00 น. ถึง 16.00 น."
        )

        result = extract(text)

        self.assertIsNone(result.bid_start_date)
        self.assertIsNone(result.bid_deadline_at)
        self.assertEqual("AMBIGUOUS_BID_WINDOWS", result.reason_code)

    def test_exact_host_allowlist_rejects_suffix_attack(self):
        result = extract(
            TITLE,
            evidence_url="https://www.oncb.go.th.attacker.example/procurement/6198",
        )

        self.assertEqual(BidNoticeStatus.UNKNOWN, result.bid_notice_status)
        self.assertIsNone(result.bid_evidence_url)
        self.assertIsNone(result.bid_evidence_hash)
        self.assertEqual("HOST_NOT_ALLOWED", result.reason_code)

    def test_explicit_allowed_hosts_replaces_defaults(self):
        text = (
            f"{TITLE} ยื่นข้อเสนอราคาในวันที่ 14/09/2569 "
            "ระหว่างเวลา 09:00 น. ถึง 12:00 น."
        )
        result = extract(
            text,
            evidence_url="https://procurement.example.go.th/notices/1",
            allowed_hosts={"procurement.example.go.th"},
        )

        self.assertEqual("2026-09-14T09:00:00+07:00", result.bid_start_date)
        self.assertEqual("2026-09-14T12:00:00+07:00", result.bid_deadline_at)

    def test_title_document_mismatch_fails_closed(self):
        text = (
            "ประกาศประกวดราคาจ้างระบบบัญชีเงินเดือน "
            "ยื่นข้อเสนอราคาในวันที่ 14 กันยายน 2569 เวลา 09.00 น. ถึง 12.00 น."
        )

        result = extract(text)

        self.assertEqual(BidNoticeStatus.UNKNOWN, result.bid_notice_status)
        self.assertIsNone(result.bid_start_date)
        self.assertEqual("TITLE_DOCUMENT_MISMATCH", result.reason_code)

    def test_ocr_only_text_can_classify_but_never_confirms_dates(self):
        ocr = (
            f"{TITLE} ยื่นข้อเสนอราคาในวันที่ 14 กันยายน 2569 "
            "เวลา 09.00 น. ถึง 12.00 น."
        )
        with patch("backend.app.scrapers.bid_document._extract_pdf_text", return_value=""), patch(
            "backend.app.scrapers.bid_document._ocr_pdf_first_pages", return_value=ocr
        ):
            result = extract(
                "ignored",
                content=b"%PDF-1.7\nsynthetic-test-only",
                content_type="application/pdf",
            )

        self.assertEqual(BidNoticeStatus.INVITATION, result.bid_notice_status)
        self.assertIsNone(result.bid_start_date)
        self.assertIsNone(result.bid_deadline_at)
        self.assertEqual("OCR_ONLY_UNCONFIRMED", result.reason_code)

    def test_aware_checked_at_is_stored_as_utc_naive(self):
        aware = datetime(2026, 9, 5, 10, 30, tzinfo=timezone(timedelta(hours=7)))

        result = extract(TITLE, checked_at=aware)

        self.assertEqual(datetime(2026, 9, 5, 3, 30), result.bidding_checked_at)
        self.assertIsNone(result.bidding_checked_at.tzinfo)


if __name__ == "__main__":
    unittest.main()

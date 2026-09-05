import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.scrapers.bid_refresh import refresh_bid_evidence
from backend.app.scrapers.web_fetcher import FetchFailure, FetchedDocument


BANGKOK = ZoneInfo("Asia/Bangkok")
NOW = datetime(2026, 9, 5, 9, 0, tzinfo=BANGKOK)


def _html_document(url, body):
    return FetchedDocument(
        requested_url=url,
        url=url,
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=body.encode("utf-8"),
    )


def _invitation_html(title, *, with_window=False):
    clause = ""
    if with_window:
        clause = (
            "ผู้ยื่นข้อเสนอต้องเสนอราคาทางระบบจัดซื้อจัดจ้างภาครัฐ"
            "ด้วยอิเล็กทรอนิกส์ ในวันที่ 16 กันยายน 2569 "
            "ระหว่างเวลา 13.00 น. ถึง 16.00 น."
        )
    return f"<html><main><h1>{title}</h1><p>{clause}</p></main></html>"


class _FakeFetcher:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def fetch(self, url):
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response(url)
        return response


class BidEvidenceRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_direct_notice_refreshes_only_evidenced_bid_fields(self):
        title = "ประกาศประกวดราคาจ้างระบบรักษาความมั่นคงปลอดภัยไซเบอร์ DGA/69/0240"
        notice_url = "https://www.dga.or.th/notices/dga-69-0240.html"
        fetcher = _FakeFetcher(
            {notice_url: _html_document(notice_url, _invitation_html(title, with_window=True))}
        )
        record = {
            "title": title,
            "announcement_date": "2026-09-04",
            "source_url": "https://www.dga.or.th/procurement/",
            "tor_url": notice_url,
            "bid_notice_status": "UNKNOWN",
            "unrelated": "preserved",
        }

        refreshed = await refresh_bid_evidence([record], fetcher=fetcher, now=NOW)

        self.assertEqual([notice_url], fetcher.calls)
        self.assertEqual("INVITATION", refreshed[0]["bid_notice_status"])
        self.assertEqual("2026-09-16T13:00:00+07:00", refreshed[0]["bid_start_date"])
        self.assertEqual("2026-09-16T16:00:00+07:00", refreshed[0]["bid_deadline_at"])
        self.assertEqual(notice_url, refreshed[0]["bid_evidence_url"])
        self.assertEqual(datetime(2026, 9, 5, 2, 0), refreshed[0]["bidding_checked_at"])
        self.assertEqual("preserved", refreshed[0]["unrelated"])
        self.assertNotIn("reason_code", refreshed[0])
        # The caller's raw adapter item is not mutated in place.
        self.assertNotIn("bid_deadline_at", record)

    async def test_failed_fetch_does_not_refresh_an_old_check(self):
        notice_url = "https://www.etda.or.th/procurement/notice.pdf.aspx"
        old_checked = datetime(2026, 9, 3, 1, 2, 3)
        record = {
            "title": "ประกาศประกวดราคาจ้างทดสอบเจาะระบบ ETDA/69/0123",
            "announcement_date": "2026-09-03",
            "source_url": "https://www.etda.or.th/procurement/",
            "tor_url": notice_url,
            "bid_notice_status": "INVITATION",
            "bid_start_date": "2026-09-08T13:00:00+07:00",
            "bid_deadline_at": "2026-09-08T16:00:00+07:00",
            "bidding_checked_at": old_checked,
        }
        fetcher = _FakeFetcher(
            {notice_url: FetchFailure("TIMEOUT", "Source request timed out", url=notice_url)}
        )

        refreshed = await refresh_bid_evidence([record], fetcher=fetcher, now=NOW)

        self.assertEqual(old_checked, refreshed[0]["bidding_checked_at"])
        self.assertEqual(record["bid_deadline_at"], refreshed[0]["bid_deadline_at"])
        self.assertEqual(record["bid_start_date"], refreshed[0]["bid_start_date"])

    async def test_detail_page_follows_only_first_two_same_site_pdf_links(self):
        title = "ประกาศประกวดราคาจ้างระบบเฝ้าระวังภัยคุกคาม DGA/69/0999"
        detail_url = "https://www.dga.or.th/procurement/999/"
        pdf_one = "https://www.dga.or.th/files/tor.pdf"
        pdf_two = "https://www.dga.or.th/files/announcement.pdf"
        pdf_three = "https://www.dga.or.th/files/extra.pdf"
        external_pdf = "https://evil.example/notice.pdf"
        detail = _invitation_html(title) + (
            f'<a href="{external_pdf}">external</a>'
            f'<a href="{pdf_one}">TOR</a>'
            f'<a href="{pdf_two}">announcement</a>'
            f'<a href="{pdf_three}">extra</a>'
        )
        fetcher = _FakeFetcher(
            {
                detail_url: _html_document(detail_url, detail),
                pdf_one: _html_document(pdf_one, _invitation_html(title)),
                pdf_two: _html_document(
                    pdf_two, _invitation_html(title, with_window=True)
                ),
                pdf_three: AssertionError("third attachment must not be fetched"),
                external_pdf: AssertionError("cross-site attachment must not be fetched"),
            }
        )
        record = {
            "title": title,
            "announcement_date": "2026-09-03",
            "source_url": detail_url,
            "procurement_method": "e-bidding",
        }

        refreshed = await refresh_bid_evidence([record], fetcher=fetcher, now=NOW)

        self.assertEqual([detail_url, pdf_one, pdf_two], fetcher.calls)
        self.assertEqual(pdf_two, refreshed[0]["bid_evidence_url"])
        self.assertEqual("2026-09-16T16:00:00+07:00", refreshed[0]["bid_deadline_at"])

    async def test_primary_draft_or_terminal_page_never_promotes_linked_invitation(self):
        for status, heading in (
            ("DRAFT", "ร่างประกาศประกวดราคาจ้างระบบเฝ้าระวังภัยคุกคาม DGA/69/0777"),
            ("AWARDED", "ประกาศผู้ชนะการเสนอราคา จ้างระบบเฝ้าระวังภัยคุกคาม DGA/69/0777"),
            ("CANCELLED", "ประกาศยกเลิก ประกวดราคาจ้างระบบเฝ้าระวังภัยคุกคาม DGA/69/0777"),
        ):
            with self.subTest(status=status):
                record_title = (
                    "ประกาศประกวดราคาจ้างระบบเฝ้าระวังภัยคุกคาม DGA/69/0777"
                )
                detail_url = f"https://www.dga.or.th/procurement/777-{status.lower()}/"
                future_url = "https://www.dga.or.th/files/future-invitation.pdf"
                detail = (
                    f"<html><main><h1>{heading}</h1>"
                    f'<a href="{future_url}">announcement</a></main></html>'
                )
                fetcher = _FakeFetcher(
                    {
                        detail_url: _html_document(detail_url, detail),
                        future_url: AssertionError(
                            "linked invitation must not override primary status"
                        ),
                    }
                )
                record = {
                    "title": record_title,
                    "announcement_date": "2026-09-03",
                    "source_url": "https://www.dga.or.th/procurement/",
                    "detail_url": detail_url,
                    "procurement_method": "e-bidding",
                }

                refreshed = await refresh_bid_evidence(
                    [record], fetcher=fetcher, now=NOW
                )

                self.assertEqual([detail_url], fetcher.calls)
                self.assertEqual(status, refreshed[0]["bid_notice_status"])
                self.assertIsNone(refreshed[0]["bid_start_date"])
                self.assertIsNone(refreshed[0]["bid_deadline_at"])

    async def test_terminal_attachment_dominates_an_older_invitation_window(self):
        title = "ประกาศประกวดราคาจ้างระบบเฝ้าระวังภัยคุกคาม DGA/69/0888"
        detail_url = "https://www.dga.or.th/procurement/888/"
        invitation_url = "https://www.dga.or.th/files/older-invitation.pdf"
        cancellation_url = "https://www.dga.or.th/files/final-cancellation.pdf"
        detail = _invitation_html(title) + (
            f'<a href="{invitation_url}">invitation</a>'
            f'<a href="{cancellation_url}">cancellation</a>'
        )
        cancellation = (
            "<html><main><h1>ประกาศยกเลิก ประกวดราคาจ้างระบบเฝ้าระวัง"
            "ภัยคุกคาม DGA/69/0888</h1></main></html>"
        )
        fetcher = _FakeFetcher(
            {
                detail_url: _html_document(detail_url, detail),
                invitation_url: _html_document(
                    invitation_url, _invitation_html(title, with_window=True)
                ),
                cancellation_url: _html_document(cancellation_url, cancellation),
            }
        )
        record = {
            "title": title,
            "announcement_date": "2026-09-03",
            "source_url": detail_url,
            "procurement_method": "e-bidding",
        }

        refreshed = await refresh_bid_evidence([record], fetcher=fetcher, now=NOW)

        self.assertEqual([detail_url, invitation_url, cancellation_url], fetcher.calls)
        self.assertEqual("CANCELLED", refreshed[0]["bid_notice_status"])
        self.assertIsNone(refreshed[0]["bid_start_date"])
        self.assertIsNone(refreshed[0]["bid_deadline_at"])
        self.assertEqual(cancellation_url, refreshed[0]["bid_evidence_url"])

    async def test_conflicting_attachment_windows_remain_unconfirmed(self):
        title = "ประกาศประกวดราคาจ้างระบบเฝ้าระวังภัยคุกคาม DGA/69/0666"
        detail_url = "https://www.dga.or.th/procurement/666/"
        first_url = "https://www.dga.or.th/files/first.pdf"
        second_url = "https://www.dga.or.th/files/second.pdf"
        detail = _invitation_html(title) + (
            f'<a href="{first_url}">first</a><a href="{second_url}">second</a>'
        )
        first_window = _invitation_html(title, with_window=True)
        second_window = first_window.replace("16 กันยายน 2569", "17 กันยายน 2569")
        fetcher = _FakeFetcher(
            {
                detail_url: _html_document(detail_url, detail),
                first_url: _html_document(first_url, first_window),
                second_url: _html_document(second_url, second_window),
            }
        )
        record = {
            "title": title,
            "announcement_date": "2026-09-03",
            "source_url": detail_url,
            "procurement_method": "e-bidding",
        }

        refreshed = await refresh_bid_evidence([record], fetcher=fetcher, now=NOW)

        self.assertEqual([detail_url, first_url, second_url], fetcher.calls)
        self.assertEqual("INVITATION", refreshed[0]["bid_notice_status"])
        self.assertIsNone(refreshed[0]["bid_start_date"])
        self.assertIsNone(refreshed[0]["bid_deadline_at"])
        self.assertEqual(datetime(2026, 9, 5, 2, 0), refreshed[0]["bidding_checked_at"])

    async def test_refresh_budget_is_capped_at_twelve_newest_records(self):
        records = []
        responses = {}
        for offset in range(13):
            project = 1000 + offset
            title = f"ประกาศประกวดราคาจ้างระบบ Cybersecurity DGA/69/{project}"
            url = f"https://www.dga.or.th/notices/{project}.html"
            records.append(
                {
                    "title": title,
                    "announcement_date": (NOW.date() - timedelta(days=offset)).isoformat(),
                    "source_url": "https://www.dga.or.th/procurement/",
                    "tor_url": url,
                }
            )
            responses[url] = _html_document(url, _invitation_html(title, with_window=True))
        fetcher = _FakeFetcher(responses)

        refreshed = await refresh_bid_evidence(
            records, fetcher=fetcher, now=NOW, max_records=99
        )

        self.assertEqual(12, len(fetcher.calls))
        self.assertNotIn("https://www.dga.or.th/notices/1012.html", fetcher.calls)
        self.assertIn("bid_deadline_at", refreshed[11])
        self.assertNotIn("bid_deadline_at", refreshed[12])

    async def test_old_draft_award_cancel_and_unlisted_hosts_are_not_fetched(self):
        records = [
            {
                "title": "ประกาศประกวดราคาจ้างทดสอบเจาะระบบ",
                "announcement_date": "2026-05-01",
                "source_url": "https://www.dga.or.th/procurement/old/",
            },
            {
                "title": "ร่างประกาศประกวดราคาจ้างทดสอบเจาะระบบ",
                "announcement_date": "2026-09-04",
                "source_url": "https://www.dga.or.th/procurement/draft/",
            },
            {
                "title": "ประกาศผู้ชนะการเสนอราคา จ้างทดสอบเจาะระบบ",
                "announcement_date": "2026-09-04",
                "source_url": "https://www.dga.or.th/procurement/award/",
            },
            {
                "title": "ประกาศยกเลิก ประกวดราคาจ้างทดสอบเจาะระบบ",
                "announcement_date": "2026-09-04",
                "source_url": "https://www.dga.or.th/procurement/cancel/",
            },
            {
                "title": "ประกาศประกวดราคาจ้างทดสอบเจาะระบบ",
                "announcement_date": "2026-09-04",
                "source_url": "https://example.go.th/procurement/",
            },
        ]
        fetcher = _FakeFetcher({})

        refreshed = await refresh_bid_evidence(records, fetcher=fetcher, now=NOW)

        self.assertEqual([], fetcher.calls)
        self.assertEqual(records, refreshed)


if __name__ == "__main__":
    unittest.main()

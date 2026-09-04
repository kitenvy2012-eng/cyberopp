import json
import unittest

from backend.app.scrapers.bot_scraper import BOT_LISTING_TEMPLATE, BOTScraper
from backend.app.scrapers.web_fetcher import FetchFailure


class _FakeDocument:
    def __init__(self, payload):
        self.text = json.dumps(payload, ensure_ascii=False)


class _FakeFetcher:
    """Stands in for SafeWebClient, replaying a scripted sequence per call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def fetch(self, url):
        self.calls.append(url)
        outcome = self.script.pop(0) if self.script else self.script
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeDocument(outcome)


def _payload(rows, *, total=2, more=True):
    return {
        "success": True,
        "totalResults": total,
        "hasLoadmore": more,
        "results": [{"rowData": row} for row in rows],
    }


class BOTListingPagingTests(unittest.IsolatedAsyncioTestCase):
    def _scraper(self, **config):
        config.setdefault("warm_delay_seconds", 1.0)
        return BOTScraper(config_json=json.dumps(config))

    def test_listing_url_addresses_a_page_index_not_a_row_offset(self):
        # The endpoint's third segment counts pages. Multiplying it by the page
        # size (the natural reading of "offset") skips 999 rows out of every
        # 1000, which is how this source appeared to hold no cyber records.
        first = BOT_LISTING_TEMPLATE.format(page_size=1000, page=0)
        second = BOT_LISTING_TEMPLATE.format(page_size=1000, page=1)
        self.assertIn(".superListingResults.1000.0.descending.json", first)
        self.assertIn(".superListingResults.1000.1.descending.json", second)
        self.assertNotIn(".1000.1000.", second)

    async def test_cold_page_is_retried_until_the_cache_serves_it(self):
        # A page the CDN has not built yet always times out, but the request is
        # what makes it build. The retry is the fetch that actually succeeds.
        row = {"procurementtitle": "จ้างทดสอบเจาะระบบ (Red Teaming) ประจำปี 2569"}
        fetcher = _FakeFetcher([
            FetchFailure("TIMEOUT", "Source request timed out", retryable=True),
            _payload([row], total=1, more=False),
        ])
        scraper = self._scraper()
        payload, error = await scraper._fetch_page(fetcher, 0, warm_deadline=float("inf"))

        self.assertIsNone(error)
        self.assertEqual(1, len(payload["results"]))
        self.assertEqual(2, len(fetcher.calls))
        self.assertEqual(fetcher.calls[0], fetcher.calls[1])

    async def test_failure_that_is_not_a_timeout_is_reported_without_retrying(self):
        fetcher = _FakeFetcher([
            FetchFailure("HTTP_ERROR", "Source returned HTTP 404", http_status=404),
        ])
        scraper = self._scraper()
        payload, error = await scraper._fetch_page(fetcher, 0, warm_deadline=float("inf"))

        self.assertIsNone(payload)
        self.assertEqual("HTTP_ERROR", error.code)
        self.assertEqual(1, len(fetcher.calls))

    async def test_warming_budget_stops_the_retry_loop(self):
        fetcher = _FakeFetcher([
            FetchFailure("TIMEOUT", "Source request timed out", retryable=True)
            for _ in range(5)
        ])
        scraper = self._scraper(warm_attempts=4, warm_delay_seconds=30.0)
        # A deadline already in the past leaves no room for a pause, so the
        # scan gives up on this page instead of stalling.
        payload, error = await scraper._fetch_page(fetcher, 0, warm_deadline=0.0)

        self.assertIsNone(payload)
        self.assertEqual("TIMEOUT", error.code)
        self.assertEqual(1, len(fetcher.calls))


class BOTRecordTests(unittest.TestCase):
    def test_row_becomes_a_source_backed_record_without_invented_fields(self):
        scraper = BOTScraper()
        item = scraper._build_item(
            {
                "procurementtitle": "จ้างประเมินระดับความมั่นคงปลอดภัยของระบบเทคโนโลยีสารสนเทศ NIST CSF",
                "publishstart": "31 มี.ค. 69",
                "category": "คัดเลือก",
                "announceType": "ประกาศจัดซื้อจัดจ้าง",
                "link": '<p><a href="/content/dam/bot/documents/th/notice.pdf"></a></p>',
            },
            page=0,
        )

        self.assertIsNotNone(item)
        self.assertEqual("ธนาคารแห่งประเทศไทย", item["agency"])
        self.assertEqual("2026-03-31", item["announcement_date"])
        self.assertEqual(
            "https://www.bot.or.th/content/dam/bot/documents/th/notice.pdf", item["tor_url"]
        )
        self.assertEqual("VERIFIED", item["verification_status"])
        self.assertTrue(item["is_official_source"])
        # The listing publishes no budget or deadline, so neither is guessed.
        self.assertIsNone(item["budget"])
        self.assertIsNone(item["median_price"])
        self.assertIsNone(item["submission_deadline"])
        self.assertEqual("UNKNOWN", item["status"])
        self.assertEqual(item["evidence_hash"], item["provenance"]["content_sha256"])

    def test_rows_that_are_not_cybersecurity_are_dropped(self):
        scraper = BOTScraper()
        item = scraper._build_item(
            {
                "procurementtitle": "จ้างติดฟิล์มหรือสติกเกอร์ขุ่นกระจกอาคาร 1, 3 และ 5 โดยวิธีเฉพาะเจาะจง",
                "publishstart": "4 ก.ย. 69",
                "category": "เฉพาะเจาะจง",
                "announceType": "ข้อมูลสาระสำคัญในสัญญา",
            },
            page=0,
        )
        self.assertIsNone(item)


if __name__ == "__main__":
    unittest.main()

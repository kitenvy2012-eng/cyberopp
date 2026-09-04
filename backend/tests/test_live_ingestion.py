import json
import tempfile
import unittest
from datetime import datetime

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.models import ScraperSource, Tender
from backend.app.scrapers.egp_scraper import EGPScraper, _is_cyber_record
from backend.app.scrapers.manager import _normalize_raw_record, _upsert_tender


class OfficialEGPAdapterTests(unittest.IsolatedAsyncioTestCase):
    ROW = {
        "project_id": "69039134035",
        "project_name": "งานทดสอบเจาะระบบความมั่นคงปลอดภัยทางไซเบอร์",
        "budget_year": 2569,
        "project_money": 8000000,
        "price_build": 7900000,
        "announce_date_en": "18 Mar 26",
        "transaction_date": "28 เม.ย. 69",
        "project_status": {"name": "ระหว่างดำเนินการ"},
        "project_type": {"name": "จ้างเหมาบริการ"},
        "purchase_method": {"name": "e-bidding"},
        "dept": {"name": "หน่วยงานทดสอบ"},
    }
    DETAIL = {
        "project": {"province": "จ.กรุงเทพมหานคร", "status": "ระหว่างดำเนินการ"},
        "contract": [
            {
                "contract_no_formatted": "23/2569",
                "price_agree": "7900000.00",
                "winner": {"name": "บริษัท ทดสอบความปลอดภัย จำกัด"},
            }
        ],
    }

    def _client(self) -> httpx.AsyncClient:
        """Route by endpoint so search and detail return their own shapes."""

        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/get/egp/project_detail"):
                return httpx.Response(
                    200, request=request, json={"success": True, "data": self.DETAIL}
                )
            if path.endswith("/get/egp/years"):
                return httpx.Response(
                    200,
                    request=request,
                    json={"success": True, "data": [{"budget_year": 2569}]},
                )
            return httpx.Response(
                200, request=request, json={"success": True, "data": [self.ROW]}
            )

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def test_official_record_keeps_missing_fields_missing_and_hash_stable(self):
        client = self._client()
        config = json.dumps({
            "keywords": ["ทดสอบเจาะระบบ"],
            "years": [2569],
            "limit": 10,
            "max_pages": 1,
            "enrich_details": False,
        })
        try:
            first = await EGPScraper(config_json=config, _client=client).scrape()
            second = await EGPScraper(config_json=config, _client=client).scrape()
        finally:
            await client.aclose()

        self.assertEqual("SUCCESS", first.outcome.status.value)
        self.assertEqual(1, len(first))
        item = first[0]
        self.assertEqual("EGP-69039134035", item["tender_code"])
        self.assertEqual("VERIFIED", item["verification_status"])
        self.assertTrue(item["is_official_source"])
        self.assertEqual("IN_PROGRESS", item["status"])
        self.assertIsNone(item["submission_deadline"])
        self.assertIsNone(item["tor_url"])
        self.assertEqual("2026-03-18", item["announcement_date"])
        self.assertEqual(item["evidence_hash"], second[0]["evidence_hash"])

    async def test_detail_enrichment_adds_contract_evidence_without_inventing_fields(self):
        client = self._client()
        config = json.dumps({
            "keywords": ["ทดสอบเจาะระบบ"],
            "years": [2569],
            "limit": 10,
            "max_pages": 1,
            "enrich_details": True,
            "max_detail_requests": 5,
        })
        try:
            result = await EGPScraper(config_json=config, _client=client).scrape()
        finally:
            await client.aclose()

        self.assertEqual("SUCCESS", result.outcome.status.value)
        item = result[0]
        self.assertEqual("OFFICIAL_GOVSPENDING_API_WITH_DETAIL", item["verification_method"])
        self.assertIn("บริษัท ทดสอบความปลอดภัย จำกัด", item["description"])
        # Enrichment must not fabricate a deadline or a document the source
        # never published.
        self.assertIsNone(item["submission_deadline"])
        self.assertIsNone(item["tor_url"])
        payload = json.loads(item["raw_payload_json"])
        self.assertEqual({"project_detail", "search_row"}, set(payload))
        self.assertEqual(item["evidence_hash"], item["provenance"]["content_sha256"])

    async def test_years_are_resolved_from_the_source_when_not_configured(self):
        client = self._client()
        try:
            scraper = EGPScraper(
                config_json=json.dumps({
                    "keywords": ["ทดสอบเจาะระบบ"],
                    "years_back": 1,
                    "enrich_details": False,
                }),
                _client=client,
            )
            years, error, requests_made = await scraper._resolve_years(client)
        finally:
            await client.aclose()
        self.assertIsNone(error)
        self.assertEqual([2569], years)
        self.assertEqual(1, requests_made)

    async def test_successful_null_data_means_no_matches_not_failure(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                request=request,
                json={"success": True, "data": None},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await EGPScraper(
                config_json=json.dumps({"keywords": ["no-match"], "years": [2569]}),
                _client=client,
            ).scrape()
        finally:
            await client.aclose()
        self.assertEqual("SUCCESS", result.outcome.status.value)
        self.assertEqual([], result)


class CyberRelevanceTests(unittest.TestCase):
    """The keyword sweep is deliberately broad, so this filter decides accuracy.

    Every string below is a real e-GP project title. The public-health ones were
    returned by the same "ป้องกันไวรัส" query as the antivirus licences.
    """

    ACCEPT = [
        "ประกวดราคาซื้อโปรแกรมป้องกันไวรัสคอมพิวเตอร์ (Antivirus) จำนวน ๑๐,๐๐๐ ใบอนุญาต",
        "ซื้อสิทธิใช้งานโปรแกรมระบบป้องกันไวรัส โดยวิธีคัดเลือก",
        "ซื้ออุปกรณ์ป้องกันเครือข่าย (firewall) แบบที่ 1 โดยวิธีเฉพาะเจาะจง",
        "เช่าระบบป้องกันและตรวจจับภัยคุกคามแบบEDR โดยวิธีเฉพาะเจาะจง",
        "ประกวดราคาจ้างเหมาบริการทดสอบเจาะระบบความมั่นคงปลอดภัยไซเบอร์",
        "เช่าโครงการพัฒนาบริการโครงสร้างพื้นฐานและความมั่นคงปลอดภัยด้านดิจิทัล",
        "ซื้อซอฟต์แวร์ยืนยันตัวตนแบบหลายปัจจัย (Multi-Factor Authentication MFA) จำนวน 1 ระบบ",
    ]
    REJECT = [
        "ซื้อวัสดุสำหรับศูนย์ฉีดวัคซีนป้องกันไวรัส Covid-19 ภาคสนาม เซ็นทรัล แจ้งวัฒนะ",
        "ซื้อวัสดุอุปกรณ์ป้องกันไวรัสโคโรนา 2019 โดยวิธีเฉพาะเจาะจง",
        "ซื้อแอลกฮอล์เพื่อป้องกันไวรัสโคโรน่า (covid-19) ขนาด 5 ลิตร โดยวิธีเฉพาะเจาะจง",
        "ประกวดราคาซื้อยา ZOLEDRONIC ACID INFUSION 5 MG,100 ML",
        "ซื้อยา RISEDRONATE SODIUM 150 MG TABLET จำนวน 1 รายการ",
        "จ้างงานโครงการยกระดับมาตรฐานถนนเพื่อสนับสนุนเศรษฐกิจ ความมั่นคงปลอดภัยในชีวิตและทรัพย์สิน",
        "ซื้อวัสดุเชื้อเพลิงและหล่อลื่น สำหรับแผนงานยุทธศาสตร์ศักยภาพการป้องกันประเทศและภัยคุกคาม",
        "เช่าอุปกรณ์ระบบตรวจสอบยืนยันตัวตนผู้โดยสาร (Passenger Validation System)",
    ]

    def test_cybersecurity_titles_are_accepted(self):
        for title in self.ACCEPT:
            with self.subTest(title=title):
                self.assertTrue(_is_cyber_record({"project_name": title}))

    def test_public_health_and_physical_titles_are_rejected(self):
        for title in self.REJECT:
            with self.subTest(title=title):
                self.assertFalse(_is_cyber_record({"project_name": title}))


class PersistenceTrustTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{self.temp_dir.name}/ingestion.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_cross_source_evidence_does_not_replace_primary_source(self):
        with self.Session() as db:
            primary = ScraperSource(
                name="GovSpending",
                source_type="EGP",
                url="https://govspending.data.go.th/",
            )
            corroborating = ScraperSource(
                name="NCSA",
                source_type="NCSA",
                url="https://www.ncsa.or.th/procurement",
            )
            db.add_all([primary, corroborating])
            db.flush()
            observed = datetime.utcnow()
            base = {
                "tender_code": "EGP-12345678901",
                "title": "จ้างทดสอบเจาะระบบความมั่นคงปลอดภัยไซเบอร์",
                "agency": "หน่วยงานรัฐ",
                "source_name": primary.name,
                "source_url": "https://govspending.data.go.th/search?project_id=12345678901",
                "source_record_id": "12345678901",
                "status": "IN_PROGRESS",
                "verification_status": "VERIFIED",
                "verification_method": "OFFICIAL_API",
                "is_official_source": True,
                "evidence_hash": "a" * 64,
                "raw_payload_json": "{}",
                "provenance": {
                    "source_url": "https://govspending.data.go.th/search?project_id=12345678901",
                    "content_sha256": "a" * 64,
                    "source_type": "OFFICIAL",
                },
            }
            normalized = _normalize_raw_record(base, primary, observed)
            tender, created = _upsert_tender(db, normalized, observed)
            self.assertTrue(created)

            second = dict(base)
            second.update({
                "source_name": corroborating.name,
                "source_url": "https://www.ncsa.or.th/data/output/egp.json",
                "verification_method": "OFFICIAL_NCSA_JSON_FEED",
                "evidence_hash": "b" * 64,
                "raw_payload_json": "{\"source\":\"ncsa\"}",
                "provenance": {
                    "source_url": "https://www.ncsa.or.th/data/output/egp.json",
                    "content_sha256": "b" * 64,
                    "source_type": "OFFICIAL",
                },
            })
            normalized_second = _normalize_raw_record(second, corroborating, observed)
            same_tender, created_again = _upsert_tender(db, normalized_second, observed)
            db.commit()

            self.assertFalse(created_again)
            self.assertEqual(tender.id, same_tender.id)
            persisted = db.query(Tender).one()
            self.assertEqual(primary.name, persisted.source_name)
            self.assertIn("govspending.data.go.th", persisted.source_url)
            self.assertEqual(2, len(persisted.provenance))
            primary_evidence = [item for item in persisted.provenance if item.is_primary]
            self.assertEqual(1, len(primary_evidence))
            self.assertEqual(primary.name, primary_evidence[0].source_name)

    def test_latest_same_source_observation_is_the_only_primary_evidence(self):
        with self.Session() as db:
            source = ScraperSource(
                name="Official procurement page",
                source_type="CUSTOM_WEB",
                url="https://example.go.th/procurement",
            )
            db.add(source)
            db.flush()
            observed = datetime.utcnow()
            base = {
                "tender_code": "SOURCE-ONE",
                "title": "ประกวดราคาจ้างทดสอบเจาะระบบความมั่นคงปลอดภัยไซเบอร์",
                "agency": "หน่วยงานรัฐ",
                "source_name": source.name,
                "source_url": "https://example.go.th/procurement/one",
                "source_record_id": "one",
                "status": "UNKNOWN",
                "verification_status": "PENDING",
                "is_official_source": True,
                "evidence_hash": "c" * 64,
                "raw_payload_json": "{\"version\":1}",
                "provenance": {
                    "source_name": source.name,
                    "source_url": source.url,
                    "content_sha256": "c" * 64,
                    "is_primary": False,
                },
            }
            first = _normalize_raw_record(base, source, observed)
            tender, created = _upsert_tender(db, first, observed)
            self.assertTrue(created)

            updated = dict(base)
            updated["evidence_hash"] = "d" * 64
            updated["raw_payload_json"] = "{\"version\":2}"
            updated["provenance"] = {
                **base["provenance"],
                "content_sha256": "d" * 64,
            }
            second = _normalize_raw_record(updated, source, observed)
            same_tender, created_again = _upsert_tender(db, second, observed)
            db.commit()

            self.assertFalse(created_again)
            self.assertEqual(tender.id, same_tender.id)
            self.assertEqual(2, len(same_tender.provenance))
            primary_evidence = [
                item for item in same_tender.provenance if item.is_primary
            ]
            self.assertEqual(1, len(primary_evidence))
            self.assertEqual("d" * 64, primary_evidence[0].content_sha256)


if __name__ == "__main__":
    unittest.main()

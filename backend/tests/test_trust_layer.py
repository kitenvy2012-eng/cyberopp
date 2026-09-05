import tempfile
import unittest
from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.app.api.stats import router as stats_router
from backend.app.api.tenders import router as tenders_router
from backend.app.core import database as database_module
from backend.app.core.database import Base, get_db
from backend.app.models.models import ScraperSource, Tender, TenderProvenance


def _tender(
    code: str,
    title: str,
    *,
    verified: bool = False,
    quarantined: bool = False,
    announced_days_ago: int = 30,
) -> Tender:
    tender = Tender(
        tender_code=code,
        title=title,
        agency="Test agency",
        category="OTHER",
        announcement_date=(date.today() - timedelta(days=announced_days_ago)).isoformat(),
        source_name="Test source",
        source_url="https://example.go.th/notices/1",
        tor_url="https://example.go.th/notices/1/tor.pdf",
        data_origin="SCRAPED",
        verification_status=(
            "REJECTED" if quarantined else "VERIFIED" if verified else "PENDING"
        ),
        is_official_source=verified,
        is_demo=False,
        is_quarantined=quarantined,
        quarantine_reason="Parser rejected this record" if quarantined else None,
    )
    tender.provenance.append(
        TenderProvenance(
            source_name="Test source",
            source_type="WEB",
            source_url="https://example.go.th/notices/1",
            source_record_id=code,
            verification_status=tender.verification_status,
            is_primary=True,
        )
    )
    return tender


class TrustLayerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = f"{self.temp_dir.name}/trust-test.db"
        self.engine = create_engine(
            f"sqlite:///{database_path}", connect_args={"check_same_thread": False}
        )
        self.original_engine = database_module.engine
        database_module.engine = self.engine
        Base.metadata.create_all(bind=self.engine)

        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as session:
            # A leftover prototype row, a genuine record, and a real scraped row
            # the parser rejected during QA.
            session.add(_tender("BOT-67-08912", "Known prototype record"))
            session.add(_tender("REAL-001", "Verified source record", verified=True))
            session.add(_tender("REAL-002", "Rejected source record", quarantined=True))
            session.add(
                ScraperSource(
                    name="Prototype supplier portal",
                    source_type="CORPORATE",
                    url="https://www.scg.com/th/supplier",
                )
            )
            session.add(
                ScraperSource(
                    name="Real source",
                    source_type="EGP",
                    url="https://govspending.data.go.th/",
                )
            )
            session.commit()

        database_module.run_database_migrations()

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
        database_module.engine = self.original_engine
        self.temp_dir.cleanup()

    def test_migration_is_idempotent_and_deletes_prototype_data(self):
        database_module.run_database_migrations()
        columns = {column["name"] for column in inspect(self.engine).get_columns("tenders")}
        self.assertIn("verification_status", columns)
        self.assertIn("is_quarantined", columns)

        with self.Session() as session:
            codes = {row.tender_code for row in session.query(Tender).all()}
            self.assertNotIn("BOT-67-08912", codes)
            self.assertEqual({"REAL-001", "REAL-002"}, codes)

            # Evidence rows belonging to the deleted record go with it; evidence
            # for real records is untouched.
            self.assertEqual(2, session.query(TenderProvenance).count())

            source_urls = {row.url for row in session.query(ScraperSource).all()}
            self.assertNotIn("https://www.scg.com/th/supplier", source_urls)
            self.assertIn("https://govspending.data.go.th/", source_urls)

    def test_default_api_excludes_quarantine_and_reports_trust_counts(self):
        response = self.client.get("/api/tenders")
        self.assertEqual(200, response.status_code)
        self.assertEqual(["REAL-001"], [item["tender_code"] for item in response.json()])

        audit_response = self.client.get("/api/tenders?include_quarantined=true")
        self.assertEqual(
            {"REAL-001", "REAL-002"},
            {item["tender_code"] for item in audit_response.json()},
        )

        stats = self.client.get("/api/stats").json()
        self.assertEqual(1, stats["total_tenders"])
        self.assertEqual(1, stats["verified_tenders"])
        self.assertEqual(0, stats["pending_tenders"])
        self.assertEqual(1, stats["quarantined_tenders"])

    def test_only_notices_announced_within_a_year_are_listed_newest_first(self):
        with self.Session() as session:
            session.add(_tender("FRESH-001", "Announced today", verified=True,
                                announced_days_ago=0))
            session.add(_tender("FRESH-002", "Announced six months ago", verified=True,
                                announced_days_ago=180))
            session.add(_tender("OLD-001", "Announced two years ago", verified=True,
                                announced_days_ago=730))
            # The source published no announcement date, so this record's age
            # cannot be established and it must not be assumed recent.
            undated = _tender("NODATE-001", "Source published no date", verified=True)
            undated.announcement_date = None
            session.add(undated)
            session.commit()

        codes = [item["tender_code"] for item in self.client.get("/api/tenders").json()]
        self.assertNotIn("OLD-001", codes)
        self.assertNotIn("NODATE-001", codes)
        self.assertIn("FRESH-001", codes)
        self.assertIn("FRESH-002", codes)
        # Newest announcement first.
        self.assertLess(codes.index("FRESH-001"), codes.index("FRESH-002"))

        dates = [
            item["announcement_date"]
            for item in self.client.get("/api/tenders").json()
        ]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_the_window_can_be_widened_on_request(self):
        with self.Session() as session:
            session.add(_tender("OLD-002", "Announced two years ago", verified=True,
                                announced_days_ago=730))
            session.commit()

        within_year = [i["tender_code"] for i in self.client.get("/api/tenders").json()]
        self.assertNotIn("OLD-002", within_year)

        everything = [
            i["tender_code"]
            for i in self.client.get("/api/tenders?max_age_days=0").json()
        ]
        self.assertIn("OLD-002", everything)

    def test_headline_counts_describe_the_same_window_as_the_list(self):
        with self.Session() as session:
            session.add(_tender("OLD-003", "Announced two years ago", verified=True,
                                announced_days_ago=730))
            session.commit()

        listed = len(self.client.get("/api/tenders").json())
        self.assertEqual(listed, self.client.get("/api/stats").json()["total_tenders"])

    def test_documents_are_never_generated_for_hidden_records(self):
        with self.Session() as session:
            visible_id = (
                session.query(Tender).filter(Tender.tender_code == "REAL-001").one().id
            )
            quarantined_id = (
                session.query(Tender).filter(Tender.tender_code == "REAL-002").one().id
            )

        hidden = self.client.get(
            f"/api/tenders/{quarantined_id}/tor-doc", follow_redirects=False
        )
        self.assertEqual(404, hidden.status_code)

        audit = self.client.get(
            f"/api/tenders/{quarantined_id}/tor-doc?include_quarantined=true",
            follow_redirects=False,
        )
        self.assertEqual(410, audit.status_code)

        real = self.client.get(f"/api/tenders/{visible_id}/tor-doc", follow_redirects=False)
        self.assertEqual(307, real.status_code)
        self.assertEqual("https://example.go.th/notices/1/tor.pdf", real.headers["location"])


if __name__ == "__main__":
    unittest.main()

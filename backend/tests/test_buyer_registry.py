"""Unit tests for Buyer Registry and Source Registry (Phase 1)."""

import os
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core import database as database_module
from backend.app.core.database import Base, get_db
from backend.app.models.models import Buyer, ScraperSource, Source, Tender
from backend.app.scrapers.manager import seed_database_if_empty
from backend.main import app

_TEST_DB = "test_buyer_registry.db"
_TEST_DB_URL = f"sqlite:///{_TEST_DB}"


class BuyerRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(_TEST_DB):
            os.remove(_TEST_DB)
        cls.engine = create_engine(
            _TEST_DB_URL, connect_args={"check_same_thread": False}
        )
        cls.original_engine = database_module.engine
        database_module.engine = cls.engine
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        database_module.engine = cls.original_engine
        cls.engine.dispose()
        if os.path.exists(_TEST_DB):
            os.remove(_TEST_DB)

    def setUp(self):
        self.db = self.TestingSessionLocal()
        seed_database_if_empty(self.db)

    def tearDown(self):
        self.db.close()

    def test_seed_initial_buyers_populated(self):
        """Seed data should populate 25 Tier-1 buyers and link their sources."""
        buyers = self.db.query(Buyer).all()
        self.assertGreaterEqual(len(buyers), 25)

        ais = self.db.query(Buyer).filter(Buyer.domain == "ais.th").first()
        self.assertIsNotNone(ais)
        self.assertEqual(ais.industry, "TELECOM")
        self.assertEqual(ais.priority, "TIER_1")

        # Check linked sources
        oncb = self.db.query(Buyer).filter(Buyer.domain == "oncb.go.th").first()
        self.assertIsNotNone(oncb)
        oncb_sources = self.db.query(Source).filter(Source.buyer_id == oncb.id).all()
        self.assertGreater(len(oncb_sources), 0)
        self.assertEqual(oncb_sources[0].buyer_id, oncb.id)

    def test_get_buyers_list_and_filters(self):
        """GET /api/buyers should support filtering and search."""
        # 1. Default list
        res = self.client.get("/api/buyers")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(len(data), 25)

        # 2. Filter by priority
        res = self.client.get("/api/buyers?priority=TIER_1")
        self.assertEqual(res.status_code, 200)
        for b in res.json():
            self.assertEqual(b["priority"], "TIER_1")

        # 3. Filter by industry
        res = self.client.get("/api/buyers?industry=BANKING")
        self.assertEqual(res.status_code, 200)
        banking_buyers = res.json()
        self.assertGreater(len(banking_buyers), 0)
        for b in banking_buyers:
            self.assertEqual(b["industry"], "BANKING")

        # 4. Search query
        res = self.client.get("/api/buyers?q=AIS")
        self.assertEqual(res.status_code, 200)
        q_results = res.json()
        self.assertEqual(len(q_results), 1)
        self.assertIn("ais.th", q_results[0]["domain"])

    def test_get_buyer_detail(self):
        """GET /api/buyers/{id} should return buyer detail with sources."""
        ais = self.db.query(Buyer).filter(Buyer.domain == "ais.th").first()
        self.assertIsNotNone(ais)

        res = self.client.get(f"/api/buyers/{ais.id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], ais.id)
        self.assertEqual(data["name"], ais.name)
        self.assertIn("sources", data)

        # Non-existent buyer
        res = self.client.get("/api/buyers/999999")
        self.assertEqual(res.status_code, 404)

    def test_create_update_delete_buyer(self):
        """CRUD operations for Buyer registry."""
        # Create
        new_buyer_payload = {
            "name": "บริษัท ทดสอบความปลอดภัยไซเบอร์ จำกัด",
            "name_th": "บริษัท ทดสอบความปลอดภัยไซเบอร์ จำกัด",
            "name_en": "Cyber Test Security Co., Ltd.",
            "domain": "cybertest.co.th",
            "industry": "TECH",
            "company_type": "PRIVATE",
            "priority": "TIER_2",
            "active": True,
            "procurement_coverage_status": "UNKNOWN",
        }
        res = self.client.post("/api/buyers", json=new_buyer_payload)
        self.assertEqual(res.status_code, 201)
        created = res.json()
        self.assertIn("id", created)
        buyer_id = created["id"]
        self.assertEqual(created["name"], new_buyer_payload["name"])

        # Duplicate check
        res_dup = self.client.post("/api/buyers", json=new_buyer_payload)
        self.assertEqual(res_dup.status_code, 409)

        # Update
        update_payload = {"priority": "TIER_1", "procurement_coverage_status": "HIGH"}
        res_update = self.client.patch(f"/api/buyers/{buyer_id}", json=update_payload)
        self.assertEqual(res_update.status_code, 200)
        updated = res_update.json()
        self.assertEqual(updated["priority"], "TIER_1")
        self.assertEqual(updated["procurement_coverage_status"], "HIGH")

        # Delete
        res_del = self.client.delete(f"/api/buyers/{buyer_id}")
        self.assertEqual(res_del.status_code, 204)

        # Verify deletion
        res_get = self.client.get(f"/api/buyers/{buyer_id}")
        self.assertEqual(res_get.status_code, 404)

    def test_buyer_activity_endpoint(self):
        """GET /api/buyers/{id}/activity returns activity stats."""
        oncb = self.db.query(Buyer).filter(Buyer.domain == "oncb.go.th").first()
        self.assertIsNotNone(oncb)

        res = self.client.get(f"/api/buyers/{oncb.id}/activity")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["buyer_id"], oncb.id)
        self.assertEqual(data["buyer_name"], oncb.name)
        self.assertIn("procurement_count_30d", data)
        self.assertIn("source_health", data)
        self.assertIn("sources", data)

    def test_sources_filtered_by_buyer_id(self):
        """GET /api/sources?buyer_id=X should return only sources for that buyer."""
        oncb = self.db.query(Buyer).filter(Buyer.domain == "oncb.go.th").first()
        self.assertIsNotNone(oncb)

        res = self.client.get(f"/api/sources?buyer_id={oncb.id}")
        self.assertEqual(res.status_code, 200)
        sources = res.json()
        self.assertGreater(len(sources), 0)
        for s in sources:
            self.assertIn("ONCB", s["name"])

    def test_sources_registry_endpoint(self):
        """GET /api/sources/registry should return full target source model."""
        res = self.client.get("/api/sources/registry")
        self.assertEqual(res.status_code, 200)
        sources = res.json()
        self.assertGreater(len(sources), 0)
        first_src = sources[0]
        self.assertIn("adapter_type", first_src)
        self.assertIn("health_status", first_src)
        self.assertIn("source_confidence", first_src)

    def test_dual_table_source_synchronization(self):
        """Creating and toggling sources syncs both scraper_sources and sources."""
        # Create a new source
        new_src = {
            "name": "ทดสอบ แหล่งจัดซื้อ กรมตรวจไซเบอร์",
            "url": "https://cyber-audit.go.th/procurement",
            "source_type": "CUSTOM_WEB",
            "is_active": True,
        }
        res = self.client.post("/api/sources", json=new_src)
        self.assertEqual(res.status_code, 200)
        src_id = res.json()["id"]

        # Check legacy table
        legacy = self.db.query(ScraperSource).filter(ScraperSource.id == src_id).first()
        self.assertIsNotNone(legacy)
        self.assertTrue(legacy.is_active)

        # Check new table
        target_src = self.db.query(Source).filter(Source.name == new_src["name"]).first()
        self.assertIsNotNone(target_src)
        self.assertTrue(target_src.is_active)
        self.assertEqual(target_src.health_status, "HEALTHY")

        # Toggle source
        res_toggle = self.client.patch(f"/api/sources/{src_id}/toggle")
        self.assertEqual(res_toggle.status_code, 200)
        self.assertFalse(res_toggle.json()["is_active"])

        # Verify both are updated
        self.db.refresh(legacy)
        self.db.refresh(target_src)
        self.assertFalse(legacy.is_active)
        self.assertFalse(target_src.is_active)
        self.assertEqual(target_src.health_status, "DISABLED")

        # Delete source
        res_delete = self.client.delete(f"/api/sources/{src_id}")
        self.assertEqual(res_delete.status_code, 200)

        # Verify deletion in both
        self.assertIsNone(self.db.query(ScraperSource).filter(ScraperSource.id == src_id).first())
        self.assertIsNone(self.db.query(Source).filter(Source.name == new_src["name"]).first())


if __name__ == "__main__":
    unittest.main()

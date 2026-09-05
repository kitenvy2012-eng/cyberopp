import unittest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.services.classifier import detect_agency_type


class CorporateClassificationTests(unittest.TestCase):
    def test_corporate_markers_classify_as_corporate(self):
        cases = {
            "บริษัท ปูนซิเมนต์ไทย จำกัด (มหาชน)": "บริษัทเอกชนชั้นนำ",
            "SCG Chemicals Co., Ltd.": "บริษัทเอกชนชั้นนำ",
            "บมจ. ทรู คอร์ปอเรชั่น": "บริษัทเอกชนชั้นนำ",
            "AIS Fibre": "บริษัทเอกชนชั้นนำ",
            "บริษัท บิทคับ ออนไลน์ จำกัด": "บริษัทเอกชนชั้นนำ",
            "Pantavanij Co., Ltd.": "บริษัทเอกชนชั้นนำ",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(detect_agency_type(name), expected)

    def test_state_enterprises_and_public_orgs_remain_intact(self):
        cases = {
            "การไฟฟ้าฝ่ายผลิตแห่งประเทศไทย": "รัฐวิสาหกิจ",
            "การไฟฟ้าส่วนภูมิภาค": "รัฐวิสาหกิจ",
            "สำนักงานคณะกรรมการป้องกันและปราบปรามยาเสพติด": "ส่วนราชการ",
            "กรมศุลกากร": "ส่วนราชการ",
            "สำนักงานพัฒนารัฐบาลดิจิทัล (องค์การมหาชน)": "องค์การมหาชน",
            "ธนาคารแห่งประเทศไทย": "องค์กรกำกับดูแล",
            "ธนาคารไทยพาณิชย์ จำกัด (มหาชน)": "สถาบันการเงิน",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(detect_agency_type(name), expected)


class SourcesTestEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_test_source_rejects_ssrf_and_invalid_urls(self):
        res = self.client.post(
            "/api/sources/test",
            json={"url": "http://127.0.0.1:8000/private", "name": "Localhost"},
        )
        self.assertEqual(res.status_code, 422)

    def test_test_source_rejects_file_urls(self):
        res = self.client.post(
            "/api/sources/test",
            json={"url": "file:///etc/passwd", "name": "File"},
        )
        self.assertEqual(res.status_code, 422)


class OpportunityScopeFilterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_active_only_scope_is_supported(self):
        res = self.client.get("/api/tenders?opportunity_scope=ACTIVE_ONLY&limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for item in data:
            self.assertNotIn(item.get("bid_notice_status"), ["AWARDED", "CANCELLED"])
            self.assertNotEqual(item.get("status"), "CLOSED")

    def test_awarded_scope_is_supported(self):
        res = self.client.get("/api/tenders?opportunity_scope=AWARDED&limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for item in data:
            self.assertTrue(
                item.get("bid_notice_status") == "AWARDED" or item.get("status") == "CLOSED"
            )

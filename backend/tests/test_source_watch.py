import json
import unittest
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.models.models import Buyer, Source, ScraperSource, PublicNotice, Tender
from backend.app.scrapers.base import ScrapeOutcome
from backend.app.scrapers.custom_scraper import CustomWebScraper
from backend.app.services.source_watch import buyer_watch, record_source_scan


class SourceWatchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.buyer = Buyer(name='บริษัททดสอบ', industry='TECH', company_type='PRIVATE')
        self.source = Source(name='บอร์ดบริษัท', source_type='PROCUREMENT_PAGE', url='https://example.com/procurement', buyer=self.buyer)
        self.db.add(self.source)
        self.db.commit()
        self.legacy = ScraperSource(name=self.source.name, source_type='CORPORATE', url=self.source.url, last_status='SUCCESS', tenders_count=0)
        self.now = datetime.utcnow()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def ingest(self, notices, **kw):
        outcome = ScrapeOutcome(source_name=self.source.name, source_url=self.source.url, public_notices=notices, **kw)
        record_source_scan(self.db, self.legacy, outcome, [], self.now)
        self.db.commit()

    def test_discovery_date_does_not_become_publication_or_opportunity(self):
        self.ingest([{'title': 'ยื่นแบบ 1 ต.ค. งานประมูลก่อสร้าง', 'url': 'https://example.com/a.pdf', 'published_date': None}])
        watch = buyer_watch(self.db, self.buyer)
        self.assertIsNone(watch['latest_procurement_date'])
        self.assertEqual(0, watch['procurement_count_30d'])
        self.assertEqual(1, watch['undated_count'])
        self.assertEqual(0, watch['actionable_count'])
        self.assertEqual(0, self.db.query(Tender).count())

    def test_counts_use_real_dates_not_total_or_arbitrary_cap(self):
        notices = [{'title': f'ประกวดราคาจ้าง Firewall {days}', 'url': f'https://example.com/{days}', 'published_date': (self.now - timedelta(days=days)).date().isoformat()} for days in [1, 40, 120]]
        self.ingest(notices)
        result = buyer_watch(self.db, self.buyer)
        self.assertEqual(1, result['procurement_count_30d'])
        self.assertEqual(2, result['procurement_count_90d'])
        self.assertEqual(0, result['actionable_count'])
        self.assertEqual(notices[0]['published_date'], self.source.latest_post_date)

    def test_repeated_scan_deduplicates_and_keeps_first_seen_and_change_time(self):
        notices = [{'title': 'ประกวดราคาจ้าง Firewall', 'url': 'https://example.com/a'}]
        self.ingest(notices)
        first = self.db.query(PublicNotice).one().first_seen_at
        changed = self.source.last_content_change_at
        self.now += timedelta(hours=1)
        self.ingest(notices)
        self.assertEqual(1, self.db.query(PublicNotice).count())
        self.assertEqual(first, self.db.query(PublicNotice).one().first_seen_at)
        self.assertEqual(changed, self.source.last_content_change_at)

    def test_failure_does_not_fake_successful_refresh(self):
        self.ingest([])
        success = self.source.last_success_at
        self.now += timedelta(minutes=10)
        self.legacy.last_status = 'FAILED'
        self.ingest([])
        self.assertEqual(success, self.source.last_success_at)
        self.assertEqual('FAILED', self.source.health_status)
        self.assertEqual(1, self.source.consecutive_failures)

    def test_duplicate_rows_with_autoflush_disabled_are_safe(self):
        self.db.autoflush = False
        row = {'title': 'ประกวดราคาจ้าง Firewall', 'url': 'https://example.com/a'}
        self.ingest([row, row])
        self.assertEqual(1, self.db.query(PublicNotice).count())

    def test_invalid_source_config_does_not_break_watch(self):
        self.source.configuration_json = 'invalid json'
        self.assertEqual('', buyer_watch(self.db, self.buyer)['sources'][0]['notes'])

    def test_scan_syncs_actual_source_activation(self):
        self.source.is_active = False
        self.legacy.is_active = True
        self.ingest([])
        self.assertTrue(self.source.is_active)
        self.assertEqual('HEALTHY', buyer_watch(self.db, self.buyer)['sources'][0]['health'])

    def test_watch_private_filter_and_search(self):
        from backend.app.api.buyers import get_buyer_watch
        self.db.add(Buyer(name='หน่วยงานรัฐ', company_type='GOVERNMENT', industry='GOVERNMENT'))
        self.db.commit()
        self.assertEqual(1, len(get_buyer_watch(db=self.db)))
        self.assertEqual(2, len(get_buyer_watch(private_only=False, db=self.db)))
        self.assertEqual([], get_buyer_watch(q='missing company', db=self.db))

    def test_never_checked_source_cannot_be_healthy_and_portal_is_not_bid(self):
        self.assertEqual('NOT_CHECKED', buyer_watch(self.db, self.buyer)['sources'][0]['health'])
        self.ingest([], access_status='REGISTRATION_ONLY')
        result = buyer_watch(self.db, self.buyer)
        self.assertEqual('REGISTRATION_ONLY', result['sources'][0]['health'])
        self.assertEqual(0, result['actionable_count'])

    def test_html_captures_noncyber_procurement_without_creating_cyber_tender(self):
        scraper = CustomWebScraper('SCB', 'https://www.scb.co.th/th/about-us/news/auction-bidding.html', json.dumps({'board_kind':'SCB', 'item_selector':'a'}))
        items = scraper._parse_html(BeautifulSoup('<a href="/getmedia/id/bidding-20251001.pdf">ยื่นแบบ 1 ต.ค. งานประมูลก่อสร้างอาคาร ปี 2569</a>', 'html.parser'), scraper.url)
        self.assertEqual([], items)
        self.assertEqual(1, len(scraper.public_notices))
        self.assertIsNone(scraper.public_notices[0]['published_date'])


if __name__ == '__main__':
    unittest.main()

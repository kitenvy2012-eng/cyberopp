"""System configuration seeds.

This module holds only *configuration*: which live sources to poll and which
notification channels exist. It deliberately contains no tender records. Every
opportunity in the database must come from a live fetch against a real source
with retained evidence, so there is no fabricated catalogue to fall back on.
"""

import json


# Every entry below was verified against the live site while it was added.
# ``verified_note`` documents what was observed so a future maintainer can tell
# a genuine source outage from a parser that was never correct.
DEFAULT_SOURCES = [
    {
        "name": "สำนักงาน ป.ป.ส. (ONCB) — ประกาศจัดซื้อจัดจ้าง",
        "source_type": "ONCB",
        "url": "https://www.oncb.go.th/procurement",
        "is_active": True,
        "config_json": json.dumps({
            "max_pages": 8,
            "is_official_source": True,
            "verified_note": "Official listing and individual notice HTML publish explicit Thai bid-submission dates and times; active notices are rechecked each scan.",
        }, ensure_ascii=False),
    },
    {
        "name": "e-GP กรมบัญชีกลาง (ระบบจัดซื้อจัดจ้างภาครัฐ)",
        "source_type": "EGP",
        "url": "https://govspending.data.go.th/",
        "is_active": True,
        "config_json": json.dumps({
            # The public endpoint returns a whole result set in one response,
            # so a single request per (budget year, keyword) is enough.
            "limit": 1000,
            "max_pages": 3,
            "max_concurrency": 6,
            "years_back": 5,
            "enrich_details": True,
            "max_detail_requests": 120,
            "verified_note": (
                "POST api-govspending.data.go.th/api/get/egp/search returns first-party "
                "e-GP project rows; GET .../get/egp/project_detail adds contract and winner."
            ),
        }, ensure_ascii=False),
    },
    {
        "name": "สกมช. (สำนักงานคณะกรรมการการรักษาความมั่นคงปลอดภัยไซเบอร์แห่งชาติ)",
        "source_type": "NCSA",
        "url": "https://www.ncsa.or.th/page/procurementannouncement",
        "is_active": True,
        "config_json": json.dumps({
            "is_official_source": True,
            "max_pages": 30,
            "discover_sitemaps": False,
            "request_delay_seconds": 0.35,
        }, ensure_ascii=False),
    },
    {
        "name": "ธนาคารแห่งประเทศไทย (BOT)",
        "source_type": "BOT",
        "url": "https://www.bot.or.th/th/news-and-media/procurement-list.html",
        "is_active": True,
        "config_json": json.dumps({
            "page_size": 1000,
            "max_pages": 12,
            "timeout_seconds": 30,
            "warm_attempts": 3,
            "warm_delay_seconds": 10,
            "max_warm_seconds": 300,
            "verified_note": (
                "superlist.superListingResults.<size>.<pageIndex>.descending.json returns the "
                "same rows the public page renders, including the announcement PDF link. "
                "The third segment is a page index, and an uncached page always times out "
                "once before the CDN can serve it."
            ),
        }, ensure_ascii=False),
    },
    {
        "name": "สำนักงานพัฒนารัฐบาลดิจิทัล (DGA) — ประกาศประกวดราคา",
        "source_type": "GOVERNMENT",
        "url": "https://www.dga.or.th/procurement/tender/year-2569/",
        "is_active": True,
        "config_json": json.dumps({
            "is_official_source": True,
            "max_pages": 10,
            "discover_sitemaps": False,
            "agency_name": "สำนักงานพัฒนารัฐบาลดิจิทัล (องค์การมหาชน)",
            "item_selector": ".item-purchase-document",
            "title_selector": ".purchase-document-title",
            "link_selector": ".purchase-document-title a",
            "code_selector": ".project-id",
            "budget_selector": ".budget",
            "announcement_date_selector": ".post-date",
            "pagination_selector": ".pagination a.page-numbers",
            "request_delay_seconds": 0.35,
        }, ensure_ascii=False),
    },
    {
        "name": "สำนักงานพัฒนาธุรกรรมทางอิเล็กทรอนิกส์ (ETDA)",
        "source_type": "GOVERNMENT",
        "url": "https://www.etda.or.th/th/newsevents/announce/etda-procurement.aspx",
        "is_active": True,
        "config_json": json.dumps({
            "is_official_source": True,
            "max_pages": 10,
            "discover_sitemaps": False,
            "agency_name": "สำนักงานพัฒนาธุรกรรมทางอิเล็กทรอนิกส์ (องค์การมหาชน)",
            "item_selector": ".content-tablelist2f.procurement table tbody tr",
            "identity_from_title": True,
            "title_selector": "td:nth-child(2)",
            "link_selector": "td:nth-child(6) a",
            "method_selector": "td:nth-child(3)",
            "announcement_date_selector": "td:nth-child(6) .textmodal",
            "tor_selector": "td:nth-child(6) a",
            "pagination_selector": ".pagination a",
            "request_delay_seconds": 0.35,
        }, ensure_ascii=False),
    },
    {
        "name": "การไฟฟ้าฝ่ายผลิตแห่งประเทศไทย (กฟผ.)",
        "source_type": "STATE_ENTERPRISE",
        # The site root only renders a menu; procure_list.php holds the table.
        "url": "https://bidding.egat.co.th/procure/procure_list.php",
        "is_active": True,
        "config_json": json.dumps({
            "is_official_source": True,
            "max_pages": 15,
            "discover_sitemaps": False,
            # bidding.egat.co.th serves no robots.txt (404); an absent policy is
            # not a deny, and the listing is public and unauthenticated.
            "robots_fail_open": True,
            "agency_name": "การไฟฟ้าฝ่ายผลิตแห่งประเทศไทย",
            "item_selector": "#procurementTable tbody tr",
            "code_selector": "td:nth-child(1)",
            "agency_selector": "td:nth-child(2)",
            "method_selector": "td:nth-child(3)",
            "title_selector": "td:nth-child(5)",
            "link_selector": "td:nth-child(5) a",
            "request_delay_seconds": 0.4,
            "verified_note": "Static table #procurementTable, 5 columns, e-GP project id in column 1.",
        }, ensure_ascii=False),
    },
    {
        "name": "การไฟฟ้าส่วนภูมิภาค (PEA) — ประกาศจัดซื้อจัดจ้าง",
        "source_type": "STATE_ENTERPRISE",
        # The site root is a Drupal landing page; /procurement/list holds the table.
        "url": "https://bidding.pea.co.th/procurement/list",
        "is_active": True,
        "config_json": json.dumps({
            "is_official_source": True,
            "max_pages": 15,
            "discover_sitemaps": False,
            "agency_name": "การไฟฟ้าส่วนภูมิภาค",
            "item_selector": "table.views-table tbody tr",
            "code_selector": "td:nth-child(1)",
            "title_selector": "td:nth-child(3)",
            "link_selector": "td:nth-child(3) a",
            "method_selector": "td:nth-child(4)",
            "tor_selector": "td:nth-child(5) a",
            # The list renders no page links; it pages purely by query string.
            "page_url_template": "https://bidding.pea.co.th/procurement/list?page={page}",
            "page_start": 1,
            "page_count": 12,
            "request_delay_seconds": 0.4,
            "verified_note": "Drupal views table, 5 columns; column 5 links the announcement PDF.",
        }, ensure_ascii=False),
    },
    {
        "name": "สำนักงาน ก.ล.ต. (SEC)",
        "source_type": "REGULATOR",
        "url": "https://www.sec.or.th/TH/Pages/ABOUTUS/PROCURE-ANNOUNCE.aspx",
        # Every request from a non-browser client is answered with HTTP 403 by
        # the site's WAF, including the site root. Leaving it enabled would only
        # produce a permanent FAILED row, so it stays off until a lawful,
        # working access path exists.
        "is_active": False,
        "last_status": "DISABLED_BLOCKED_BY_SOURCE",
        "config_json": json.dumps({
            "is_official_source": True,
            "disabled_reason": (
                "sec.or.th ตอบ HTTP 403 กับ client ที่ไม่ใช่เบราว์เซอร์ทุกคำขอ "
                "ประกาศของ ก.ล.ต. ยังถูกเก็บผ่านช่องทาง e-GP"
            ),
        }, ensure_ascii=False),
    },
    {
        "name": "การท่าอากาศยานไทย จำกัด (มหาชน)",
        "source_type": "STATE_ENTERPRISE",
        "url": "https://aotdatainfo.airportthai.co.th/bidding/Category/index/158",
        # The announcement list is rendered client-side; the served HTML has no
        # rows to parse. Kept visible and documented rather than silently
        # reporting a successful scan that finds nothing.
        "is_active": False,
        "last_status": "DISABLED_JS_RENDERED",
        "config_json": json.dumps({
            "is_official_source": True,
            "disabled_reason": (
                "หน้า bidding ของ ทอท. เรนเดอร์รายการด้วย JavaScript "
                "HTML ที่ส่งมาไม่มีแถวประกาศให้ parse ประกาศของ ทอท. ยังถูกเก็บผ่านช่องทาง e-GP"
            ),
        }, ensure_ascii=False),
    },
    {
        "name": "บริษัท ปูนซิเมนต์ไทย จำกัด (มหาชน) (SCG) — จัดซื้อจัดจ้าง",
        "source_type": "CORPORATE",
        "url": "https://www.scg.com/th/procurement/",
        # The path 302s to https://www.scg.com/ — the page does not exist, so an
        # enabled source would re-scrape the SCG homepage on every cycle and
        # report success while collecting nothing. SCG also names ClaudeBot,
        # GPTBot and CCBot under `Disallow: /` in its robots.txt.
        # `backend/discover_procurement_pages.py` found no procurement board on
        # any of the 24 private companies it probed.
        "is_active": False,
        "last_status": "DISABLED_NO_PUBLIC_BOARD",
        "config_json": json.dumps({
            "agency_name": "บริษัท ปูนซิเมนต์ไทย จำกัด (มหาชน)",
            "agency_type": "บริษัทเอกชนชั้นนำ",
            "disabled_reason": (
                "scg.com/th/procurement/ redirect ไปหน้าแรก ไม่มีหน้าประกาศจัดซื้อสาธารณะ "
                "ช่องทางจริงของ SCG คือลงทะเบียนคู่ค้า แล้วรับ RFP ทางอีเมล"
            ),
        }, ensure_ascii=False),
    },
]

DEFAULT_CHANNELS = [
    {
        "name": "ระบบแจ้งเตือนภายในเว็บ (In-App Notification)",
        "channel_type": "IN_APP",
        "is_enabled": True,
        "min_budget": 0.0
    },
    {
        "name": "LINE Messaging API (ฝ่ายขาย & Pre-sales Cyber)",
        "channel_type": "LINE_MESSAGING",
        "token": "",
        "chat_id": "",
        "is_enabled": False,
        "min_budget": 500000.0
    },
    {
        "name": "Discord Procurement Channel",
        "channel_type": "DISCORD",
        "target_url": "",
        "is_enabled": False,
        "min_budget": 0.0
    },
    {
        "name": "Telegram Cyber Alerts Bot",
        "channel_type": "TELEGRAM",
        "token": "",
        "chat_id": "",
        "is_enabled": False,
        "min_budget": 0.0
    }
]

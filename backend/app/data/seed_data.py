"""System configuration seeds.

This module holds only *configuration*: which live sources to poll and which
notification channels exist. It deliberately contains no tender records. Every
opportunity in the database must come from a live fetch against a real source
with retained evidence, so there is no fabricated catalogue to fall back on.
"""

import json


# 25 Initial Tier-1 Target Organizations (Telecom, Banking, Energy, Retail, Tech, Government)
INITIAL_BUYERS = [
    {
        "name": "บริษัท แอดวานซ์ อินโฟร์ เซอร์วิส จำกัด (มหาชน)",
        "name_th": "บริษัท แอดวานซ์ อินโฟร์ เซอร์วิส จำกัด (มหาชน)",
        "name_en": "Advanced Info Service Public Company Limited (AIS)",
        "domain": "ais.th",
        "industry": "TELECOM",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "MEDIUM",
    },
    {
        "name": "บริษัท ทรู คอร์ปอเรชั่น จำกัด (มหาชน)",
        "name_th": "บริษัท ทรู คอร์ปอเรชั่น จำกัด (มหาชน)",
        "name_en": "True Corporation Public Company Limited",
        "domain": "true.th",
        "industry": "TELECOM",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "MEDIUM",
    },
    {
        "name": "บริษัท โทรคมนาคมแห่งชาติ จำกัด (มหาชน)",
        "name_th": "บริษัท โทรคมนาคมแห่งชาติ จำกัด (มหาชน)",
        "name_en": "National Telecom Public Company Limited (NT)",
        "domain": "ntplc.co.th",
        "industry": "TELECOM",
        "company_type": "STATE_ENTERPRISE",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "ธนาคารกสิกรไทย จำกัด (มหาชน)",
        "name_th": "ธนาคารกสิกรไทย จำกัด (มหาชน)",
        "name_en": "Kasikornbank Public Company Limited (KBANK)",
        "domain": "kasikornbank.com",
        "industry": "BANKING",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "LOW",
    },
    {
        "name": "ธนาคารไทยพาณิชย์ จำกัด (มหาชน)",
        "name_th": "ธนาคารไทยพาณิชย์ จำกัด (มหาชน)",
        "name_en": "The Siam Commercial Bank Public Company Limited (SCB)",
        "domain": "scb.co.th",
        "industry": "BANKING",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "LOW",
    },
    {
        "name": "ธนาคารกรุงเทพ จำกัด (มหาชน)",
        "name_th": "ธนาคารกรุงเทพ จำกัด (มหาชน)",
        "name_en": "Bangkok Bank Public Company Limited (BBL)",
        "domain": "bangkokbank.com",
        "industry": "BANKING",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "LOW",
    },
    {
        "name": "ธนาคารกรุงไทย จำกัด (มหาชน)",
        "name_th": "ธนาคารกรุงไทย จำกัด (มหาชน)",
        "name_en": "Krungthai Bank Public Company Limited (KTB)",
        "domain": "krungthai.com",
        "industry": "BANKING",
        "company_type": "STATE_ENTERPRISE",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "ธนาคารทหารไทยธนชาต จำกัด (มหาชน)",
        "name_th": "ธนาคารทหารไทยธนชาต จำกัด (มหาชน)",
        "name_en": "TMBThanachart Bank Public Company Limited (TTB)",
        "domain": "ttbbank.com",
        "industry": "BANKING",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "LOW",
    },
    {
        "name": "ธนาคารแห่งประเทศไทย (BOT)",
        "name_th": "ธนาคารแห่งประเทศไทย",
        "name_en": "Bank of Thailand",
        "domain": "bot.or.th",
        "industry": "BANKING",
        "company_type": "GOVERNMENT",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "สำนักงานคณะกรรมการกำกับหลักทรัพย์และตลาดหลักทรัพย์ (ก.ล.ต.)",
        "name_th": "สำนักงานคณะกรรมการกำกับหลักทรัพย์และตลาดหลักทรัพย์",
        "name_en": "Securities and Exchange Commission Thailand (SEC)",
        "domain": "sec.or.th",
        "industry": "BANKING",
        "company_type": "GOVERNMENT",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "บริษัท ปตท. จำกัด (มหาชน)",
        "name_th": "บริษัท ปตท. จำกัด (มหาชน)",
        "name_en": "PTT Public Company Limited",
        "domain": "pttplc.com",
        "industry": "ENERGY",
        "company_type": "STATE_ENTERPRISE",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "บริษัท ปูนซิเมนต์ไทย จำกัด (มหาชน) (SCG)",
        "name_th": "บริษัท ปูนซิเมนต์ไทย จำกัด (มหาชน)",
        "name_en": "The Siam Cement Public Company Limited (SCG)",
        "domain": "scg.com",
        "industry": "MANUFACTURING",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "MEDIUM",
    },
    {
        "name": "การไฟฟ้าฝ่ายผลิตแห่งประเทศไทย (กฟผ.)",
        "name_th": "การไฟฟ้าฝ่ายผลิตแห่งประเทศไทย",
        "name_en": "Electricity Generating Authority of Thailand (EGAT)",
        "domain": "egat.co.th",
        "industry": "ENERGY",
        "company_type": "STATE_ENTERPRISE",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "การไฟฟ้าส่วนภูมิภาค (กฟภ.)",
        "name_th": "การไฟฟ้าส่วนภูมิภาค",
        "name_en": "Provincial Electricity Authority (PEA)",
        "domain": "pea.co.th",
        "industry": "ENERGY",
        "company_type": "STATE_ENTERPRISE",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "การไฟฟ้านครหลวง (กฟน.)",
        "name_th": "การไฟฟ้านครหลวง",
        "name_en": "Metropolitan Electricity Authority (MEA)",
        "domain": "mea.or.th",
        "industry": "ENERGY",
        "company_type": "STATE_ENTERPRISE",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "บริษัท ซีพี ออลล์ จำกัด (มหาชน)",
        "name_th": "บริษัท ซีพี ออลล์ จำกัด (มหาชน)",
        "name_en": "CP ALL Public Company Limited",
        "domain": "cpall.co.th",
        "industry": "RETAIL",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "LOW",
    },
    {
        "name": "บริษัท เซ็นทรัล รีเทล คอร์ปอเรชั่น จำกัด (มหาชน)",
        "name_th": "บริษัท เซ็นทรัล รีเทล คอร์ปอเรชั่น จำกัด (มหาชน)",
        "name_en": "Central Retail Corporation Public Company Limited",
        "domain": "centralretail.com",
        "industry": "RETAIL",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "LOW",
    },
    {
        "name": "บริษัท ดับบลิวเอชเอ คอร์ปอเรชั่น จำกัด (มหาชน)",
        "name_th": "บริษัท ดับบลิวเอชเอ คอร์ปอเรชั่น จำกัด (มหาชน)",
        "name_en": "WHA Corporation Public Company Limited",
        "domain": "wha-group.com",
        "industry": "LOGISTICS",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "LOW",
    },
    {
        "name": "บริษัท บิทคับ แคปปิตอล กรุ๊ป โฮลดิ้งส์ จำกัด",
        "name_th": "บริษัท บิทคับ แคปปิตอล กรุ๊ป โฮลดิ้งส์ จำกัด",
        "name_en": "Bitkub Capital Group Holdings Co., Ltd.",
        "domain": "bitkub.com",
        "industry": "FINTECH",
        "company_type": "PRIVATE",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "LOW",
    },
    {
        "name": "สำนักงานคณะกรรมการการรักษาความมั่นคงปลอดภัยไซเบอร์แห่งชาติ (สกมช.)",
        "name_th": "สำนักงานคณะกรรมการการรักษาความมั่นคงปลอดภัยไซเบอร์แห่งชาติ",
        "name_en": "National Cyber Security Agency (NCSA)",
        "domain": "ncsa.or.th",
        "industry": "GOVERNMENT",
        "company_type": "GOVERNMENT",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "สำนักงานพัฒนารัฐบาลดิจิทัล (องค์การมหาชน) (DGA)",
        "name_th": "สำนักงานพัฒนารัฐบาลดิจิทัล (องค์การมหาชน)",
        "name_en": "Digital Government Development Agency (DGA)",
        "domain": "dga.or.th",
        "industry": "GOVERNMENT",
        "company_type": "GOVERNMENT",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "สำนักงานพัฒนาธุรกรรมทางอิเล็กทรอนิกส์ (ETDA)",
        "name_th": "สำนักงานพัฒนาธุรกรรมทางอิเล็กทรอนิกส์",
        "name_en": "Electronic Transactions Development Agency (ETDA)",
        "domain": "etda.or.th",
        "industry": "GOVERNMENT",
        "company_type": "GOVERNMENT",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "สำนักงานคณะกรรมการป้องกันและปราบปรามยาเสพติด (สำนักงาน ป.ป.ส.)",
        "name_th": "สำนักงานคณะกรรมการป้องกันและปราบปรามยาเสพติด",
        "name_en": "Office of the Narcotics Control Board (ONCB)",
        "domain": "oncb.go.th",
        "industry": "GOVERNMENT",
        "company_type": "GOVERNMENT",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "บริษัท ท่าอากาศยานไทย จำกัด (มหาชน) (AOT)",
        "name_th": "บริษัท ท่าอากาศยานไทย จำกัด (มหาชน)",
        "name_en": "Airports of Thailand Public Company Limited (AOT)",
        "domain": "airportthai.co.th",
        "industry": "TRANSPORTATION",
        "company_type": "STATE_ENTERPRISE",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "HIGH",
    },
    {
        "name": "บริษัท กรุงเทพดุสิตเวชการ จำกัด (มหาชน) (BDMS)",
        "name_th": "บริษัท กรุงเทพดุสิตเวชการ จำกัด (มหาชน)",
        "name_en": "Bangkok Dusit Medical Services Public Company Limited (BDMS)",
        "domain": "bdms.co.th",
        "industry": "HEALTHCARE",
        "company_type": "PUBLIC",
        "priority": "TIER_1",
        "active": True,
        "procurement_coverage_status": "LOW",
    },
]

# Every entry below was verified against the live site while it was added.
# ``verified_note`` documents what was observed so a future maintainer can tell
# a genuine source outage from a parser that was never correct.
DEFAULT_SOURCES = [
    {
        "name": "สำนักงาน ป.ป.ส. (ONCB) — ประกาศจัดซื้อจัดจ้าง",
        "source_type": "ONCB",
        "url": "https://www.oncb.go.th/procurement",
        "buyer_domain": "oncb.go.th",
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
        "buyer_domain": None,
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
        "buyer_domain": "ncsa.or.th",
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
        "buyer_domain": "bot.or.th",
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
        "buyer_domain": "dga.or.th",
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
        "buyer_domain": "etda.or.th",
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
        "buyer_domain": "egat.co.th",
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
        "buyer_domain": "pea.co.th",
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
        "buyer_domain": "sec.or.th",
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
        "buyer_domain": "airportthai.co.th",
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
        "buyer_domain": "scg.com",
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

"""Find the procurement page on a company's own website, and prove it is one.

Guessing URLs by hand produces sources that quietly redirect to a homepage and
scrape nothing — which is how a dashboard ends up looking full while carrying no
usable opportunities. This walks each domain the way a person would:

  1. read robots.txt and honour it
  2. try the paths Thai companies actually use for procurement
  3. read the sitemap for anything procurement-shaped
  4. keep only pages that survive verification

A candidate is only reported as usable when the page still exists after
redirects (a redirect to "/" means the page is gone), the body reads like a
procurement notice board, and it contains repeated rows carrying a date. That
last test is what separates a real announcement list from a policy page about
procurement.

    PYTHONPATH=. backend/venv/bin/python backend/discover_procurement_pages.py
    PYTHONPATH=. backend/venv/bin/python backend/discover_procurement_pages.py --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "CyberOppBot/1.0 (public-procurement discovery; respects robots.txt)"

# Verified public entry points found through source search, not guessed paths.
VERIFIED_ENTRY_POINTS = {
    "scb.co.th": "https://www.scb.co.th/th/about-us/news/auction-bidding.html",
    "ais.th": "https://aisprocurement.cloud.ais.th/en",
}

# Paths Thai companies and state enterprises actually use.
CANDIDATE_PATHS = (
    "/procurement", "/procurement/", "/th/procurement", "/th/procurement/",
    "/en/procurement", "/supplier", "/th/supplier", "/suppliers",
    "/eprocurement", "/e-procurement", "/purchasing", "/tender", "/tenders",
    "/bidding", "/bid", "/vendor", "/vendors",
    "/th/about-us/procurement", "/about-us/procurement",
    "/จัดซื้อจัดจ้าง", "/th/จัดซื้อจัดจ้าง",
    "/news/procurement", "/th/news/procurement",
)

SITEMAP_HINT = re.compile(
    r"procure|supplier|vendor|tender|bidding|purchas|จัดซื้อ|จัดจ้าง|ประกวดราคา", re.I
)

# Words that make a page look like a notice board rather than a policy page.
NOTICE_WORDS = re.compile(
    r"ประกวดราคา|ประกาศ\s*จัดซื้อ|จัดซื้อจัดจ้าง|สอบราคา|ยื่นข้อเสนอ|เชิญชวน|"
    r"invitation to bid|request for proposal|\brfp\b|\brfq\b|e-?bidding|tender notice",
    re.I,
)
# A real listing repeats dated rows.
DATE = re.compile(
    r"\d{1,2}\s*(?:ม\.ค\.|ก\.พ\.|มี\.ค\.|เม\.ย\.|พ\.ค\.|มิ\.ย\.|ก\.ค\.|ส\.ค\.|ก\.ย\.|ต\.ค\.|พ\.ย\.|ธ\.ค\.|"
    r"มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม)"
    r"\s*\d{2,4}|\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}"
)
ROW_SELECTORS = (
    "table tbody tr", "table tr", ".views-row", "article", ".item", ".card",
    ".news-item", "li.post", ".list-group-item", ".post", "ul li",
)


@dataclass
class Finding:
    company: str
    url: str
    status: str
    http_status: Optional[int] = None
    redirected_to_root: bool = False
    notice_words: int = 0
    dated_rows: int = 0
    row_selector: str = ""
    note: str = ""

    @property
    def usable(self) -> bool:
        return self.status == "USABLE"


async def _robots(client: httpx.AsyncClient, origin: str) -> Optional[RobotFileParser]:
    parser = RobotFileParser()
    try:
        response = await client.get(urljoin(origin, "/robots.txt"))
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        # No policy published is not a prohibition.
        parser.parse([])
        return parser
    parser.parse(response.text.splitlines())
    return parser


def _allowed(parser: Optional[RobotFileParser], url: str) -> bool:
    if parser is None:
        return False
    try:
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return False


def _assess(html: str) -> tuple[int, int, str]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    words = len(NOTICE_WORDS.findall(text))
    best_rows, best_selector = 0, ""
    for selector in ROW_SELECTORS:
        rows = [
            element
            for element in soup.select(selector)
            if DATE.search(element.get_text(" ", strip=True))
            and NOTICE_WORDS.search(element.get_text(" ", strip=True))
        ]
        if len(rows) > best_rows:
            best_rows, best_selector = len(rows), selector
    return words, best_rows, best_selector


async def _check(
    client: httpx.AsyncClient, company: str, url: str, parser: Optional[RobotFileParser]
) -> Finding:
    if not _allowed(parser, url):
        return Finding(company, url, "ROBOTS_DENIED", note="robots.txt disallows this path")
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        return Finding(company, url, "UNREACHABLE", note=type(exc).__name__)

    final = str(response.url)
    # A procurement path that lands on the site root no longer exists; treating
    # it as a source would scrape the homepage forever.
    root = f"{urlsplit(final).scheme}://{urlsplit(final).netloc}/"
    redirected = final.rstrip("/") == root.rstrip("/") and url.rstrip("/") != root.rstrip("/")
    if response.status_code >= 400:
        return Finding(company, url, "NOT_FOUND", response.status_code)
    if redirected:
        return Finding(company, url, "REDIRECTS_TO_ROOT", response.status_code, True,
                       note=f"-> {final}")

    words, rows, selector = _assess(response.text)
    if rows >= 3:
        status = "USABLE"
    elif words >= 3:
        status = "NOTICE_TEXT_NO_ROWS"
    else:
        status = "NOT_A_NOTICE_BOARD"
    return Finding(company, final, status, response.status_code, False, words, rows, selector)


async def _sitemap_candidates(
    client: httpx.AsyncClient, origin: str, parser: Optional[RobotFileParser], limit: int = 6
) -> list[str]:
    """Ask the site's own sitemap where its procurement pages are."""
    found: list[str] = []
    seeds = [urljoin(origin, "/sitemap.xml"), urljoin(origin, "/sitemap_index.xml")]
    for seed in seeds:
        if not _allowed(parser, seed):
            continue
        try:
            response = await client.get(seed)
        except httpx.HTTPError:
            continue
        if response.status_code >= 400:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", response.text)
        # One level of sitemap-index expansion, biased to procurement-ish files.
        nested = [loc for loc in locs if loc.endswith(".xml") and SITEMAP_HINT.search(loc)][:2]
        for child in nested:
            try:
                locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", (await client.get(child)).text)
            except httpx.HTTPError:
                continue
        for loc in locs:
            if SITEMAP_HINT.search(loc) and not loc.endswith(".xml") and loc not in found:
                found.append(loc)
            if len(found) >= limit:
                return found
    return found


async def discover(company: str, homepage: str, semaphore: asyncio.Semaphore) -> list[Finding]:
    origin = f"{urlsplit(homepage).scheme}://{urlsplit(homepage).netloc}"
    results: list[Finding] = []
    domain = urlsplit(homepage).hostname.removeprefix("www.")
    async with semaphore:
        async with httpx.AsyncClient(
            timeout=25, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            parser = await _robots(client, origin)
            if parser is None:
                return [Finding(company, origin, "UNREACHABLE", note="robots.txt unreachable")]

            seen: set[str] = set()
            # Follow actual site navigation before resorting to common paths.
            # A failed path probe is never proof that a company has no notices.
            candidates = []
            verified = VERIFIED_ENTRY_POINTS.get(domain)
            if verified:
                verified_origin = f"{urlsplit(verified).scheme}://{urlsplit(verified).netloc}"
                verified_policy = await _robots(client, verified_origin)
                results.append(await _check(client, company, verified, verified_policy))
                seen.add(verified)
            if _allowed(parser, homepage):
                try:
                    root_page = await client.get(homepage)
                    root_soup = BeautifulSoup(root_page.text, "lxml")
                    for link in root_soup.select("a[href]"):
                        candidate = urljoin(homepage, link["href"])
                        if urlsplit(candidate).netloc == urlsplit(homepage).netloc and SITEMAP_HINT.search(link.get_text(" ", strip=True) + candidate):
                            candidates.append(candidate)
                except httpx.HTTPError:
                    pass
            for url in candidates[:20] + [urljoin(origin, path) for path in CANDIDATE_PATHS]:
                if url in seen:
                    continue
                seen.add(url)
                finding = await _check(client, company, url, parser)
                if finding.status in {"USABLE", "NOTICE_TEXT_NO_ROWS"}:
                    results.append(finding)
                if finding.usable:
                    return results  # A verified board is enough for this company.

            for url in await _sitemap_candidates(client, origin, parser):
                if url in seen:
                    continue
                seen.add(url)
                finding = await _check(client, company, url, parser)
                if finding.status in {"USABLE", "NOTICE_TEXT_NO_ROWS"}:
                    results.append(finding)
                if finding.usable:
                    break
    return results or [Finding(company, origin, "NOT_FOUND_IN_CHECKED_PATHS", note="Limited discovery only; not evidence that no public procurement channel exists")]


COMPANIES: dict[str, str] = {
    # Ministries and departments: legally required to publish invitations, and
    # most run a simple CMS whose announcement page is a plain dated list.
    "กรมบัญชีกลาง": "https://www.cgd.go.th",
    "สำนักงานปลัดสำนักนายกฯ": "https://www.opm.go.th",
    "กระทรวงดิจิทัลฯ": "https://www.mdes.go.th",
    "กระทรวงการคลัง": "https://www.mof.go.th",
    "กรมสรรพากร": "https://www.rd.go.th",
    "กรมศุลกากร": "https://www.customs.go.th",
    "กรมสรรพสามิต": "https://www.excise.go.th",
    "กรมที่ดิน": "https://www.dol.go.th",
    "กรมการปกครอง": "https://www.dopa.go.th",
    "กรมพัฒนาธุรกิจการค้า": "https://www.dbd.go.th",
    "กรมการค้าภายใน": "https://www.dit.go.th",
    "กรมทางหลวง": "https://www.doh.go.th",
    "กรมทางหลวงชนบท": "https://www.drr.go.th",
    "กรมชลประทาน": "https://www.rid.go.th",
    "กรมอุตุนิยมวิทยา": "https://www.tmd.go.th",
    "กรมควบคุมโรค": "https://ddc.moph.go.th",
    "กรมการแพทย์": "https://www.dms.go.th",
    "สำนักงานปลัดสาธารณสุข": "https://ops.moph.go.th",
    "สำนักงานประกันสังคม": "https://www.sso.go.th",
    "กรมสุขภาพจิต": "https://www.dmh.go.th",
    "สำนักงาน ก.พ.": "https://www.ocsc.go.th",
    "สำนักงบประมาณ": "https://www.bb.go.th",
    "สำนักงานตำรวจแห่งชาติ": "https://www.royalthaipolice.go.th",
    "กรมสอบสวนคดีพิเศษ (DSI)": "https://www.dsi.go.th",
    "สำนักงาน ปปง.": "https://www.amlo.go.th",
    "สำนักงาน ป.ป.ช.": "https://www.nacc.go.th",
    "กรมบังคับคดี": "https://www.led.go.th",
    "สำนักงานศาลยุติธรรม": "https://www.coj.go.th",
    "สำนักงานอัยการสูงสุด": "https://www.ago.go.th",
    "กรมราชทัณฑ์": "https://www.correct.go.th",
    "สพฐ.": "https://www.obec.go.th",
    "สำนักงานปลัดศึกษาธิการ": "https://www.moe.go.th",
    "สกสค.": "https://www.otep.go.th",
    "กรมส่งเสริมการปกครองท้องถิ่น": "https://www.dla.go.th",
    "กรมพัฒนาชุมชน": "https://www.cdd.go.th",
    "กรมการจัดหางาน": "https://www.doe.go.th",
    "กรมสวัสดิการและคุ้มครองแรงงาน": "https://www.labour.go.th",
    "กรมพัฒนาฝีมือแรงงาน": "https://www.dsd.go.th",
    "กรมอุทยานแห่งชาติ": "https://www.dnp.go.th",
    "กรมป่าไม้": "https://www.forest.go.th",
    "กรมควบคุมมลพิษ": "https://www.pcd.go.th",
    "กรมโรงงานอุตสาหกรรม": "https://www.diw.go.th",
    "สำนักงานเศรษฐกิจอุตสาหกรรม": "https://www.oie.go.th",
    "กรมการท่องเที่ยว": "https://www.dot.go.th",
    "กรมประชาสัมพันธ์": "https://www.prd.go.th",
    "สำนักงานสถิติแห่งชาติ": "https://www.nso.go.th",
    "กรมวิทยาศาสตร์บริการ": "https://www.dss.go.th",
    "สำนักงาน กสทช.": "https://www.nbtc.go.th",
    "สำนักงาน ก.ล.ต.": "https://www.sec.or.th",
    "สำนักงาน คปภ.": "https://www.oic.or.th",
    "สปสช.": "https://www.nhso.go.th",
    "สสส.": "https://www.thaihealth.or.th",
    "สวทช. (NSTDA)": "https://www.nstda.or.th",
    "GISTDA": "https://www.gistda.or.th",
    "depa": "https://www.depa.or.th",
    "สถาบันการแพทย์ฉุกเฉิน": "https://www.niems.go.th",
    "การกีฬาแห่งประเทศไทย": "https://www.sat.or.th",
    "องค์การเภสัชกรรม": "https://www.gpo.or.th",
    "สภากาชาดไทย": "https://www.redcross.or.th",
    "ราชวิทยาลัยจุฬาภรณ์": "https://www.cra.ac.th",
    # State enterprises and state-owned companies
    "NT": "https://www.ntplc.co.th",
    "MEA": "https://www.mea.or.th",
    "PWA": "https://www.pwa.co.th",
    "MWA": "https://www.mwa.co.th",
    "SRT": "https://www.railway.co.th",
    "รฟม. (MRTA)": "https://www.mrta.co.th",
    "ขสมก.": "https://www.bmta.co.th",
    "Thailand Post": "https://www.thailandpost.co.th",
    "การท่าเรือ": "https://www.port.co.th",
    "กนอ. (IEAT)": "https://www.ieat.go.th",
    "ธ.ออมสิน": "https://www.gsb.or.th",
    "ธ.ก.ส.": "https://www.baac.or.th",
    "ธอส.": "https://www.ghbank.co.th",
    "EXIM Bank": "https://www.exim.go.th",
    "อสมท": "https://www.mcot.net",
    "การยาสูบ": "https://www.thaitobacco.or.th",
    "สลากกินแบ่ง": "https://www.glo.or.th",
    "ททท.": "https://www.tat.or.th",
    # Universities: large IT/security buyers that publish their own boards
    "จุฬาลงกรณ์": "https://www.chula.ac.th",
    "มหิดล": "https://mahidol.ac.th",
    "ธรรมศาสตร์": "https://tu.ac.th",
    "เกษตรศาสตร์": "https://www.ku.ac.th",
    "เชียงใหม่": "https://www.cmu.ac.th",
    "ขอนแก่น": "https://www.kku.ac.th",
    "สงขลานครินทร์": "https://www.psu.ac.th",
    "พระจอมเกล้าธนบุรี": "https://www.kmutt.ac.th",
    "พระจอมเกล้าลาดกระบัง": "https://www.kmitl.ac.th",
    "ศรีนครินทรวิโรฒ": "https://www.swu.ac.th",
    # --- Added from measured demand: the e-GP spending record for FY2568-69
    # shows who actually buys cyber work. Within a one-year window the buyers
    # break down as 1,123 ordinary departments, 316 hospitals, 125 schools and
    # colleges, and the armed forces alone account for ~350 records. The list
    # below targets those groups; a domain that does not resolve or has no
    # dated notice list simply drops out of the findings.
    "กองบัญชาการกองทัพไทย": "https://www.rtarf.mi.th",
    "กองทัพบก": "https://www.rta.mi.th",
    "กองทัพเรือ": "https://www.navy.mi.th",
    "กองทัพอากาศ": "https://www.rtaf.mi.th",
    "กระทรวงกลาโหม": "https://www.mod.go.th",
    "กอ.รมน.": "https://www.isoc.go.th",
    "สำนักข่าวกรองแห่งชาติ": "https://www.nia.go.th",
    "กระทรวงสาธารณสุข": "https://www.moph.go.th",
    "กรมสนับสนุนบริการสุขภาพ": "https://hss.moph.go.th",
    "กรมอนามัย": "https://www.anamai.moph.go.th",
    "กรมวิทยาศาสตร์การแพทย์": "https://www.dmsc.moph.go.th",
    "กรมการแพทย์แผนไทย": "https://www.dtam.moph.go.th",
    "โรงพยาบาลราชวิถี": "https://www.rajavithi.go.th",
    "สถาบันมะเร็งแห่งชาติ": "https://www.nci.go.th",
    "โรงพยาบาลศิริราช": "https://www.si.mahidol.ac.th",
    "โรงพยาบาลรามาธิบดี": "https://www.rama.mahidol.ac.th",
    "สำนักงานคณะกรรมการการอาชีวศึกษา": "https://www.vec.go.th",
    "กระทรวง อว.": "https://www.mhesi.go.th",
    "จุฬาลงกรณ์มหาวิทยาลัย": "https://www.chula.ac.th",
    "มหาวิทยาลัยมหิดล": "https://www.mahidol.ac.th",
    "มหาวิทยาลัยเกษตรศาสตร์": "https://www.ku.ac.th",
    "มหาวิทยาลัยธรรมศาสตร์": "https://www.tu.ac.th",
    "มหาวิทยาลัยเชียงใหม่": "https://www.cmu.ac.th",
    "มหาวิทยาลัยขอนแก่น": "https://www.kku.ac.th",
    "มหาวิทยาลัยสงขลานครินทร์": "https://www.psu.ac.th",
    "มหาวิทยาลัยบูรพา": "https://www.buu.ac.th",
    "มหาวิทยาลัยนเรศวร": "https://www.nu.ac.th",
    "มหาวิทยาลัยมหาสารคาม": "https://www.msu.ac.th",
    "มหาวิทยาลัยศิลปากร": "https://www.su.ac.th",
    "มหาวิทยาลัยศรีนครินทรวิโรฒ": "https://www.swu.ac.th",
    "มจธ.": "https://www.kmutt.ac.th",
    "มจพ.": "https://www.kmutnb.ac.th",
    "มหาวิทยาลัยวลัยลักษณ์": "https://www.wu.ac.th",
    "มหาวิทยาลัยแม่ฟ้าหลวง": "https://www.mfu.ac.th",
    "มหาวิทยาลัยเทคโนโลยีสุรนารี": "https://www.sut.ac.th",
    "มหาวิทยาลัยรามคำแหง": "https://www.ru.ac.th",
    "มหาวิทยาลัยสุโขทัยธรรมาธิราช": "https://www.stou.ac.th",
    "นิด้า (NIDA)": "https://www.nida.ac.th",
    "มหาวิทยาลัยแม่โจ้": "https://www.mju.ac.th",
    "มหาวิทยาลัยอุบลราชธานี": "https://www.ubu.ac.th",
    "มหาวิทยาลัยพะเยา": "https://www.up.ac.th",
    "การไฟฟ้านครหลวง (MEA)": "https://www.mea.or.th",
    "ธนาคารออมสิน": "https://www.gsb.or.th",
    "ธ.ก.ส.": "https://www.baac.or.th",
    "ธอส.": "https://www.ghbank.co.th",
    "NT (โทรคมนาคมแห่งชาติ)": "https://www.ntplc.co.th",
    "ไปรษณีย์ไทย": "https://www.thailandpost.co.th",
    "การประปานครหลวง": "https://www.mwa.co.th",
    "การประปาส่วนภูมิภาค": "https://www.pwa.co.th",
    "การท่าเรือแห่งประเทศไทย": "https://www.port.co.th",
    "การรถไฟแห่งประเทศไทย": "https://www.railway.co.th",
    "ขสมก.": "https://www.bmta.co.th",
    "กรุงเทพมหานคร": "https://www.bangkok.go.th",
    "อสมท": "https://www.mcot.net",
    "ททท.": "https://www.tat.or.th",
    "สำนักงานสลากกินแบ่งรัฐบาล": "https://www.glo.or.th",
    "การยาสูบแห่งประเทศไทย": "https://www.thaitobacco.or.th",
    "ตลาดหลักทรัพย์แห่งประเทศไทย": "https://www.set.or.th",
    "กรมทรัพยากรทางทะเลและชายฝั่ง": "https://www.dmcr.go.th",
    "กรมทรัพยากรน้ำ": "https://www.dwr.go.th",
    "กรมทรัพยากรน้ำบาดาล": "https://www.dgr.go.th",
    "กรมคุมประพฤติ": "https://www.probation.go.th",
    "กรมพินิจและคุ้มครองเด็กและเยาวชน": "https://www.djop.go.th",
    "กรมกิจการผู้สูงอายุ": "https://www.dop.go.th",
    "กรมกิจการเด็กและเยาวชน": "https://www.dcy.go.th",
    "กรมส่งเสริมการค้าระหว่างประเทศ": "https://www.ditp.go.th",
    "กรมเจรจาการค้าระหว่างประเทศ": "https://www.dtn.go.th",
    "กรมศิลปากร": "https://www.finearts.go.th",
    "กรมการขนส่งทางบก": "https://www.dlt.go.th",
    "กรมเจ้าท่า": "https://www.md.go.th",
    "กรมท่าอากาศยาน": "https://www.airports.go.th",
    "กรมพัฒนาพลังงานทดแทน": "https://www.dede.go.th",
    "สำนักงานนโยบายและแผนพลังงาน": "https://www.eppo.go.th",
    "กรมธุรกิจพลังงาน": "https://www.doeb.go.th",
    "กรมเชื้อเพลิงธรรมชาติ": "https://www.dmf.go.th",
    "กรมวิชาการเกษตร": "https://www.doa.go.th",
    "กรมส่งเสริมการเกษตร": "https://www.doae.go.th",
    "กรมประมง": "https://www.fisheries.go.th",
    "กรมปศุสัตว์": "https://www.dld.go.th",
    "กรมการข้าว": "https://www.ricethailand.go.th",
    "กรมพัฒนาที่ดิน": "https://www.ldd.go.th",
    "สำนักงานเศรษฐกิจการเกษตร": "https://www.oae.go.th",
    "กรมป้องกันและบรรเทาสาธารณภัย": "https://www.disaster.go.th",
    "กรมโยธาธิการและผังเมือง": "https://www.dpt.go.th",
    "สำนักงานปรมาณูเพื่อสันติ": "https://www.oap.go.th",
    "สถาบันมาตรวิทยาแห่งชาติ": "https://www.nimt.or.th",
    "สำนักงานมาตรฐานผลิตภัณฑ์อุตสาหกรรม": "https://www.tisi.go.th",
    "กรมทรัพย์สินทางปัญญา": "https://www.ipthailand.go.th",
    "เทศบาลนครอุดรธานี": "https://www.udoncity.go.th",
    "เมืองพัทยา": "https://www.pattaya.go.th",
    "เทศบาลนครนนทบุรี": "https://www.nakornnont.go.th",
}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="Write the full findings to this file.")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--sector", choices=["private", "government", "all"], default="private", help="Default: registered private-sector buyer domains")
    args = parser.parse_args()

    from backend.app.data.seed_data import INITIAL_BUYERS
    private_companies = {b["name"]: "https://www." + b["domain"] for b in INITIAL_BUYERS if b.get("domain") and b["company_type"] in {"PRIVATE", "PUBLIC"}}
    targets = private_companies if args.sector == "private" else COMPANIES if args.sector == "government" else {**COMPANIES, **private_companies}
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    batches = await asyncio.gather(
        *[discover(name, home, semaphore) for name, home in targets.items()]
    )
    findings = [item for batch in batches for item in batch]

    usable = [f for f in findings if f.usable]
    partial = [f for f in findings if f.status == "NOTICE_TEXT_NO_ROWS"]

    print(f"\n{'=' * 78}\nUSABLE — a real, dated announcement list ({len(usable)})\n{'=' * 78}")
    for f in sorted(usable, key=lambda x: -x.dated_rows):
        print(f"  {f.dated_rows:>3} rows  {f.company:<18} {f.url}")
        print(f"            selector: {f.row_selector}")

    print(f"\n{'=' * 78}\nTALKS ABOUT PROCUREMENT BUT LISTS NOTHING ({len(partial)})\n{'=' * 78}")
    for f in sorted(partial, key=lambda x: -x.notice_words)[:15]:
        print(f"  {f.notice_words:>3} words  {f.company:<18} {f.url}")

    from collections import Counter
    print(f"\n{'=' * 78}\nWHY THE REST FAILED\n{'=' * 78}")
    for status, n in Counter(
        f.status for f in findings if f.status not in {"USABLE", "NOTICE_TEXT_NO_ROWS"}
    ).most_common():
        print(f"  {n:>3}  {status}")

    print(f"\ncompanies probed: {len(targets)}   with a usable board: "
          f"{len({f.company for f in usable})}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump([asdict(f) for f in findings], handle, ensure_ascii=False, indent=2)
        print(f"full findings written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

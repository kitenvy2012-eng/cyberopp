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
    async with semaphore:
        async with httpx.AsyncClient(
            timeout=25, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            parser = await _robots(client, origin)
            if parser is None:
                return [Finding(company, origin, "UNREACHABLE", note="robots.txt unreachable")]

            seen: set[str] = set()
            for url in (urljoin(origin, path) for path in CANDIDATE_PATHS):
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
    return results or [Finding(company, origin, "NO_PROCUREMENT_PAGE")]


COMPANIES: dict[str, str] = {
    # Listed private groups
    "SCG": "https://www.scg.com",
    "PTT": "https://www.pttplc.com",
    "PTTEP": "https://www.pttep.com",
    "CP All": "https://www.cpall.co.th",
    "CPF": "https://www.cpfworldwide.com",
    "True Corporation": "https://www.truecorp.co.th",
    "AIS": "https://www.ais.th",
    "Central Pattana": "https://www.cpn.co.th",
    "ThaiBev": "https://www.thaibev.com",
    "BDMS": "https://www.bdms.co.th",
    "Bumrungrad": "https://www.bumrungrad.com",
    "Gulf": "https://www.gulf.co.th",
    "B.Grimm": "https://www.bgrimmpower.com",
    "IRPC": "https://www.irpc.co.th",
    "Thai Oil": "https://www.thaioilgroup.com",
    "GC": "https://www.pttgcgroup.com",
    "Banpu": "https://www.banpu.com",
    "Minor": "https://www.minor.com",
    "SCB": "https://www.scb.co.th",
    "KBank": "https://www.kasikornbank.com",
    "Bangkok Bank": "https://www.bangkokbank.com",
    "Krungthai": "https://krungthai.com",
    "TTB": "https://www.ttbbank.com",
    "Krungsri": "https://www.krungsri.com",
    # State-owned companies and enterprises: legally must publish
    "AOT": "https://www.airportthai.co.th",
    "Thai Airways": "https://www.thaiairways.com",
    "NT": "https://www.ntplc.co.th",
    "MEA": "https://www.mea.or.th",
    "PWA": "https://www.pwa.co.th",
    "MWA": "https://www.mwa.co.th",
    "SRT": "https://www.railway.co.th",
    "Thailand Post": "https://www.thailandpost.co.th",
    "MCOT": "https://www.mcot.net",
    "GSB": "https://www.gsb.or.th",
    "BAAC": "https://www.baac.or.th",
    "GHB": "https://www.ghbank.co.th",
    "EXIM": "https://www.exim.go.th",
    "IEAT": "https://www.ieat.go.th",
    "TAT": "https://www.tat.or.th",
    "Thai Tobacco": "https://www.thaitobacco.or.th",
}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="Write the full findings to this file.")
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    batches = await asyncio.gather(
        *[discover(name, home, semaphore) for name, home in COMPANIES.items()]
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

    print(f"\ncompanies probed: {len(COMPANIES)}   with a usable board: "
          f"{len({f.company for f in usable})}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump([asdict(f) for f in findings], handle, ensure_ascii=False, indent=2)
        print(f"full findings written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

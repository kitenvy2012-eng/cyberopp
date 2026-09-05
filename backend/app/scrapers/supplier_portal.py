"""Read a public supplier entry page without logging in or inventing tenders."""
from bs4 import BeautifulSoup
from backend.app.scrapers.base import BaseScraper, ScrapeStatus, ScrapeError
from backend.app.scrapers.web_fetcher import SafeWebClient, FetchFailure


class SupplierPortalScraper(BaseScraper):
    async def scrape(self):
        outcome = self.new_outcome()
        async with SafeWebClient(timeout_seconds=15, max_retries=0) as client:
            try:
                document = await client.fetch(self.url)
                soup = BeautifulSoup(document.text, "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                if "procurement" not in title.lower():
                    raise FetchFailure("PORTAL_NOT_RECOGNIZED", "Expected the official procurement entry page", url=document.url)
                outcome.access_status = "REGISTRATION_ONLY"
            except FetchFailure as exc:
                outcome.errors.append(exc.to_scrape_error())
            outcome.pages_fetched = client.pages_fetched
        return self.finish_outcome(outcome, status=ScrapeStatus.FAILED if outcome.errors else ScrapeStatus.SUCCESS)

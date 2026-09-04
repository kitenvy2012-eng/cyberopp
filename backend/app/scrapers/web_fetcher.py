"""Polite, robots-aware HTTP fetching with SSRF and size protections."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from backend.app.scrapers.base import (
    ScrapeError,
    URLValidationError,
    canonicalize_url,
    redact_url,
)


DEFAULT_USER_AGENT = "CyberOppBot/1.0 (public-procurement discovery; respects robots.txt)"


@dataclass(frozen=True)
class FetchedDocument:
    requested_url: str
    url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";", 1)[0].strip().lower()

    @property
    def text(self) -> str:
        content_type = self.headers.get("content-type", "")
        charset = "utf-8"
        for part in content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                charset = value.strip(" \"'")
                break
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


class FetchFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        url: Optional[str] = None,
        retryable: bool = False,
        http_status: Optional[int] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.url = redact_url(url) if url else None
        self.retryable = retryable
        self.http_status = http_status

    def to_scrape_error(self) -> ScrapeError:
        return ScrapeError(
            code=self.code,
            message=self.message,
            url=self.url,
            retryable=self.retryable,
            http_status=self.http_status,
        )


@dataclass
class _RobotsPolicy:
    parser: RobotFileParser
    delay_seconds: float = 0.0
    sitemaps: List[str] = None

    def __post_init__(self) -> None:
        if self.sitemaps is None:
            self.sitemaps = []


class SafeWebClient:
    """HTTP client that validates every redirect and obeys robots.txt by default."""

    def __init__(
        self,
        *,
        client: Optional[httpx.AsyncClient] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 8 * 1024 * 1024,
        max_redirects: int = 5,
        max_retries: int = 2,
        request_delay_seconds: float = 0.25,
        robots_fail_open: bool = False,
        resolve_dns: bool = True,
    ):
        self.user_agent = user_agent
        self.max_response_bytes = max(1024, int(max_response_bytes))
        self.max_redirects = max(0, int(max_redirects))
        self.max_retries = max(0, int(max_retries))
        self.request_delay_seconds = max(0.0, float(request_delay_seconds))
        self.robots_fail_open = bool(robots_fail_open)
        self.resolve_dns = bool(resolve_dns)
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml,application/atom+xml,application/json;q=0.9,*/*;q=0.5",
                "Accept-Language": "th-TH,th;q=0.9,en;q=0.7",
            },
        )
        self.pages_fetched = 0
        self.pages_skipped = 0
        self._cache: Dict[str, FetchedDocument] = {}
        self._robots: Dict[str, _RobotsPolicy] = {}
        self._last_request_at: Dict[str, float] = {}
        self._origin_locks: Dict[str, asyncio.Lock] = {}

    async def __aenter__(self) -> "SafeWebClient":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def fetch(
        self,
        url: str,
        *,
        respect_robots: bool = True,
        headers: Optional[Mapping[str, str]] = None,
        use_cache: bool = True,
        method: str = "GET",
        data: Optional[Mapping[str, Any]] = None,
    ) -> FetchedDocument:
        method = method.upper()
        if method not in {"GET", "POST"}:
            raise FetchFailure("INVALID_METHOD", "Only GET and POST requests are supported", url=url)
        try:
            target = canonicalize_url(url)
        except URLValidationError as exc:
            raise FetchFailure("INVALID_URL", str(exc), url=url) from exc
        cacheable = use_cache and method == "GET" and data is None
        if cacheable and target in self._cache:
            return self._cache[target]

        requested_url = target
        visited = set()
        for _ in range(self.max_redirects + 1):
            if target in visited:
                raise FetchFailure("REDIRECT_LOOP", "Redirect loop detected", url=target)
            visited.add(target)
            await self._ensure_public_url(target)

            delay = self.request_delay_seconds
            if respect_robots:
                policy = await self._robots_policy(target)
                if not policy.parser.can_fetch(self.user_agent, target):
                    self.pages_skipped += 1
                    raise FetchFailure(
                        "ROBOTS_DENIED",
                        "robots.txt does not permit crawling this URL",
                        url=target,
                    )
                delay = max(delay, policy.delay_seconds)

            response = await self._request(
                target,
                method=method,
                headers=headers,
                data=data,
                delay_seconds=delay,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                await response.aclose()
                if not location:
                    raise FetchFailure(
                        "INVALID_REDIRECT",
                        "Redirect response has no Location header",
                        url=target,
                        http_status=response.status_code,
                    )
                try:
                    target = canonicalize_url(location, target)
                except URLValidationError as exc:
                    raise FetchFailure("INVALID_REDIRECT", str(exc), url=target) from exc
                if response.status_code in {301, 302, 303}:
                    method = "GET"
                    data = None
                continue

            document = await self._read_response(response, requested_url=requested_url, final_url=target)
            self.pages_fetched += 1
            if cacheable:
                self._cache[requested_url] = document
                self._cache[target] = document
            return document

        raise FetchFailure("TOO_MANY_REDIRECTS", "Too many redirects", url=target)

    async def sitemaps_for(self, url: str) -> List[str]:
        """Return public sitemap URLs explicitly declared by this origin."""
        policy = await self._robots_policy(canonicalize_url(url))
        return list(policy.sitemaps)

    async def _ensure_public_url(self, url: str) -> None:
        """Resolve hostnames and reject any non-global target before connecting."""
        if not self.resolve_dns:
            return
        parts = urlsplit(url)
        hostname = parts.hostname
        if not hostname:
            raise FetchFailure("INVALID_URL", "URL has no hostname", url=url)
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None
        if literal is not None:
            if not literal.is_global:
                raise FetchFailure("UNSAFE_ADDRESS", "URL resolves to a non-public address", url=url)
            return

        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except (OSError, socket.gaierror) as exc:
            raise FetchFailure(
                "DNS_ERROR",
                "Could not resolve source hostname",
                url=url,
                retryable=True,
            ) from exc
        addresses = {info[4][0].split("%", 1)[0] for info in infos if info[4]}
        if not addresses:
            raise FetchFailure("DNS_ERROR", "Source hostname returned no addresses", url=url, retryable=True)
        for address_text in addresses:
            try:
                address = ipaddress.ip_address(address_text)
            except ValueError as exc:
                raise FetchFailure("DNS_ERROR", "Resolver returned an invalid address", url=url) from exc
            if not address.is_global:
                raise FetchFailure(
                    "UNSAFE_ADDRESS",
                    "Source hostname resolves to a non-public address",
                    url=url,
                )

    async def _robots_policy(self, url: str) -> _RobotsPolicy:
        parts = urlsplit(url)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        if origin in self._robots:
            return self._robots[origin]

        robots_url = f"{origin}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            await self._ensure_public_url(robots_url)
            response = await self._request(
                robots_url,
                method="GET",
                headers={"Accept": "text/plain,*/*;q=0.1"},
                data=None,
                delay_seconds=self.request_delay_seconds,
            )
            status = response.status_code
            if status == 200:
                document = await self._read_response(
                    response,
                    requested_url=robots_url,
                    final_url=robots_url,
                    count_http_errors=False,
                )
                robots_lines = document.text.splitlines()
                parser.parse(robots_lines)
                declared_sitemaps = []
                for line in robots_lines:
                    directive, separator, value = line.partition(":")
                    if separator and directive.strip().lower() == "sitemap":
                        try:
                            declared_sitemaps.append(canonicalize_url(value.strip(), robots_url))
                        except URLValidationError:
                            continue
            else:
                await response.aclose()
                if status in {401, 403} or status >= 500:
                    if not self.robots_fail_open:
                        raise FetchFailure(
                            "ROBOTS_UNAVAILABLE",
                            "robots.txt could not be consulted safely",
                            url=robots_url,
                            retryable=status >= 500,
                            http_status=status,
                        )
                # RFC 9309 treats other 4xx responses as no robots file.
                parser.parse(["User-agent: *", "Allow: /"])
                declared_sitemaps = []
        except FetchFailure:
            if not self.robots_fail_open:
                raise
            parser.parse(["User-agent: *", "Allow: /"])
            declared_sitemaps = []

        delay = parser.crawl_delay(self.user_agent) or parser.crawl_delay("*") or 0.0
        request_rate = parser.request_rate(self.user_agent) or parser.request_rate("*")
        if request_rate and request_rate.requests > 0:
            delay = max(delay, request_rate.seconds / request_rate.requests)
        policy = _RobotsPolicy(
            parser=parser,
            delay_seconds=float(delay),
            sitemaps=list(dict.fromkeys(declared_sitemaps)),
        )
        self._robots[origin] = policy
        return policy

    async def _request(
        self,
        url: str,
        *,
        method: str,
        headers: Optional[Mapping[str, str]],
        data: Optional[Mapping[str, Any]],
        delay_seconds: float,
    ) -> httpx.Response:
        origin = _origin(url)
        lock = self._origin_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            await self._throttle(origin, delay_seconds)
            for attempt in range(self.max_retries + 1):
                try:
                    request = self.client.build_request(method, url, headers=headers, data=data)
                    response = await self.client.send(request, stream=True, follow_redirects=False)
                except httpx.TimeoutException as exc:
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.5 * (2**attempt))
                        continue
                    raise FetchFailure("TIMEOUT", "Source request timed out", url=url, retryable=True) from exc
                except httpx.HTTPError as exc:
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.5 * (2**attempt))
                        continue
                    raise FetchFailure("NETWORK_ERROR", "Source request failed", url=url, retryable=True) from exc

                self._last_request_at[origin] = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.max_retries:
                        retry_after = _retry_after_seconds(response.headers.get("retry-after"))
                        await response.aclose()
                        await asyncio.sleep(retry_after if retry_after is not None else 0.5 * (2**attempt))
                        continue
                return response
        raise AssertionError("unreachable")

    async def _read_response(
        self,
        response: httpx.Response,
        *,
        requested_url: str,
        final_url: str,
        count_http_errors: bool = True,
    ) -> FetchedDocument:
        status = response.status_code
        if count_http_errors and status >= 400:
            await response.aclose()
            raise FetchFailure(
                "HTTP_ERROR",
                f"Source returned HTTP {status}",
                url=final_url,
                retryable=status == 429 or status >= 500,
                http_status=status,
            )

        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_response_bytes:
                    await response.aclose()
                    raise FetchFailure(
                        "RESPONSE_TOO_LARGE",
                        "Source response exceeds the configured size limit",
                        url=final_url,
                        http_status=status,
                    )
            except ValueError:
                pass

        chunks = []
        size = 0
        try:
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self.max_response_bytes:
                    raise FetchFailure(
                        "RESPONSE_TOO_LARGE",
                        "Source response exceeds the configured size limit",
                        url=final_url,
                        http_status=status,
                    )
                chunks.append(chunk)
        finally:
            await response.aclose()
        return FetchedDocument(
            requested_url=requested_url,
            url=final_url,
            status_code=status,
            headers=dict(response.headers),
            content=b"".join(chunks),
        )

    async def _throttle(self, origin: str, delay_seconds: float) -> None:
        last_request = self._last_request_at.get(origin)
        if last_request is None or delay_seconds <= 0:
            return
        remaining = delay_seconds - (time.monotonic() - last_request)
        if remaining > 0:
            await asyncio.sleep(remaining)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _retry_after_seconds(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return min(max(float(value), 0.0), 30.0)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                return None
            seconds = retry_at.timestamp() - time.time()
            return min(max(seconds, 0.0), 30.0)
        except (TypeError, ValueError, OverflowError):
            return None

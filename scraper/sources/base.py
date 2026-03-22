"""
Abstract base scraper class — shared rate limiting, retry logic, and browser setup.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Iterator

import httpx
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from ..models import RawListing, Source
from ..config import RATE_LIMITS, USER_AGENTS, BROWSER_ARGS, VIEWPORT

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    source: Source

    def __init__(self):
        self._last_request: float = 0.0
        self._client: httpx.Client | None = None

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _wait(self) -> None:
        """Block until the minimum inter-request delay has elapsed."""
        delay = RATE_LIMITS.get(self.source.value, 2.5)
        elapsed = time.monotonic() - self._last_request
        if elapsed < delay:
            sleep_for = delay - elapsed + random.uniform(0.3, 1.2)
            logger.debug(f"[{self.source}] rate limit: sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)
        self._last_request = time.monotonic()

    # ------------------------------------------------------------------
    # HTTP client (for non-JS pages)
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": random.choice(USER_AGENTS)},
                timeout=20,
                follow_redirects=True,
            )
        return self._client

    def fetch(self, url: str, **kwargs) -> httpx.Response:
        self._wait()
        client = self._get_client()
        try:
            resp = client.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            logger.warning(f"[{self.source}] HTTP {e.response.status_code} for {url}")
            raise

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # Playwright helpers (for JS-rendered pages)
    # ------------------------------------------------------------------

    async def fetch_with_browser(self, url: str, wait_selector: str = "body") -> str:
        """Fetch a page using Playwright and return its HTML content."""
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch(
                headless=True,
                args=BROWSER_ARGS,
            )
            context: BrowserContext = await browser.new_context(
                viewport=VIEWPORT,
                user_agent=random.choice(USER_AGENTS),
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            # Block unnecessary resources
            await context.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
                lambda route: route.abort(),
            )
            page: Page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector(wait_selector, timeout=15000)
            html = await page.content()
            await browser.close()
            return html

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def scrape(self, max_pages: int) -> Iterator[RawListing]:
        """
        Yield RawListing objects. Implementations must:
        - Call self._wait() before each HTTP request
        - Stop after max_pages pages
        - Handle errors gracefully (log and continue)
        """
        ...

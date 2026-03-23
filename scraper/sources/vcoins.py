"""
VCoins scraper — fixed-price dealer marketplace.

VCoins is an ASP.NET WebForms site. Search results are loaded via a form
postback, so we use Playwright to submit the search form and then parse
the resulting div.item-detail elements.

is_auction = False since these are fixed dealer prices, not realized auction prices.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import RawListing, Source
from ..config import MAX_PAGES
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL    = "https://www.vcoins.com"
SEARCH_URL  = f"{BASE_URL}/en/search.aspx"
ITEMS_PER_PAGE = 50  # VCoins default page size


class VCoinsScraper(BaseScraper):
    source = Source.VCOINS

    def scrape(self, max_pages: int = MAX_PAGES["vcoins"]) -> Iterator[RawListing]:
        today = date.today()
        for page_num in range(1, max_pages + 1):
            logger.info(f"[VCoins] Fetching page {page_num} via Playwright form submit")
            try:
                html = asyncio.run(self._fetch_page(page_num))
            except Exception as e:
                logger.error(f"[VCoins] Playwright fetch failed page {page_num}: {e}")
                break

            soup = BeautifulSoup(html, "lxml")
            items = soup.select("div.item-detail")

            if not items:
                logger.info(f"[VCoins] No items on page {page_num}")
                break

            yielded = 0
            for item in items:
                listing = self._parse_item(item, today)
                if listing:
                    yield listing
                    yielded += 1

            logger.info(f"[VCoins] Page {page_num}: {yielded} listings")
            if yielded < 3:
                break

    async def _fetch_page(self, page_num: int) -> str:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            page = await context.new_page()

            # Load the search page and submit the form
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
            await page.fill('input[type="text"]', "NGC ancient")

            if page_num > 1:
                # VCoins pagination: click the page link after initial results load
                await page.click('input[type="submit"]')
                await page.wait_for_load_state("networkidle", timeout=15000)
                # Try clicking the specific page number
                try:
                    await page.click(f'a[href*="page={page_num}"], a:text("{page_num}")', timeout=5000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
            else:
                await page.click('input[type="submit"]')
                await page.wait_for_load_state("networkidle", timeout=15000)

            html = await page.content()
            await browser.close()
            return html

    def _parse_item(self, item, today: date) -> RawListing | None:
        try:
            # Title and URL — the product link is inside p.description
            link_el = item.select_one("p.description a[href*='/product/']")
            if not link_el:
                return None
            title = link_el.get_text(strip=True)
            href  = link_el.get("href", "")
            lot_url = urljoin(BASE_URL, href) if href else BASE_URL

            if not title:
                return None

            # Price — div.prices may contain a strike-through original and a discounted price
            price_div = item.select_one("div.prices")
            price: float | None = None
            currency = "USD"
            if price_div:
                # Prefer the discounted price span if present
                discounted = price_div.select_one("span.discounted-price")
                price_el = discounted if discounted else price_div.select_one("h3")
                price_text = price_el.get_text(strip=True) if price_el else ""
                price = _parse_vcoins_price(price_text)

            # Image
            img_el = item.select_one("img")
            image_url: str | None = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")
                if image_url and not image_url.startswith("http"):
                    image_url = urljoin(BASE_URL, image_url)

            return RawListing(
                title=title,
                description="",
                price=price,
                currency=currency,
                sale_date=today,
                lot_url=lot_url,
                image_url=image_url,
                source=Source.VCOINS,
                raw_cert_text=title,
                is_auction=False,
            )
        except Exception as e:
            logger.debug(f"[VCoins] Parse error: {e}")
            return None


def _parse_vcoins_price(text: str) -> float | None:
    """Parse VCoins price string like 'US$ 6,975.00' or '$1,250.00'."""
    # Remove currency symbols and labels
    clean = text.replace("US$", "").replace("$", "").replace(",", "").strip()
    m = re.search(r"[\d]+(?:\.\d+)?", clean)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None

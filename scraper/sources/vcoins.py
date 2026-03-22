"""
VCoins scraper — fixed-price dealer marketplace.

VCoins blocks simple HTTP requests (403). We use Playwright to render the page.
is_auction = False since these are fixed dealer prices, not realized auction prices.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import Iterator
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from ..models import RawListing, Source
from ..config import MAX_PAGES
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL   = "https://www.vcoins.com"
SEARCH_URL = f"{BASE_URL}/en/search.aspx"


class VCoinsScraper(BaseScraper):
    source = Source.VCOINS

    def scrape(self, max_pages: int = MAX_PAGES["vcoins"]) -> Iterator[RawListing]:
        today = date.today()
        for page_num in range(1, max_pages + 1):
            params = {"type": "1", "cat": "0", "keywords": "NGC ancient", "page": str(page_num)}
            url = f"{SEARCH_URL}?{urlencode(params)}"
            logger.info(f"[VCoins] Fetching page {page_num} via Playwright")
            try:
                html = asyncio.run(self.fetch_with_browser(url, wait_selector=".search-results, .item, body"))
            except Exception as e:
                logger.error(f"[VCoins] Playwright fetch failed page {page_num}: {e}")
                break

            soup = BeautifulSoup(html, "lxml")

            # VCoins search results — try multiple possible selectors
            items = (soup.select(".search-results .item") or
                     soup.select("div[class*='item']") or
                     soup.select("li[class*='item']") or
                     soup.select(".product"))

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

    def _parse_item(self, item, today: date) -> RawListing | None:
        try:
            # Title / link
            title_el = (item.select_one("a[class*='title']") or
                        item.select_one("h2 a") or item.select_one("h3 a") or
                        item.select_one("a"))
            if not title_el:
                return None
            title   = title_el.get_text(strip=True)
            href    = title_el.get("href", "")
            lot_url = urljoin(BASE_URL, href) if href else BASE_URL

            # Price
            price_el  = (item.select_one("[class*='price']") or
                         item.select_one("span[class*='amount']"))
            price_text = price_el.get_text(strip=True) if price_el else ""
            currency  = "USD" if "$" in price_text else "EUR" if "€" in price_text else "GBP" if "£" in price_text else "USD"
            m = re.search(r"[\d,]+(?:\.\d{2})?", price_text.replace(",", ""))
            price = float(m.group().replace(",", "")) if m else None

            # Description
            desc_el = (item.select_one("[class*='desc']") or item.select_one("p"))
            description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

            # Image
            img_el    = item.select_one("img")
            image_url = img_el.get("src") or img_el.get("data-src") if img_el else None
            if image_url and not image_url.startswith("http"):
                image_url = urljoin(BASE_URL, image_url)

            return RawListing(
                title=title,
                description=description,
                price=price,
                currency=currency,
                sale_date=today,
                lot_url=lot_url,
                image_url=image_url,
                source=Source.VCOINS,
                raw_cert_text=f"{title} {description}",
                is_auction=False,
            )
        except Exception as e:
            logger.debug(f"[VCoins] Parse error: {e}")
            return None

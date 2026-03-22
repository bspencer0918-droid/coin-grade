"""
Roma Numismatics scraper.

Roma posts auction results at romanumismatics.com/auction-house/results
Pages are JS-rendered via React; we use Playwright.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import RawListing, Source
from ..config import MAX_PAGES
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL   = "https://www.romanumismatics.com"
RESULTS_URL = f"{BASE_URL}/auction-house/results"


class RomaScraper(BaseScraper):
    source = Source.ROMA

    def scrape(self, max_pages: int = MAX_PAGES["roma"]) -> Iterator[RawListing]:
        import asyncio

        for page_num in range(1, max_pages + 1):
            url = f"{RESULTS_URL}?page={page_num}&search=NGC"
            logger.info(f"[Roma] Fetching page {page_num}")
            try:
                html = asyncio.run(self.fetch_with_browser(url, wait_selector=".lot, .result-item, main"))
            except Exception as e:
                logger.error(f"[Roma] Browser fetch failed page {page_num}: {e}")
                break

            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".lot, .lot-item, article.result, .auction-result")
            if not items:
                logger.info(f"[Roma] No items on page {page_num}")
                break

            yielded = 0
            for item in items:
                listing = self._parse_item(item)
                if listing:
                    yield listing
                    yielded += 1
            logger.info(f"[Roma] Page {page_num}: {yielded} listings")
            if yielded < 5:
                break

    def _parse_item(self, item) -> RawListing | None:
        try:
            title_el = item.select_one("h2, h3, .lot-title, .title")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)

            link_el = item.select_one("a[href]")
            lot_url = urljoin(BASE_URL, link_el["href"]) if link_el else ""

            # Price (Roma shows in GBP/USD)
            price_el = item.select_one(".hammer-price, .price, .realized")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price, currency = _parse_roma_price(price_text)

            # Date
            date_el = item.select_one(".date, .sale-date, time")
            sale_date = _parse_date(date_el.get("datetime") or date_el.get_text(strip=True) if date_el else "")

            desc_el = item.select_one(".description, .lot-desc, p")
            description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

            img_el = item.select_one("img")
            image_url = img_el.get("src") or img_el.get("data-src") if img_el else None

            return RawListing(
                title=title,
                description=description,
                price=price,
                currency=currency,
                sale_date=sale_date,
                lot_url=lot_url or BASE_URL,
                image_url=image_url,
                source=Source.ROMA,
                raw_cert_text=f"{title} {description}",
                is_auction=True,
            )
        except Exception as e:
            logger.debug(f"[Roma] Parse error: {e}")
            return None


def _parse_roma_price(text: str) -> tuple[float | None, str]:
    currency = "GBP" if "£" in text else "EUR" if "€" in text else "USD"
    m = re.search(r"[\d,]+(?:\.\d{2})?", text.replace(",", ""))
    if m:
        try:
            return float(m.group().replace(",", "")), currency
        except ValueError:
            pass
    return None, currency


def _parse_date(text: str) -> date | None:
    for fmt in ["%Y-%m-%d", "%d %B %Y", "%B %d, %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None

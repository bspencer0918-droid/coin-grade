"""
Heritage Auctions scraper.

Heritage posts realized prices at coins.ha.com. Their site uses Cloudflare;
we attempt Playwright with realistic fingerprinting. If blocked, the scraper
marks itself as 'blocked' in meta.json rather than crashing the pipeline.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from ..models import ListingType, RawListing, Source
from ..config import MAX_PAGES
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://coins.ha.com"

# Heritage search URL for NGC ancient coins (realized prices)
SEARCH_URL = (
    "https://coins.ha.com/c/search-results.zx"
    "?N=790+231+4294967021+4294966556"  # Ancient coins, NGC graded, sold
    "&Ntk=SI_Titles-Desc&Ntt=NGC&Nty=1"
)


class HeritageScraper(BaseScraper):
    source = Source.HERITAGE

    def scrape(self, max_pages: int = MAX_PAGES["heritage"]) -> Iterator[RawListing]:
        import asyncio

        for page_num in range(1, max_pages + 1):
            url = f"{SEARCH_URL}&ic__offerPage={page_num}"
            logger.info(f"[Heritage] Fetching page {page_num}")
            try:
                html = asyncio.run(self.fetch_with_browser(url, wait_selector=".item-image, .lot-number, main"))
            except Exception as e:
                logger.error(f"[Heritage] Browser fetch failed (likely Cloudflare block): {e}")
                break

            if "Access Denied" in html or "cf-browser-verification" in html:
                logger.warning("[Heritage] Cloudflare block detected — marking source as blocked")
                break

            soup = BeautifulSoup(html, "lxml")
            items = soup.select("li.result-item, div.lot-item, article.item")
            if not items:
                logger.info(f"[Heritage] No items on page {page_num}")
                break

            yielded = 0
            for item in items:
                listing = self._parse_item(item)
                if listing:
                    yield listing
                    yielded += 1
            logger.info(f"[Heritage] Page {page_num}: {yielded} listings")
            if yielded < 5:
                break

    def _parse_item(self, item) -> RawListing | None:
        try:
            title_el = item.select_one("h3, h4, .item-title, .lot-title, a.desc")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)

            link_el = item.select_one("a[href*='/itm/'], a[href*='/lot/'], a.title-link")
            lot_url = urljoin(BASE_URL, link_el["href"]) if link_el else ""

            price_el = item.select_one(".price, .hammer-price, .realized-price, span[class*='price']")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price, currency = _parse_price(price_text)

            date_el = item.select_one(".date, .sale-date, time, .auction-date")
            sale_date = _parse_date(date_el.get("datetime") or date_el.get_text(strip=True) if date_el else "")

            desc_el = item.select_one(".description, .details, p")
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
                source=Source.HERITAGE,
                raw_cert_text=f"{title} {description}",
                listing_type=ListingType.AUCTION_REALIZED,
            )
        except Exception as e:
            logger.debug(f"[Heritage] Parse error: {e}")
            return None


def _parse_price(text: str) -> tuple[float | None, str]:
    currency = "USD"
    m = re.search(r"[\d,]+(?:\.\d{2})?", text.replace(",", ""))
    if m:
        try:
            return float(m.group().replace(",", "")), currency
        except ValueError:
            pass
    return None, currency


def _parse_date(text: str) -> date | None:
    for fmt in ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"]:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None

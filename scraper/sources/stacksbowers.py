"""
Stack's Bowers Galleries scraper.

Stack's Bowers is one of the largest US numismatic auction houses.
We search their realized-price archive for NGC- and PCGS-graded coins
(both ancient and US) using their public search results pages.

The site is behind Cloudflare so we use Playwright for page fetching.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import ListingType, RawListing, Source
from ..config import MAX_PAGES
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.stacksbowers.com"

# Search queries: (url, label)
# Realized auction results filtered by keyword
SEARCH_QUERIES = [
    (
        "https://www.stacksbowers.com/Pages/ItemList.aspx"
        "?TYPE=1&CURRENCY=1&kw=NGC+ancient",
        "ancient/NGC",
    ),
    (
        "https://www.stacksbowers.com/Pages/ItemList.aspx"
        "?TYPE=1&CURRENCY=1&kw=NGC",
        "US/NGC",
    ),
    (
        "https://www.stacksbowers.com/Pages/ItemList.aspx"
        "?TYPE=1&CURRENCY=1&kw=PCGS",
        "US/PCGS",
    ),
]

ITEMS_PER_PAGE = 48  # Stack's Bowers default grid size


class StacksBowersScraper(BaseScraper):
    source = Source.STACKSBOWERS

    def scrape(self, max_pages: int = MAX_PAGES["stacksbowers"]) -> Iterator[RawListing]:
        pages_per_query = max(max_pages // len(SEARCH_QUERIES), 10)

        for base_url, label in SEARCH_QUERIES:
            for page_num in range(1, pages_per_query + 1):
                url = f"{base_url}&pg={page_num}"
                logger.info(f"[StacksBowers:{label}] Fetching page {page_num}")
                self._wait()

                try:
                    html = asyncio.run(
                        self.fetch_with_browser(
                            url,
                            wait_selector=".lot-item, .item-card, .results-item, main",
                        )
                    )
                except Exception as e:
                    logger.error(f"[StacksBowers:{label}] Browser fetch failed: {e}")
                    break

                if "Access Denied" in html or "cf-browser-verification" in html:
                    logger.warning(f"[StacksBowers:{label}] Cloudflare block — skipping")
                    break

                soup = BeautifulSoup(html, "lxml")

                # Stack's Bowers uses various container classes across their site versions
                items = soup.select(
                    ".lot-item, .item-card, .search-result-item, "
                    "article.item, li.result-item"
                )
                if not items:
                    logger.info(f"[StacksBowers:{label}] No items on page {page_num}")
                    break

                yielded = 0
                for item in items:
                    listing = self._parse_item(item, label)
                    if listing:
                        yield listing
                        yielded += 1

                logger.info(f"[StacksBowers:{label}] Page {page_num}: {yielded} listings")
                if yielded < 3:
                    break

    def _parse_item(self, item, label: str) -> RawListing | None:
        try:
            # Title
            title_el = item.select_one(
                "h3, h4, .lot-title, .item-title, a.title, .desc-title"
            )
            if not title_el:
                return None
            title = title_el.get_text(separator=" ", strip=True)
            if not title:
                return None

            # Lot URL
            link_el = item.select_one("a[href]")
            lot_url = urljoin(BASE_URL, link_el["href"]) if link_el else BASE_URL

            # Realized price
            price_el = item.select_one(
                ".realized-price, .hammer-price, .price, "
                "span[class*='realized'], span[class*='price']"
            )
            price_text = price_el.get_text(strip=True) if price_el else ""
            price, currency = _parse_price(price_text)

            # Sale date
            date_el = item.select_one(
                ".sale-date, .date, .auction-date, time, "
                "span[class*='date']"
            )
            sale_date_text = ""
            if date_el:
                sale_date_text = date_el.get("datetime") or date_el.get_text(strip=True)
            sale_date = _parse_date(sale_date_text)

            # Description / lot notes
            desc_el = item.select_one(".description, .details, .lot-desc, p")
            description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

            # Thumbnail
            img_el = item.select_one("img")
            image_url: str | None = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src") or None
                if image_url and image_url.startswith("/"):
                    image_url = urljoin(BASE_URL, image_url)

            return RawListing(
                title=title,
                description=description,
                price=price,
                currency=currency,
                sale_date=sale_date,
                lot_url=lot_url,
                image_url=image_url,
                source=Source.STACKSBOWERS,
                raw_cert_text=f"{title} {description}",
                listing_type=ListingType.AUCTION_REALIZED,
            )
        except Exception as e:
            logger.debug(f"[StacksBowers] Parse error: {e}")
            return None


def _parse_price(text: str) -> tuple[float | None, str]:
    """Extract numeric price and currency from a price string."""
    currency = "USD"
    if not text:
        return None, currency
    # Detect currency symbol
    if "£" in text:
        currency = "GBP"
    elif "€" in text:
        currency = "EUR"
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        val = float(cleaned)
        return (val if val > 0 else None), currency
    except ValueError:
        return None, currency


def _parse_date(text: str) -> date | None:
    """Parse a date string into a date object."""
    if not text:
        return None
    for fmt in ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d %B %Y"]:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None

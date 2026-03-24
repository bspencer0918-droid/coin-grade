"""
GreatCollections scraper.

GreatCollections is an online auction platform specializing exclusively in
NGC- and PCGS-certified coins. They publish all realized prices publicly.

Their search results page returns HTML-rendered lot grids. We fetch multiple
keyword searches covering ancient and US certified coins.
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

BASE_URL = "https://www.greatcollections.com"

# Search configurations — GreatCollections is cert-first so every item has
# NGC or PCGS cert. We search completed ("sold") auctions.
SEARCH_QUERIES = [
    # Ancient / world coins, NGC graded
    {"keywords": "NGC ancient", "label": "ancient/NGC"},
    # US coins, NGC graded (broad — GC is primarily US certified)
    {"keywords": "NGC",         "label": "US/NGC"},
    # US coins, PCGS graded
    {"keywords": "PCGS",        "label": "US/PCGS"},
]

RESULTS_PER_PAGE = 60  # GC shows 60 lots per grid page


class GreatCollectionsScraper(BaseScraper):
    source = Source.GREATCOLLECTIONS

    def scrape(self, max_pages: int = MAX_PAGES["greatcollections"]) -> Iterator[RawListing]:
        pages_per_query = max(max_pages // len(SEARCH_QUERIES), 10)

        for query in SEARCH_QUERIES:
            label = query["label"]
            for page_num in range(1, pages_per_query + 1):
                params = urlencode({
                    "keywords": query["keywords"],
                    "sold":     1,           # realized prices only
                    "page":     page_num,
                })
                url = f"{BASE_URL}/Coins/Search.cfm?{params}"
                logger.info(f"[GreatCollections:{label}] Fetching page {page_num}")
                self._wait()

                try:
                    resp = self.fetch(url)
                    html = resp.text
                except Exception as e:
                    logger.error(f"[GreatCollections:{label}] Fetch failed: {e}")
                    break

                soup = BeautifulSoup(html, "lxml")

                # GreatCollections lot containers
                items = soup.select(
                    ".lot-item, .coin-item, .item-card, "
                    "div[class*='lot-'], li[class*='coin-']"
                )
                if not items:
                    logger.info(f"[GreatCollections:{label}] No items on page {page_num}")
                    break

                yielded = 0
                for item in items:
                    listing = self._parse_item(item, label)
                    if listing:
                        yield listing
                        yielded += 1

                logger.info(f"[GreatCollections:{label}] Page {page_num}: {yielded} listings")
                if yielded < 3:
                    break

    def _parse_item(self, item, label: str) -> RawListing | None:
        try:
            # Title
            title_el = item.select_one(
                "h3, h4, .lot-title, .coin-title, .item-title, a.title, "
                "span[class*='title'], a[href*='/Coin/']"
            )
            if not title_el:
                return None
            title = title_el.get_text(separator=" ", strip=True)
            if not title:
                return None

            # Lot URL
            link_el = item.select_one("a[href*='/Coin/'], a[href*='/lot/'], a[href]")
            lot_url = urljoin(BASE_URL, link_el["href"]) if link_el else BASE_URL

            # Realized price — GC always shows realized price for sold items
            price_el = item.select_one(
                ".realized-price, .sold-price, .final-price, .price, "
                "span[class*='price'], span[class*='sold']"
            )
            price_text = price_el.get_text(strip=True) if price_el else ""
            price, currency = _parse_price(price_text)

            # Sale date
            date_el = item.select_one(
                ".sale-date, .sold-date, .auction-date, time, "
                "span[class*='date'], div[class*='date']"
            )
            sale_date_text = ""
            if date_el:
                sale_date_text = date_el.get("datetime") or date_el.get_text(strip=True)
            sale_date = _parse_date(sale_date_text)

            # Description / cert text — GC often puts NGC/PCGS cert info in subtitle
            desc_el = item.select_one(
                ".description, .grade-info, .cert-info, .details, "
                "span[class*='grade'], span[class*='cert'], p"
            )
            description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

            # Image
            img_el = item.select_one("img")
            image_url: str | None = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src") or None
                if image_url and image_url.startswith("/"):
                    image_url = urljoin(BASE_URL, image_url)

            # GreatCollections always lists certified coins; combine all visible
            # text so ngc_detector / pcgs_detector can find grade/cert number
            raw_cert_text = " ".join(
                el.get_text(separator=" ", strip=True)
                for el in item.select("span, div, p")
            )

            return RawListing(
                title=title,
                description=description,
                price=price,
                currency=currency,
                sale_date=sale_date,
                lot_url=lot_url,
                image_url=image_url,
                source=Source.GREATCOLLECTIONS,
                raw_cert_text=raw_cert_text,
                listing_type=ListingType.AUCTION_REALIZED,
            )
        except Exception as e:
            logger.debug(f"[GreatCollections] Parse error: {e}")
            return None


def _parse_price(text: str) -> tuple[float | None, str]:
    """Extract numeric price and currency from a price string."""
    currency = "USD"
    if not text:
        return None, currency
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

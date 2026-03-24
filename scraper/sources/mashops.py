"""
MA Shops scraper — European dealer marketplace.

Like VCoins, MA Shops is a fixed-price platform. `is_auction` is False.
Prices are typically in EUR; we normalize to USD.

HTML structure (table-based):
  <TR>
    <TD class="spxThumbTd"><IMG class="spx-thumb" src="..."></TD>
    <TD class="left spx-title"><A href="/...">Title</A></TD>
    <TD class="right spx-price"><span class="price">EUR 450</span></TD>
  </TR>
Search URL: /shops/search.php?searchstr=NGC+ancient&curr=USD
Pagination: data-page attribute on .spx-navigation-page links
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Iterator
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from ..models import ListingType, RawListing, Source
from ..config import MAX_PAGES
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL   = "https://www.ma-shops.com"
SEARCH_URL = f"{BASE_URL}/shops/search.php"


class MAShopsScraper(BaseScraper):
    source = Source.MASHOPS

    def scrape(self, max_pages: int = MAX_PAGES["mashops"]) -> Iterator[RawListing]:
        today = date.today()

        for page_num in range(1, max_pages + 1):
            params = {
                "searchstr": "NGC ancient",
                "curr":      "USD",
                "p":         str(page_num),
            }
            url = f"{SEARCH_URL}?{urlencode(params)}"
            logger.info(f"[MA Shops] Fetching page {page_num}: {url}")
            try:
                resp = self.fetch(url)
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception as e:
                logger.error(f"[MA Shops] Page {page_num} failed: {e}")
                break

            # Table rows that contain listings — each has a spx-title cell
            rows = soup.select("tr:has(td.spx-title)")
            if not rows:
                # Fallback: any row with a spx-thumb image
                rows = soup.select("tr:has(td.spxThumbTd)")
            if not rows:
                logger.info(f"[MA Shops] No items on page {page_num}")
                break

            yielded = 0
            for row in rows:
                listing = self._parse_row(row, today)
                if listing:
                    yield listing
                    yielded += 1

            logger.info(f"[MA Shops] Page {page_num}: {yielded} listings")
            if yielded < 3:
                break

            # Check if there's a next page
            next_link = soup.select_one(".spx-navigation-right a")
            if not next_link:
                break

    def _parse_row(self, row, today: date) -> RawListing | None:
        try:
            # Title and URL
            title_td = row.select_one("td.spx-title")
            if not title_td:
                return None
            link_el = title_td.select_one("a")
            if not link_el:
                return None
            title   = link_el.get_text(strip=True)
            href    = link_el.get("href", "")
            lot_url = urljoin(BASE_URL, href) if href else BASE_URL

            # Price
            price_td  = row.select_one("td.spx-price")
            price_text = price_td.get_text(strip=True) if price_td else ""
            currency   = "EUR" if "EUR" in price_text or "€" in price_text else "USD" if "$" in price_text else "EUR"
            # MA Shops returns prices in US$ format when curr=USD is passed
            # (e.g. "1,444.45 US$") — strip commas and parse directly.
            price: float | None = None
            m = re.search(r"[\d,]+(?:\.\d+)?", price_text)
            if m:
                try:
                    price = float(m.group().replace(",", ""))
                except ValueError:
                    pass

            # Description — use title text; MA Shops doesn't show desc in search
            description = title_td.get_text(separator=" ", strip=True)

            # Image
            img_el    = row.select_one("img.spx-thumb, td.spxThumbTd img")
            image_url: str | None = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")
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
                source=Source.MASHOPS,
                raw_cert_text=f"{title} {description}",
                listing_type=ListingType.FIXED_PRICE,
            )
        except Exception as e:
            logger.debug(f"[MA Shops] Parse error: {e}")
            return None

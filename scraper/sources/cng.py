"""
CNG (Classical Numismatic Group) scraper.

CNG archives completed auction lots at cngcoins.com. Their HTML is well-structured
and does not require JavaScript rendering, making it the most reliable source.

Search URL for NGC-tagged ancient coins:
  https://www.cngcoins.com/Coins.aspx?SEARCH_IN_DESCRIPTIONS=1&KEYWORDS=NGC&ITEM_TYPE=1&PAGE_TYPE=1
"""
from __future__ import annotations

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

BASE_URL   = "https://www.cngcoins.com"
SEARCH_URL = f"{BASE_URL}/Coins.aspx"

# How many results per page CNG returns (typically 100)
PAGE_SIZE  = 100


class CNGScraper(BaseScraper):
    source = Source.CNG

    def scrape(self, max_pages: int = MAX_PAGES["cng"]) -> Iterator[RawListing]:
        for page_num in range(1, max_pages + 1):
            params = {
                "SEARCH_IN_DESCRIPTIONS": "1",
                "KEYWORDS":   "NGC",
                "ITEM_TYPE":  "1",     # coins only
                "PAGE_TYPE":  "1",     # completed lots
                "PAGING_START": str((page_num - 1) * PAGE_SIZE),
            }
            url = f"{SEARCH_URL}?{urlencode(params)}"
            logger.info(f"[CNG] Fetching page {page_num}: {url}")

            try:
                resp = self.fetch(url)
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception as e:
                logger.error(f"[CNG] Page {page_num} failed: {e}")
                break

            listings = soup.select("div.COIN_SEARCHRESULTS_ITEM, div.lot-item, tr.lot_row")
            if not listings:
                # Try alternate structure
                listings = soup.select("table.ResultsTable tr[id]")

            if not listings:
                logger.info(f"[CNG] No listings on page {page_num}, stopping")
                break

            yielded = 0
            for item in listings:
                listing = self._parse_item(item)
                if listing:
                    yield listing
                    yielded += 1

            logger.info(f"[CNG] Page {page_num}: {yielded} listings")
            if yielded < 10:
                break  # Sparse page — likely last

    def _parse_item(self, item) -> RawListing | None:
        try:
            # Title / denomination
            title_el = (item.select_one("a.SEARCH_LOT_DESCRIPTION_LINK") or
                        item.select_one(".lot-title") or
                        item.select_one("td.lotDesc a"))
            if not title_el:
                return None
            title = title_el.get_text(strip=True)

            # Lot URL
            href = title_el.get("href", "")
            lot_url = urljoin(BASE_URL, href) if href else ""
            if not lot_url:
                return None

            # Price — CNG shows hammer price as "Realized: $1,250"
            price_el = (item.select_one(".SEARCH_LOT_REALIZED") or
                        item.select_one(".realized-price") or
                        item.select_one("td.price"))
            price_text = price_el.get_text(strip=True) if price_el else ""
            price, currency = _parse_cng_price(price_text)

            # Date
            date_el = (item.select_one(".SEARCH_LOT_DATE") or
                       item.select_one(".lot-date") or
                       item.select_one("td.date"))
            sale_date = _parse_cng_date(date_el.get_text(strip=True) if date_el else "")

            # Description (often in a separate element or tooltip)
            desc_el = item.select_one(".SEARCH_LOT_DESCRIPTION, .lot-desc, td.desc")
            description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

            # Image
            img_el = item.select_one("img.lot-image, img[src*='cngcoins']")
            image_url = img_el.get("src") if img_el else None
            if image_url and not image_url.startswith("http"):
                image_url = urljoin(BASE_URL, image_url)

            # Raw cert text (title + description combined for NGC detection)
            raw_cert = f"{title} {description}"

            return RawListing(
                title=title,
                description=description,
                price=price,
                currency=currency,
                sale_date=sale_date,
                lot_url=lot_url,
                image_url=image_url,
                source=Source.CNG,
                raw_cert_text=raw_cert,
                is_auction=True,
            )
        except Exception as e:
            logger.debug(f"[CNG] Parse error: {e}")
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_cng_price(text: str) -> tuple[float | None, str]:
    """Parse CNG price text like 'Realized: $1,250' or 'Est. $800-$1,000'."""
    text = text.replace("Realized:", "").replace("Est.", "").strip()
    # Take first price if range
    m = re.search(r'[\$£€]?([\d,]+(?:\.\d{2})?)', text.replace(",", ""))
    if m:
        try:
            currency = "GBP" if "£" in text else "EUR" if "€" in text else "USD"
            return float(m.group(1).replace(",", "")), currency
        except ValueError:
            pass
    return None, "USD"


def _parse_cng_date(text: str) -> date | None:
    """Parse date strings like 'June 2024', '14 Jun 2024', '2024-06-14'."""
    import re
    from datetime import datetime

    formats = ["%B %Y", "%d %b %Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"]
    text = re.sub(r'\s+', ' ', text.strip())
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None

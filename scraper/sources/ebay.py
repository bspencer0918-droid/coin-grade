"""
eBay scraper — uses the official eBay Finding API (completed sold listings).

eBay ToS prohibits scraping; this module uses the free Finding API instead.
Register at https://developer.ebay.com to obtain credentials.

API docs: https://developer.ebay.com/devzone/finding/callref/findCompletedItems.html
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date
from typing import Iterator

import httpx

from ..models import ListingType, RawListing, Source
from ..config import EBAY_APP_ID, MAX_PAGES
from .base import BaseScraper

logger = logging.getLogger(__name__)

FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
# eBay category 4733 = Coins: Ancient
ANCIENT_CATEGORY_ID = "4733"
ENTRIES_PER_PAGE = 100


class EbayScraper(BaseScraper):
    source = Source.EBAY

    def scrape(self, max_pages: int = MAX_PAGES["ebay"]) -> Iterator[RawListing]:
        if not EBAY_APP_ID:
            logger.warning("[eBay] No EBAY_APP_ID set — skipping eBay scrape")
            return

        client = httpx.Client(timeout=15)
        try:
            for page_num in range(1, max_pages + 1):
                yield from self._fetch_page(client, page_num)
        finally:
            client.close()

    def _fetch_page(self, client: httpx.Client, page_num: int) -> Iterator[RawListing]:
        """Call the Finding API findCompletedItems endpoint."""
        params = {
            "OPERATION-NAME":         "findCompletedItems",
            "SERVICE-VERSION":        "1.13.0",
            "SECURITY-APPNAME":       EBAY_APP_ID,
            "RESPONSE-DATA-FORMAT":   "XML",
            "REST-PAYLOAD":           "",
            "keywords":               "NGC ancient",
            "categoryId":             ANCIENT_CATEGORY_ID,
            "itemFilter(0).name":     "SoldItemsOnly",
            "itemFilter(0).value":    "true",
            "itemFilter(1).name":     "ListingType",
            "itemFilter(1).value":    "Auction",
            "sortOrder":              "EndTimeSoonest",
            "paginationInput.pageNumber":       str(page_num),
            "paginationInput.entriesPerPage":   str(ENTRIES_PER_PAGE),
        }

        self._wait()
        logger.info(f"[eBay] Fetching page {page_num}")
        try:
            resp = client.get(FINDING_API_URL, params=params)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[eBay] API error page {page_num}: {e}")
            return

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            logger.error(f"[eBay] XML parse error: {e}")
            return

        ns = {"e": "http://www.ebay.com/marketplace/search/v1/services"}

        items = root.findall(".//e:item", ns)
        if not items:
            logger.info(f"[eBay] No items on page {page_num}")
            return

        for item in items:
            listing = self._parse_item(item, ns)
            if listing:
                yield listing

        logger.info(f"[eBay] Page {page_num}: {len(items)} items")

    def _parse_item(self, item, ns: dict) -> RawListing | None:
        try:
            def text(tag: str) -> str:
                el = item.find(tag, ns)
                return el.text.strip() if el is not None and el.text else ""

            title   = text("e:title")
            item_id = text("e:itemId")
            url     = text("e:viewItemURL")

            if not title or not url:
                return None

            # Price
            price_text  = text("e:sellingStatus/e:currentPrice")
            currency    = item.find("e:sellingStatus/e:currentPrice", ns)
            currency_code = currency.attrib.get("currencyId", "USD") if currency is not None else "USD"
            try:
                price = float(price_text) if price_text else None
            except ValueError:
                price = None

            # End date (= sale date for completed items)
            end_time_str = text("e:listingInfo/e:endTime")
            sale_date = _parse_ebay_date(end_time_str)

            # Image
            image_url = text("e:galleryURL") or None

            # Build raw cert text from title + subtitle
            subtitle     = text("e:subtitle")
            raw_cert     = f"{title} {subtitle}"

            return RawListing(
                title=title,
                description=subtitle,
                price=price,
                currency=currency_code,
                sale_date=sale_date,
                lot_url=url,
                image_url=image_url,
                source=Source.EBAY,
                raw_cert_text=raw_cert,
                listing_type=ListingType.AUCTION_REALIZED,
            )
        except Exception as e:
            logger.debug(f"[eBay] Parse error: {e}")
            return None


def _parse_ebay_date(iso_str: str) -> date | None:
    """Parse eBay ISO 8601 date like '2024-06-15T14:30:00.000Z'."""
    if not iso_str:
        return None
    from datetime import datetime
    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
        try:
            return datetime.strptime(iso_str[:26], fmt).date()
        except ValueError:
            continue
    return None

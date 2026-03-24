"""
Harlan J. Berk Ltd scraper — uses the site's internal JSON API.

API: POST https://www.hjbltd.com/api/cms/filter_results
Returns ancient NGC coins from the buy/bid and catalog inventory groups.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterator

import httpx

from ..models import ListingType, RawListing, Source
from ..config import MAX_PAGES
from .base import BaseScraper

logger = logging.getLogger(__name__)

API_URL      = "https://www.hjbltd.com/api/cms/filter_results"
DETAIL_URL   = "https://www.hjbltd.com/api/cms/inventory_lot_detail"
FRONTEND_URL = "https://www.hjbltd.com/#!/inventory/item-detail"
ITEMS_PER_PAGE = 100

# Inventory groups that contain ancient coins
GROUPS = ["bb", "cc"]


class HJBScraper(BaseScraper):
    source = Source.HJB

    def scrape(self, max_pages: int = MAX_PAGES["hjb"]) -> Iterator[RawListing]:
        client = httpx.Client(
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.hjbltd.com/",
            },
            timeout=20,
        )
        today = date.today()
        try:
            for group in GROUPS:
                for page_num in range(1, max_pages + 1):
                    logger.info(f"[HJB] Fetching group={group} page={page_num}")
                    self._wait()
                    try:
                        resp = client.post(API_URL, json={
                            "InventoryGroup":    group,
                            "FetchNext":         ITEMS_PER_PAGE,
                            "Offset":            page_num,
                            "Quantity":          0,
                            "Keyword":           "NGC",
                            "IsCollectionQuery": 0,
                        })
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as e:
                        logger.error(f"[HJB] API error group={group} page={page_num}: {e}")
                        break

                    items = data.get("data", {}).get("items", [])
                    if not items:
                        logger.info(f"[HJB] No items for group={group} page={page_num}")
                        break

                    if items and page_num == 1 and group == GROUPS[0]:
                        logger.info(f"[HJB] Sample item keys: {list(items[0].keys())}")
                        logger.info(f"[HJB] Sample title: {items[0].get('Title','')[:100]}")
                        logger.info(f"[HJB] Sample desc: {str(items[0].get('Description',''))[:100]}")
                        # Log all field values for first item to see where NGC text hides
                        all_vals = {k: str(v)[:80] for k, v in items[0].items() if v}
                        logger.info(f"[HJB] First item all fields: {all_vals}")

                    yielded = 0
                    for item in items:
                        listing = self._parse_item(item, today)
                        if listing:
                            yield listing
                            yielded += 1

                    logger.info(f"[HJB] group={group} page={page_num}: {yielded} listings")

                    total = data.get("data", {}).get("totalItemsCount", 0)
                    if page_num * ITEMS_PER_PAGE >= total:
                        break
        finally:
            client.close()

    def _parse_item(self, item: dict, today: date) -> RawListing | None:
        try:
            title = (item.get("Title") or "").strip()
            if not title:
                return None

            inv_num = item.get("InventoryNumber", "")
            group   = item.get("InventoryGroup", "")
            lot_url = f"{FRONTEND_URL}/{group}/{inv_num}" if inv_num else "https://www.hjbltd.com"

            price_raw = item.get("Price")
            price: float | None = None
            if price_raw is not None:
                try:
                    price = float(price_raw)
                except (ValueError, TypeError):
                    pass

            image_url = item.get("Image") or None
            if image_url and not image_url.startswith("http"):
                image_url = f"https://www.hjbltd.com{image_url}"

            description = item.get("Description") or ""

            # Include all string/numeric fields so NGC cert/grade text in any
            # field (e.g. "Grade", "CertNumber", internal tags) gets picked up
            all_fields = " ".join(str(v) for v in item.values() if v)

            return RawListing(
                title=title,
                description=description,
                price=price,
                currency="USD",
                sale_date=today,
                lot_url=lot_url,
                image_url=image_url,
                source=Source.HJB,
                raw_cert_text=all_fields,
                listing_type=ListingType.FIXED_PRICE,
            )
        except Exception as e:
            logger.debug(f"[HJB] Parse error: {e}")
            return None

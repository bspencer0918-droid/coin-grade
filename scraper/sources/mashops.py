"""
MA Shops scraper — European dealer marketplace.

Like VCoins, MA Shops is a fixed-price platform. `is_auction` is False.
Prices are typically in EUR; we normalize to USD.
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

BASE_URL   = "https://www.ma-shops.com"
SEARCH_URL = f"{BASE_URL}/search/"


class MAShopsScraper(BaseScraper):
    source = Source.MASHOPS

    def scrape(self, max_pages: int = MAX_PAGES["mashops"]) -> Iterator[RawListing]:
        today = date.today()

        for page_num in range(1, max_pages + 1):
            params = {
                "keywords": "NGC ancient",
                "currency": "USD",
                "page":     str(page_num),
            }
            url = f"{SEARCH_URL}?{urlencode(params)}"
            logger.info(f"[MA Shops] Fetching page {page_num}: {url}")
            try:
                resp = self.fetch(url)
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception as e:
                logger.error(f"[MA Shops] Page {page_num} failed: {e}")
                break

            items = soup.select("div.item, li.search-result, article.coin")
            if not items:
                logger.info(f"[MA Shops] No items on page {page_num}")
                break

            yielded = 0
            for item in items:
                listing = self._parse_item(item, today)
                if listing:
                    yield listing
                    yielded += 1
            logger.info(f"[MA Shops] Page {page_num}: {yielded} listings")
            if yielded < 5:
                break

    def _parse_item(self, item, today: date) -> RawListing | None:
        try:
            title_el = item.select_one("a.title, h3 a, h4 a, .item-title a")
            if not title_el:
                return None
            title   = title_el.get_text(strip=True)
            href    = title_el.get("href", "")
            lot_url = urljoin(BASE_URL, href) if href else ""

            price_el  = item.select_one(".price, span.amount, .item-price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            currency  = "EUR" if "€" in price_text else "USD" if "$" in price_text else "EUR"
            m = re.search(r"[\d,]+(?:\.\d{2})?", price_text.replace(".", "").replace(",", "."))
            price = float(m.group().replace(",", "")) if m else None

            desc_el = item.select_one(".description, p, .details")
            description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

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
                lot_url=lot_url or BASE_URL,
                image_url=image_url,
                source=Source.MASHOPS,
                raw_cert_text=f"{title} {description}",
                is_auction=False,
            )
        except Exception as e:
            logger.debug(f"[MA Shops] Parse error: {e}")
            return None

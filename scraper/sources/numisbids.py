"""
NumisBids scraper — aggregates results from many European auction houses.

Server-rendered HTML, no JS required.
Search URL: https://www.numisbids.com/searchall?searchall=NGC+ancient&pg=N
Listing container: div.browse
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

BASE_URL   = "https://www.numisbids.com"
SEARCH_URL = f"{BASE_URL}/searchall"


class NumisBidsScraper(BaseScraper):
    source = Source.NUMISBIDS

    def scrape(self, max_pages: int = MAX_PAGES["numisbids"]) -> Iterator[RawListing]:
        for page_num in range(1, max_pages + 1):
            url = f"{SEARCH_URL}?searchall=NGC+ancient&pg={page_num}"
            logger.info(f"[NumisBids] Fetching page {page_num}")
            try:
                resp = self.fetch(url)
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception as e:
                logger.error(f"[NumisBids] Page {page_num} failed: {e}")
                break

            items = soup.select("div.browse")
            if not items:
                logger.info(f"[NumisBids] No items on page {page_num}")
                break

            # Build a map of sale dates from the status bars on the page
            sale_dates = _extract_sale_dates(soup)

            yielded = 0
            for item in items:
                listing = self._parse_item(item, sale_dates)
                if listing:
                    yield listing
                    yielded += 1

            logger.info(f"[NumisBids] Page {page_num}: {yielded} listings")
            if yielded < 5:
                break

    def _parse_item(self, item, sale_dates: dict) -> RawListing | None:
        try:
            # Title
            title_el = item.select_one("span.summary a, div.browsetext span a")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)

            # Lot URL
            link_el = item.select_one("a[href*='/sale/']") or item.select_one("a[href]")
            lot_url = urljoin(BASE_URL, link_el["href"]) if link_el else BASE_URL

            # Price — look for USD estimate in data-message or text
            price: float | None = None
            currency = "USD"
            rate_el = item.select_one("span.rateclick")
            if rate_el:
                # data-message may contain "USD 1,250"
                msg = rate_el.get("data-message", "") or rate_el.get_text(strip=True)
                price, currency = _parse_numisbids_price(msg)
            if price is None:
                # fallback: any price text in the item
                price_text = item.get_text()
                price, currency = _parse_numisbids_price(price_text)

            # Sale date — find closest preceding statusbar
            sale_date = _find_closest_date(item, sale_dates)

            # Image
            img_el = item.select_one("img")
            image_url: str | None = None
            if img_el:
                src = img_el.get("src") or img_el.get("data-src")
                if src:
                    image_url = urljoin(BASE_URL, src) if not src.startswith("http") else src

            # Description
            desc_el = item.select_one("div.browsetext, span.summary")
            description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

            return RawListing(
                title=title,
                description=description,
                price=price,
                currency=currency,
                sale_date=sale_date,
                lot_url=lot_url,
                image_url=image_url,
                source=Source.NUMISBIDS,
                raw_cert_text=f"{title} {description}",
                is_auction=True,
            )
        except Exception as e:
            logger.debug(f"[NumisBids] Parse error: {e}")
            return None


def _extract_sale_dates(soup) -> dict:
    """Map each statusbar element to its parsed date for proximity lookups."""
    dates = {}
    for bar in soup.select("div.statusbar-container, div.salestatus"):
        text = bar.get_text()
        d = _parse_date_from_text(text)
        if d:
            dates[id(bar)] = (bar, d)
    return dates


def _find_closest_date(item, sale_dates: dict) -> date | None:
    """Walk siblings/parents to find the nearest sale date."""
    parent = item.parent
    for _ in range(5):
        if parent is None:
            break
        for sibling in parent.children:
            if hasattr(sibling, "select"):
                bars = sibling.select("div.statusbar-container, div.salestatus")
                for bar in bars:
                    text = bar.get_text()
                    d = _parse_date_from_text(text)
                    if d:
                        return d
        parent = parent.parent
    return date.today()


def _parse_numisbids_price(text: str) -> tuple[float | None, str]:
    currency = "EUR"
    if "USD" in text or "$" in text:
        currency = "USD"
    elif "GBP" in text or "£" in text:
        currency = "GBP"
    elif "CHF" in text:
        currency = "CHF"
    m = re.search(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
    if m:
        try:
            return float(m.group().replace(",", "")), currency
        except ValueError:
            pass
    return None, currency


def _parse_date_from_text(text: str) -> date | None:
    # Matches patterns like "24-25 Mar 2026", "March 2026", "2026-03-24"
    patterns = [
        r"(\d{1,2}[-–]\d{1,2}\s+\w+\s+\d{4})",
        r"(\d{1,2}\s+\w+\s+\d{4})",
        r"(\w+\s+\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
    ]
    fmts = [
        "%d-%m %B %Y", "%d–%m %B %Y",
        "%d %B %Y", "%d %b %Y",
        "%B %Y", "%b %Y",
        "%Y-%m-%d",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip()
            # For ranges like "24-25 Mar 2026", take first date
            raw = re.sub(r"(\d+)[-–]\d+", r"\1", raw)
            for fmt in fmts:
                try:
                    return datetime.strptime(raw, fmt).date()
                except ValueError:
                    continue
    return None

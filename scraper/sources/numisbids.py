"""
NumisBids scraper — aggregates results from many European auction houses.

Server-rendered HTML, no JS required.
Search URL: https://www.numisbids.com/searchall?searchall=NGC+ancient&pg=N
Results URL: https://www.numisbids.com/n.pl?p=results&searchtext=NGC+ancient&pg=N
Listing container: div.browse
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import ListingType, RawListing, Source
from ..config import MAX_PAGES, cutoff_date
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL    = "https://www.numisbids.com"
SEARCH_URL  = f"{BASE_URL}/searchall"
RESULTS_URL = f"{BASE_URL}/n.pl"


class NumisBidsScraper(BaseScraper):
    source = Source.NUMISBIDS

    # Selectors tried in order — NumisBids has changed its markup over time
    _ITEM_SELECTORS = [
        "div.browse",
        "div.lot",
        "div.result-item",
        "li.result",
        "article.lot",
        "div[class*='lot']",
        "div[class*='browse']",
    ]

    # Search templates: {pg} is substituted with the page number.
    # We try both the general searchall (includes upcoming + past) and
    # the results-only archive (past/realized auctions only).
    _SEARCHES = [
        (f"{SEARCH_URL}?searchall=NGC+ancient&pg={{pg}}", "searchall/NGC-ancient"),
        (f"{RESULTS_URL}?p=results&searchtext=NGC+ancient&pg={{pg}}", "results/NGC-ancient"),
    ]

    def scrape(self, max_pages: int = MAX_PAGES["numisbids"]) -> Iterator[RawListing]:
        cutoff = cutoff_date()
        pages_per_search = max(max_pages // len(self._SEARCHES), 10)

        for url_template, label in self._SEARCHES:
            self._debug_logged = False  # reset per search
            for page_num in range(1, pages_per_search + 1):
                url = url_template.format(pg=page_num)
                logger.info(f"[NumisBids:{label}] Fetching page {page_num}")
                try:
                    resp = self.fetch(url)
                    soup = BeautifulSoup(resp.text, "lxml")
                except Exception as e:
                    logger.error(f"[NumisBids:{label}] Page {page_num} failed: {e}")
                    break

                # Try each selector until we find items
                items = []
                for sel in self._ITEM_SELECTORS:
                    items = soup.select(sel)
                    if items:
                        logger.info(f"[NumisBids:{label}] Matched selector '{sel}' → {len(items)} items")
                        break

                if not items:
                    body_text = soup.get_text(separator=" ", strip=True)[:400]
                    logger.info(f"[NumisBids:{label}] No items on page {page_num}. Body snippet: {body_text}")
                    break

                # Build a map of sale dates from the status bars on the page
                sale_dates = _extract_sale_dates(soup)

                yielded = 0
                past_cutoff = 0
                for item in items:
                    listing = self._parse_item(item, sale_dates)
                    if listing:
                        if listing.sale_date and listing.sale_date < cutoff:
                            past_cutoff += 1
                            continue
                        yield listing
                        yielded += 1

                logger.info(f"[NumisBids:{label}] Page {page_num}: {yielded} listings")
                # If all items on this page are older than cutoff, stop paginating
                if past_cutoff > 0 and yielded == 0:
                    logger.info(f"[NumisBids:{label}] All items older than {cutoff} — stopping")
                    break
                if yielded < 5 and past_cutoff == 0:
                    break

    def _parse_item(self, item, sale_dates: dict) -> RawListing | None:
        try:
            item_text = item.get_text(separator=" ")

            # Log the first item's structure for debugging
            if getattr(self, "_debug_logged", False) is False:
                self._debug_logged = True
                logger.info(f"[NumisBids] First item HTML snippet: {str(item)[:500]}")
                logger.info(f"[NumisBids] First item text: {item_text[:300]}")

            # Lot URL — span.lot a holds the canonical lot link
            link_el = item.select_one("span.lot a, a[href*='/sale/'], a[href]")
            lot_url = urljoin(BASE_URL, link_el["href"]) if link_el else BASE_URL

            # Title — NumisBids puts the coin description in div.browsetext (below
            # div.browsetext-top which only has the lot number and price header).
            # Fall back to any descriptive text in the item if the selector misses.
            title = ""
            for sel in ["div.browsetext", "span.summary", "div.description",
                        "p.description", "div.lot-title"]:
                el = item.select_one(sel)
                if el:
                    title = el.get_text(separator=" ", strip=True)
                    if title:
                        break
            # Last resort: strip lot-number prefix and price prefix from full text
            if not title:
                # Remove "Lot NNNNN" and "Starting price: NNN" / "Result: NNN" preamble
                title = re.sub(r'^Lot\s+\d+\s*', '', item_text.strip())
                title = re.sub(r'(?:Starting price|Result|Realized|Hammer)\s*:[\s\d.,€$£EURUGBCHF]+', '', title)
                title = title.strip()
            if not title:
                return None

            # Determine listing type from label text
            is_realized = bool(re.search(
                r'(?:Result|Realized|Hammer|Zuschlag|Résultat)\s*:', item_text, re.IGNORECASE
            ))
            listing_type = ListingType.AUCTION_REALIZED if is_realized else ListingType.AUCTION_ESTIMATE

            # Price extraction
            price: float | None = None
            currency = "EUR"

            # 1. Try specific realized-price element classes
            for sel in ["span.result", "div.result", "span.hammer", "span.price",
                        "td.result", "td.hammer", "div.price", "span.priceresult",
                        "span.estimate"]:
                el = item.select_one(sel)
                if el:
                    price, currency = _parse_numisbids_price(el.get_text(strip=True))
                    if price and price > 10:
                        break

            # 2. Try rateclick data attributes
            if not price:
                rate_el = item.select_one("span.rateclick")
                if rate_el:
                    raw_val = (rate_el.get("data-eur") or rate_el.get("data-rawvalue")
                               or rate_el.get("data-price") or "")
                    if raw_val:
                        try:
                            price = float(str(raw_val).replace(",", ""))
                            currency = "EUR"
                        except (ValueError, TypeError):
                            pass

            # 3. Scan for label patterns — both "currency amount" and "amount currency"
            if not price:
                # "Result: €500" / "Starting price: 500 EUR" / "Hammer: CHF 200"
                m = re.search(
                    r'(?:Result|Realized|Hammer|Zuschlag|Résultat|Starting price|Estimate)\s*:?\s*'
                    r'(?:([€$£]|EUR|USD|GBP|CHF)\s*)?([\d.,]+)'
                    r'(?:\s*(EUR|USD|GBP|CHF))?',
                    item_text, re.IGNORECASE
                )
                if m:
                    currency_raw = (m.group(1) or m.group(3) or "EUR").strip()
                    currency = {"€": "EUR", "$": "USD", "£": "GBP"}.get(currency_raw, currency_raw.upper() or "EUR")
                    price, _ = _parse_numisbids_price(m.group(2))

            # 4. Any "NNN EUR/GBP/CHF/USD" or "€/£ NNN" pattern
            if not price:
                m = re.search(
                    r'([\d][,\d]*(?:\.\d+)?)\s*(EUR|GBP|CHF|USD)'
                    r'|([€£\$])\s*([\d][,\d]*(?:\.\d+)?)',
                    item_text
                )
                if m:
                    if m.group(1):  # amount then currency
                        currency = m.group(2)
                        price, _ = _parse_numisbids_price(m.group(1))
                    else:           # currency symbol then amount
                        currency = {"€": "EUR", "£": "GBP", "$": "USD"}.get(m.group(3), "EUR")
                        price, _ = _parse_numisbids_price(m.group(4))

            # Skip if no price found or suspiciously low
            if not price or price < 25:
                return None

            # Sale date
            sale_date = _find_closest_date(item, sale_dates)

            # Image
            img_el = item.select_one("img")
            image_url: str | None = None
            if img_el:
                src = img_el.get("src") or img_el.get("data-src")
                if src:
                    image_url = urljoin(BASE_URL, src) if not src.startswith("http") else src

            # Description (browsetext-top has the lot/price header; skip it)
            desc_el = item.select_one("div.browsetext")
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
                listing_type=listing_type,
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

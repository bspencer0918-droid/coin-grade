"""
CNG (Classical Numismatic Group) scraper.

Structure discovered via inspection:
- Completed lots are at Lots.aspx?AUCTION_ID=X&KEYWORDS=NGC&SEARCH_IN_DESCRIPTIONS=1
- Each lot occupies two consecutive TRs:
    TR[n]:   Title row — "Electronic Auction NNN  Lot: X.  [Full coin description with NGC grade]"
    TR[n+1]: Price row — div.description x2 (two lots side by side) + a.abtn links
- Each TR pair actually encodes TWO lots side by side (left and right columns)
- We iterate recent AUCTION_IDs descending to get recent results
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..models import RawListing, Source
from ..config import MAX_PAGES
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cngcoins.com"

# We'll scan this range of auction IDs (most recent completed auctions)
# CNG is currently at ID ~218-219; IDs go back many years
AUCTION_ID_START = 217   # most recent completed
AUCTION_ID_END   = 150   # go back ~67 auctions (~4-5 years of data)


class CNGScraper(BaseScraper):
    source = Source.CNG

    def scrape(self, max_pages: int = MAX_PAGES["cng"]) -> Iterator[RawListing]:
        auctions_checked = 0
        for auction_id in range(AUCTION_ID_START, AUCTION_ID_END - 1, -1):
            if auctions_checked >= max_pages:
                break
            url = (f"{BASE_URL}/Lots.aspx?AUCTION_ID={auction_id}"
                   f"&KEYWORDS=NGC&SEARCH_IN_DESCRIPTIONS=1&ITEM_COUNT=200")
            logger.info(f"[CNG] Scraping auction ID {auction_id}")
            try:
                resp = self.fetch(url)
            except Exception as e:
                logger.warning(f"[CNG] Auction {auction_id} fetch failed: {e}")
                auctions_checked += 1
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            # Get auction date from page if available
            auction_date = _extract_auction_date(soup)

            count = 0
            for listing in _parse_lots(soup, auction_id, auction_date):
                yield listing
                count += 1
            auctions_checked += 1
            logger.info(f"[CNG] Auction {auction_id}: {count} NGC listings")


def _extract_auction_date(soup: BeautifulSoup) -> date | None:
    """Try to extract the auction date from the page header."""
    for el in soup.find_all(string=re.compile(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}')):
        m = re.search(r'(\w+ \d{4})', str(el))
        if m:
            try:
                return datetime.strptime(m.group(1), "%B %Y").date()
            except ValueError:
                pass
    return None


def _parse_lots(soup: BeautifulSoup, auction_id: int, auction_date: date | None) -> Iterator[RawListing]:
    """
    Parse paired title+price rows from a CNG lots page.
    Yields RawListing objects.
    """
    all_trs = soup.find_all("tr")

    i = 0
    while i < len(all_trs) - 1:
        title_tr = all_trs[i]
        title_text = title_tr.get_text(separator=" ", strip=True)

        # Title rows contain "Lot:" followed by a coin description
        if "Lot:" not in title_text:
            i += 1
            continue

        # The next TR is the price/link row
        price_tr = all_trs[i + 1] if i + 1 < len(all_trs) else None
        if price_tr is None:
            break

        # Each TR pair has up to 2 lots side by side — parse both columns
        descs  = price_tr.select("div.description")
        links  = price_tr.select("a.abtn")
        titles = _split_lot_titles(title_tr)

        for col_idx in range(max(len(descs), len(titles))):
            title = titles[col_idx] if col_idx < len(titles) else ""
            desc_el = descs[col_idx] if col_idx < len(descs) else None
            link_el = links[col_idx] if col_idx < len(links) else None

            if not title and not desc_el:
                continue

            price, currency = _parse_price(desc_el)
            lot_url = link_el.get("href", "") if link_el else ""
            if not lot_url:
                lot_url = f"{BASE_URL}/Lots.aspx?AUCTION_ID={auction_id}"

            yield RawListing(
                title=title,
                description=_clean_desc(desc_el),
                price=price,
                currency=currency,
                sale_date=auction_date,
                lot_url=lot_url,
                image_url=None,
                source=Source.CNG,
                raw_cert_text=title,
                is_auction=True,
            )

        i += 2   # Skip past the price row


def _split_lot_titles(title_tr: Tag) -> list[str]:
    """
    Extract individual lot title strings from a title row.
    TDs in the row may each contain one lot title.
    Falls back to splitting on 'Lot:' boundaries.
    """
    tds = title_tr.find_all("td")
    titles = []
    for td in tds:
        txt = td.get_text(separator=" ", strip=True)
        if "Lot:" in txt:
            titles.append(txt)
    if not titles:
        # Fallback: split whole row on 'Lot:' markers
        full = title_tr.get_text(separator=" ", strip=True)
        parts = re.split(r'(?=Lot:\s*\d)', full)
        titles = [p.strip() for p in parts if "Lot:" in p]
    return titles


def _parse_price(desc_el: Tag | None) -> tuple[float | None, str]:
    """Extract sold price from a div.description element."""
    if desc_el is None:
        return None, "USD"
    text = desc_el.get_text(separator=" ", strip=True)
    # "Sold Price: $ 1 250" or "Sold Price: $1,250"
    m = re.search(r'Sold\s+Price\s*:?\s*\$?\s*:?\s*([\d\s,]+)', text, re.IGNORECASE)
    if m:
        raw = re.sub(r'[\s,]', '', m.group(1))
        try:
            return float(raw), "USD"
        except ValueError:
            pass
    return None, "USD"


def _clean_desc(desc_el: Tag | None) -> str:
    if desc_el is None:
        return ""
    return desc_el.get_text(separator=" ", strip=True)

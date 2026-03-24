"""
Coin Archives scraper — https://www.coinarchives.com/a/ (ancient coins)

Strategy (three-phase):

Phase 1 — Discover firms:
  Fetch /a/auction_list.php and extract all auction house names that have
  had auctions within the last HISTORY_MONTHS months.

Phase 2 — Discover AucIDs:
  For each unique firm keyword, search results.php?search=NGC+[keyword].
  Each result row contains a lot-viewer link with AucID=XXXX embedded.
  Collect all unique AucIDs and the auction dates they correspond to.

Phase 3 — Harvest per auction:
  For each discovered AucID, search results.php?auc=XXXX&search=NGC&results=100.
  Ancient coin auctions rarely have >100 NGC lots, so this gives complete
  per-auction coverage with no pagination needed.

This bypasses the free-tier 100-result search cap by querying each
auction individually rather than the global search index.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from ..models import ListingType, RawListing, Source
from ..config import MAX_PAGES, cutoff_date
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL       = "https://www.coinarchives.com"
LIST_URL       = f"{BASE_URL}/a/auction_list.php"
RESULTS_URL    = f"{BASE_URL}/a/results.php"
LOT_VIEWER_URL = f"{BASE_URL}/a/lotviewer.php"

# Common noise words stripped when building firm search keywords
_STOP_WORDS = {
    "de", "la", "le", "les", "et", "ses", "fils", "und", "die", "der",
    "the", "and", "of", "for", "in", "&",
    "sarl", "gmbh", "ag", "ltd", "llc", "bv", "b.v.", "co", "kg",
    "co.", "kg.", "ohg", "ohg.", "inc", "s.a.", "sa", "s.a",
    "numismatik", "numismatica", "numismatique", "münzhandlung",
    "coin", "coins", "auctions", "auction", "galleries", "gallery",
    "rare", "fine", "arts", "world", "international",
}


def _firm_keyword(firm: str) -> str | None:
    """Extract a short searchable keyword from an auction house name."""
    # Remove punctuation noise, split
    clean = re.sub(r"[,.()\[\]]", " ", firm)
    words = clean.split()
    for word in words:
        w = word.strip("&")
        if len(w) >= 3 and w.lower() not in _STOP_WORDS:
            return w   # first significant word
    return None


class CoinArchivesScraper(BaseScraper):
    source = Source.COINARCHIVES

    def scrape(self, max_pages: int = MAX_PAGES["coinarchives"]) -> Iterator[RawListing]:
        cutoff = cutoff_date()
        queries_used = 0
        seen_lot_ids: set[str] = set()
        discovered_auc_ids: dict[str, date | None] = {}  # AucID → auction date

        # ------------------------------------------------------------------ #
        # Phase 1: fetch auction list, collect firm keywords for recent dates #
        # ------------------------------------------------------------------ #
        firm_keywords = self._fetch_firm_keywords(cutoff)
        logger.info(f"[CoinArchives] {len(firm_keywords)} unique firms active since {cutoff}")

        # ------------------------------------------------------------------ #
        # Phase 2: per-firm searches — gather AucIDs and some initial lots   #
        # ------------------------------------------------------------------ #
        # Start with broad baseline terms, then per-firm terms
        search_terms = ["NGC roman", "NGC greek", "NGC byzantine", "NGC ancient MS",
                        "NGC ancient AU", "NGC ancient XF", "NGC ancient VF"]
        search_terms += [f"NGC {kw}" for kw in firm_keywords]

        for term in search_terms:
            if queries_used >= max_pages:
                break
            url = f"{RESULTS_URL}?{urlencode({'search': term, 'results': 100, 'upcoming': 0})}"
            logger.info(f"[CoinArchives] Phase-2 search: '{term}'")
            rows, new_auc_ids = self._fetch_results_page(url, cutoff, seen_lot_ids)
            queries_used += 1
            discovered_auc_ids.update(new_auc_ids)
            for listing in rows:
                yield listing

        logger.info(f"[CoinArchives] Phase-2 done — {len(discovered_auc_ids)} unique AucIDs found")

        # ------------------------------------------------------------------ #
        # Phase 3: per-auction queries for complete NGC coverage              #
        # ------------------------------------------------------------------ #
        for auc_id, auc_date in sorted(
            discovered_auc_ids.items(),
            key=lambda kv: kv[1] or date.min,
            reverse=True,
        ):
            if queries_used >= max_pages:
                break
            if auc_date and auc_date < cutoff:
                continue   # skip auctions outside our window
            url = f"{RESULTS_URL}?{urlencode({'auc': auc_id, 'search': 'NGC', 'results': 100, 'upcoming': 0})}"
            logger.info(f"[CoinArchives] Phase-3 AucID={auc_id} ({auc_date})")
            rows, _ = self._fetch_results_page(url, cutoff, seen_lot_ids)
            queries_used += 1
            for listing in rows:
                yield listing

        logger.info(f"[CoinArchives] Finished — {queries_used} total queries, "
                    f"{len(seen_lot_ids)} unique lots harvested")

    # ---------------------------------------------------------------------- #
    # Helpers                                                                 #
    # ---------------------------------------------------------------------- #

    def _fetch_firm_keywords(self, cutoff: date) -> list[str]:
        """Parse the auction list and return unique firm keywords for recent auctions."""
        try:
            resp = self.fetch(LIST_URL)
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.error(f"[CoinArchives] Auction list fetch failed: {e}")
            return []

        keywords: dict[str, None] = {}  # ordered set
        for row in soup.select("tr"):
            cells = row.select("td")
            if len(cells) < 3:
                continue
            firm_text = cells[0].get_text(strip=True).rstrip("\xa0")
            date_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            auc_date  = _parse_date(date_text)
            if not auc_date or auc_date < cutoff:
                continue
            kw = _firm_keyword(firm_text)
            if kw and kw not in keywords:
                keywords[kw] = None

        return list(keywords)

    def _fetch_results_page(
        self,
        url: str,
        cutoff: date,
        seen_lot_ids: set[str],
    ) -> tuple[list[RawListing], dict[str, date | None]]:
        """
        Fetch one results page, yield parsed listings and return newly-seen AucIDs.
        Mutates seen_lot_ids in place for deduplication.
        """
        listings: list[RawListing] = []
        new_auc_ids: dict[str, date | None] = {}

        try:
            resp = self.fetch(url)
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.error(f"[CoinArchives] Fetch failed: {url} — {e}")
            return listings, new_auc_ids

        rows = soup.select("table.results tr[id]")
        logger.debug(f"[CoinArchives] {len(rows)} rows from {url}")

        for row in rows:
            lot_id = row.get("id", "")
            if not lot_id:
                continue

            # Extract AucID from the lot-viewer link
            link_el = row.select_one("a.R[href*='AucID']")
            auc_id: str | None = None
            if link_el:
                m = re.search(r"AucID=(\d+)", link_el.get("href", ""))
                if m:
                    auc_id = m.group(1)

            # Parse sale date (used for AucID date tracking)
            sale_date = _extract_date(row)
            if auc_id and auc_id not in new_auc_ids:
                new_auc_ids[auc_id] = sale_date

            if lot_id in seen_lot_ids:
                continue
            seen_lot_ids.add(lot_id)

            # Skip if this lot's date is older than our window
            if sale_date and sale_date < cutoff:
                continue

            listing = self._parse_row(row, lot_id, sale_date)
            if listing:
                listings.append(listing)

        return listings, new_auc_ids

    def _parse_row(self, row, lot_id: str, sale_date: date | None) -> RawListing | None:
        try:
            # --- Lot link (lot viewer URL) ---
            link_el = row.select_one("a.R[href]")
            if link_el:
                href = link_el.get("href", "")
                lot_url = urljoin(BASE_URL + "/a/", href) if href else BASE_URL
            else:
                lot_url = BASE_URL

            # --- Title / description ---
            auction_title_el = row.select_one("div.auctiontitle")
            lot_text_el      = row.select_one("span.lottext")

            auction_title = auction_title_el.get_text(strip=True) if auction_title_el else ""
            lot_text      = lot_text_el.get_text(separator=" ", strip=True) if lot_text_el else ""

            if not auction_title and not lot_text:
                return None

            full_text = f"{auction_title} {lot_text}"

            # --- Price ---
            price_el  = row.select_one("td.price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            # Skip upcoming auctions or unsold lots
            if not price_text or price_text.lower() in (
                "upcoming auction", "upcoming\nAuction", "unsold", "n/a", ""
            ) or "upcoming" in price_text.lower():
                return None

            price, currency = _parse_price(price_text)
            if not price or price <= 0:
                return None

            # --- Image ---
            image_url: str | None = None
            img_el = row.select_one("img[src*='coinarchives.com']")
            if img_el:
                src = img_el.get("src", "")
                # Swap thumb URL for full-size image URL
                image_url = src.replace("/thumb", "/image") if src else None

            # Compose a clean title (auction house + first 200 chars of description)
            title = f"{auction_title} — {lot_text[:200]}" if lot_text else auction_title

            return RawListing(
                title=title,
                description=lot_text,
                price=price,
                currency=currency,
                sale_date=sale_date,
                lot_url=lot_url,
                image_url=image_url,
                source=Source.COINARCHIVES,
                raw_cert_text=full_text,
                listing_type=ListingType.AUCTION_REALIZED,
            )
        except Exception as e:
            logger.debug(f"[CoinArchives] Parse error lot {lot_id}: {e}")
            return None


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _extract_date(row) -> date | None:
    """Find the sale date from the <nobr> date cell in a results row."""
    for nobr in row.select("nobr"):
        d = _parse_date(nobr.get_text(strip=True))
        if d:
            return d
    # Fallback: scan all cells
    for cell in row.select("td"):
        d = _parse_date(cell.get_text(strip=True))
        if d:
            return d
    return None


def _parse_date(text: str) -> date | None:
    """Parse formats: '13 May 2026', 'May 2026', '2026-05-13'."""
    text = text.strip()
    for fmt in ["%d %b %Y", "%d %B %Y", "%B %Y", "%b %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # Regex fallback for embedded dates
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", text)
    if m:
        for fmt in ["%d %B %Y", "%d %b %Y"]:
            try:
                return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt).date()
            except ValueError:
                continue
    return None


def _parse_price(text: str) -> tuple[float | None, str]:
    """Parse '1,500 USD', '220 GBP', '€ 450', 'CHF 1.200' etc."""
    currency = "USD"
    if "EUR" in text or "€" in text:
        currency = "EUR"
    elif "GBP" in text or "£" in text:
        currency = "GBP"
    elif "CHF" in text:
        currency = "CHF"

    # Remove currency symbols and letters, then parse the number
    num_text = re.sub(r"[A-Za-z€£$,\s]", "", text)
    # Handle European decimal (dot as thousands separator): "1.200" → 1200
    # If there's a dot and no comma, it might be European thousands separator
    if "." in num_text and "," not in text:
        # If the dot is followed by exactly 3 digits at end, treat as thousands sep
        if re.search(r"\.\d{3}$", num_text):
            num_text = num_text.replace(".", "")

    try:
        return float(num_text), currency
    except ValueError:
        pass
    return None, currency

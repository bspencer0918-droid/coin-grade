"""
Sixbid coin archive scraper — uses the public Solr REST API at
sixbid-coin-archive.com which returns 743+ NGC ancient results.

API: POST https://www.sixbid-coin-archive.com/backend/ca-search
Pagination via 'start' offset (15 results per page).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Iterator

import httpx

from ..models import RawListing, Source
from ..config import MAX_PAGES, RATE_LIMITS
from .base import BaseScraper

logger = logging.getLogger(__name__)

API_URL      = "https://www.sixbid-coin-archive.com/backend/ca-search"
RESULTS_PER_PAGE = 50
BASE_LOT_URL = "https://www.sixbid-coin-archive.com"


class SixbidScraper(BaseScraper):
    source = Source.SIXBID

    def scrape(self, max_pages: int = MAX_PAGES["sixbid"]) -> Iterator[RawListing]:
        client = httpx.Client(
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://www.sixbid-coin-archive.com",
                "Referer": "https://www.sixbid-coin-archive.com/en/search?q=NGC+ancient",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            timeout=30,
        )
        try:
            for page_num in range(max_pages):
                start = page_num * RESULTS_PER_PAGE
                logger.info(f"[Sixbid] Fetching offset {start}")
                self._wait()
                try:
                    resp = client.post(API_URL, json={
                        "query":        "NGC ancient",
                        "language":     "en",
                        "start":        start,
                        "rows":         RESULTS_PER_PAGE,
                        "currency":     "usd",
                        "thesaurus":    False,
                        "translations": False,
                        "highlight":    False,
                    })
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.error(f"[Sixbid] API error at offset {start}: {e}")
                    break

                docs = data.get("response", {}).get("docs", [])
                if not docs:
                    logger.info(f"[Sixbid] No results at offset {start}; top-level keys: {list(data.keys())}")
                    break

                if page_num == 0:
                    logger.info(f"[Sixbid] Sample doc keys: {list(docs[0].keys())}")
                    logger.info(f"[Sixbid] Sample description: {str(docs[0].get('description',''))[:120]}")
                    logger.info(f"[Sixbid] Sample price_realised: {docs[0].get('price_realised')}")
                    logger.info(f"[Sixbid] Total hits: {data.get('response',{}).get('numFound','?')}")

                yielded = 0
                for doc in docs:
                    listing = self._parse_doc(doc)
                    if listing:
                        yield listing
                        yielded += 1

                logger.info(f"[Sixbid] Offset {start}: {yielded} listings")
                if len(docs) < RESULTS_PER_PAGE:
                    break  # last page
        finally:
            client.close()

    def _parse_doc(self, doc: dict) -> RawListing | None:
        try:
            title_raw = doc.get("description", [""])[0] if isinstance(doc.get("description"), list) else doc.get("description", "")
            title = title_raw.strip() if title_raw else ""
            if not title:
                return None

            lot_url = doc.get("bidding_link") or BASE_LOT_URL
            if lot_url and not lot_url.startswith("http"):
                lot_url = f"{BASE_LOT_URL}{lot_url}"

            # Price — prefer realized, fallback to estimate
            price_raw = doc.get("price_realised") or doc.get("price_estimate") or doc.get("price_start")
            price: float | None = None
            if price_raw is not None:
                try:
                    price = float(str(price_raw).replace(",", ""))
                except (ValueError, TypeError):
                    pass

            # Currency
            currency = (doc.get("currency") or "EUR").upper()

            # Date
            sale_date = _parse_sixbid_date(doc.get("auction_start", ""))

            # Image
            image_url = doc.get("image_url") or doc.get("thumbnail") or None

            # Auction house for description context
            house = ""
            company = doc.get("company_name")
            if isinstance(company, list) and company:
                house = company[0]
            elif isinstance(company, str):
                house = company
            description = f"{house} | {doc.get('auction_title', '')}".strip(" |")

            return RawListing(
                title=title,
                description=description,
                price=price,
                currency=currency,
                sale_date=sale_date,
                lot_url=lot_url,
                image_url=image_url,
                source=Source.SIXBID,
                raw_cert_text=f"{title} {description}",
                is_auction=True,
            )
        except Exception as e:
            logger.debug(f"[Sixbid] Parse error: {e}")
            return None


def _parse_sixbid_date(raw: str) -> date | None:
    if not raw:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(raw[:19], fmt).date()
        except ValueError:
            continue
    return None

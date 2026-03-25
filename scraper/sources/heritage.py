"""
Heritage Auctions scraper.

Heritage posts realized prices at coins.ha.com behind a login wall.
Prices are loaded by Vue.js and are NOT present in static HTML.

Two modes:
  1. CDP mode  — connects to an existing Chrome window via remote debugging
                 (--remote-debugging-port=9222).  Prices are fully visible
                 because we reuse the user's authenticated session.
  2. HTTP mode — plain httpx/curl-cffi requests for titles, dates, URLs.
                 Prices will be None (Heritage binds sessions to browser
                 fingerprint, so cookie extraction cannot authenticate).

To enable CDP mode:
  Start Chrome with the flag:
    chrome.exe --remote-debugging-port=9222
  Log in to ha.com, then run the scraper normally.

URL format for faceted search:
  coin_category=1495           → Ancient Coins (parent)
  coin_category_child={ID}     → Civilization sub-category
  ancient_coin_grade={ID}      → Heritage's own grade taxonomy
  page=200~{N}                 → 200 results/page, page N
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cf_requests
    _USE_CURL_CFFI = True
except ImportError:
    import httpx as _httpx
    _USE_CURL_CFFI = False

from ..models import ListingType, RawListing, Source
from ..config import MAX_PAGES, HERITAGE_COOKIE

logger = logging.getLogger(__name__)

BASE_URL   = "https://coins.ha.com"
SEARCH_URL = f"{BASE_URL}/c/search/results.zx"
CDP_URL    = "http://localhost:9222"

RPP = 200   # results per page (Heritage max = 200)

# -----------------------------------------------------------------------
# Civilization sub-categories (coin_category_child values)
# Source: Heritage filter sidebar, coin_category parent = 1495 (Ancient)
# -----------------------------------------------------------------------
CIVILIZATIONS = [
    ("greek",     4615),
    ("roman",     4777),
    ("byzantine", 4496),
    ("celtic",    4505),
    ("near-east", 4748),   # covers Persian, Parthian, etc.
    ("judaea",    4656),
]

# -----------------------------------------------------------------------
# Ancient Coin Grade values (ancient_coin_grade parameter)
# Ordered finest → lowest to match the images shown (images 7-19)
# -----------------------------------------------------------------------
GRADES = [
    ("Gem",  2393),
    ("Ch MS", 1843),
    ("MS",   3044),
    ("Ch AU", 1841),
    ("AU",   1572),
    ("Ch XF", 1845),
    ("XF",   4347),
    ("Ch VF", 1844),
    ("VF",   4227),
    ("Ch F",  1842),
    ("Fine", 2280),
    ("VG",   4232),
    ("Good", 2460),
    ("AG",   1428),
]

# Base params shared by all searches
_BASE_PARAMS = {
    "si":           "2",
    "dept":         "1909",
    "archive_state":"5327",
    "sold_status":  "1526~1524",
    "coin_category":"1495",
    "mode":         "archive",
    "layout":       "list",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_RATE = 3.0   # seconds between page requests


def _cdp_available() -> bool:
    """Return True if Chrome is running with --remote-debugging-port=9222."""
    try:
        import urllib.request
        urllib.request.urlopen(f"{CDP_URL}/json", timeout=2)
        return True
    except Exception:
        return False


def _build_url(civ_id: int, grade_id: int, page_num: int) -> str:
    params = dict(_BASE_PARAMS)
    params["coin_category_child"] = str(civ_id)
    params["ancient_coin_grade"]  = str(grade_id)
    if page_num > 1:
        params["page"] = f"{RPP}~{page_num}"
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{SEARCH_URL}?{qs}"


class HeritageScraper:
    source = Source.HERITAGE

    def scrape(self, max_pages: int = MAX_PAGES["heritage"]) -> Iterator[RawListing]:
        if _cdp_available():
            logger.info("[Heritage] Chrome CDP detected — using browser session for prices")
            yield from asyncio.run(self._scrape_cdp(max_pages))
        else:
            logger.info(
                "[Heritage] No CDP connection — scraping without prices. "
                "To get prices: start Chrome with --remote-debugging-port=9222 "
                "and log in to ha.com."
            )
            yield from self._scrape_http(max_pages)

    # ------------------------------------------------------------------
    # CDP path: use existing logged-in Chrome via Playwright
    # ------------------------------------------------------------------

    async def _scrape_cdp(self, max_pages: int) -> list[RawListing]:
        from playwright.async_api import async_playwright

        results: list[RawListing] = []
        seen_urls: set[str] = set()

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()

            for civ_label, civ_id in CIVILIZATIONS:
                for grade_label, grade_id in GRADES:
                    label = f"{civ_label}/{grade_label}"
                    combo_results = 0

                    for page_num in range(1, max_pages + 1):
                        url = _build_url(civ_id, grade_id, page_num)
                        logger.info(f"[Heritage:{label}] CDP page {page_num}: {url}")
                        time.sleep(_RATE)

                        try:
                            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            # Wait for Vue.js to populate prices
                            try:
                                await page.wait_for_selector(
                                    ".bot-price-data, li.item-block", timeout=15000
                                )
                                await page.wait_for_timeout(2000)
                            except Exception:
                                pass
                            html = await page.content()
                        except Exception as e:
                            logger.error(f"[Heritage:{label}] CDP fetch failed: {e}")
                            break

                        soup = BeautifulSoup(html, "lxml")
                        items = soup.select("li.item-block, div.item-block")
                        if not items:
                            logger.info(f"[Heritage:{label}] No items on page {page_num} — stopping")
                            break

                        page_new = 0
                        for item in items:
                            listing = _parse_item(item)
                            if listing and listing.lot_url not in seen_urls:
                                seen_urls.add(listing.lot_url)
                                results.append(listing)
                                page_new += 1
                                combo_results += 1

                        logger.info(
                            f"[Heritage:{label}] page {page_num}: "
                            f"{len(items)} items, {page_new} new (combo total: {combo_results})"
                        )

                        # If fewer items than a full page, we've reached the end
                        if len(items) < RPP:
                            logger.info(f"[Heritage:{label}] Last page reached ({len(items)} < {RPP})")
                            break

                        # If all items on this page were duplicates for 2+ pages, stop
                        if page_new == 0:
                            logger.info(f"[Heritage:{label}] All duplicates on page {page_num} — stopping")
                            break

                    logger.info(f"[Heritage:{label}] Finished — {combo_results} new listings")

            await page.close()

        logger.info(f"[Heritage] CDP scrape complete — {len(results)} total unique listings")
        return results

    # ------------------------------------------------------------------
    # HTTP fallback: titles + dates only, prices = None
    # ------------------------------------------------------------------

    def _scrape_http(self, max_pages: int) -> Iterator[RawListing]:
        session_headers = dict(_HEADERS)
        if HERITAGE_COOKIE:
            session_headers["Cookie"] = HERITAGE_COOKIE

        if _USE_CURL_CFFI:
            client_ctx = cf_requests.Session(impersonate="chrome124")
        else:
            client_ctx = _httpx.Client(headers=session_headers, follow_redirects=True, timeout=30)

        seen_urls: set[str] = set()

        with client_ctx as client:
            if _USE_CURL_CFFI:
                client.headers.update(session_headers)

            for civ_label, civ_id in CIVILIZATIONS:
                for grade_label, grade_id in GRADES:
                    label = f"{civ_label}/{grade_label}"
                    yield from self._scrape_combo_http(
                        client, civ_id, grade_id, label, max_pages, seen_urls
                    )

    def _scrape_combo_http(
        self, client, civ_id, grade_id, label, max_pages, seen_urls
    ) -> Iterator[RawListing]:
        for page_num in range(1, max_pages + 1):
            url = _build_url(civ_id, grade_id, page_num)
            logger.info(f"[Heritage:{label}] HTTP page {page_num}")
            time.sleep(_RATE)

            try:
                r = client.get(url)
            except Exception as e:
                logger.error(f"[Heritage:{label}] Fetch error: {e}")
                break

            status = r.status_code if hasattr(r, "status_code") else r.status
            if status != 200:
                logger.warning(f"[Heritage:{label}] HTTP {status} on page {page_num}")
                break

            soup = BeautifulSoup(r.text, "lxml")
            items = soup.select("li.item-block, div.item-block")
            if not items:
                break

            page_new = 0
            for item in items:
                listing = _parse_item(item)
                if listing and listing.lot_url not in seen_urls:
                    seen_urls.add(listing.lot_url)
                    yield listing
                    page_new += 1

            logger.info(f"[Heritage:{label}] page {page_num}: {page_new} new")
            if len(items) < RPP or page_new == 0:
                break


def _parse_item(item) -> RawListing | None:
    try:
        # Title
        title_el = item.select_one("a.item-title, .item-title")
        if not title_el:
            return None
        title = title_el.get_text(separator=" ", strip=True)
        if not title:
            return None

        # Lot URL
        lot_url = title_el.get("href") or ""
        if lot_url.startswith("/"):
            lot_url = BASE_URL + lot_url
        if not lot_url:
            link_el = item.select_one("a[href*='/itm/'], a.photo-holder")
            lot_url = link_el.get("href", BASE_URL) if link_el else BASE_URL

        # Price — .bot-price-data populated by Vue.js (CDP mode only)
        price_el = item.select_one(".bot-price-data, .item-value strong, .realized")
        price_text = price_el.get_text(strip=True) if price_el else ""
        if any(w in price_text.lower() for w in ["sign", "join", "login", "register"]):
            price_text = ""
        price, currency = _parse_price(price_text)

        # Date
        date_el = item.select_one(".time-bidding-open .time-remaining, .time-remaining")
        sale_date_text = date_el.get_text(strip=True) if date_el else ""
        sale_date = _parse_date(sale_date_text)

        # Description
        desc_el = item.select_one(".item-info p")
        description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

        # Image
        img_el = item.select_one("img.thumbnail, img")
        image_url: str | None = None
        if img_el:
            image_url = img_el.get("src") or img_el.get("data-src") or None

        return RawListing(
            title=title,
            description=description,
            price=price,
            currency=currency,
            sale_date=sale_date,
            lot_url=lot_url,
            image_url=image_url,
            source=Source.HERITAGE,
            raw_cert_text=f"{title} {description}",
            listing_type=ListingType.AUCTION_REALIZED,
        )
    except Exception as e:
        logger.debug(f"[Heritage] Parse error: {e}")
        return None


def _parse_price(text: str) -> tuple[float | None, str]:
    if not text:
        return None, "USD"
    m = re.search(r"[\d,]+(?:\.\d{2})?", text.replace(",", ""))
    if m:
        try:
            return float(m.group().replace(",", "")), "USD"
        except ValueError:
            pass
    return None, "USD"


def _parse_date(text: str) -> date | None:
    for fmt in ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%b. %d, %Y"]:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None

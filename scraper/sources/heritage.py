"""
Heritage Auctions scraper.

Heritage posts realized prices at coins.ha.com. Viewing prices requires
a free account. We log in via Playwright before scraping, then search
for NGC/PCGS-graded ancient and US coin lots.

Credentials are read from HERITAGE_EMAIL / HERITAGE_PASSWORD env vars
(set as GitHub Secrets; never hardcoded).
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import ListingType, RawListing, Source
from ..config import MAX_PAGES, HERITAGE_EMAIL, HERITAGE_PASSWORD
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL   = "https://coins.ha.com"
LOGIN_URL  = "https://www.ha.com/c/login.zx"

# Search queries: (url_fragment, label)
# N-parameter facets: 790=Coins, 4294967021=Realized prices,
# 4294966556=additional filter. Ntk/Ntt = keyword search.
SEARCH_QUERIES = [
    (
        f"{BASE_URL}/c/search-results.zx"
        "?N=790+231+4294967021+4294966556"
        "&Ntk=SI_Titles-Desc&Ntt=NGC&Nty=1",
        "ancient/NGC",
    ),
    (
        f"{BASE_URL}/c/search-results.zx"
        "?N=790+4294967021+4294966556"
        "&Ntk=SI_Titles-Desc&Ntt=NGC&Nty=1",
        "US/NGC",
    ),
    (
        f"{BASE_URL}/c/search-results.zx"
        "?N=790+4294967021+4294966556"
        "&Ntk=SI_Titles-Desc&Ntt=PCGS&Nty=1",
        "US/PCGS",
    ),
]


class HeritageScraper(BaseScraper):
    source = Source.HERITAGE

    def scrape(self, max_pages: int = MAX_PAGES["heritage"]) -> Iterator[RawListing]:
        if not HERITAGE_EMAIL or not HERITAGE_PASSWORD:
            logger.warning("[Heritage] No credentials set — skipping (set HERITAGE_EMAIL / HERITAGE_PASSWORD)")
            return

        pages_per_query = max(max_pages // len(SEARCH_QUERIES), 10)

        for search_url, label in SEARCH_QUERIES:
            for page_num in range(1, pages_per_query + 1):
                url = f"{search_url}&ic__offerPage={page_num}"
                logger.info(f"[Heritage:{label}] Fetching page {page_num}")
                self._wait()

                try:
                    html = asyncio.run(
                        self._fetch_authenticated(url)
                    )
                except Exception as e:
                    logger.error(f"[Heritage:{label}] Fetch failed: {e}")
                    break

                if "Access Denied" in html or "cf-browser-verification" in html:
                    logger.warning(f"[Heritage:{label}] Cloudflare block — skipping")
                    break

                # If redirected back to login, our session expired
                if "loginForm" in html or "sign-in" in html.lower():
                    logger.warning(f"[Heritage:{label}] Session expired / login wall — stopping")
                    break

                soup = BeautifulSoup(html, "lxml")
                items = soup.select(
                    "li.result-item, div.lot-item, article.item, "
                    "div[class*='result-item'], li[class*='lot']"
                )
                if not items:
                    # Log a snippet to help debug selector changes
                    snippet = soup.get_text(separator=" ", strip=True)[:300]
                    logger.info(f"[Heritage:{label}] No items on page {page_num}. Snippet: {snippet}")
                    break

                yielded = 0
                for item in items:
                    listing = self._parse_item(item, label)
                    if listing:
                        yield listing
                        yielded += 1

                logger.info(f"[Heritage:{label}] Page {page_num}: {yielded} listings")
                if yielded < 3:
                    break

    async def _fetch_authenticated(self, url: str) -> str:
        """
        Launch a Playwright browser, log in to Heritage with stored
        credentials, then navigate to url and return the page HTML.
        Session cookies are not persisted between calls — we log in
        fresh each time (Heritage sessions last the duration of the run).
        """
        from playwright.async_api import async_playwright
        from ..config import BROWSER_ARGS, VIEWPORT, USER_AGENTS
        import random

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
            context = await browser.new_context(
                viewport=VIEWPORT,
                user_agent=random.choice(USER_AGENTS),
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            # Block images/fonts to speed up scraping
            await context.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
                lambda route: route.abort(),
            )
            page = await context.new_page()

            # --- Login ---
            logger.info("[Heritage] Logging in...")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

            try:
                await page.wait_for_selector(
                    "input[type='email'], input[name='email'], input[id*='email'], input[placeholder*='mail']",
                    timeout=10000,
                )
                await page.fill(
                    "input[type='email'], input[name='email'], input[id*='email'], input[placeholder*='mail']",
                    HERITAGE_EMAIL,
                )
                await page.fill(
                    "input[type='password'], input[name='password'], input[id*='password']",
                    HERITAGE_PASSWORD,
                )
                await page.click(
                    "button[type='submit'], input[type='submit'], button[class*='login'], button[class*='sign']"
                )
                # Wait for redirect after successful login
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                logger.info(f"[Heritage] Login complete, now at: {page.url}")
            except Exception as e:
                logger.warning(f"[Heritage] Login step failed: {e} — attempting to scrape anyway")

            # --- Fetch target page with authenticated session ---
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_selector(
                    ".result-item, .lot-item, article.item, main",
                    timeout=15000,
                )
            except Exception:
                pass  # proceed anyway and let the parser decide

            html = await page.content()
            await browser.close()
            return html

    def _parse_item(self, item, label: str) -> RawListing | None:
        try:
            title_el = item.select_one(
                "h3, h4, .item-title, .lot-title, a.desc, a[class*='title']"
            )
            if not title_el:
                return None
            title = title_el.get_text(separator=" ", strip=True)
            if not title:
                return None

            link_el = item.select_one("a[href*='/itm/'], a[href*='/lot/'], a.title-link, a[href]")
            lot_url = urljoin(BASE_URL, link_el["href"]) if link_el else BASE_URL

            price_el = item.select_one(
                ".price, .hammer-price, .realized-price, span[class*='price'], "
                "div[class*='price'], span[class*='realized']"
            )
            price_text = price_el.get_text(strip=True) if price_el else ""
            price, currency = _parse_price(price_text)

            date_el = item.select_one(
                ".date, .sale-date, time, .auction-date, span[class*='date']"
            )
            sale_date_text = ""
            if date_el:
                sale_date_text = date_el.get("datetime") or date_el.get_text(strip=True)
            sale_date = _parse_date(sale_date_text)

            desc_el = item.select_one(".description, .details, p")
            description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

            img_el = item.select_one("img")
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
    currency = "USD"
    if not text:
        return None, currency
    m = re.search(r"[\d,]+(?:\.\d{2})?", text.replace(",", ""))
    if m:
        try:
            return float(m.group().replace(",", "")), currency
        except ValueError:
            pass
    return None, currency


def _parse_date(text: str) -> date | None:
    for fmt in ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"]:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None

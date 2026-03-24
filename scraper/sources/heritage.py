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
from ..config import MAX_PAGES, HERITAGE_USERNAME, HERITAGE_EMAIL, HERITAGE_PASSWORD
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL   = "https://coins.ha.com"
LOGIN_URL  = "https://www.ha.com/c/login.zx"

# Search queries: (url_fragment, label)
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
        # Accept either username or email for the login field
        login_id = HERITAGE_USERNAME or HERITAGE_EMAIL
        if not login_id or not HERITAGE_PASSWORD:
            logger.warning("[Heritage] No credentials set — skipping (set HERITAGE_USERNAME + HERITAGE_PASSWORD)")
            return

        # Run entire scrape in a single async browser session (login once, reuse session)
        results = asyncio.run(self._scrape_async(max_pages))
        yield from results

    async def _scrape_async(self, max_pages: int) -> list[RawListing]:
        from playwright.async_api import async_playwright
        from ..config import BROWSER_ARGS, VIEWPORT, USER_AGENTS
        import random

        results: list[RawListing] = []
        pages_per_query = max(max_pages // len(SEARCH_QUERIES), 10)

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
            # Block images/fonts/media to speed up scraping
            await context.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
                lambda route: route.abort(),
            )
            page = await context.new_page()

            # Apply stealth patches to evade Cloudflare bot detection
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
                logger.info("[Heritage] Stealth mode applied")
            except ImportError:
                logger.warning("[Heritage] playwright-stealth not installed — Cloudflare may block us")

            # Login once for the entire session
            logged_in = await self._login(page)
            if not logged_in:
                logger.warning("[Heritage] Login failed — will attempt to scrape anyway (may hit paywall)")

            for search_url, label in SEARCH_QUERIES:
                for page_num in range(1, pages_per_query + 1):
                    url = f"{search_url}&ic__offerPage={page_num}"
                    logger.info(f"[Heritage:{label}] Fetching page {page_num}")
                    self._wait()

                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        try:
                            await page.wait_for_selector(
                                ".result-item, .lot-item, article.item, main, #content",
                                timeout=15000,
                            )
                        except Exception:
                            pass  # proceed and let the parser decide

                        html = await page.content()
                    except Exception as e:
                        logger.error(f"[Heritage:{label}] Fetch failed: {e}")
                        break

                    if "Access Denied" in html or "cf-browser-verification" in html:
                        logger.warning(f"[Heritage:{label}] Cloudflare block — skipping")
                        break

                    if "loginForm" in html or ("sign-in" in html.lower() and "logged" not in html.lower()):
                        logger.warning(f"[Heritage:{label}] Session expired / login wall — stopping")
                        break

                    soup = BeautifulSoup(html, "lxml")

                    # Log the page URL and title to help diagnose redirects
                    title_el = soup.find("title")
                    logger.info(f"[Heritage:{label}] Page title: {title_el.get_text()[:80] if title_el else '?'}")

                    items = soup.select(
                        "li.result-item, div.lot-item, article.item, "
                        "div[class*='result-item'], li[class*='lot'], "
                        "div.lot-details, div[class*='lot-details']"
                    )
                    if not items:
                        snippet = soup.get_text(separator=" ", strip=True)[:400]
                        logger.info(f"[Heritage:{label}] No items on page {page_num}. Snippet: {snippet}")
                        break

                    yielded = 0
                    for item in items:
                        listing = self._parse_item(item, label)
                        if listing:
                            results.append(listing)
                            yielded += 1

                    logger.info(f"[Heritage:{label}] Page {page_num}: {yielded} listings")
                    if yielded < 3:
                        break

            await browser.close()

        return results

    async def _login(self, page) -> bool:
        """
        Navigate to Heritage login page and submit credentials.
        The form uses "Heritage Auctions username" (not email) + password.
        Returns True if login appears successful.
        """
        login_id = HERITAGE_USERNAME or HERITAGE_EMAIL

        logger.info("[Heritage] Navigating to login page...")
        try:
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=45000)
        except Exception as e:
            logger.warning(f"[Heritage] Login page load timeout (continuing): {e}")

        logger.info(f"[Heritage] Login page URL: {page.url}")

        # Check for Cloudflare block
        try:
            html = await page.content()
            if "cf-browser-verification" in html or "Access Denied" in html:
                logger.warning("[Heritage] Cloudflare challenge on login page — stealth may not have worked")
                return False
        except Exception:
            pass

        # --- Fill username ---
        # Heritage form label: "Heritage Auctions username:"
        # The input is a plain text field (not type=email).
        username_selectors = [
            "input[name='username']",
            "input[name='userName']",
            "input[name='haUsername']",
            "input[id='username']",
            "input[id='userName']",
            "input[autocomplete='username']",
            "input[placeholder*='username' i]",
            "input[type='text']",        # only text input visible before password
        ]
        username_filled = False
        for sel in username_selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=5000)
                if el:
                    await el.click()
                    await el.fill(login_id)
                    logger.info(f"[Heritage] Filled username '{login_id}' using: {sel}")
                    username_filled = True
                    break
            except Exception:
                continue

        if not username_filled:
            logger.warning("[Heritage] Could not find username input — logging visible inputs:")
            try:
                inputs = await page.query_selector_all("input")
                for inp in inputs[:15]:
                    attrs = await inp.evaluate(
                        "el => ({type: el.type, name: el.name, id: el.id, "
                        "placeholder: el.placeholder, autocomplete: el.autocomplete})"
                    )
                    logger.info(f"[Heritage] Input found: {attrs}")
            except Exception:
                pass
            return False

        # --- Fill password ---
        password_selectors = [
            "input[type='password']",
            "input[name='password']",
            "input[name='haPassword']",
            "input[id='password']",
        ]
        for sel in password_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.fill(HERITAGE_PASSWORD)
                    logger.info(f"[Heritage] Filled password using: {sel}")
                    break
            except Exception:
                continue

        # --- Click "Sign In" button ---
        # The button text in the screenshot is exactly "Sign In"
        submit_selectors = [
            "button:has-text('Sign In')",
            "input[value='Sign In']",
            "button[type='submit']",
            "input[type='submit']",
            "button[class*='sign' i]",
            "button[class*='login' i]",
            "form button",
        ]
        submitted = False
        for sel in submit_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    logger.info(f"[Heritage] Clicked submit: {sel}")
                    submitted = True
                    break
            except Exception:
                continue

        if not submitted:
            await page.keyboard.press("Enter")
            submitted = True

        if submitted:
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
                logger.info(f"[Heritage] Post-login URL: {page.url}")
                if "login" not in page.url.lower():
                    logger.info("[Heritage] Login successful")
                    return True
                logger.warning("[Heritage] Still on login page after submit")
            except Exception as e:
                logger.warning(f"[Heritage] Post-login wait failed: {e}")

        return False

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

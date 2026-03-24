"""
Scraper configuration — URLs, selectors, rate limits, timeouts.
"""
import os
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# How many months of auction history to collect.
# The daily scraper uses this to stop paginating once it reaches data
# older than HISTORY_MONTHS.  Set higher for backfill runs.
HISTORY_MONTHS: int = int(os.getenv("HISTORY_MONTHS", "6"))


def cutoff_date() -> date:
    """Return the oldest sale date we care about (today minus HISTORY_MONTHS)."""
    today = date.today()
    # Approximate: subtract 30 days per month
    return today - timedelta(days=30 * HISTORY_MONTHS)

# Project root (one level above this file)
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CATALOG_DIR = DATA_DIR / "catalog"
PRICES_DIR  = DATA_DIR / "prices"

# Ensure output directories exist
DATA_DIR.mkdir(exist_ok=True)
CATALOG_DIR.mkdir(exist_ok=True)
PRICES_DIR.mkdir(exist_ok=True)
(CATALOG_DIR / "roman"     / "by-ruler").mkdir(parents=True, exist_ok=True)
(CATALOG_DIR / "greek"     ).mkdir(parents=True, exist_ok=True)
(CATALOG_DIR / "byzantine" / "by-ruler").mkdir(parents=True, exist_ok=True)
(CATALOG_DIR / "persian"   ).mkdir(parents=True, exist_ok=True)
(CATALOG_DIR / "celtic"    ).mkdir(parents=True, exist_ok=True)
(CATALOG_DIR / "egyptian"  ).mkdir(parents=True, exist_ok=True)
(CATALOG_DIR / "other"     ).mkdir(parents=True, exist_ok=True)

# NGC cert cache (not committed to repo)
NGC_CACHE_FILE = ROOT / "scraper" / "ngc_cache.json"

# Exchange rate API
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY", "")

# Rate limiting (seconds between requests per source)
RATE_LIMITS = {
    "cng":          2.5,
    "heritage":     4.0,
    "vcoins":       2.5,
    "mashops":      2.5,
    "numisbids":    2.0,
    "sixbid":       1.5,   # REST API
    "hjb":          2.0,   # JSON API
    "coinarchives": 3.0,   # be respectful to free tier
    "ngc":          2.0,   # cert lookup
}

# Max pages / iterations per source per run.
# Date-cutoff logic in each scraper stops pagination earlier than this
# hard cap, so these are just safety limits.
MAX_PAGES = {
    "cng":          120,  # ~120 auctions ≈ 4 years of archive
    "heritage":     50,
    "vcoins":       50,
    "mashops":      200,  # hundreds of pages across all searches
    "numisbids":    100,  # date-cutoff stops this early
    "sixbid":       200,  # 50 results/page via API; date filter applied server-side
    "hjb":          20,
    "coinarchives": 150,  # one "page" = one search/auction query; covers ~100 firms + baseline
}

# Playwright browser config
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
]

VIEWPORT = {"width": 1280, "height": 900}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Source URLs
URLS = {
    "cng": {
        "archive":  "https://www.cngcoins.com/Coins.aspx?PAGE_TYPE=1&ITEM_TYPE=1",
        "search":   "https://www.cngcoins.com/Coins.aspx?SEARCH_IN_DESCRIPTIONS=1&KEYWORDS=NGC&ITEM_TYPE=1",
    },
    "heritage": {
        "search":   "https://coins.ha.com/c/search-results.zx?N=790+231+4294967021+4294966556",
    },
    "vcoins": {
        "search":   "https://www.vcoins.com/en/search.aspx?type=1&cat=0&keywords=NGC+ancient",
    },
    "mashops": {
        "search":   "https://www.ma-shops.com/search/?keywords=NGC+ancient&currency=USD",
    },
}

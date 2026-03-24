"""
Scraper configuration — URLs, selectors, rate limits, timeouts.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

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

# eBay API
EBAY_APP_ID  = os.getenv("EBAY_APP_ID",  "")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID", "")
EBAY_DEV_ID  = os.getenv("EBAY_DEV_ID",  "")

# Exchange rate API
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY", "")

# Rate limiting (seconds between requests per source)
RATE_LIMITS = {
    "cng":       2.5,
    "roma":      3.0,
    "heritage":  4.0,
    "ebay":      1.0,   # API, not scraping
    "vcoins":    2.5,
    "mashops":   2.5,
    "numisbids": 2.0,
    "sixbid":    1.5,   # REST API
    "hjb":       2.0,   # JSON API
    "ngc":       2.0,   # cert lookup
}

# Max pages to scrape per source per run (limits runtime)
MAX_PAGES = {
    "cng":       20,
    "roma":      15,
    "heritage":  15,
    "ebay":      50,   # API pages
    "vcoins":    20,
    "mashops":   15,
    "numisbids": 10,
    "sixbid":    20,   # 15 results per page via API
    "hjb":       10,
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
    "roma": {
        "archive":  "https://www.romanumismatics.com/auction-house/results",
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

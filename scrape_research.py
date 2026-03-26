"""
Research scraper — collects collector knowledge from coin forums and
reference databases using the existing Chrome CDP session.

HOW TO USE:
  1. Start Chrome with --remote-debugging-port=9222 (use start-chrome-debug.bat)
  2. Navigate to the site you want scraped (log in if needed)
  3. Run:  python scrape_research.py numisforums
           python scrape_research.py forumancientcoins
           python scrape_research.py wildwinds
           python scrape_research.py all

Output is saved to  research/<site>/  as JSON files.

The scraper respects rate limits (3 s between pages, 30 s pause every
5 minutes) and stops after MAX_THREADS threads or MAX_PAGES pages.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

CDP_URL    = "http://localhost:9222"
RATE        = 3.0    # seconds between requests
MAX_PAGES   = 999    # effectively unlimited — stop only when subforum runs out
MAX_THREADS = 9999   # effectively unlimited
OUTPUT_DIR  = Path("research")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ForumPost:
    author: str
    date:   str
    text:   str

@dataclass
class ForumThread:
    title:    str
    url:      str
    subforum: str
    posts:    list[ForumPost] = field(default_factory=list)
    tags:     list[str]       = field(default_factory=list)
    views:    int             = 0
    replies:  int             = 0

@dataclass
class CoinTypeEntry:
    label:       str
    url:         str
    date_range:  str
    description: str
    references:  list[str] = field(default_factory=list)
    image_urls:  list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Site configurations
# ---------------------------------------------------------------------------

SITES = {
    "numisforums": {
        "start_url":   "https://www.numisforums.com",
        "mode":        "forum_ips",
        "description": "numisforums.com — coin collector community",
        "subforum_urls": [
            # Core ancient coin subforums
            ("https://www.numisforums.com/?forumId=14", "Greek Coins"),
            ("https://www.numisforums.com/?forumId=15", "Roman Imperial"),
            ("https://www.numisforums.com/?forumId=7",  "Roman Republic"),
            ("https://www.numisforums.com/?forumId=9",  "Byzantine"),
            ("https://www.numisforums.com/?forumId=25", "ID Help & Authentication"),
            # Additional sections (IDs discovered from site structure)
            ("https://www.numisforums.com/?forumId=8",  "Ancient General"),
            ("https://www.numisforums.com/?forumId=10", "Near East & Islamic"),
            ("https://www.numisforums.com/?forumId=11", "Celtic & Barbarian"),
            ("https://www.numisforums.com/?forumId=12", "Judaea & Jewish"),
            ("https://www.numisforums.com/?forumId=13", "Egypt & African"),
            ("https://www.numisforums.com/?forumId=16", "Fakes & Forgeries"),
            ("https://www.numisforums.com/?forumId=17", "Grading & Valuation"),
            ("https://www.numisforums.com/?forumId=18", "Buying & Selling"),
            ("https://www.numisforums.com/?forumId=19", "Market Talk"),
            ("https://www.numisforums.com/?forumId=20", "Research & References"),
            ("https://www.numisforums.com/?forumId=21", "General Discussion"),
            ("https://www.numisforums.com/?forumId=22", "Show & Tell"),
            ("https://www.numisforums.com/?forumId=23", "Errors & Varieties"),
            ("https://www.numisforums.com/?forumId=24", "Ancients General"),
            ("https://www.numisforums.com/?forumId=26", "Attribution Help"),
            ("https://www.numisforums.com/?forumId=27", "Provenance Research"),
            # Tag pages — aggregate by topic
            ("https://www.numisforums.com/tags/greek/",     "tag:greek"),
            ("https://www.numisforums.com/tags/roman/",     "tag:roman"),
            ("https://www.numisforums.com/tags/byzantine/", "tag:byzantine"),
            ("https://www.numisforums.com/tags/fake/",      "tag:fake"),
            ("https://www.numisforums.com/tags/grading/",   "tag:grading"),
            ("https://www.numisforums.com/tags/ngc/",       "tag:ngc"),
            ("https://www.numisforums.com/tags/value/",     "tag:value"),
            ("https://www.numisforums.com/tags/denarius/",  "tag:denarius"),
            ("https://www.numisforums.com/tags/tetradrachm/","tag:tetradrachm"),
            ("https://www.numisforums.com/tags/solidus/",   "tag:solidus"),
            ("https://www.numisforums.com/tags/owl/",       "tag:owl"),
            ("https://www.numisforums.com/tags/alexander/", "tag:alexander"),
        ],
    },
    "forumancientcoins": {
        "start_url":   "https://www.forumancientcoins.com/board/",
        "mode":        "forum",
        "description": "Forum Ancient Coins — major ancient coin community",
        "target_keywords": [
            "ancient", "greek", "roman", "byzantine",
            "grading", "value", "attribution",
        ],
    },
    "cointalk_ancient": {
        "start_url":   "https://www.cointalk.com/forums/ancient-coins.6/",
        "mode":        "forum",
        "description": "CoinTalk ancient coins subforum",
        "target_keywords": [
            "tetradrachm", "denarius", "solidus", "owl",
            "value", "grade", "ngc", "attribution",
        ],
    },
    "wildwinds": {
        "start_url":   "https://www.wildwinds.com/coins/greece/attica/athens/t.html",
        "mode":        "reference",
        "description": "Wildwinds — ancient coin type reference database",
        "extra_urls": [
            # Greek city-states & kingdoms
            "https://www.wildwinds.com/coins/greece/attica/athens/i.html",
            "https://www.wildwinds.com/coins/greece/macedon/alexander_iii/t.html",
            "https://www.wildwinds.com/coins/greece/macedon/philip_ii/t.html",
            "https://www.wildwinds.com/coins/greece/macedon/philip_iii/t.html",
            "https://www.wildwinds.com/coins/greece/sicily/syracuse/t.html",
            "https://www.wildwinds.com/coins/greece/corinthia/corinth/t.html",
            "https://www.wildwinds.com/coins/greece/thrace/lysimachos/t.html",
            "https://www.wildwinds.com/coins/greece/seleucid/seleukos_i/t.html",
            "https://www.wildwinds.com/coins/greece/seleucid/antiochos_iii/t.html",
            "https://www.wildwinds.com/coins/greece/ptolemaic/ptolemy_i/t.html",
            "https://www.wildwinds.com/coins/greece/ptolemaic/ptolemy_ii/t.html",
            "https://www.wildwinds.com/coins/greece/ptolemaic/ptolemy_iii/t.html",
            "https://www.wildwinds.com/coins/greece/baktria/menander/t.html",
            "https://www.wildwinds.com/coins/greece/parthia/mithradates_ii/t.html",
            "https://www.wildwinds.com/coins/greece/judaea/i.html",
            # Roman Republican
            "https://www.wildwinds.com/coins/rsc/julius_caesar/t.html",
            "https://www.wildwinds.com/coins/rsc/mark_antony/t.html",
            # Roman Imperial — all major rulers
            "https://www.wildwinds.com/coins/ric/augustus/t.html",
            "https://www.wildwinds.com/coins/ric/tiberius/t.html",
            "https://www.wildwinds.com/coins/ric/caligula/t.html",
            "https://www.wildwinds.com/coins/ric/claudius/t.html",
            "https://www.wildwinds.com/coins/ric/nero/t.html",
            "https://www.wildwinds.com/coins/ric/vespasian/t.html",
            "https://www.wildwinds.com/coins/ric/titus/t.html",
            "https://www.wildwinds.com/coins/ric/domitian/t.html",
            "https://www.wildwinds.com/coins/ric/nerva/t.html",
            "https://www.wildwinds.com/coins/ric/trajan/t.html",
            "https://www.wildwinds.com/coins/ric/hadrian/t.html",
            "https://www.wildwinds.com/coins/ric/antoninus_pius/t.html",
            "https://www.wildwinds.com/coins/ric/marcus_aurelius/t.html",
            "https://www.wildwinds.com/coins/ric/commodus/t.html",
            "https://www.wildwinds.com/coins/ric/septimius_severus/t.html",
            "https://www.wildwinds.com/coins/ric/caracalla/t.html",
            "https://www.wildwinds.com/coins/ric/julia_domna/t.html",
            "https://www.wildwinds.com/coins/ric/elagabalus/t.html",
            "https://www.wildwinds.com/coins/ric/severus_alexander/t.html",
            "https://www.wildwinds.com/coins/ric/gordian_iii/t.html",
            "https://www.wildwinds.com/coins/ric/philip_i/t.html",
            "https://www.wildwinds.com/coins/ric/gallienus/t.html",
            "https://www.wildwinds.com/coins/ric/aurelian/t.html",
            "https://www.wildwinds.com/coins/ric/probus/t.html",
            "https://www.wildwinds.com/coins/ric/diocletian/t.html",
            "https://www.wildwinds.com/coins/ric/constantine_i/t.html",
            "https://www.wildwinds.com/coins/ric/constantius_ii/t.html",
            "https://www.wildwinds.com/coins/ric/julian_ii/t.html",
            "https://www.wildwinds.com/coins/ric/theodosius_i/t.html",
            # Byzantine
            "https://www.wildwinds.com/coins/byz/justinian_i/t.html",
            "https://www.wildwinds.com/coins/byz/heraclius/t.html",
            "https://www.wildwinds.com/coins/byz/constans_ii/t.html",
            "https://www.wildwinds.com/coins/byz/constantine_iv/t.html",
            "https://www.wildwinds.com/coins/byz/basil_i/t.html",
            "https://www.wildwinds.com/coins/byz/basil_ii/t.html",
            "https://www.wildwinds.com/coins/byz/constantine_x/t.html",
            "https://www.wildwinds.com/coins/byz/alexius_i/t.html",
        ],
    },

    "forumancientcoins": {
        "start_url":   "https://www.forumancientcoins.com/board/",
        "mode":        "forum",
        "description": "Forum Ancient Coins — the largest ancient coin community online",
        "target_keywords": [
            "greek", "roman", "byzantine", "ancient", "value", "price",
            "fake", "forgery", "attribution", "identification", "grading",
            "ngc", "denarius", "tetradrachm", "solidus", "owl",
        ],
    },

    "cointalk_ancient": {
        "start_url":   "https://www.cointalk.com/forums/ancient-coins.6/",
        "mode":        "forum",
        "description": "CoinTalk ancient coins subforum — large mainstream collector community",
        "target_keywords": [
            "ancient", "greek", "roman", "byzantine", "value", "grade",
            "ngc", "attribution", "fake", "identification",
        ],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_coin_relevant(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(kw in t for kw in keywords)


def _clean_text(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def _extract_references(text: str) -> list[str]:
    """Pull coin reference citations from free text."""
    patterns = [
        r'\bRIC\s+(?:II?I?V?|[1-9])?\s*\d+',
        r'\bSear\s+(?:SG|SRCV|GCV)?\s*\d+',
        r'\bBMC\s+\d+',
        r'\bSNG\s+\w+\s+\d+',
        r'\bCrawford\s+\d+/\d+',
        r'\bThompson\s+\d+',
        r'\bSG\s*\d{3,5}',
    ]
    refs = []
    for p in patterns:
        refs.extend(re.findall(p, text, re.IGNORECASE))
    return list(set(refs))


# ---------------------------------------------------------------------------
# IPS (Invision Community) forum scraper — for numisforums.com
# ---------------------------------------------------------------------------

async def scrape_forum_ips(page, site_cfg: dict, out_dir: Path) -> list[ForumThread]:
    """
    Scraper tuned for Invision Community (IPS) software.
    Thread URLs:  /topic/123-slug/
    Pagination:   /topic/123-slug/page/2/
    Forum pages:  /?forumId=14&page=2
    Comments:     /topic/123-slug/?do=findComment&comment=456  (same thread — strip query)
    """
    subforum_list = site_cfg["subforum_urls"]
    threads_out:  list[ForumThread] = []
    seen_thread_paths: set[str] = set()   # deduplicate by path only (no query string)
    thread_queue: list[tuple[str, str]] = []
    last_pause = time.time()
    base = "https://www.numisforums.com"

    # Load already-scraped URLs so we skip them on re-runs
    already_scraped: set[str] = set()
    threads_file = out_dir / "threads.json"
    if threads_file.exists():
        try:
            prev = json.loads(threads_file.read_text(encoding="utf-8"))
            already_scraped = {t["url"] for t in prev}
            logger.info(f"Resuming — {len(already_scraped)} threads already scraped, will skip")
        except Exception:
            pass

    # Step 1: visit each subforum and collect thread URLs
    for sf_url, sf_label in subforum_list:
        logger.info(f"Scanning subforum: {sf_label} ({sf_url})")

        for pg in range(1, MAX_PAGES + 1):
            if time.time() - last_pause >= 300:
                logger.info("5-min pause...")
                time.sleep(30)
                last_pause = time.time()

            # IPS pagination: ?forumId=14&page=2
            target = sf_url if pg == 1 else f"{sf_url}&page={pg}"
            time.sleep(RATE)

            try:
                await page.goto(target, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                html = await page.content()
            except Exception as e:
                logger.warning(f"Failed to load {target}: {e}")
                break

            soup = BeautifulSoup(html, "lxml")
            found = 0

            for a in soup.find_all("a", href=True):
                href = a["href"]
                # IPS thread URLs: /topic/NNN-slug/
                if not re.search(r'/topic/\d+', href):
                    continue
                # Strip query string for dedup (removes ?do=findComment&comment=...)
                parsed    = urlparse(urljoin(base, href))
                clean_path = parsed.path.rstrip("/")
                if clean_path in seen_thread_paths:
                    continue
                # Skip paginated thread links (we'll paginate inside the thread scraper)
                if "/page/" in clean_path:
                    continue
                seen_thread_paths.add(clean_path)
                clean_url = f"{base}{clean_path}/"
                if clean_url not in already_scraped:
                    thread_queue.append((clean_url, sf_label))
                found += 1

            logger.info(f"  Page {pg}: {found} new threads (total queued: {len(thread_queue)})")
            if found == 0:
                break
            if len(thread_queue) >= MAX_THREADS:
                break

        if len(thread_queue) >= MAX_THREADS:
            break

    logger.info(f"Total threads to scrape: {len(thread_queue)}")

    # Step 2: scrape each thread
    for idx, (thread_url, subforum) in enumerate(thread_queue[:MAX_THREADS]):
        if time.time() - last_pause >= 300:
            logger.info("5-min pause...")
            time.sleep(30)
            last_pause = time.time()

        logger.info(f"Thread {idx+1}/{min(len(thread_queue), MAX_THREADS)}: {thread_url}")
        time.sleep(RATE)

        try:
            await page.goto(thread_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1500)
            html = await page.content()
        except Exception as e:
            logger.warning(f"Failed: {e}")
            continue

        soup = BeautifulSoup(html, "lxml")

        # IPS title
        title_el = (soup.find("h1", class_=re.compile(r'ipsType_pageTitle|topic-title')) or
                    soup.find("h1"))
        title = _clean_text(title_el.get_text()) if title_el else "Unknown"

        # IPS posts: div[data-role="commentContent"] or .cPost_contentWrap or .ipsComment_content
        post_els = soup.select(
            "[data-role='commentContent'], .cPost_contentWrap, "
            ".ipsComment_content, .ipsType_richText, .post_body, "
            "article .ipsComment_content"
        )
        # Fallback: any reasonably-sized block
        if not post_els:
            post_els = [el for el in soup.select("div, article")
                        if len(_clean_text(el.get_text())) > 100][:10]

        posts: list[ForumPost] = []
        for el in post_els[:15]:
            text = _clean_text(el.get_text(separator=" "))
            if len(text) < 40:
                continue
            # Author: look for IPS author elements nearby
            author_el = (el.find_previous(class_=re.compile(r'cAuthorPane_author|ipsComment_author|author')) or
                         el.find_previous(attrs={"data-role": "authorName"}))
            date_el   = el.find_previous("time")
            author = _clean_text(author_el.get_text()) if author_el else ""
            date   = date_el.get("datetime", _clean_text(date_el.get_text())) if date_el else ""
            posts.append(ForumPost(author=author[:50], date=date[:50], text=text[:2000]))

        refs = _extract_references(" ".join(p.text for p in posts))

        # Tags: IPS uses data-ipstruncate or .ipsBadge
        tags = [_clean_text(t.get_text()) for t in soup.select(".ipsBadge, .ipsTag, [data-tag]") if _clean_text(t.get_text())]

        threads_out.append(ForumThread(
            title=title[:200], url=thread_url, subforum=subforum,
            posts=posts, tags=tags
        ))

        if (idx + 1) % 25 == 0:
            _save_threads(threads_out, out_dir)
            logger.info(f"Checkpoint: {len(threads_out)} threads saved")

    return threads_out


# ---------------------------------------------------------------------------
# Generic Forum scraper (fallback for non-IPS sites)
# ---------------------------------------------------------------------------

async def scrape_forum(page, site_cfg: dict, out_dir: Path) -> list[ForumThread]:
    """Navigate a forum site and collect thread content."""
    start_url    = site_cfg["start_url"]
    target_kws   = site_cfg.get("target_keywords", [])
    threads_out: list[ForumThread] = []
    visited:     set[str]  = set()
    thread_urls: list[tuple[str, str]] = []  # (url, subforum_name)

    # Step 1: discover subforums from start URL
    logger.info(f"Discovering subforums at {start_url}")
    time.sleep(RATE)
    try:
        await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        html = await page.content()
    except Exception as e:
        logger.error(f"Could not load {start_url}: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    base = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"

    # Find subforum links — common patterns across forum software
    subforum_links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href  = a["href"]
        label = _clean_text(a.get_text())
        if not label or len(label) < 3:
            continue
        full  = urljoin(base, href)
        # Only stay on same domain
        if urlparse(full).netloc != urlparse(base).netloc:
            continue
        # Skip navigation / user links
        if any(skip in href.lower() for skip in ["login", "register", "profile", "pm", "logout", "search", "faq", "mailto"]):
            continue
        # Keep if label matches our keyword interest
        if not target_kws or _is_coin_relevant(label, target_kws):
            subforum_links.append((full, label))

    # Deduplicate
    seen_sf: set[str] = set()
    unique_subforums: list[tuple[str, str]] = []
    for url, label in subforum_links:
        if url not in seen_sf:
            seen_sf.add(url)
            unique_subforums.append((url, label))

    logger.info(f"Found {len(unique_subforums)} relevant subforum links")
    for u, l in unique_subforums[:5]:
        logger.info(f"  · {l}: {u}")

    # Save subforum map
    (out_dir / "subforums.json").write_text(
        json.dumps([{"url": u, "label": l} for u, l in unique_subforums], indent=2),
        encoding="utf-8"
    )

    # Step 2: visit each subforum, collect thread links
    last_pause = time.time()
    for sf_url, sf_label in unique_subforums:
        if len(thread_urls) >= MAX_THREADS:
            break
        logger.info(f"Scanning subforum: {sf_label}")

        for page_num in range(1, MAX_PAGES + 1):
            if time.time() - last_pause >= 300:
                logger.info("5-min pause (rate limiting)...")
                time.sleep(30)
                last_pause = time.time()

            # Build paginated URL (handles common patterns)
            if page_num == 1:
                target = sf_url
            elif "page=" in sf_url or "start=" in sf_url:
                break  # already paginated URL, skip
            elif sf_url.endswith("/"):
                target = f"{sf_url}page-{page_num}"
            else:
                target = f"{sf_url}?page={page_num}"

            if target in visited:
                break
            visited.add(target)

            time.sleep(RATE)
            try:
                await page.goto(target, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1500)
                html = await page.content()
            except Exception as e:
                logger.warning(f"Fetch failed ({target}): {e}")
                break

            soup2 = BeautifulSoup(html, "lxml")
            found_threads = 0

            for a in soup2.find_all("a", href=True):
                href  = a["href"]
                label = _clean_text(a.get_text())
                full  = urljoin(base, href)
                if urlparse(full).netloc != urlparse(base).netloc:
                    continue
                # Thread links usually contain "thread", "topic", "showthread", or "t=" in URL
                is_thread = any(x in href.lower() for x in [
                    "thread", "topic", "showthread", "viewtopic", "/t/", "?t=", "&t=",
                ])
                if is_thread and full not in visited and label and len(label) > 5:
                    thread_urls.append((full, sf_label))
                    visited.add(full)
                    found_threads += 1

            logger.info(f"  Page {page_num}: {found_threads} threads found (total {len(thread_urls)})")
            if found_threads == 0:
                break
            if len(thread_urls) >= MAX_THREADS:
                break

    logger.info(f"Collected {len(thread_urls)} thread URLs to scrape")

    # Step 3: scrape each thread
    for idx, (thread_url, subforum) in enumerate(thread_urls[:MAX_THREADS]):
        if time.time() - last_pause >= 300:
            logger.info("5-min pause...")
            time.sleep(30)
            last_pause = time.time()

        logger.info(f"Thread {idx+1}/{min(len(thread_urls), MAX_THREADS)}: {thread_url}")
        time.sleep(RATE)

        try:
            await page.goto(thread_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1500)
            html = await page.content()
        except Exception as e:
            logger.warning(f"Thread fetch failed: {e}")
            continue

        soup3 = BeautifulSoup(html, "lxml")

        # Extract title
        title_el = soup3.find("h1") or soup3.find("h2")
        title    = _clean_text(title_el.get_text()) if title_el else "Unknown"

        # Extract posts — try common forum post selectors
        post_els = (
            soup3.select("article.message, div.message-body, div.postbody, "
                         "div.post_body, div.post-content, div.bbWrapper, "
                         "td.postbody, div.entry-content, .post-text, "
                         ".message-inner, .postText")
        )

        posts: list[ForumPost] = []
        for el in post_els[:20]:  # cap at 20 posts per thread
            text = _clean_text(el.get_text(separator=" "))
            if len(text) < 30:
                continue
            # Try to find author/date near the post element
            author_el = el.find_previous(class_=re.compile(r'author|username|user-name|poster'))
            date_el   = el.find_previous(class_=re.compile(r'date|time|post-date'))
            author = _clean_text(author_el.get_text()) if author_el else ""
            date   = _clean_text(date_el.get_text())   if date_el   else ""
            posts.append(ForumPost(author=author[:50], date=date[:50], text=text[:2000]))

        refs  = _extract_references(" ".join(p.text for p in posts))
        tags  = []
        # Try to extract tags/labels if the forum has them
        for tag_el in soup3.select(".label, .tag, .thread-tag, .prefix"):
            t = _clean_text(tag_el.get_text())
            if t:
                tags.append(t)

        thread = ForumThread(
            title=title[:200], url=thread_url, subforum=subforum,
            posts=posts, tags=tags
        )
        threads_out.append(thread)

        # Checkpoint every 25 threads
        if (idx + 1) % 25 == 0:
            _save_threads(threads_out, out_dir)
            logger.info(f"Checkpoint saved: {len(threads_out)} threads")

    return threads_out


# ---------------------------------------------------------------------------
# Reference scraper (Wildwinds-style coin type pages)
# ---------------------------------------------------------------------------

async def scrape_reference(page, site_cfg: dict, out_dir: Path) -> list[CoinTypeEntry]:
    urls_to_scrape = [site_cfg["start_url"]] + site_cfg.get("extra_urls", [])
    entries: list[CoinTypeEntry] = []
    last_pause = time.time()

    for url in urls_to_scrape:
        if time.time() - last_pause >= 300:
            time.sleep(30)
            last_pause = time.time()

        logger.info(f"Reference page: {url}")
        time.sleep(RATE)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            html = await page.content()
        except Exception as e:
            logger.warning(f"Failed: {e}")
            continue

        soup = BeautifulSoup(html, "lxml")

        # Wildwinds layout: table rows with coin images and descriptions
        for row in soup.select("tr, .coin-entry, .type-row"):
            text = _clean_text(row.get_text(separator=" "))
            if len(text) < 20:
                continue

            # Extract reference numbers from row text
            refs = _extract_references(text)
            if not refs and not any(x in text.lower() for x in ["bc", "ad", "sear", "ric", "bmc"]):
                continue

            # Date range pattern
            date_m = re.search(r'\b(?:ca?\.?\s*)?(\d{1,3}\s*(?:BC|AD).*?\d{1,3}\s*(?:BC|AD))', text, re.I)
            date_range = date_m.group(0) if date_m else ""

            # Images
            img_urls = [urljoin(url, img["src"]) for img in row.select("img") if img.get("src")]

            entries.append(CoinTypeEntry(
                label=text[:120],
                url=url,
                date_range=date_range,
                description=text[:500],
                references=refs,
                image_urls=img_urls[:3],
            ))

        logger.info(f"  Extracted {len(entries)} type entries so far")

    return entries


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

def _save_threads(threads: list[ForumThread], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Merge with any previously saved threads (so re-runs accumulate)
    existing_urls: set[str] = set()
    existing: list[dict] = []
    threads_file = out_dir / "threads.json"
    if threads_file.exists():
        try:
            existing = json.loads(threads_file.read_text(encoding="utf-8"))
            existing_urls = {t["url"] for t in existing}
        except Exception:
            existing = []

    new_data = [asdict(t) for t in threads if t.url not in existing_urls]
    merged   = existing + new_data
    threads_file.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    # Compact summary for quick analysis
    summary = []
    for t in merged:
        posts    = t.get("posts", [])
        all_text = t.get("title","") + " " + " ".join(p.get("text","") for p in posts)
        refs     = _extract_references(all_text)
        summary.append({
            "title":    t.get("title",""),
            "url":      t.get("url",""),
            "subforum": t.get("subforum",""),
            "replies":  len(posts),
            "refs":     refs,
            "snippet":  (posts[0].get("text","")[:200] if posts else ""),
        })
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Saved {len(merged)} total threads ({len(new_data)} new) → {threads_file}")


def _save_reference(entries: list[CoinTypeEntry], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    data = [asdict(e) for e in entries]
    (out_dir / "types.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# CDP availability check
# ---------------------------------------------------------------------------

def _cdp_available() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:9222/json", timeout=2)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(site_key: str):
    if site_key == "all":
        keys = list(SITES.keys())
    elif site_key in SITES:
        keys = [site_key]
    else:
        logger.error(f"Unknown site '{site_key}'. Options: {', '.join(SITES)} or 'all'")
        return

    if not _cdp_available():
        logger.error(
            "Chrome CDP not available.\n"
            "Start Chrome with --remote-debugging-port=9222 (use start-chrome-debug.bat),\n"
            "navigate to the site (log in if needed), then re-run."
        )
        return

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page    = await context.new_page()

        for key in keys:
            cfg     = SITES[key]
            out_dir = OUTPUT_DIR / key
            out_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"=== Scraping: {cfg['description']} ===")

            if cfg["mode"] == "forum_ips":
                threads = await scrape_forum_ips(page, cfg, out_dir)
                _save_threads(threads, out_dir)
                logger.info(f"=== {key}: saved {len(threads)} threads to {out_dir}/threads.json ===")

            elif cfg["mode"] == "forum":
                threads = await scrape_forum(page, cfg, out_dir)
                _save_threads(threads, out_dir)
                logger.info(f"=== {key}: saved {len(threads)} threads to {out_dir}/threads.json ===")

            elif cfg["mode"] == "reference":
                entries = await scrape_reference(page, cfg, out_dir)
                _save_reference(entries, out_dir)
                logger.info(f"=== {key}: saved {len(entries)} type entries to {out_dir}/types.json ===")

        await page.close()

    logger.info("=== Research scrape complete ===")
    logger.info(f"Output directory: {OUTPUT_DIR.resolve()}")


def main():
    site = sys.argv[1] if len(sys.argv) > 1 else "all"
    asyncio.run(run(site))


if __name__ == "__main__":
    main()

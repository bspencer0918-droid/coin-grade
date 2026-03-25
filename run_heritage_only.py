"""
Standalone Heritage Auctions scraper run — with checkpointing.

Scrapes Heritage by civilization × grade using CDP (authenticated browser
session).  After each civilization+grade combo completes, intermediate
results are written to heritage_checkpoint.json so the run can be resumed
after interruption.

Usage:
    python run_heritage_only.py            # full run (or resume from checkpoint)
    python run_heritage_only.py --publish  # just publish checkpoint data → catalog
"""
import json
import logging
import sys
from pathlib import Path

from scraper.pipeline import (
    HeritageScraper,
    raw_to_sale,
    build_coin_catalog,
    merge_historical,
    write_outputs,
    load_exchange_rates,
    Source,
    SourceStatus,
)
from scraper.config import EXCHANGE_RATE_API_KEY, MAX_PAGES
from scraper.sources.heritage import CIVILIZATIONS, GRADES, _build_url, _cdp_available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

CHECKPOINT_FILE = Path("heritage_checkpoint.json")


def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        try:
            data = json.loads(CHECKPOINT_FILE.read_text())
            logger.info(
                f"Resuming from checkpoint: "
                f"{data.get('total_listings', 0)} listings, "
                f"{len(data.get('completed_combos', []))} combos done"
            )
            return data
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}")
    return {"completed_combos": [], "total_listings": 0, "raw_sales": []}


def save_checkpoint(cp: dict):
    CHECKPOINT_FILE.write_text(json.dumps(cp))
    logger.info(
        f"Checkpoint saved: {cp['total_listings']} listings, "
        f"{len(cp['completed_combos'])} combos done"
    )


def publish_from_checkpoint(cp: dict):
    """Process checkpoint data → catalog → write outputs."""
    if not cp.get("raw_sales"):
        logger.warning("No sales in checkpoint")
        return

    logger.info(f"Publishing {len(cp['raw_sales'])} raw sales from checkpoint…")
    load_exchange_rates(EXCHANGE_RATE_API_KEY)

    # Reconstruct (Sale, classification) tuples from saved dicts
    from scraper.models import RawListing, Source as Src, ListingType
    from datetime import date

    results = []
    seen_ids: set[str] = set()
    for raw_dict in cp["raw_sales"]:
        try:
            # Convert dict back to RawListing
            sale_date_str = raw_dict.get("sale_date")
            sale_date = date.fromisoformat(sale_date_str) if sale_date_str else None
            raw = RawListing(
                title=raw_dict["title"],
                description=raw_dict.get("description", ""),
                price=raw_dict["price"],
                currency=raw_dict.get("currency", "USD"),
                sale_date=sale_date,
                lot_url=raw_dict["lot_url"],
                image_url=raw_dict.get("image_url"),
                source=Src.HERITAGE,
                raw_cert_text=raw_dict.get("raw_cert_text", raw_dict["title"]),
                listing_type=ListingType.AUCTION_REALIZED,
            )
            result = raw_to_sale(raw)
            if result:
                sale, classification = result
                if sale.id not in seen_ids:
                    seen_ids.add(sale.id)
                    results.append((sale, classification))
        except Exception as e:
            logger.debug(f"Skip bad raw sale: {e}")

    count = len(results)
    logger.info(f"Processed {count} unique sales")

    statuses = {Source.HERITAGE: SourceStatus(status="ok", listings_scraped=count)}
    coin_details = build_coin_catalog(results)
    merge_historical(coin_details)
    write_outputs(coin_details, statuses)
    logger.info("=== Publish complete ===")


def main():
    if "--publish" in sys.argv:
        cp = load_checkpoint()
        publish_from_checkpoint(cp)
        return

    logger.info("=== Heritage-only scrape starting (with checkpointing) ===")
    load_exchange_rates(EXCHANGE_RATE_API_KEY)

    cp = load_checkpoint()
    completed = set(cp.get("completed_combos", []))
    raw_sales_list: list[dict] = cp.get("raw_sales", [])
    seen_urls: set[str] = {r["lot_url"] for r in raw_sales_list if r.get("lot_url")}

    if not _cdp_available():
        logger.error(
            "Chrome CDP not available — start Chrome with --remote-debugging-port=9222 "
            "and log in to ha.com, then re-run."
        )
        return

    import asyncio
    import time
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
    from scraper.sources.heritage import _parse_item, CDP_URL, RPP, _RATE

    async def run_cdp():
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()

            for civ_label, civ_id in CIVILIZATIONS:
                for grade_label, grade_id in GRADES:
                    combo_key = f"{civ_label}/{grade_label}"
                    if combo_key in completed:
                        logger.info(f"[Heritage:{combo_key}] Skipping (already done)")
                        continue

                    combo_count = 0
                    max_pages = MAX_PAGES.get("heritage", 100)

                    for page_num in range(1, max_pages + 1):
                        url = _build_url(civ_id, grade_id, page_num)
                        logger.info(f"[Heritage:{combo_key}] page {page_num}")
                        time.sleep(_RATE)

                        try:
                            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            try:
                                await page.wait_for_selector(
                                    ".bot-price-data, li.item-block", timeout=15000
                                )
                                await page.wait_for_timeout(2000)
                            except Exception:
                                pass
                            html = await page.content()
                        except Exception as e:
                            logger.error(f"[Heritage:{combo_key}] Fetch failed: {e}")
                            break

                        soup = BeautifulSoup(html, "lxml")
                        items = soup.select("li.item-block, div.item-block")
                        if not items:
                            logger.info(f"[Heritage:{combo_key}] No items — done")
                            break

                        page_new = 0
                        for item in items:
                            listing = _parse_item(item)
                            if listing and listing.lot_url not in seen_urls:
                                seen_urls.add(listing.lot_url)
                                raw_sales_list.append({
                                    "title": listing.title,
                                    "description": listing.description,
                                    "price": listing.price,
                                    "currency": listing.currency,
                                    "sale_date": listing.sale_date.isoformat() if listing.sale_date else None,
                                    "lot_url": listing.lot_url,
                                    "image_url": listing.image_url,
                                    "raw_cert_text": listing.raw_cert_text,
                                })
                                page_new += 1
                                combo_count += 1

                        logger.info(
                            f"[Heritage:{combo_key}] page {page_num}: "
                            f"{len(items)} items, {page_new} new (combo: {combo_count})"
                        )

                        if len(items) == 0 or page_new == 0:
                            break

                    logger.info(f"[Heritage:{combo_key}] Done — {combo_count} new listings")
                    completed.add(combo_key)
                    cp["completed_combos"] = list(completed)
                    cp["total_listings"] = len(raw_sales_list)
                    cp["raw_sales"] = raw_sales_list
                    save_checkpoint(cp)

            await page.close()

    asyncio.run(run_cdp())

    logger.info(f"=== Scrape complete — {len(raw_sales_list)} total raw sales ===")
    logger.info("Publishing results to catalog…")

    cp["raw_sales"] = raw_sales_list
    publish_from_checkpoint(cp)

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()

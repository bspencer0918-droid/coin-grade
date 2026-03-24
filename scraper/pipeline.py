"""
Main pipeline orchestrator.

Run with:  python -m scraper.pipeline
"""
from __future__ import annotations

import hashlib
import json
import logging
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import DATA_DIR, CATALOG_DIR, PRICES_DIR, EXCHANGE_RATE_API_KEY
from .models import (
    Category, CoinDetail, CoinSummary, ListingType, Meta, NGCGrade,
    NGC_GRADE_ORDER, PriceRange, RawListing, Sale, SaleMetadata,
    Source, SourceStatus,
)
from .sources.cng       import CNGScraper
from .sources.ebay      import EbayScraper
from .sources.heritage  import HeritageScraper
from .sources.mashops   import MAShopsScraper
from .sources.vcoins    import VCoinsScraper
from .sources.numisbids import NumisBidsScraper
from .sources.sixbid    import SixbidScraper
from .sources.hjb       import HJBScraper
from .utils.coin_classifier  import classify
from .utils.ngc_detector     import detect_ngc, verify_cert
from .utils.price_normalizer import load_exchange_rates, to_usd
from .utils.slab_ocr         import extract_cert_from_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

SCRAPERS = [
    CNGScraper(),
    EbayScraper(),
    HeritageScraper(),
    VCoinsScraper(),
    MAShopsScraper(),
    NumisBidsScraper(),
    SixbidScraper(),
    HJBScraper(),
]


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def raw_to_sale(raw: RawListing, usd_rate_fn=to_usd) -> Sale | None:
    """
    Convert a RawListing into a Sale by:
    1. Running NGC detection
    2. Running coin classifier
    3. Normalizing price to USD
    """
    if raw.price is None or raw.price <= 0:
        return None

    ngc = detect_ngc(raw.title, raw.description, raw.raw_cert_text)

    # If we found NGC grade info but no cert number, try OCR on the slab image.
    # This catches listings (e.g. VCoins, MA Shops) where the cert is only
    # visible on the label photo and not written in the listing text.
    if ngc.grade and not ngc.cert_number and raw.image_url:
        ocr_cert = extract_cert_from_image(raw.image_url)
        if ocr_cert:
            logger.debug(f"[OCR] Cert {ocr_cert} from image, re-running detector")
            ngc = detect_ngc(raw.title, raw.description,
                             f"{raw.raw_cert_text} cert {ocr_cert}")

    if not ngc.grade and not ngc.cert_number:
        return None  # Not NGC — skip

    classification = classify(raw.title, raw.description)

    price_usd = usd_rate_fn(raw.price, raw.currency)

    # Stable ID: hash of source + lot_url
    sale_id = f"{raw.source.value}-{hashlib.md5(raw.lot_url.encode()).hexdigest()[:12]}"

    sale = Sale(
        id=sale_id,
        source=raw.source,
        listing_type=raw.listing_type,
        lot_url=raw.lot_url,
        title=raw.title,
        description=raw.description,
        hammer_price_usd=price_usd,
        currency_original=raw.currency,
        price_original=raw.price,
        buyers_premium_included=False,
        sale_date=raw.sale_date or datetime.now(timezone.utc).date(),
        image_url=raw.image_url,
        ngc=ngc,
        metadata=SaleMetadata(),
    )
    return sale, classification


def run_scrapers() -> tuple[list[tuple[Sale, dict]], dict[Source, SourceStatus]]:
    """Run all scrapers and return (sales_with_classification, source_statuses)."""
    results: list[tuple[Sale, dict]] = []
    statuses: dict[Source, SourceStatus] = {}

    for scraper in SCRAPERS:
        source = scraper.source
        count  = 0
        dupes  = 0
        status = SourceStatus(status="pending")
        logger.info(f"=== Starting {source.value.upper()} scraper ===")

        # Dedup by sale ID only (source + md5 of lot_url).
        # Note: do NOT normalize/strip query params — many sites (MA Shops,
        # NumisBids) use query params as the item identifier, so stripping
        # them would make every item on the site look identical.
        seen_ids: set[str] = set()

        try:
            from .config import MAX_PAGES
            max_pages = MAX_PAGES.get(source.value, 10)

            for raw in scraper.scrape(max_pages=max_pages):
                result = raw_to_sale(raw)
                if result:
                    sale, classification = result

                    if sale.id in seen_ids:
                        dupes += 1
                        continue

                    seen_ids.add(sale.id)
                    results.append((sale, classification))
                    count += 1

            status = SourceStatus(status="ok", listings_scraped=count)
            if dupes:
                logger.info(f"=== {source.value.upper()} done: {count} NGC listings ({dupes} duplicates removed) ===")
            else:
                logger.info(f"=== {source.value.upper()} done: {count} NGC listings ===")

        except Exception as e:
            logger.error(f"=== {source.value.upper()} failed: {e} ===")
            status = SourceStatus(status="error", listings_scraped=count, last_error=str(e))

        finally:
            try:
                scraper.close()
            except Exception:
                pass
            statuses[source] = status

    return results, statuses


def build_coin_catalog(
    sales_with_class: list[tuple[Sale, dict]]
) -> dict[str, CoinDetail]:
    """Group sales by coin slug and build CoinDetail objects."""
    grouped: dict[str, list[tuple[Sale, dict]]] = defaultdict(list)

    for sale, classification in sales_with_class:
        slug = classification["slug"]
        grouped[slug].append((sale, classification))

    coin_details: dict[str, CoinDetail] = {}

    for slug, items in grouped.items():
        # Cross-source dedup: if same NGC cert number appears from multiple sources
        # (e.g. a CNG sale also listed on VCoins), keep only the auction_realized
        # version, or the first if all are the same type.
        cert_seen: dict[str, Sale] = {}
        deduped_items: list[tuple[Sale, dict]] = []
        for sale, cls_data in items:
            cert = sale.ngc.cert_number
            if cert:
                if cert not in cert_seen:
                    cert_seen[cert] = sale
                    deduped_items.append((sale, cls_data))
                else:
                    # Prefer auction_realized over fixed_price for the same cert
                    existing = cert_seen[cert]
                    if (sale.listing_type == ListingType.AUCTION_REALIZED
                            and existing.listing_type != ListingType.AUCTION_REALIZED):
                        # Replace existing with this realized sale
                        deduped_items = [(s, c) for s, c in deduped_items
                                         if s.ngc.cert_number != cert]
                        deduped_items.append((sale, cls_data))
                        cert_seen[cert] = sale
            else:
                deduped_items.append((sale, cls_data))

        items = deduped_items
        sales = [s for s, _ in items]
        cls   = items[0][1]          # use classification from first sale

        all_prices      = [s.hammer_price_usd for s in sales]
        realized_sales  = [s for s in sales if s.listing_type == ListingType.AUCTION_REALIZED]
        realized_prices = [s.hammer_price_usd for s in realized_sales]
        fixed_count     = sum(1 for s in sales if s.listing_type == ListingType.FIXED_PRICE)

        # Use only realized auction prices for median/range — asking prices skew stats
        price_source = realized_prices if realized_prices else all_prices
        dates   = sorted([s.sale_date.isoformat() for s in sales], reverse=True)

        grade_dist: dict[str, int] = defaultdict(int)
        for sale in sales:
            if sale.ngc.grade:
                grade_dist[sale.ngc.grade.value] += 1

        ngc_verified = sum(1 for s in sales if s.ngc.verified)

        # Thumbnail: prefer realized sale images (more likely to be coin photos)
        thumbnail = next((s.image_url for s in realized_sales if s.image_url), None)
        if not thumbnail:
            thumbnail = next((s.image_url for s in sales if s.image_url), None)

        coin_details[slug] = CoinDetail(
            slug=slug,
            category=cls["category"],
            ruler=cls["ruler"],
            ruler_normalized=cls["ruler_normalized"],
            dynasty=cls["dynasty"],
            denomination=cls["denomination"],
            metal=cls["metal"],
            sale_count=len(sales),
            realized_count=len(realized_sales),
            fixed_price_count=fixed_count,
            ngc_verified_count=ngc_verified,
            price_range_usd=PriceRange(min=min(price_source), max=max(price_source)) if price_source else None,
            median_price_usd=statistics.median(price_source) if price_source else 0.0,
            last_sale_date=dates[0] if dates else "",
            grade_distribution=dict(grade_dist),
            thumbnail_url=thumbnail,
            sales=sales,
        )

    return coin_details


def write_outputs(coin_details: dict[str, CoinDetail], statuses: dict[Source, SourceStatus]) -> None:
    """Write all JSON output files."""
    now = datetime.now(timezone.utc)
    total_sales   = sum(c.sale_count       for c in coin_details.values())
    ngc_verified  = sum(c.ngc_verified_count for c in coin_details.values())

    # --- meta.json ---
    meta = Meta(
        last_updated=now.isoformat(),
        next_update=(now.replace(hour=6, minute=0, second=0, microsecond=0)).isoformat(),
        total_listings=total_sales,
        ngc_verified_count=ngc_verified,
        ngc_mentioned_count=total_sales - ngc_verified,
        sources={src.value: status for src, status in statuses.items()},
    )
    _write_json(DATA_DIR / "meta.json", meta.model_dump())

    # --- catalog/index.json ---
    summaries = [
        CoinSummary(
            slug=c.slug, category=c.category, ruler=c.ruler,
            ruler_normalized=c.ruler_normalized, dynasty=c.dynasty,
            denomination=c.denomination, metal=c.metal,
            sale_count=c.sale_count, realized_count=c.realized_count,
            fixed_price_count=c.fixed_price_count,
            ngc_verified_count=c.ngc_verified_count,
            price_range_usd=c.price_range_usd, median_price_usd=c.median_price_usd,
            last_sale_date=c.last_sale_date, grade_distribution=c.grade_distribution,
            thumbnail_url=c.thumbnail_url,
        )
        for c in coin_details.values()
    ]
    catalog_index = {
        "schema_version": "1.2",
        "generated_at":  now.isoformat(),
        "coins": [s.model_dump() for s in summaries],
    }
    _write_json(CATALOG_DIR / "index.json", catalog_index)

    # --- Individual price files ---
    for slug, coin in coin_details.items():
        _write_json(PRICES_DIR / f"{slug}.json", coin.model_dump())

    # --- Per-category ruler indexes ---
    for category in Category:
        rulers_in_cat = sorted(set(
            (c.ruler, c.ruler_normalized)
            for c in coin_details.values()
            if c.category == category and c.ruler and c.ruler_normalized
        ))
        ruler_index = {
            "rulers": [
                {
                    "name":       ruler,
                    "slug":       slug,
                    "reign":      "",  # populated from rulers.yaml in future
                    "sale_count": sum(1 for c in coin_details.values() if c.ruler_normalized == slug),
                    "data_url":   f"{category.value}/by-ruler/{slug}.json",
                }
                for ruler, slug in rulers_in_cat
            ]
        }
        ruler_dir = CATALOG_DIR / category.value / "by-ruler"
        ruler_dir.mkdir(parents=True, exist_ok=True)
        _write_json(ruler_dir / "index.json", ruler_index)

    logger.info(f"Wrote {len(coin_details)} coin types, {total_sales} total sales")


def _write_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    logger.debug(f"Wrote {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=== Coin Grade Scraper Pipeline Starting ===")

    # Load exchange rates first
    load_exchange_rates(EXCHANGE_RATE_API_KEY)

    # Run all scrapers
    sales_with_class, statuses = run_scrapers()
    logger.info(f"Total NGC listings collected: {len(sales_with_class)}")

    if not sales_with_class:
        logger.warning("No listings collected — writing empty outputs")

    # Build coin catalog
    coin_details = build_coin_catalog(sales_with_class)
    logger.info(f"Unique coin types: {len(coin_details)}")

    # Write all JSON
    write_outputs(coin_details, statuses)

    logger.info("=== Pipeline Complete ===")


if __name__ == "__main__":
    main()

"""
Main pipeline orchestrator.

Run with:  python -m scraper.pipeline
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
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
from .sources.cng              import CNGScraper
from .sources.heritage         import HeritageScraper
from .sources.numisbids        import NumisBidsScraper
from .sources.sixbid           import SixbidScraper
from .sources.hjb              import HJBScraper
from .sources.coinarchives     import CoinArchivesScraper
from .sources.stacksbowers     import StacksBowersScraper
from .sources.greatcollections import GreatCollectionsScraper
from .utils.coin_classifier  import classify
from .utils.ngc_detector     import detect_ngc, verify_cert
from .utils.pcgs_detector    import detect_pcgs
from .utils.price_normalizer import load_exchange_rates, to_usd
from .utils.slab_ocr         import extract_cert_from_image, extract_label_from_image

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
    HeritageScraper(),
    NumisBidsScraper(),
    SixbidScraper(),
    HJBScraper(),
    CoinArchivesScraper(),
    StacksBowersScraper(),
    GreatCollectionsScraper(),
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

    # If NGC not found, try PCGS
    if not ngc.grade and not ngc.cert_number:
        pcgs = detect_pcgs(raw.title, raw.description, raw.raw_cert_text)
        if pcgs.grade or pcgs.cert_number:
            ngc = pcgs   # reuse NGCInfo model; grading_service='pcgs' already set

    # Run OCR on the slab image to extract all label fields.
    # This fills in cert number, grade, scores, weight, region, denomination,
    # and obv/rev description directly from the label photo.
    ocr_label = None
    if raw.image_url:
        ocr_label = extract_label_from_image(raw.image_url)

        if ocr_label.found_anything:
            # Build an enriched cert text and re-run NGC detection
            ocr_extra = " ".join(filter(None, [
                f"NGC {ocr_label.grade}" if ocr_label.grade else "",
                f"cert {ocr_label.cert_number}" if ocr_label.cert_number else "",
                ocr_label.denomination,
                ocr_label.region,
                ocr_label.date_struck,
                ocr_label.obv_rev_desc,
            ]))
            enriched_cert_text = f"{raw.raw_cert_text} {ocr_extra}"

            if ngc.grading_service == "pcgs":
                ngc = detect_pcgs(raw.title, raw.description, enriched_cert_text)
            else:
                ngc = detect_ngc(raw.title, raw.description, enriched_cert_text)

            # If OCR found grade/scores directly, apply them even if text detector missed
            if ocr_label.grade and not ngc.grade:
                from .models import NGCGrade
                grade_map = {"MS": NGCGrade.MS, "AU": NGCGrade.AU, "XF": NGCGrade.XF,
                             "EF": NGCGrade.XF, "VF": NGCGrade.VF, "F": NGCGrade.F,
                             "VG": NGCGrade.VG, "G": NGCGrade.G, "AG": NGCGrade.AG}
                parsed_grade = grade_map.get(ocr_label.grade.upper())
                if parsed_grade:
                    ngc = ngc.model_copy(update={"grade": parsed_grade})

            if ocr_label.cert_number and not ngc.cert_number:
                ngc = ngc.model_copy(update={"cert_number": ocr_label.cert_number})
            if ocr_label.strike_score and not ngc.strike_score:
                ngc = ngc.model_copy(update={"strike_score": ocr_label.strike_score})
            if ocr_label.surface_score and not ngc.surface_score:
                ngc = ngc.model_copy(update={"surface_score": ocr_label.surface_score})
            if ocr_label.details_note and not ngc.details_grade:
                ngc = ngc.model_copy(update={"details_grade": ocr_label.details_note})

    if not ngc.grade and not ngc.cert_number:
        return None  # Neither NGC nor PCGS — skip

    classification = classify(raw.title, raw.description)

    # Supplement classification with OCR label data when text parsing missed it
    if ocr_label:
        if ocr_label.date_struck and not classification.get("date_struck"):
            classification["date_struck"] = ocr_label.date_struck
        if ocr_label.region and not classification.get("mint"):
            classification["mint"] = ocr_label.region
        if ocr_label.denomination and not classification.get("denomination"):
            classification["denomination"] = ocr_label.denomination

    price_usd = usd_rate_fn(raw.price, raw.currency)

    # Stable ID: hash of source + lot_url
    sale_id = f"{raw.source.value}-{hashlib.md5(raw.lot_url.encode()).hexdigest()[:12]}"

    # Populate SaleMetadata from OCR label fields
    metadata = SaleMetadata(
        mint=ocr_label.region if ocr_label else None,
        weight_g=ocr_label.weight_g if ocr_label else None,
        obverse_desc=None,
        reverse_desc=None,
    )
    # Split "obv Apollo, rv lion head" into separate fields if possible
    if ocr_label and ocr_label.obv_rev_desc:
        obv_rv = ocr_label.obv_rev_desc
        rv_split = re.split(r'\brv\b|\brev\b', obv_rv, maxsplit=1, flags=re.IGNORECASE)
        metadata.obverse_desc = rv_split[0].strip().lstrip("obv").strip(" ,") if rv_split else obv_rv
        if len(rv_split) > 1:
            metadata.reverse_desc = rv_split[1].strip()

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
        metadata=metadata,
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

        # Representative strike/surface: most recent realized sale of the top grade
        # that actually has scores recorded.
        top_grade_enum = next(
            (g for g in NGC_GRADE_ORDER if any(s.ngc.grade == g for s in realized_sales)),
            None,
        )
        rep_sale = None
        if top_grade_enum:
            scored = sorted(
                [s for s in realized_sales
                 if s.ngc.grade == top_grade_enum and s.ngc.strike_score is not None],
                key=lambda s: s.sale_date, reverse=True,
            )
            rep_sale = scored[0] if scored else None
            # For US coins: grab numeric grade from any top-grade sale
            if not rep_sale:
                any_top = sorted(
                    [s for s in realized_sales if s.ngc.grade == top_grade_enum and s.ngc.grade_numeric],
                    key=lambda s: s.sale_date, reverse=True,
                )
                rep_sale = any_top[0] if any_top else rep_sale

        # Dominant grading service
        services = [s.ngc.grading_service for s in sales]
        ngc_count  = services.count("ngc")
        pcgs_count = services.count("pcgs")
        if ngc_count == 0:
            dominant_service = "pcgs"
        elif pcgs_count == 0:
            dominant_service = "ngc"
        else:
            dominant_service = "ngc" if ngc_count >= pcgs_count else "pcgs"

        # Median weight across all sales that have weight data
        weights = [s.metadata.weight_g for s in sales if s.metadata.weight_g]
        median_weight = statistics.median(weights) if weights else None

        coin_details[slug] = CoinDetail(
            slug=slug,
            category=cls["category"],
            ruler=cls.get("ruler"),
            ruler_normalized=cls.get("ruler_normalized"),
            dynasty=cls.get("dynasty"),
            ruler_dates=cls.get("ruler_dates"),
            ruler_rarity=cls.get("ruler_rarity"),
            series=cls.get("series"),
            date_struck=cls.get("date_struck"),
            mint_mark=cls.get("mint_mark"),
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
            median_weight_g=median_weight,
            top_strike_score=rep_sale.ngc.strike_score if rep_sale else None,
            top_surface_score=rep_sale.ngc.surface_score if rep_sale else None,
            top_grade_numeric=rep_sale.ngc.grade_numeric if rep_sale else None,
            dominant_service=dominant_service,
            sales=sales,
        )

    return coin_details


def merge_historical(coin_details: dict[str, CoinDetail]) -> None:
    """
    Load existing price files from disk and merge their historical sales into
    coin_details in-place.  Sales are deduplicated by ID so re-scraping the
    same lot never creates a duplicate entry.

    This is how we build a multi-year database: each daily run adds new sales
    on top of all previously accumulated ones.
    """
    new_ids_total = 0
    preserved_coins = 0

    for price_file in PRICES_DIR.glob("*.json"):
        slug = price_file.stem
        try:
            existing_data = json.loads(price_file.read_text(encoding="utf-8"))
            existing_sales_raw = existing_data.get("sales", [])
            if not existing_sales_raw:
                continue

            existing_sales = [Sale.model_validate(s) for s in existing_sales_raw]
        except Exception as e:
            logger.warning(f"[merge] Could not load {price_file.name}: {e}")
            continue

        if slug in coin_details:
            # Merge: add any historical sale IDs not already in the current run
            current_ids = {s.id for s in coin_details[slug].sales}
            new_sales = [s for s in existing_sales if s.id not in current_ids]
            if new_sales:
                coin_details[slug].sales.extend(new_sales)
                new_ids_total += len(new_sales)
                # Recompute aggregate stats with the full merged sale list
                _recompute_stats(coin_details[slug])
        else:
            # Coin type not found in today's scrape — preserve it entirely
            # by reconstructing a CoinDetail from the stored file.
            try:
                coin_details[slug] = CoinDetail.model_validate(existing_data)
                preserved_coins += 1
            except Exception as e:
                logger.warning(f"[merge] Could not reconstruct CoinDetail for {slug}: {e}")

    logger.info(
        f"[merge] Added {new_ids_total} historical sales; "
        f"preserved {preserved_coins} coin types not seen today"
    )


def _recompute_stats(coin: CoinDetail) -> None:
    """Recompute aggregate fields after sales list has been extended with historical data."""
    sales = coin.sales
    realized = [s for s in sales if s.listing_type == ListingType.AUCTION_REALIZED]
    fixed    = [s for s in sales if s.listing_type == ListingType.FIXED_PRICE]

    price_source = [s.hammer_price_usd for s in realized] or [s.hammer_price_usd for s in sales]
    dates = sorted([s.sale_date.isoformat() for s in sales], reverse=True)

    grade_dist: dict[str, int] = defaultdict(int)
    for s in sales:
        if s.ngc.grade:
            grade_dist[s.ngc.grade.value] += 1

    coin.sale_count          = len(sales)
    coin.realized_count      = len(realized)
    coin.fixed_price_count   = len(fixed)
    coin.ngc_verified_count  = sum(1 for s in sales if s.ngc.verified)
    coin.price_range_usd     = PriceRange(min=min(price_source), max=max(price_source)) if price_source else None
    coin.median_price_usd    = statistics.median(price_source) if price_source else 0.0
    coin.last_sale_date      = dates[0] if dates else ""
    coin.grade_distribution  = dict(grade_dist)

    # Thumbnail: prefer realized sale images
    thumbnail = next((s.image_url for s in realized if s.image_url), None)
    if not thumbnail:
        thumbnail = next((s.image_url for s in sales if s.image_url), None)
    coin.thumbnail_url = thumbnail


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
            ruler_dates=c.ruler_dates, ruler_rarity=c.ruler_rarity,
            denomination=c.denomination, metal=c.metal,
            sale_count=c.sale_count, realized_count=c.realized_count,
            fixed_price_count=c.fixed_price_count,
            ngc_verified_count=c.ngc_verified_count,
            price_range_usd=c.price_range_usd, median_price_usd=c.median_price_usd,
            last_sale_date=c.last_sale_date, grade_distribution=c.grade_distribution,
            thumbnail_url=c.thumbnail_url,
            median_weight_g=c.median_weight_g,
            top_strike_score=c.top_strike_score,
            top_surface_score=c.top_surface_score,
            top_grade_numeric=c.top_grade_numeric,
            dominant_service=c.dominant_service,
            series=c.series,
            date_struck=c.date_struck,
            mint_mark=c.mint_mark,
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

    # Build coin catalog from today's scrape
    coin_details = build_coin_catalog(sales_with_class)
    logger.info(f"Unique coin types from today's scrape: {len(coin_details)}")

    # Merge with all previously accumulated historical sales
    merge_historical(coin_details)
    logger.info(f"Total unique coin types after merge: {len(coin_details)}")

    # Write all JSON
    write_outputs(coin_details, statuses)

    logger.info("=== Pipeline Complete ===")


if __name__ == "__main__":
    main()

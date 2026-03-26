"""
Fix misclassified coins by re-running the updated classifier on known-bad files.

Run:  python reclassify_misclassified.py [--dry-run]

For each sale in a target file, re-classifies it with the updated classifier.
Coins that stay in the same slug are kept; coins that reclassify elsewhere
are redistributed to the correct price file and the catalog index is updated.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

PRICES_DIR = Path("data/prices")
CATALOG_DIR = Path("data/catalog")
INDEX_FILE  = CATALOG_DIR / "index.json"
DRY_RUN     = "--dry-run" in sys.argv

# Files to reclassify (slug -> file path)
TARGETS = [
    "roman-julius-caesar-ar-denarius",
    "roman-mark-antony-ar-denarius",
    "roman-augustus-ar-denarius",
    "roman-tiberius-av-solidus",
    "roman-augustus-unknown",
    "roman-ar-denarius",
]


def _median(vals):
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def reclassify():
    from scraper.utils.coin_classifier import classify, _load_rulers, _load_taxonomy
    _load_rulers.cache_clear()
    _load_taxonomy.cache_clear()

    with open(INDEX_FILE, encoding="utf-8") as f:
        index = json.load(f)
    summaries = {c["slug"]: c for c in index["coins"]}

    for parent_slug in TARGETS:
        prices_file = PRICES_DIR / f"{parent_slug}.json"
        if not prices_file.exists():
            print(f"SKIP (no file): {parent_slug}")
            continue

        coin_data = json.loads(prices_file.read_text(encoding="utf-8"))
        sales = coin_data.get("sales", [])
        print(f"\n{parent_slug}  [{len(sales)} sales]")

        # Re-classify each sale
        by_slug: dict[str, list[dict]] = defaultdict(list)
        for sale in sales:
            result = classify(sale.get("title", ""), sale.get("description", ""))
            new_slug = result["slug"]
            by_slug[new_slug].append(sale)

        kept  = by_slug.get(parent_slug, [])
        moved = {slug: sls for slug, sls in by_slug.items() if slug != parent_slug}
        print(f"  Kept in {parent_slug}: {len(kept)}")
        for slug, sls in sorted(moved.items(), key=lambda x: -len(x[1])):
            print(f"  -> {slug}: {len(sls)}")

        if DRY_RUN:
            continue

        # Write updated parent file (only the correctly classified sales)
        parent_summary = summaries.get(parent_slug, {})
        if kept:
            parent_coin = {**coin_data, "sales": kept}
            if parent_summary:
                prices = [s["hammer_price_usd"] for s in kept]
                realized = [s for s in kept if s.get("listing_type") == "auction_realized"]
                realized_prices = [s["hammer_price_usd"] for s in realized]
                price_src = realized_prices if realized_prices else prices
                parent_coin.update({
                    "sale_count": len(kept),
                    "realized_count": len(realized),
                    "fixed_price_count": len(kept) - len(realized),
                    "median_price_usd": _median(price_src),
                    "price_range_usd": {
                        "min": min(price_src) if price_src else 0,
                        "max": max(price_src) if price_src else 0,
                    },
                })
            prices_file.write_text(json.dumps(parent_coin, ensure_ascii=False, default=str), encoding="utf-8")
            if parent_summary:
                summaries[parent_slug] = {**parent_summary, **{k: parent_coin[k] for k in
                    ["sale_count","realized_count","fixed_price_count","median_price_usd","price_range_usd"]
                    if k in parent_coin}}
        else:
            # All moved — remove parent file and index entry
            prices_file.write_text(json.dumps({**coin_data, "sales": []}, ensure_ascii=False, default=str), encoding="utf-8")
            summaries.pop(parent_slug, None)
            print(f"  Parent file cleared (all reclassified)")

        # Merge moved sales into destination files
        for dest_slug, dest_sales in moved.items():
            dest_file = PRICES_DIR / f"{dest_slug}.json"
            if dest_file.exists():
                existing = json.loads(dest_file.read_text(encoding="utf-8"))
                combined = existing.get("sales", []) + dest_sales
                # Deduplicate by lot_url
                seen = set()
                deduped = []
                for s in combined:
                    key = s.get("lot_url", "") or s.get("title", "")
                    if key not in seen:
                        seen.add(key)
                        deduped.append(s)
                existing["sales"] = deduped
                # Recompute stats
                prices = [s["hammer_price_usd"] for s in deduped]
                realized = [s for s in deduped if s.get("listing_type") == "auction_realized"]
                realized_prices = [s["hammer_price_usd"] for s in realized]
                price_src = realized_prices if realized_prices else prices
                existing.update({
                    "sale_count": len(deduped),
                    "realized_count": len(realized),
                    "fixed_price_count": len(deduped) - len(realized),
                    "median_price_usd": _median(price_src) if price_src else 0,
                    "price_range_usd": {
                        "min": min(price_src) if price_src else 0,
                        "max": max(price_src) if price_src else 0,
                    },
                })
                dest_file.write_text(json.dumps(existing, ensure_ascii=False, default=str), encoding="utf-8")
                # Update index summary
                if dest_slug in summaries:
                    summaries[dest_slug].update({k: existing[k] for k in
                        ["sale_count","realized_count","median_price_usd","price_range_usd"]
                        if k in existing})
                else:
                    summaries[dest_slug] = {k: existing[k] for k in existing if k != "sales"}
                print(f"  Merged {len(dest_sales)} into existing {dest_slug}")
            else:
                # Destination doesn't exist — create a minimal file
                prices = [s["hammer_price_usd"] for s in dest_sales]
                realized = [s for s in dest_sales if s.get("listing_type") == "auction_realized"]
                realized_prices = [s["hammer_price_usd"] for s in realized]
                price_src = realized_prices if realized_prices else prices
                new_file = {
                    "slug": dest_slug,
                    "sale_count": len(dest_sales),
                    "realized_count": len(realized),
                    "fixed_price_count": len(dest_sales) - len(realized),
                    "median_price_usd": _median(price_src) if price_src else 0,
                    "price_range_usd": {"min": min(price_src) if price_src else 0, "max": max(price_src) if price_src else 0},
                    "sales": dest_sales,
                }
                dest_file.write_text(json.dumps(new_file, ensure_ascii=False, default=str), encoding="utf-8")
                summaries[dest_slug] = {k: new_file[k] for k in new_file if k != "sales"}
                print(f"  Created new file: {dest_slug} ({len(dest_sales)} sales)")

    if not DRY_RUN:
        index["coins"] = list(summaries.values())
        INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        total_moved = sum(
            sum(len(sls) for sls in {slug: sls for slug, sls in defaultdict(list).items() if slug != p}.values())
            for p in TARGETS
        )
        print(f"\nDone. Index updated: {len(index['coins'])} types.")


if __name__ == "__main__":
    reclassify()

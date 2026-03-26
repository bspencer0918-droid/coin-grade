"""
Retroactive type-split reclassification.

Reads existing price JSON files, applies detect_coin_type() to each sale,
and creates new split files (e.g. greek-athens-ar-tetradrachm-classical-owl).

Run from the project root:
    python reclassify_types.py [--dry-run]

--dry-run: show what would change, don't write files.
"""
from __future__ import annotations

import json
import sys
import statistics
from collections import defaultdict
from pathlib import Path
from datetime import date

PRICES_DIR   = Path("data/prices")
CATALOG_DIR  = Path("data/catalog")
INDEX_FILE   = CATALOG_DIR / "index.json"
DRY_RUN      = "--dry-run" in sys.argv

# Slugs to split — only process these parent types.
# Only split where the type genuinely changes price substantially AND
# we have enough title-based signal to classify reliably.
SPLIT_SLUGS = {
    "greek-athens-ar-tetradrachm",         # Archaic 5x vs Classical 1x vs New Style 0.35x
    "greek-alexander-iii-ar-tetradrachm",  # Lifetime 4x vs posthumous
    "roman-julius-caesar-ar-denarius",     # Elephant vs portrait denarius
    "roman-tiberius-ar-denarius",          # All are Tribute Pennies — label for clarity
    "roman-mark-antony-ar-denarius",       # Legionary type vs other types
}

# Type labels from taxonomy (keep in sync with coin_type_taxonomy.yaml)
TYPE_LABELS = {
    "archaic-owl":             "Athens AR Tetradrachm — Archaic Owl",
    "transitional-owl":        "Athens AR Tetradrachm — Transitional Owl",
    "classical-owl":           "Athens AR Tetradrachm — Classical Owl",
    "late-classical-owl":      "Athens AR Tetradrachm — Late Classical/Intermediate",
    "new-style-owl":           "Athens AR Tetradrachm — New Style",
    "lifetime-issue":          "Alexander III AR Tetradrachm — Lifetime Issue",
    "posthumous-early":        "Alexander III AR Tetradrachm — Early Posthumous",
    "posthumous-late":         "Alexander III AR Tetradrachm — Late Posthumous/Imitative",
    "dacia-capta":             "Trajan AR Denarius — DACIA CAPTA",
    "arabia-adquisita":        "Trajan AR Denarius — ARABIA ADQVISITA",
    "column-types":            "Trajan AR Denarius — Column/Triumph Types",
    "spqr-optimo-principi":    "Trajan AR Denarius — SPQR OPTIMO PRINCIPI",
    "elephant-priestly":       "Julius Caesar AR Denarius — Elephant/Priestly",
    "portrait-denarius":       "Julius Caesar AR Denarius — Portrait Type",
    "tribute-penny-type":      "Tiberius AR Denarius — Tribute Penny",
    "caius-lucius":            "Augustus AR Denarius — CAIVS LVCIVS",
    "constantine-i-solidus":   "Constantine I AV Solidus",
    "justinian-i-solidus":     "Justinian I AV Solidus",
    "legionary":               "Mark Antony AR Denarius — Legionary",
}

# Grade order for distribution / statistics
GRADE_ORDER = ["MS", "AU", "XF", "VF", "F", "VG", "G", "AG", "P"]


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _rebuild_summary(parent_summary: dict, slug: str, sales: list[dict]) -> dict:
    """Build a CoinSummary dict from a list of sales and a parent summary template."""
    all_prices = [s["hammer_price_usd"] for s in sales]
    realized   = [s for s in sales if s["listing_type"] == "auction_realized"]
    realized_prices = [s["hammer_price_usd"] for s in realized]
    price_src  = realized_prices if realized_prices else all_prices

    grade_dist: dict[str, int] = defaultdict(int)
    for s in sales:
        g = s.get("ngc", {}).get("grade")
        if g:
            grade_dist[g] += 1

    last_date  = sorted(s["sale_date"] for s in sales)[-1]
    thumbnail  = next((s["image_url"] for s in realized if s.get("image_url")), None)
    if not thumbnail:
        thumbnail = next((s["image_url"] for s in sales if s.get("image_url")), None)

    ngc_verified = sum(1 for s in sales if s.get("ngc", {}).get("verified"))
    ngc_count    = sum(1 for s in sales if s.get("ngc", {}).get("grade"))

    # Extract the type suffix (e.g. "classical-owl" from "..-classical-owl")
    parent_slug_prefix = parent_summary.get("slug", "")
    if slug != parent_slug_prefix and slug.startswith(parent_slug_prefix + "-"):
        type_suffix = slug[len(parent_slug_prefix) + 1:]
    else:
        type_suffix = ""
    label = TYPE_LABELS.get(type_suffix, "")

    return {
        **parent_summary,
        "slug":                slug,
        "denomination":        label if label else parent_summary.get("denomination", slug),
        "sale_count":          len(sales),
        "realized_count":      len(realized),
        "fixed_price_count":   len(sales) - len(realized),
        "ngc_verified_count":  ngc_verified,
        "price_range_usd":     {"min": min(price_src) if price_src else 0,
                                "max": max(price_src) if price_src else 0},
        "median_price_usd":    _median(price_src),
        "last_sale_date":      last_date,
        "grade_distribution":  dict(grade_dist),
        "thumbnail_url":       thumbnail,
    }


def reclassify():
    from scraper.utils.coin_classifier import detect_coin_type, _load_taxonomy
    _load_taxonomy.cache_clear()

    # Load existing index
    with open(INDEX_FILE, encoding="utf-8") as f:
        index = json.load(f)

    # Build lookup: slug → summary
    summaries = {c["slug"]: c for c in index["coins"]}
    new_summaries = {slug: s for slug, s in summaries.items()}

    total_split = 0

    for parent_slug in sorted(SPLIT_SLUGS):
        prices_file = PRICES_DIR / f"{parent_slug}.json"
        if not prices_file.exists():
            print(f"  SKIP (no file): {parent_slug}")
            continue

        with open(prices_file, encoding="utf-8") as f:
            coin_data = json.load(f)

        sales = coin_data.get("sales", [])
        parent_summary = summaries.get(parent_slug, {})

        # Group sales by detected type
        by_type: dict[str, list[dict]] = defaultdict(list)
        for sale in sales:
            t = detect_coin_type(parent_slug, sale.get("title", ""), sale.get("description", ""))
            if t:
                by_type[t].append(sale)
            else:
                by_type["__unclassified__"].append(sale)

        unclassified = by_type.pop("__unclassified__", [])
        typed_count  = sum(len(v) for v in by_type.values())
        print(f"\n{parent_slug}  [{len(sales)} total]")
        for t, t_sales in sorted(by_type.items(), key=lambda x: -len(x[1])):
            print(f"  -> {t}: {len(t_sales)}")
        if unclassified:
            print(f"  -> (unclassified): {len(unclassified)}")

        if DRY_RUN:
            continue

        # Write new type-specific files
        for type_id, type_sales in by_type.items():
            new_slug = f"{parent_slug}-{type_id}"
            out_file = PRICES_DIR / f"{new_slug}.json"

            # Build full CoinDetail structure (extends CoinSummary)
            summary = _rebuild_summary(parent_summary, new_slug, type_sales) if parent_summary else {"slug": new_slug}
            new_coin = {**summary, "sales": type_sales}
            out_file.write_text(json.dumps(new_coin, ensure_ascii=False, default=str), encoding="utf-8")

            # Update index summary
            if parent_summary:
                new_summaries[new_slug] = _rebuild_summary(parent_summary, new_slug, type_sales)

        # If most sales are classified, update parent to only hold unclassified
        # (keeps backward compat: parent slug still exists but with fewer entries)
        # Update parent file: keep only unclassified sales (or empty if all classified)
        if parent_summary:
            parent_coin = {**_rebuild_summary(parent_summary, parent_slug, unclassified), "sales": unclassified}
        else:
            parent_coin = {**coin_data, "sales": unclassified}
        prices_file.write_text(json.dumps(parent_coin, ensure_ascii=False, default=str), encoding="utf-8")
        if unclassified and parent_summary:
            new_summaries[parent_slug] = _rebuild_summary(parent_summary, parent_slug, unclassified)
        else:
            # All sales classified — remove parent from index
            new_summaries.pop(parent_slug, None)

        total_split += typed_count

    if not DRY_RUN:
        # Rebuild catalog index
        index["coins"] = list(new_summaries.values())
        INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        print(f"\nDone. {total_split} sales reclassified. Index updated: {len(index['coins'])} types.")
    else:
        print(f"\n[DRY RUN] Would reclassify {total_split} sales.")


if __name__ == "__main__":
    reclassify()

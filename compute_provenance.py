"""
Perceptual image hashing for coin provenance tracking.

Identifies when the same physical coin reappears across multiple auction
records by computing a perceptual hash (pHash) of each sale image and
finding near-duplicate matches (Hamming distance ≤ 8).

Usage:
    python compute_provenance.py [--max-images N] [--dry-run]

Options:
    --max-images N   Cap total image downloads (default: 5000)
    --dry-run        Hash only; skip writing output files
    --slug SLUG      Process only a specific price file slug

Output:
    - Adds `image_hash` field to each processed sale record
    - Writes data/catalog/provenance_chains.json with all match groups
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import time

# Fix Windows cp1252 console encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from collections import defaultdict
from pathlib import Path
from typing import Optional

import requests
import imagehash
from PIL import Image

PRICES_DIR   = Path("data/prices")
CATALOG_DIR  = Path("data/catalog")
CHAINS_FILE  = CATALOG_DIR / "provenance_chains.json"

# Hamming distance threshold: 0-3 = identical photo, 4-8 = same coin/slightly different crop
MATCH_THRESHOLD = 8

DRY_RUN    = "--dry-run"    in sys.argv
SLUG_FILTER = next((sys.argv[sys.argv.index("--slug") + 1] for i, a in enumerate(sys.argv) if a == "--slug"), None) if "--slug" in sys.argv else None
MAX_IMAGES = int(next((sys.argv[sys.argv.index("--max-images") + 1] for i, a in enumerate(sys.argv) if a == "--max-images"), 5000)) if "--max-images" in sys.argv else 5000

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; coin-provenance-tracker/1.0; +https://chroniclecoins.app)"
})


def phash_from_url(url: str) -> Optional[str]:
    """Download image and return its pHash hex string, or None on failure."""
    try:
        resp = SESSION.get(url, timeout=10, stream=True)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        # Crop to centre 80% to reduce border/watermark interference
        w, h = img.size
        margin_w, margin_h = int(w * 0.10), int(h * 0.10)
        img = img.crop((margin_w, margin_h, w - margin_w, h - margin_h))
        h_val = imagehash.phash(img, hash_size=8)
        return str(h_val)
    except Exception as e:
        return None


def hamming(a: str, b: str) -> int:
    """Hamming distance between two hex pHash strings."""
    ia = int(a, 16)
    ib = int(b, 16)
    return bin(ia ^ ib).count("1")


def load_all_sales() -> dict[str, list[dict]]:
    """Returns {slug: [sales]} for all price files (or just SLUG_FILTER)."""
    result = {}
    for f in sorted(PRICES_DIR.glob("*.json")):
        slug = f.stem
        if SLUG_FILTER and slug != SLUG_FILTER:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        sales = data.get("sales", [])
        if sales:
            result[slug] = sales
    return result


def compute_hashes(all_sales: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """
    Download and hash images for sales that don't yet have image_hash.
    Returns updated {slug: [sales]} dict.
    Writes updated price files immediately for checkpoint safety.
    """
    total_downloaded = 0
    total_already    = 0
    total_no_image   = 0

    for slug, sales in all_sales.items():
        needs_hash = [s for s in sales if s.get("image_url") and not s.get("image_hash")]
        has_hash   = sum(1 for s in sales if s.get("image_hash"))
        total_already += has_hash

        if not needs_hash:
            continue
        if total_downloaded >= MAX_IMAGES:
            break

        prices_file = PRICES_DIR / f"{slug}.json"
        data = json.loads(prices_file.read_text(encoding="utf-8"))
        sale_index = {s.get("id", s.get("lot_url", "")): i for i, s in enumerate(data["sales"])}

        changed = False
        for sale in needs_hash:
            if total_downloaded >= MAX_IMAGES:
                break
            url = sale.get("image_url", "")
            if not url:
                total_no_image += 1
                continue

            h = phash_from_url(url)
            total_downloaded += 1
            sale_key = sale.get("id", sale.get("lot_url", ""))
            if h and sale_key in sale_index:
                data["sales"][sale_index[sale_key]]["image_hash"] = h
                sale["image_hash"] = h
                changed = True

            if total_downloaded % 50 == 0:
                print(f"  {total_downloaded} hashed ({total_already} already had hashes)…")

            # Polite rate limiting: ~3 requests/second
            time.sleep(0.33)

        if changed and not DRY_RUN:
            prices_file.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"\nHashing complete: {total_downloaded} new, {total_already} pre-existing, {total_no_image} no-image")
    return all_sales


def find_provenance_chains(all_sales: dict[str, list[dict]]) -> list[dict]:
    """
    Group sales whose image hashes are within MATCH_THRESHOLD Hamming distance.
    Returns list of provenance groups (only groups with 2+ sales).
    """
    # Collect (hash, sale_ref) pairs
    hashed: list[tuple[str, dict]] = []
    for slug, sales in all_sales.items():
        for sale in sales:
            h = sale.get("image_hash")
            if not h:
                continue
            hashed.append((h, {
                "sale_id":   sale.get("id", ""),
                "slug":      slug,
                "source":    sale.get("source", ""),
                "title":     sale.get("title", "")[:120],
                "lot_url":   sale.get("lot_url", ""),
                "sale_date": sale.get("sale_date", ""),
                "price_usd": sale.get("hammer_price_usd", 0),
                "image_url": sale.get("image_url", ""),
            }))

    print(f"\nMatching {len(hashed)} hashed sales against each other…")

    # Union-Find for grouping
    parent = list(range(len(hashed)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    # O(n²) is fine for n ≤ 50k with early exit — takes ~5s for 5k hashed
    for i in range(len(hashed)):
        for j in range(i + 1, len(hashed)):
            if hamming(hashed[i][0], hashed[j][0]) <= MATCH_THRESHOLD:
                union(i, j)

    # Group by root
    groups: dict[int, list] = defaultdict(list)
    for i, (h, ref) in enumerate(hashed):
        groups[find(i)].append({**ref, "hash": h})

    # Keep only multi-sale groups (actual provenance matches)
    chains = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # Sort by date so earliest sale is first
        members.sort(key=lambda x: x["sale_date"])
        chains.append({
            "hash": members[0]["hash"],
            "sales": members,
            "price_change_pct": round(
                ((members[-1]["price_usd"] - members[0]["price_usd"]) / members[0]["price_usd"] * 100)
                if members[0]["price_usd"] > 0 else 0, 1
            ),
        })

    chains.sort(key=lambda x: -len(x["sales"]))
    return chains


def main():
    print(f"Loading price files…")
    all_sales = load_all_sales()
    total_sales = sum(len(v) for v in all_sales.values())
    total_with_img = sum(1 for sales in all_sales.values() for s in sales if s.get("image_url"))
    print(f"  {len(all_sales)} files · {total_sales:,} sales · {total_with_img:,} have images")

    print(f"\nPhase 1: Hashing images (max {MAX_IMAGES})…")
    all_sales = compute_hashes(all_sales)

    print(f"\nPhase 2: Finding provenance matches (Hamming ≤ {MATCH_THRESHOLD})…")
    chains = find_provenance_chains(all_sales)

    print(f"\nFound {len(chains)} provenance chains:")
    for chain in chains[:20]:
        dates = [s["sale_date"] for s in chain["sales"]]
        prices = [s["price_usd"] for s in chain["sales"]]
        slugs = list({s["slug"] for s in chain["sales"]})
        change = chain["price_change_pct"]
        change_str = f"+{change}%" if change >= 0 else f"{change}%"
        print(f"  [{len(chain['sales'])} sales, {change_str}] {' → '.join(dates)} | {slugs[0]}")
        for s in chain["sales"]:
            print(f"    ${s['price_usd']:,.0f}  {s['sale_date']}  {s['source']}  {s['title'][:70]}")

    if not DRY_RUN:
        CHAINS_FILE.write_text(
            json.dumps({"generated": str(time.time()), "chains": chains}, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8"
        )
        print(f"\nWrote {len(chains)} chains → {CHAINS_FILE}")


if __name__ == "__main__":
    main()

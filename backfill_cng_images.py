"""
Backfill image URLs for existing CNG lot records at auctions.cngcoins.com.

Each lot page embeds the AuctionMobility CDN image URL in its HTML.
This script fetches each lot page, extracts the image URL, and stores it
in the price file so compute_provenance.py can hash it.

Usage:
    python backfill_cng_images.py [--dry-run]
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DRY_RUN   = "--dry-run" in sys.argv
PRICES_DIR = Path("data/prices")

IMG_RE = re.compile(
    r'https://images\d+-cdn\.auctionmobility\.com'
    r'/is3/auctionmobility-static\d+/[A-Za-z0-9_\-]+/'
    r'([0-9A-Z]{1,2}-[A-Z0-9]{6})/[^\s"\'\\<>]+\.jpg'
)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; coin-provenance-tracker/1.0)",
})


def extract_cng_image_url(lot_url: str) -> str | None:
    """Fetch a CNG lot page and return the first AuctionMobility CDN image URL."""
    try:
        resp = SESSION.get(lot_url, timeout=20)
        resp.raise_for_status()
        # Unescape HTML entities and JSON escape sequences
        text = resp.text.replace("\\u0026", "&").replace("&amp;", "&")
        m = IMG_RE.search(text)
        if m:
            url = m.group(0).split('"')[0].split("'")[0]
            # Use 400x400 for hashing (smaller download)
            url = re.sub(r'width=\d+', 'width=400', url)
            url = re.sub(r'height=\d+', 'height=400', url)
            return url
    except Exception:
        pass
    return None


def main() -> None:
    total_updated = 0
    total_already = 0
    total_failed  = 0

    for prices_file in sorted(PRICES_DIR.glob("*.json")):
        data = json.loads(prices_file.read_text(encoding="utf-8"))
        sales = data.get("sales", [])

        needs_img = [
            s for s in sales
            if s.get("source") == "cng"
            and "auctions.cngcoins.com" in s.get("lot_url", "")
            and not s.get("image_url")
        ]
        already = sum(
            1 for s in sales
            if s.get("source") == "cng"
            and s.get("image_url")
        )
        total_already += already

        if not needs_img:
            continue

        print(f"\n{prices_file.stem}: {len(needs_img)} CNG lots to backfill")
        changed = False

        sale_index = {
            s.get("id", s.get("lot_url", "")): i for i, s in enumerate(sales)
        }

        for sale in needs_img:
            lot_url = sale["lot_url"]
            img_url = extract_cng_image_url(lot_url)
            key = sale.get("id", lot_url)

            if img_url and key in sale_index:
                data["sales"][sale_index[key]]["image_url"] = img_url
                sale["image_url"] = img_url
                total_updated += 1
                changed = True
                print(f"  OK  {lot_url.split('/')[-1]}  {img_url[:60]}…")
            else:
                total_failed += 1
                print(f"  FAIL {lot_url.split('/')[-1]}")

            time.sleep(1.0)  # polite rate limit

        if changed and not DRY_RUN:
            prices_file.write_text(
                json.dumps(data, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

    print(f"\nDone: {total_updated} updated, {total_already} already had URLs, {total_failed} failed")


if __name__ == "__main__":
    main()

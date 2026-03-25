"""
Discovery script: connect to Heritage via CDP, load the Ancient Coins page,
and extract the filter parameter names + values from the sidebar.
Run with: python -m scraper.heritage_discover
"""
import asyncio
import json
import sys
from bs4 import BeautifulSoup

CDP_URL = "http://localhost:9222"
SEARCH_URL = (
    "https://coins.ha.com/c/search/results.zx"
    "?si=2&dept=1909&archive_state=5327"
    "&sold_status=1526~1524&coin_category=1495&mode=archive"
)


async def discover():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()

        print(f"Navigating to: {SEARCH_URL}")
        await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # Print the page title
        title = soup.find("title")
        print(f"Page title: {title.get_text() if title else '?'}\n")

        # Look for filter sidebar — Heritage uses various containers
        # Try to find checkboxes / filter links
        print("=== FILTER LINKS (href patterns) ===")
        for a in soup.select("a[href*='ancient_coin_grade'], a[href*='coin_category'], a[href*='civilization']"):
            print(f"  {a.get('href', '')[:120]}  |  text: {a.get_text(strip=True)[:50]}")

        print("\n=== FILTER FORM INPUTS ===")
        for inp in soup.select("input[name*='grade'], input[name*='category'], input[name*='civil']"):
            print(f"  name={inp.get('name')} value={inp.get('value')} type={inp.get('type')}")

        print("\n=== CHECKBOXES IN SIDEBAR ===")
        # Heritage typically wraps filters in a refinements/sidebar div
        sidebar = soup.select_one(
            "div.refine-search, div.refinement-panel, "
            "div.search-filters, aside, div[class*='refine'], div[class*='filter']"
        )
        if sidebar:
            print(f"Found sidebar: {sidebar.get('class')}")
            for inp in sidebar.select("input"):
                print(f"  input name={inp.get('name')} value={inp.get('value')} type={inp.get('type')}")
            for a in sidebar.select("a"):
                href = a.get("href", "")
                text = a.get_text(strip=True)[:60]
                if href and text:
                    print(f"  <a> {text!r}: {href[:120]}")
        else:
            print("No sidebar found — dumping all filter-related elements")

        print("\n=== ALL LINKS CONTAINING SEARCH PARAMS ===")
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if "results.zx" in href or "search/results" in href:
                key = href[:150]
                if key not in seen:
                    seen.add(key)
                    print(f"  {href[:150]}")

        print("\n=== CURRENT URL ===")
        print(await page.url)

        # Save full HTML for manual inspection
        with open("heritage_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("\nFull HTML saved to heritage_page.html")

        await page.close()


if __name__ == "__main__":
    asyncio.run(discover())

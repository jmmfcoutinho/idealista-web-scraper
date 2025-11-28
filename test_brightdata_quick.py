#!/usr/bin/env python3
"""Quick Bright Data test for Idealista URLs.

Uses Bright Data Scraping Browser with Playwright.
"""

import os
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

# Scraping Browser credentials from the playground
BROWSER_USER = "brd-customer-hl_52df750f-zone-scraping_browser1"
BROWSER_PASS = "ge1z02xlafb5"
BROWSER_WS = f"wss://{BROWSER_USER}:{BROWSER_PASS}@brd.superproxy.io:9222"

print(f"Using Scraping Browser: {BROWSER_USER}")

# Test URLs
TEST_URLS = [
    {
        "name": "search_cascais",
        "url": "https://www.idealista.pt/comprar-casas/cascais/",
        "wait_selector": "article.item",
    },
    {
        "name": "homepage",
        "url": "https://www.idealista.pt/",
        "wait_selector": "nav.locations-list",
    },
]


def test_scraping_browser(name: str, url: str, wait_selector: str) -> dict:
    """Test using Bright Data Scraping Browser with Playwright."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"Wait selector: {wait_selector}")
    
    start_time = time.time()
    
    try:
        with sync_playwright() as p:
            print("Connecting to Scraping Browser...")
            browser = p.chromium.connect_over_cdp(BROWSER_WS)
            
            print("Connected! Creating page...")
            page = browser.new_page()
            
            print(f"Navigating to {url}...")
            page.goto(url, timeout=120_000, wait_until="domcontentloaded")
            
            print(f"Waiting for selector: {wait_selector}...")
            try:
                page.wait_for_selector(wait_selector, timeout=30_000)
                print("Selector found!")
            except Exception as e:
                print(f"Selector wait failed: {e}")
            
            # Get page content
            html = page.content()
            html_len = len(html)
            
            elapsed = time.time() - start_time
            
            # Check for success indicators
            has_idealista = "idealista" in html.lower()
            has_listings = "article" in html and "item" in html
            # Check for actual blocking (not just recaptcha config vars)
            is_blocked = "access denied" in html.lower() or "you have been blocked" in html.lower()
            
            print(f"Time: {elapsed:.2f}s")
            print(f"HTML size: {html_len:,} bytes")
            print(f"Has Idealista content: {has_idealista}")
            print(f"Has listings structure: {has_listings}")
            print(f"Blocked/Captcha: {is_blocked}")
            
            # Save HTML for inspection
            output_file = f"html/brightdata_{name}.html"
            os.makedirs("html", exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"Saved to: {output_file}")
            
            browser.close()
            
            return {
                "name": name,
                "method": "scraping_browser",
                "success": has_idealista and not is_blocked,
                "html_size": html_len,
                "has_content": has_idealista,
                "time": elapsed,
            }
            
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"EXCEPTION: {type(e).__name__}: {e}")
        return {"name": name, "success": False, "error": str(e), "time": elapsed}


def main():
    print("=" * 60)
    print("BRIGHT DATA SCRAPING BROWSER TEST FOR IDEALISTA")
    print("=" * 60)
    
    results = []
    
    for test in TEST_URLS:
        result = test_scraping_browser(test["name"], test["url"], test["wait_selector"])
        results.append(result)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    successes = sum(1 for r in results if r.get("success"))
    print(f"Results: {successes}/{len(results)} successful")
    print()
    
    for r in results:
        status = "✓" if r.get("success") else "✗"
        time_str = f"{r['time']:.2f}s"
        if r.get("success"):
            print(f"  {status} {r['name']}: {r.get('html_size', 0):,} bytes ({time_str})")
        else:
            print(f"  {status} {r['name']}: {r.get('error', 'failed')[:60]} ({time_str})")
    
    print("\n" + "-" * 60)
    if successes == len(results):
        print("✓ All tests passed! Bright Data Scraping Browser works great.")
    elif successes > 0:
        print("⚠ Some tests failed. Check the errors above.")
    else:
        print("✗ All tests failed. May need different configuration.")


if __name__ == "__main__":
    main()

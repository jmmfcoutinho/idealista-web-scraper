#!/usr/bin/env python3
"""Quick Zyte API test for Idealista URLs."""

import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ZYTE_API_KEY")
if not API_KEY:
    print("ERROR: ZYTE_API_KEY not found in environment variables")
    sys.exit(1)

print(f"Using API key: {API_KEY[:8]}...{API_KEY[-4:]}")

# Test URLs - a few key ones to validate the provider works
TEST_URLS = [
    # Search results page - this is the most important one
    {
        "name": "search_cascais",
        "url": "https://www.idealista.pt/comprar-casas/cascais/",
        "wait_selector": "article.item",
    },
    # Listing detail page
    {
        "name": "listing_detail",
        "url": "https://www.idealista.pt/imovel/33492587/",
        "wait_selector": "section.detail-info",
    },
    # Homepage
    {
        "name": "homepage",
        "url": "https://www.idealista.pt/",
        "wait_selector": "nav.locations-list",
    },
]


def test_url(name: str, url: str, wait_selector: str) -> dict:
    """Test a single URL with Zyte API."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"Wait selector: {wait_selector}")
    
    start_time = time.time()
    
    try:
        payload = {
            "url": url,
            "browserHtml": True,
            "actions": [
                {
                    "action": "waitForSelector",
                    "selector": {"type": "css", "value": wait_selector},
                    "timeout": 15,
                }
            ],
        }
        
        response = requests.post(
            "https://api.zyte.com/v1/extract",
            auth=(API_KEY, ""),
            json=payload,
            timeout=120,
        )
        
        elapsed = time.time() - start_time
        
        print(f"Status: {response.status_code}")
        print(f"Time: {elapsed:.2f}s")
        
        if response.status_code != 200:
            error_text = response.text[:500]
            print(f"ERROR: {error_text}")
            return {"name": name, "success": False, "error": error_text, "time": elapsed}
        
        data = response.json()
        
        if "browserHtml" not in data:
            print(f"ERROR: No browserHtml in response")
            return {"name": name, "success": False, "error": "No browserHtml", "time": elapsed}
        
        html = data["browserHtml"]
        html_len = len(html)
        
        # Check for action errors
        action_errors = []
        if "actions" in data:
            for action in data["actions"]:
                if action.get("error"):
                    action_errors.append(action["error"])
        
        # Check for common success indicators
        has_content = "idealista" in html.lower()
        has_listings = "article" in html and "item" in html
        
        print(f"HTML size: {html_len:,} bytes")
        print(f"Has Idealista content: {has_content}")
        print(f"Has listings structure: {has_listings}")
        
        if action_errors:
            print(f"Action errors: {action_errors}")
        
        # Show snippet around key content
        if wait_selector.replace(".", "") in html:
            print("✓ Wait selector found in HTML")
        else:
            print("⚠ Wait selector NOT found in HTML")
        
        return {
            "name": name,
            "success": True,
            "html_size": html_len,
            "has_content": has_content,
            "time": elapsed,
            "action_errors": action_errors,
        }
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"EXCEPTION: {type(e).__name__}: {e}")
        return {"name": name, "success": False, "error": str(e), "time": elapsed}


def main():
    print("=" * 60)
    print("ZYTE API QUICK TEST FOR IDEALISTA")
    print("=" * 60)
    
    results = []
    for test in TEST_URLS:
        result = test_url(test["name"], test["url"], test["wait_selector"])
        results.append(result)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    successes = sum(1 for r in results if r["success"])
    print(f"Results: {successes}/{len(results)} successful")
    print()
    
    for r in results:
        status = "✓" if r["success"] else "✗"
        time_str = f"{r['time']:.2f}s"
        if r["success"]:
            print(f"  {status} {r['name']}: {r['html_size']:,} bytes ({time_str})")
        else:
            print(f"  {status} {r['name']}: {r.get('error', 'unknown error')} ({time_str})")
    
    # Recommendation
    print("\n" + "-" * 60)
    if successes == len(results):
        print("✓ All tests passed! Zyte is working well.")
    elif successes > 0:
        print("⚠ Some tests failed. Check the errors above.")
    else:
        print("✗ All tests failed. Consider switching providers.")


if __name__ == "__main__":
    main()

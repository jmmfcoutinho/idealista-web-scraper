# Async Scraping Implementation Plan

## Overview

This document provides a phased implementation plan for adding async/parallel scraping capabilities to the Idealista web scraper. The goal is to enable concurrent fetching of pages via Bright Data's Scraping Browser while maintaining backward compatibility with the existing sync implementation.

**Target Speedup**: 3-10x faster scraping through concurrent browser sessions  
**Risk Level**: Medium (requires careful rate limiting to avoid bans)  
**Estimated Effort**: 3-5 days of implementation + testing

---

## Table of Contents

1. [Current Architecture](#1-current-architecture)
2. [Target Architecture](#2-target-architecture)
3. [Phase 1: Async Client Layer](#phase-1-async-client-layer)
4. [Phase 2: Async Utilities](#phase-2-async-utilities)
5. [Phase 3: Async Scrapers](#phase-3-async-scrapers)
6. [Phase 4: CLI Integration](#phase-4-cli-integration)
7. [Phase 5: Configuration](#phase-5-configuration)
8. [Phase 6: Testing](#phase-6-testing)
9. [Phase 7: Documentation](#phase-7-documentation)
10. [Database Considerations](#database-considerations)
11. [Risk Mitigation](#risk-mitigation)
12. [Rollback Strategy](#rollback-strategy)

---

## 1. Current Architecture

### 1.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                           CLI Layer                              │
│  __main__.py: typer commands (prescrape, scrape, scrape-details) │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Scraper Layer                            │
│  PreScraper, ListingsScraper, DetailsScraper                     │
│  - Accept PageClient + session_factory                           │
│  - Sequential for loops over URLs                                │
└─────────────────────────────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                                     ▼
┌─────────────────────────┐           ┌─────────────────────────┐
│      Client Layer        │           │     Database Layer       │
│  PageClient Protocol     │           │  SQLAlchemy (sync)       │
│  - BrightDataClient      │           │  sessionmaker factory    │
│  - RequestsClient        │           │  Models: Listing, etc.   │
│  - sync_playwright       │           │                          │
└─────────────────────────┘           └─────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Parsing Layer                            │
│  selectors.py: Pure functions (parse_listings_page, etc.)        │
│  - No I/O, no async needed                                       │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Key Sync Patterns

| Component | Pattern | File |
|-----------|---------|------|
| Playwright | `sync_playwright()` | `client.py` |
| Sleep/Delay | `time.sleep()` via `sleep_with_jitter()` | `time_utils.py` |
| Retry | Sync `retry_with_backoff()` | `time_utils.py` |
| DB Sessions | `sessionmaker` (sync) | `db/base.py` |
| HTTP Requests | `requests.Session` | `client.py`, `billing.py` |

### 1.3 Current Request Flow

```python
# ListingsScraper._scrape_segment() - simplified
while page <= max_pages:
    html = self.client.get_html(url, wait_selector)  # BLOCKING
    listings, metadata = parse_listings_page(html)   # CPU-bound, fast
    for card in listings:
        self._upsert_listing_card(session, card)     # DB write
    session.commit()
    page += 1
```

**Bottleneck**: Each `get_html()` call blocks for 2-10 seconds (network + JS render + delay).

---

## 2. Target Architecture

### 2.1 Design Principles

1. **Backward Compatibility**: Keep sync implementation working; async is opt-in via `--async` flag
2. **Shared Interface**: Both sync and async clients implement similar protocols
3. **Configurable Concurrency**: `--concurrency N` controls parallel browser sessions
4. **Graceful Degradation**: Falls back to sync if async fails or is unavailable
5. **Database Safety**: Batch commits with proper session handling

### 2.2 Target Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                           CLI Layer                              │
│  --async flag, --concurrency N option                            │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Scraper Layer                            │
│  AsyncPreScraper, AsyncListingsScraper, AsyncDetailsScraper      │
│  - asyncio.gather() with Semaphore(N)                            │
│  - Batch processing of URLs                                      │
└─────────────────────────────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
│  AsyncPageClient Protocol                                        │
│  - AsyncBrightDataClient (async_playwright)                      │
│  - Multiple concurrent browser sessions                          │
│  - Semaphore-controlled concurrency                              │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Async Utilities                             │
│  async_sleep_with_jitter(), async_retry_with_backoff()           │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Concurrency Model

```python
# Option B from engineer's advice: Multiple browser connections with semaphore
async def scrape_urls(urls: list[str], concurrency: int = 5):
    sem = asyncio.Semaphore(concurrency)
    
    async def fetch_one(url: str) -> tuple[str, str]:
        async with sem:
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(BROWSER_WS)
                page = await browser.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    html = await page.content()
                    return url, html
                finally:
                    await browser.close()
    
    results = await asyncio.gather(*(fetch_one(u) for u in urls))
    return results
```

---

## Phase 1: Async Client Layer

**Goal**: Create async versions of the page client without modifying existing sync code.

### 1.1 New Files to Create

#### `src/idealista_scraper/scraping/async_client.py`

```python
"""Async HTTP client for Bright Data Scraping Browser."""

from __future__ import annotations

import asyncio
import time
from typing import Protocol

from playwright.async_api import async_playwright

from idealista_scraper.config import ScrapingConfig, get_brightdata_credentials
from idealista_scraper.utils.billing import get_bandwidth_tracker
from idealista_scraper.utils.logging import get_logger
from idealista_scraper.utils.async_time_utils import (
    async_sleep_with_jitter,
    async_retry_with_backoff,
)

logger = get_logger(__name__)


class AsyncPageClient(Protocol):
    """Protocol for async page fetching."""
    
    async def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """Fetch HTML content asynchronously."""
        ...
    
    async def close(self) -> None:
        """Clean up resources."""
        ...


class AsyncBrightDataClientError(Exception):
    """Exception raised when Bright Data returns an error."""
    
    def __init__(self, message: str, is_connection_error: bool = False) -> None:
        super().__init__(message)
        self.is_connection_error = is_connection_error


class AsyncBrightDataClient:
    """Async Bright Data Scraping Browser client.
    
    Each call to get_html() creates a new browser connection for better
    IP rotation and isolation. Concurrency is controlled externally via
    semaphore.
    """
    
    BROWSER_HOST = "brd.superproxy.io"
    BROWSER_PORT = 9222
    DEFAULT_TIMEOUT = 120_000  # 2 minutes
    WAIT_TIMEOUT = 30_000  # 30 seconds
    
    def __init__(
        self,
        browser_user: str | None = None,
        browser_pass: str | None = None,
        config: ScrapingConfig | None = None,
    ) -> None:
        if browser_user is None or browser_pass is None:
            creds = get_brightdata_credentials()
            browser_user = browser_user or creds["user"]
            browser_pass = browser_pass or creds["password"]
        
        self.browser_user = browser_user
        self.browser_pass = browser_pass
        self.config = config or ScrapingConfig()
        self._request_count = 0
        self._browser_ws = (
            f"wss://{self.browser_user}:{self.browser_pass}"
            f"@{self.BROWSER_HOST}:{self.BROWSER_PORT}"
        )
    
    async def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """Fetch HTML content from a URL using async Playwright.
        
        Creates a new browser connection for each request to enable
        better IP rotation when running concurrently.
        """
        # Add delay between requests (jitter for anti-detection)
        if self._request_count > 0:
            await async_sleep_with_jitter(self.config.delay_seconds)
        self._request_count += 1
        
        async def fetch() -> str:
            return await self._fetch_with_brightdata(url, wait_selector)
        
        try:
            return await async_retry_with_backoff(
                coro_func=fetch,
                max_retries=self.config.max_retries,
                base_delay=2.0,
                max_delay=60.0,
                retryable_exceptions=(AsyncBrightDataClientError,),
            )
        except AsyncBrightDataClientError as e:
            msg = f"Failed to fetch {url} after {self.config.max_retries} retries: {e}"
            raise RuntimeError(msg) from e
    
    async def _fetch_with_brightdata(
        self, url: str, wait_selector: str | None
    ) -> str:
        """Make a single async request to Bright Data."""
        logger.debug("Fetching URL via Bright Data (async): %s", url)
        start_time = time.time()
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(self._browser_ws)
                
                try:
                    page = await browser.new_page()
                    await page.goto(
                        url,
                        timeout=self.DEFAULT_TIMEOUT,
                        wait_until="domcontentloaded",
                    )
                    
                    if wait_selector:
                        try:
                            await page.wait_for_selector(
                                wait_selector,
                                timeout=self.WAIT_TIMEOUT,
                            )
                        except Exception as e:
                            logger.warning(
                                "Selector '%s' not found: %s", wait_selector, e
                            )
                    
                    html = await page.content()
                    duration = time.time() - start_time
                    
                    # Record bandwidth
                    html_bytes = len(html.encode("utf-8"))
                    tracker = get_bandwidth_tracker()
                    stats = tracker.record_request(
                        url=url,
                        bytes_received=html_bytes,
                        duration_seconds=duration,
                    )
                    
                    logger.debug(
                        "Fetched %d bytes in %.1fs (est. cost: $%.4f)",
                        html_bytes, duration, stats.estimated_cost,
                    )
                    return html
                    
                finally:
                    await browser.close()
                    
        except Exception as e:
            error_msg = str(e)
            is_connection = "connect" in error_msg.lower()
            raise AsyncBrightDataClientError(
                f"Bright Data error: {error_msg}",
                is_connection_error=is_connection,
            ) from e
    
    async def close(self) -> None:
        """No persistent resources to clean up."""
        pass


def create_async_client(config: ScrapingConfig) -> AsyncPageClient:
    """Create an async page client based on configuration."""
    if config.use_brightdata:
        return AsyncBrightDataClient(config=config)
    raise ValueError("Async client requires use_brightdata=True")
```

### 1.2 Changes Required

| File | Change |
|------|--------|
| `scraping/__init__.py` | Export `AsyncBrightDataClient`, `AsyncPageClient`, `create_async_client` |

### 1.3 Testing Checklist

- [ ] `AsyncBrightDataClient` connects to Bright Data successfully
- [ ] `async_playwright` works with `connect_over_cdp`
- [ ] Wait selector timeout handling works
- [ ] Retry logic triggers on connection errors
- [ ] Bandwidth tracking records async requests

---

## Phase 2: Async Utilities

**Goal**: Create async versions of time utilities (sleep, retry).

### 2.1 New Files to Create

#### `src/idealista_scraper/utils/async_time_utils.py`

```python
"""Async time and retry utilities."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from idealista_scraper.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


async def async_sleep_with_jitter(
    base_delay: float,
    jitter_factor: float = 0.1,
) -> None:
    """Async sleep with random jitter for anti-detection."""
    jitter = random.uniform(-jitter_factor, jitter_factor) * base_delay
    actual_delay = max(0, base_delay + jitter)
    await asyncio.sleep(actual_delay)


async def async_retry_with_backoff(
    coro_func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Retry an async function with exponential backoff.
    
    Args:
        coro_func: A zero-argument async function to call.
        max_retries: Maximum retry attempts.
        base_delay: Initial delay between retries.
        max_delay: Maximum delay between retries.
        exponential_base: Base for exponential backoff.
        retryable_exceptions: Exception types that trigger retry.
    
    Returns:
        The return value of the coroutine.
    
    Raises:
        The last exception if all retries fail.
    """
    last_exception: Exception | None = None
    
    for attempt in range(max_retries + 1):
        try:
            return await coro_func()
        except retryable_exceptions as e:
            last_exception = e
            if attempt == max_retries:
                logger.error(
                    "All %d attempts failed. Last error: %s",
                    max_retries + 1, e,
                )
                raise
            
            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            logger.warning(
                "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt + 1, max_retries + 1, e, delay,
            )
            await async_sleep_with_jitter(delay)
    
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected state in async_retry_with_backoff")
```

### 2.2 Changes Required

| File | Change |
|------|--------|
| `utils/__init__.py` | Export async utilities |

### 2.3 Testing Checklist

- [ ] `async_sleep_with_jitter` adds appropriate randomness
- [ ] `async_retry_with_backoff` retries on specified exceptions
- [ ] Backoff delay increases exponentially
- [ ] Max delay is respected

---

## Phase 3: Async Scrapers

**Goal**: Create async versions of scrapers that process URLs concurrently.

### 3.1 Architecture Decision: Batch Processing

Rather than converting every internal method to async, we'll use a **batch fetch pattern**:

1. Collect URLs to fetch
2. Fetch all URLs concurrently with semaphore
3. Process results sequentially (for simpler DB handling)

```python
# Conceptual flow
urls = build_urls_for_segment(segment)
html_results = await fetch_batch(urls, concurrency=5)  # Parallel
for url, html in html_results:
    listings = parse_listings_page(html)  # CPU, fast
    upsert_to_db(session, listings)       # Sequential writes
session.commit()
```

### 3.2 New Files to Create

#### `src/idealista_scraper/scraping/async_listings_scraper.py`

```python
"""Async listings scraper with concurrent page fetching."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy.orm import Session

from idealista_scraper.config import RunConfig
from idealista_scraper.db import Concelho, Listing, ListingHistory, ScrapeRun
from idealista_scraper.scraping.async_client import AsyncPageClient
from idealista_scraper.scraping.client import WAIT_SELECTOR_SEARCH_RESULTS
from idealista_scraper.scraping.listings_scraper import (
    MAX_PAGES_LIMIT,
    ScrapeSegment,
    build_paginated_url,
    build_search_url,
)
from idealista_scraper.scraping.selectors import parse_listings_page
from idealista_scraper.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


@dataclass
class FetchResult:
    """Result of fetching a single URL."""
    url: str
    page_num: int
    html: str | None
    error: str | None = None


class AsyncListingsScraper:
    """Async scraper with concurrent page fetching.
    
    Uses asyncio.gather() with Semaphore to fetch multiple pages
    in parallel while respecting concurrency limits.
    """
    
    def __init__(
        self,
        client: AsyncPageClient,
        session_factory: Callable[[], Session],
        config: RunConfig,
        concurrency: int = 5,
    ) -> None:
        self.client = client
        self.session_factory = session_factory
        self.config = config
        self.concurrency = concurrency
        self._concelho_cache: dict[str, Concelho | None] = {}
        self._semaphore: asyncio.Semaphore | None = None
    
    async def run(self) -> dict[str, int]:
        """Run async scraping with concurrency control."""
        logger.info(
            "Starting async listings scraper (concurrency=%d)",
            self.concurrency,
        )
        
        self._semaphore = asyncio.Semaphore(self.concurrency)
        session = self.session_factory()
        scrape_run = self._create_scrape_run(session)
        
        stats = {
            "listings_processed": 0,
            "listings_created": 0,
            "listings_updated": 0,
            "pages_scraped": 0,
            "segments_scraped": 0,
        }
        
        try:
            operations: list[Literal["comprar", "arrendar"]]
            if self.config.operation == "both":
                operations = ["comprar", "arrendar"]
            else:
                operations = [self.config.operation]
            
            for location_slug in self.config.locations:
                for operation in operations:
                    for property_type in self.config.property_types:
                        segment_stats = await self._scrape_location(
                            session=session,
                            location_slug=location_slug,
                            operation=operation,
                            property_type=property_type,
                        )
                        for key in stats:
                            stats[key] += segment_stats.get(key, 0)
            
            scrape_run.status = "success"
            scrape_run.ended_at = datetime.now(UTC)
            scrape_run.listings_processed = stats["listings_processed"]
            scrape_run.listings_created = stats["listings_created"]
            scrape_run.listings_updated = stats["listings_updated"]
            session.commit()
            
            return stats
            
        except Exception as e:
            logger.exception("Async scraper failed: %s", e)
            scrape_run.status = "failed"
            scrape_run.error_message = str(e)
            scrape_run.ended_at = datetime.now(UTC)
            session.commit()
            raise
            
        finally:
            session.close()
            await self.client.close()
    
    async def _fetch_page(
        self,
        url: str,
        page_num: int,
    ) -> FetchResult:
        """Fetch a single page with semaphore control."""
        async with self._semaphore:
            try:
                html = await self.client.get_html(
                    url,
                    wait_selector=WAIT_SELECTOR_SEARCH_RESULTS,
                )
                return FetchResult(url=url, page_num=page_num, html=html)
            except Exception as e:
                logger.error("Failed to fetch page %d: %s", page_num, e)
                return FetchResult(
                    url=url, page_num=page_num, html=None, error=str(e)
                )
    
    async def _fetch_pages_batch(
        self,
        base_url: str,
        start_page: int,
        end_page: int,
    ) -> list[FetchResult]:
        """Fetch a batch of pages concurrently."""
        tasks = []
        for page in range(start_page, end_page + 1):
            url = build_paginated_url(base_url, page)
            tasks.append(self._fetch_page(url, page))
        
        results = await asyncio.gather(*tasks)
        return list(results)
    
    async def _scrape_location(
        self,
        session: Session,
        location_slug: str,
        operation: Literal["comprar", "arrendar"],
        property_type: str,
    ) -> dict[str, int]:
        """Scrape a location with batch fetching."""
        logger.info("Scraping %s %s in %s", operation, property_type, location_slug)
        
        stats = {
            "listings_processed": 0,
            "listings_created": 0,
            "listings_updated": 0,
            "pages_scraped": 0,
            "segments_scraped": 0,
        }
        
        segment = ScrapeSegment(
            location_slug=location_slug,
            operation=operation,
            property_type=property_type,
            max_price=self.config.filters.max_price,
            min_price=self.config.filters.min_price,
        )
        
        while True:
            segment_stats = await self._scrape_segment_async(session, segment)
            for key in stats:
                stats[key] += segment_stats.get(key, 0)
            stats["segments_scraped"] += 1
            
            next_max_price = segment_stats.get("next_max_price")
            if next_max_price is None:
                break
            
            if segment.min_price and next_max_price <= segment.min_price:
                break
            
            segment = ScrapeSegment(
                location_slug=location_slug,
                operation=operation,
                property_type=property_type,
                max_price=next_max_price,
                min_price=segment.min_price,
            )
        
        return stats
    
    async def _scrape_segment_async(
        self,
        session: Session,
        segment: ScrapeSegment,
    ) -> dict[str, int | None]:
        """Scrape a segment with batch page fetching.
        
        Strategy:
        1. Fetch first page to get total pages
        2. Batch fetch remaining pages concurrently
        3. Process all results sequentially for DB writes
        """
        logger.info("Scraping segment (async): %s", segment)
        
        stats: dict[str, int | None] = {
            "listings_processed": 0,
            "listings_created": 0,
            "listings_updated": 0,
            "pages_scraped": 0,
            "next_max_price": None,
        }
        
        base_url = build_search_url(
            location_slug=segment.location_slug,
            operation=segment.operation,
            property_type=segment.property_type,
            max_price=segment.max_price,
            min_price=segment.min_price,
            order="precos-desc",
        )
        
        max_pages = min(
            self.config.scraping.max_pages or MAX_PAGES_LIMIT,
            MAX_PAGES_LIMIT,
        )
        
        # Fetch first page to determine total pages
        first_result = await self._fetch_page(base_url, 1)
        if first_result.html is None:
            logger.error("Failed to fetch first page")
            return stats
        
        listings, metadata = parse_listings_page(
            first_result.html, segment.operation, segment.property_type
        )
        
        # Process first page
        lowest_price = self._process_page_results(
            session, segment, listings, metadata, stats
        )
        
        total_pages = min(metadata.last_page or 1, max_pages)
        logger.info(
            "First page: %d listings, %d total pages",
            len(listings), total_pages,
        )
        
        if total_pages <= 1 or not metadata.has_next_page:
            session.commit()
            return stats
        
        # Batch fetch remaining pages
        # Fetch in batches to avoid overwhelming the system
        BATCH_SIZE = self.concurrency * 2
        
        for batch_start in range(2, total_pages + 1, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE - 1, total_pages)
            
            logger.info(
                "Fetching pages %d-%d concurrently...",
                batch_start, batch_end,
            )
            
            results = await self._fetch_pages_batch(
                base_url, batch_start, batch_end
            )
            
            # Process results sequentially
            for result in sorted(results, key=lambda r: r.page_num):
                if result.html is None:
                    continue
                
                page_listings, page_metadata = parse_listings_page(
                    result.html, segment.operation, segment.property_type
                )
                
                page_lowest = self._process_page_results(
                    session, segment, page_listings, page_metadata, stats
                )
                
                if page_lowest and (lowest_price is None or page_lowest < lowest_price):
                    lowest_price = page_lowest
            
            # Commit after each batch
            session.commit()
        
        # Check if we need price segmentation
        if total_pages >= MAX_PAGES_LIMIT and lowest_price is not None:
            logger.info(
                "Reached page limit. Will segment at price: %d",
                lowest_price,
            )
            stats["next_max_price"] = lowest_price
        
        return stats
    
    def _process_page_results(
        self,
        session: Session,
        segment: ScrapeSegment,
        listings: list,
        metadata,
        stats: dict[str, int | None],
    ) -> int | None:
        """Process parsed listings and update stats. Returns lowest price."""
        for card in listings:
            created = self._upsert_listing_card(session, segment, card)
            stats["listings_processed"] = (stats["listings_processed"] or 0) + 1
            if created:
                stats["listings_created"] = (stats["listings_created"] or 0) + 1
            else:
                stats["listings_updated"] = (stats["listings_updated"] or 0) + 1
        
        stats["pages_scraped"] = (stats["pages_scraped"] or 0) + 1
        
        logger.info(
            "Page %d: %d listings (lowest: %s)",
            metadata.page, len(listings), metadata.lowest_price_on_page,
        )
        
        return metadata.lowest_price_on_page
    
    # Reuse sync helper methods (they don't need async)
    def _create_scrape_run(self, session: Session) -> ScrapeRun:
        """Create a new scrape run record."""
        scrape_run = ScrapeRun(
            run_type="scrape-async",
            status="running",
            started_at=datetime.now(UTC),
            config={
                **self.config.model_dump(),
                "concurrency": self.concurrency,
            },
        )
        session.add(scrape_run)
        session.commit()
        return scrape_run
    
    def _upsert_listing_card(self, session, segment, card) -> bool:
        """Upsert a listing - reuses sync implementation."""
        # Import and delegate to sync implementation
        from idealista_scraper.scraping.listings_scraper import ListingsScraper
        
        # Create temporary instance just for the helper method
        sync_scraper = ListingsScraper.__new__(ListingsScraper)
        sync_scraper._concelho_cache = self._concelho_cache
        
        return sync_scraper._upsert_listing_card(session, segment, card)
    
    def _get_concelho(self, session, location_slug):
        """Get concelho - reuses sync cache."""
        if location_slug not in self._concelho_cache:
            concelho = session.query(Concelho).filter_by(slug=location_slug).first()
            self._concelho_cache[location_slug] = concelho
        return self._concelho_cache[location_slug]
```

### 3.3 Additional Async Scrapers

Create similar async versions for:

#### `src/idealista_scraper/scraping/async_pre_scraper.py`

```python
"""Async pre-scraper for districts and concelhos."""
# Similar pattern: batch fetch district pages concurrently
```

#### `src/idealista_scraper/scraping/async_details_scraper.py`

```python
"""Async details scraper for listing enrichment."""

# This one benefits most from parallelization since it's
# fetching many independent detail pages

async def run(self) -> dict[str, int]:
    listings = self._get_listings_needing_details(session)
    
    # Fetch all detail pages concurrently
    async def fetch_detail(listing):
        async with self._semaphore:
            html = await self.client.get_html(listing.url, ...)
            return listing.id, html
    
    results = await asyncio.gather(
        *(fetch_detail(l) for l in listings),
        return_exceptions=True,
    )
    
    # Process results sequentially
    for listing_id, html_or_error in results:
        if isinstance(html_or_error, Exception):
            stats["listings_failed"] += 1
        else:
            detail = parse_listing_detail(html_or_error)
            self._update_listing_from_detail(listing, detail)
            stats["listings_enriched"] += 1
```

### 3.4 Changes Required

| File | Change |
|------|--------|
| `scraping/__init__.py` | Export async scrapers |

### 3.5 Testing Checklist

- [ ] Concurrent fetching respects semaphore limit
- [ ] Failed fetches don't crash the batch
- [ ] Results are processed in correct order
- [ ] Database commits happen at appropriate intervals
- [ ] Price segmentation still works correctly

---

## Phase 4: CLI Integration

**Goal**: Add CLI flags for async mode and concurrency control.

### 4.1 New CLI Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--async` / `--sync` | bool | `False` | Enable async/concurrent scraping |
| `--concurrency` | int | `5` | Number of concurrent browser sessions |

### 4.2 Changes to `__main__.py`

```python
# Add new options
AsyncOption = Annotated[
    bool,
    typer.Option(
        "--async/--sync",
        help="Use async concurrent scraping (faster but higher cost).",
    ),
]

ConcurrencyOption = Annotated[
    int,
    typer.Option(
        "--concurrency",
        help="Number of concurrent browser sessions (only with --async).",
        min=1,
        max=20,
    ),
]


@app.command()
def scrape(
    config: ConfigOption = None,
    operation: OperationOption = None,
    district: DistrictOption = None,
    concelho: ConcelhoOption = None,
    max_pages: Annotated[int | None, ...] = None,
    use_async: AsyncOption = False,  # NEW
    concurrency: ConcurrencyOption = 5,  # NEW
    verbose: VerboseOption = False,
    dry_run: DryRunOption = False,
    track_cost: TrackCostOption = False,
) -> None:
    """Scrape listing cards from search results."""
    # ... existing setup ...
    
    if use_async:
        # Use async scraper
        import asyncio
        from idealista_scraper.scraping import (
            AsyncListingsScraper,
            create_async_client,
        )
        
        async def run_async():
            client = create_async_client(run_config.scraping)
            scraper = AsyncListingsScraper(
                client=client,
                session_factory=session_factory,
                config=run_config,
                concurrency=concurrency,
            )
            return await scraper.run()
        
        stats = asyncio.run(run_async())
    else:
        # Use existing sync scraper
        client = create_client(run_config.scraping)
        scraper = ListingsScraper(...)
        stats = scraper.run()
```

### 4.3 Dry Run Output for Async

```python
if dry_run:
    logger.info("[DRY RUN] Mode: %s", "async" if use_async else "sync")
    if use_async:
        logger.info("[DRY RUN] Concurrency: %d browser sessions", concurrency)
    # ... existing dry run output ...
```

### 4.4 Testing Checklist

- [ ] `--async` flag enables async scraper
- [ ] `--concurrency` is validated (1-20)
- [ ] `--concurrency` without `--async` shows warning
- [ ] Dry run shows async mode info
- [ ] Cost tracking works with async

---

## Phase 5: Configuration

**Goal**: Add async configuration to YAML and settings.

### 5.1 Updates to `config.example.yaml`

```yaml
# Scraping configuration
scraping:
  delay_seconds: 2.0
  max_retries: 3
  use_brightdata: true
  max_pages: null
  
  # Async/concurrency settings (NEW)
  async:
    enabled: false           # Use async by default
    concurrency: 5           # Concurrent browser sessions
    batch_size: 10           # Pages to fetch per batch
    jitter_factor: 0.2       # Random delay variation (0.0-1.0)
```

### 5.2 Updates to `settings.py`

```python
class AsyncConfig(BaseModel):
    """Configuration for async scraping behavior."""
    
    enabled: bool = Field(default=False)
    concurrency: int = Field(default=5, ge=1, le=20)
    batch_size: int = Field(default=10, ge=1, le=50)
    jitter_factor: float = Field(default=0.2, ge=0.0, le=1.0)


class ScrapingConfig(BaseModel):
    """Configuration for scraping behavior."""
    
    delay_seconds: float = Field(default=2.0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    use_brightdata: bool = Field(default=True)
    max_pages: int | None = Field(default=None, ge=1)
    async_config: AsyncConfig = Field(default_factory=AsyncConfig)  # NEW
```

### 5.3 CLI Override Mapping

```python
# In _flatten_cli_overrides()
key_mapping = {
    # ... existing ...
    "use_async": ["scraping", "async_config", "enabled"],
    "concurrency": ["scraping", "async_config", "concurrency"],
}
```

---

## Phase 6: Testing

**Goal**: Comprehensive test coverage for async functionality.

### 6.1 New Test Files

#### `tests/test_async_client.py`

```python
"""Tests for async client."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from idealista_scraper.scraping.async_client import (
    AsyncBrightDataClient,
    AsyncBrightDataClientError,
)


class TestAsyncBrightDataClient:
    """Tests for AsyncBrightDataClient."""
    
    @pytest.mark.asyncio
    async def test_get_html_success(self):
        """Test successful HTML fetch."""
        # Mock async_playwright
        ...
    
    @pytest.mark.asyncio
    async def test_get_html_retry_on_error(self):
        """Test retry behavior on transient errors."""
        ...
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_with_semaphore(self):
        """Test that semaphore limits concurrency."""
        ...


class TestAsyncRetry:
    """Tests for async retry logic."""
    
    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test backoff delay increases."""
        ...
```

#### `tests/test_async_scrapers.py`

```python
"""Tests for async scrapers."""

import pytest
from unittest.mock import AsyncMock

from idealista_scraper.scraping.async_listings_scraper import (
    AsyncListingsScraper,
    FetchResult,
)


class TestAsyncListingsScraper:
    """Tests for AsyncListingsScraper."""
    
    @pytest.mark.asyncio
    async def test_fetch_pages_batch_respects_concurrency(self):
        """Test batch fetching with concurrency limit."""
        ...
    
    @pytest.mark.asyncio
    async def test_failed_fetch_doesnt_crash_batch(self):
        """Test graceful handling of individual failures."""
        ...
    
    @pytest.mark.asyncio
    async def test_price_segmentation_works_async(self):
        """Test price segmentation in async mode."""
        ...
```

#### `tests/test_cli_async.py`

```python
"""Tests for async CLI options."""

from typer.testing import CliRunner
from idealista_scraper.__main__ import app

runner = CliRunner()


class TestAsyncCliOptions:
    """Tests for --async and --concurrency options."""
    
    def test_scrape_async_dry_run(self):
        """Test async dry run output."""
        result = runner.invoke(
            app,
            ["scrape", "--concelho", "cascais", "--async", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "async" in result.output.lower()
    
    def test_concurrency_validation(self):
        """Test concurrency bounds validation."""
        result = runner.invoke(
            app,
            ["scrape", "--concelho", "cascais", "--async", "--concurrency", "50"],
        )
        assert result.exit_code != 0
```

### 6.2 Integration Tests

```python
# tests/test_async_integration.py

@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_scrape_cascais():
    """Integration test: async scrape of small location."""
    # Requires BRIGHTDATA_* env vars
    ...
```

### 6.3 Test Dependencies

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    # ... existing ...
    "pytest-asyncio>=0.23",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## Phase 7: Documentation

### 7.1 Update README.md

Add section on async mode:

```markdown
## Async Mode (Faster Scraping)

For faster scraping, use async mode with concurrent browser sessions:

```bash
# Scrape with 5 concurrent sessions (default)
idealista-scraper scrape --concelho cascais --async

# Increase concurrency (higher cost, faster)
idealista-scraper scrape --concelho cascais --async --concurrency 10

# Check estimated speedup
idealista-scraper scrape --concelho cascais --async --dry-run
```

### Trade-offs

| Mode | Speed | Cost | Ban Risk |
|------|-------|------|----------|
| Sync (default) | 1x | Lower | Lower |
| Async (5) | ~5x | ~5x | Medium |
| Async (10) | ~8x | ~8x | Higher |

### When to Use Async

- Large locations with many pages
- Initial data population
- Time-sensitive scraping needs

### When to Use Sync

- Small locations
- Re-scraping with few changes
- Lower budget constraints
```

### 7.2 Docstrings

Ensure all new modules have comprehensive docstrings explaining:
- Purpose and use case
- Concurrency model
- Error handling behavior
- Cost implications

---

## Database Considerations

### Current Pattern (Sync)

```python
session = self.session_factory()
# ... do work ...
session.commit()
session.close()
```

### Async Compatibility

SQLAlchemy sessions are **not thread-safe**, but they work fine with asyncio as long as:

1. **Single session per coroutine chain**: Don't share sessions across concurrent tasks
2. **Sequential DB writes**: Process parsed results sequentially, not concurrently
3. **Batch commits**: Commit after each batch of pages, not after each listing

### Why Not Async SQLAlchemy?

- Adds complexity (`sqlalchemy[asyncio]`, async session management)
- DB writes are fast (~1ms per listing)
- Bottleneck is network I/O, not DB I/O
- SQLite doesn't benefit from async anyway

### Recommended Pattern

```python
# Fetch concurrently
results = await asyncio.gather(*(fetch(url) for url in urls))

# Process sequentially with single session
session = self.session_factory()
for url, html in results:
    listings = parse(html)
    for listing in listings:
        upsert(session, listing)
session.commit()
session.close()
```

---

## Risk Mitigation

### 1. Rate Limiting / Bans

**Risk**: Idealista blocks IPs/sessions making too many concurrent requests.

**Mitigations**:
- Default concurrency of 5 (conservative)
- Jitter on delays (`jitter_factor=0.2`)
- Each request gets new browser/IP via Bright Data
- Monitor for 429/403 errors and back off

### 2. Bright Data Costs

**Risk**: Higher concurrency = higher costs.

**Mitigations**:
- `--track-cost` flag to monitor spend
- Clear documentation of cost implications
- Default to sync mode (async is opt-in)

### 3. Memory Usage

**Risk**: Many concurrent browser connections use more memory.

**Mitigations**:
- `BATCH_SIZE` limits concurrent fetches
- Browsers are closed immediately after use
- Monitor memory in production

### 4. Error Cascades

**Risk**: One failed request could affect others.

**Mitigations**:
- Individual error handling per fetch
- `return_exceptions=True` in `asyncio.gather`
- Failed pages are logged and skipped

---

## Rollback Strategy

If async implementation causes issues:

1. **Feature Flag**: `--async` is opt-in; sync remains default
2. **Config Override**: `async.enabled: false` in config
3. **Code Isolation**: Async code in separate files; sync code unchanged
4. **Quick Disable**: Remove `--async` flag handling in CLI

```python
# Emergency disable in __main__.py
if use_async:
    logger.warning("Async mode temporarily disabled. Using sync.")
    use_async = False
```

---

## Implementation Checklist

### Phase 1: Async Client ☐
- [ ] Create `src/idealista_scraper/scraping/async_client.py`
- [ ] Implement `AsyncBrightDataClient` class
- [ ] Implement `AsyncPageClient` Protocol
- [ ] Implement `create_async_client()` factory
- [ ] Update `scraping/__init__.py` exports
- [ ] Test with single URL fetch
- [ ] Test error handling and retries
- [ ] Test bandwidth tracking integration

### Phase 2: Async Utilities ☐
- [ ] Create `src/idealista_scraper/utils/async_time_utils.py`
- [ ] Implement `async_sleep_with_jitter()`
- [ ] Implement `async_retry_with_backoff()`
- [ ] Update `utils/__init__.py` exports
- [ ] Unit tests for jitter distribution
- [ ] Unit tests for exponential backoff

### Phase 3: Async Scrapers ☐
- [ ] Create `src/idealista_scraper/scraping/async_listings_scraper.py`
- [ ] Create `src/idealista_scraper/scraping/async_details_scraper.py`
- [ ] Create `src/idealista_scraper/scraping/async_pre_scraper.py` (optional, lower priority)
- [ ] Update `scraping/__init__.py` exports
- [ ] Ensure `_upsert_listing_card` reuse works correctly
- [ ] Integration tests with mock client
- [ ] Test price segmentation logic in async context

### Phase 4: CLI Integration ☐
- [ ] Add `--async/--sync` flag to `scrape` command
- [ ] Add `--async/--sync` flag to `scrape-details` command
- [ ] Add `--concurrency` option (with validation 1-20)
- [ ] Update dry-run output to show async mode
- [ ] Handle `--concurrency` without `--async` (warning)
- [ ] Integrate `CostTracker` with async execution
- [ ] CLI tests for new options

### Phase 5: Configuration ☐
- [ ] Add `AsyncConfig` model to `settings.py`
- [ ] Add `async_config` field to `ScrapingConfig`
- [ ] Update `config.example.yaml` with async section
- [ ] Update `_flatten_cli_overrides()` for new keys
- [ ] Config validation tests
- [ ] Test config file loading with async settings

### Phase 6: Testing ☐
- [ ] Create `tests/test_async_client.py`
- [ ] Create `tests/test_async_scrapers.py`
- [ ] Create `tests/test_cli_async.py`
- [ ] Create `tests/test_async_time_utils.py`
- [ ] Add `pytest-asyncio>=0.23` to dev dependencies
- [ ] Update `pyproject.toml` with `asyncio_mode = "auto"`
- [ ] Integration test with real Bright Data (marked `@pytest.mark.integration`)
- [ ] Verify all existing tests still pass

### Phase 7: Documentation ☐
- [ ] Update `README.md` with async mode section
- [ ] Add comprehensive docstrings to all new modules
- [ ] Update CLI `--help` output (automatic via typer)
- [ ] Add inline comments for complex async patterns
- [ ] Document cost implications prominently

---

## Appendix A: File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `src/idealista_scraper/scraping/async_client.py` | **Create** | Async client with `AsyncBrightDataClient` |
| `src/idealista_scraper/utils/async_time_utils.py` | **Create** | Async sleep and retry utilities |
| `src/idealista_scraper/scraping/async_listings_scraper.py` | **Create** | Async listings scraper |
| `src/idealista_scraper/scraping/async_details_scraper.py` | **Create** | Async details scraper |
| `src/idealista_scraper/scraping/async_pre_scraper.py` | **Create** | Async pre-scraper (optional) |
| `src/idealista_scraper/scraping/__init__.py` | **Modify** | Add async exports |
| `src/idealista_scraper/utils/__init__.py` | **Modify** | Add async utility exports |
| `src/idealista_scraper/config/settings.py` | **Modify** | Add `AsyncConfig` model |
| `src/idealista_scraper/__main__.py` | **Modify** | Add `--async`, `--concurrency` options |
| `config.example.yaml` | **Modify** | Add async configuration section |
| `pyproject.toml` | **Modify** | Add `pytest-asyncio` dependency |
| `tests/test_async_client.py` | **Create** | Async client tests |
| `tests/test_async_scrapers.py` | **Create** | Async scraper tests |
| `tests/test_cli_async.py` | **Create** | CLI async option tests |
| `tests/test_async_time_utils.py` | **Create** | Async utility tests |
| `README.md` | **Modify** | Add async mode documentation |

---

## Appendix B: Dependency Changes

### New Dependencies

None required - `playwright` already supports async via `playwright.async_api`.

### Dev Dependencies

```toml
# Add to pyproject.toml [project.optional-dependencies] dev
"pytest-asyncio>=0.23",
```

### Pytest Configuration

```toml
# Add to pyproject.toml [tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## Appendix C: Environment Variables

No new environment variables required. The async client uses the same credentials:

| Variable | Used By | Required |
|----------|---------|----------|
| `BRIGHTDATA_BROWSER_USER` | `AsyncBrightDataClient` | Yes (for async) |
| `BRIGHTDATA_BROWSER_PASS` | `AsyncBrightDataClient` | Yes (for async) |
| `BRIGHTDATA_API_KEY` | `CostTracker` | No (for cost tracking) |

---

## Appendix D: Performance Expectations

### Theoretical Speedup

| Pages | Sync Time (5s/page) | Async (5 concurrent) | Async (10 concurrent) |
|-------|---------------------|----------------------|-----------------------|
| 10 | 50s | 10s (5x) | 5s (10x) |
| 60 | 5 min | 1 min (5x) | 30s (10x) |
| 180 | 15 min | 3 min (5x) | 1.5 min (10x) |

### Real-World Factors

- Network latency variance
- Bright Data session setup time (~1-2s per connection)
- Diminishing returns above 10 concurrent sessions
- Idealista rate limiting may throttle high concurrency

### Recommended Starting Points

| Use Case | Concurrency | Rationale |
|----------|-------------|-----------|
| First run / testing | 3 | Conservative, monitor behavior |
| Regular scraping | 5 | Good balance of speed/cost |
| Urgent full refresh | 10 | Maximum practical speed |

---

## Summary

This plan provides a phased approach to adding async scraping that:

1. **Maintains backward compatibility** - Sync mode remains default
2. **Is opt-in** - Async enabled via `--async` flag
3. **Controls costs** - Configurable concurrency with sensible defaults
4. **Minimizes risk** - Easy to disable or roll back
5. **Reuses existing code** - Parsing and DB logic unchanged
6. **Is well-tested** - Comprehensive test coverage

Expected results:
- **3-10x speedup** depending on concurrency and network conditions
- **Same data quality** - Parsing logic unchanged
- **Controllable costs** - Pay for speed when needed

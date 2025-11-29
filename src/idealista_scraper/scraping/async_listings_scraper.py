"""Async listings scraper with concurrent page fetching.

This module implements an async version of the listings scraper that uses
asyncio.gather() with Semaphore for concurrent page fetching while maintaining
backward compatibility with the existing sync implementation.
"""

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
from idealista_scraper.scraping.selectors import (
    ParsedListingCard,
    SearchMetadata,
    parse_listings_page,
)
from idealista_scraper.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


@dataclass
class FetchResult:
    """Result of fetching a single URL.

    Attributes:
        url: The URL that was fetched.
        page_num: The page number.
        html: The HTML content if successful, None otherwise.
        error: Error message if failed, None otherwise.
    """

    url: str
    page_num: int
    html: str | None
    error: str | None = None


class AsyncListingsScraper:
    """Async scraper with concurrent page fetching.

    Uses asyncio.gather() with Semaphore to fetch multiple pages
    in parallel while respecting concurrency limits.

    Attributes:
        client: Async page client for fetching HTML pages.
        session_factory: Factory function to create database sessions.
        config: Run configuration with locations and scraping settings.
        concurrency: Maximum number of concurrent browser sessions.
    """

    def __init__(
        self,
        client: AsyncPageClient,
        session_factory: Callable[[], Session],
        config: RunConfig,
        concurrency: int = 5,
    ) -> None:
        """Initialize the AsyncListingsScraper.

        Args:
            client: Async page client for fetching HTML pages.
            session_factory: Factory function to create database sessions.
            config: Run configuration with locations and settings.
            concurrency: Number of concurrent browser sessions (1-20).
        """
        self.client = client
        self.session_factory = session_factory
        self.config = config
        self.concurrency = concurrency
        self._concelho_cache: dict[str, Concelho | None] = {}
        self._semaphore: asyncio.Semaphore | None = None

    async def run(self) -> dict[str, int]:
        """Run async scraping with concurrency control.

        Iterates over configured locations, operations, and property types,
        applying price segmentation when necessary. Uses concurrent fetching
        within each segment for better performance.

        Returns:
            Dictionary with statistics: {
                "listings_processed": int,
                "listings_created": int,
                "listings_updated": int,
                "pages_scraped": int,
                "segments_scraped": int,
            }

        Raises:
            RuntimeError: If scraping repeatedly fails.
        """
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
            # Determine operations to scrape
            operations: list[Literal["comprar", "arrendar"]]
            if self.config.operation == "both":
                operations = ["comprar", "arrendar"]
            elif self.config.operation in ("comprar", "arrendar"):
                operations = [self.config.operation]
            else:
                operations = []

            # Iterate over locations, operations, and property types
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

            # Update scrape run status
            scrape_run.status = "success"
            scrape_run.ended_at = datetime.now(UTC)
            scrape_run.listings_processed = stats["listings_processed"]
            scrape_run.listings_created = stats["listings_created"]
            scrape_run.listings_updated = stats["listings_updated"]
            session.commit()

            logger.info(
                "Async listings scraper completed: %d listings processed "
                "(%d created, %d updated), %d pages, %d segments",
                stats["listings_processed"],
                stats["listings_created"],
                stats["listings_updated"],
                stats["pages_scraped"],
                stats["segments_scraped"],
            )

            return stats

        except Exception as e:
            logger.exception("Async listings scraper failed: %s", e)
            scrape_run.status = "failed"
            scrape_run.error_message = str(e)
            scrape_run.ended_at = datetime.now(UTC)
            scrape_run.listings_processed = stats["listings_processed"]
            scrape_run.listings_created = stats["listings_created"]
            scrape_run.listings_updated = stats["listings_updated"]
            session.commit()
            raise

        finally:
            session.close()
            await self.client.close()

    def _create_scrape_run(self, session: Session) -> ScrapeRun:
        """Create a new scrape run record.

        Args:
            session: Database session.

        Returns:
            The created ScrapeRun instance.
        """
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

    async def _fetch_page(
        self,
        url: str,
        page_num: int,
    ) -> FetchResult:
        """Fetch a single page with semaphore control.

        Args:
            url: The URL to fetch.
            page_num: The page number being fetched.

        Returns:
            FetchResult with HTML content or error.
        """
        if self._semaphore is None:
            msg = "Semaphore not initialized - call run() first"
            raise RuntimeError(msg)

        async with self._semaphore:
            try:
                html = await self.client.get_html(
                    url,
                    wait_selector=WAIT_SELECTOR_SEARCH_RESULTS,
                )
                return FetchResult(url=url, page_num=page_num, html=html)
            except Exception as e:
                logger.error("Failed to fetch page %d: %s", page_num, e)
                return FetchResult(url=url, page_num=page_num, html=None, error=str(e))

    async def _fetch_pages_batch(
        self,
        base_url: str,
        start_page: int,
        end_page: int,
    ) -> list[FetchResult]:
        """Fetch a batch of pages concurrently.

        Args:
            base_url: Base search URL without pagination.
            start_page: First page number to fetch (inclusive).
            end_page: Last page number to fetch (inclusive).

        Returns:
            List of FetchResult objects.
        """
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
        """Scrape all listings for a location with price segmentation.

        Uses the same price segmentation strategy as the sync scraper:
        1. Start with no price limit, sorted by price descending.
        2. If total pages > 60, scrape up to page 60 and note lowest price.
        3. Create new segment with max_price = lowest_price and repeat.

        Args:
            session: Database session.
            location_slug: Location slug to scrape.
            operation: Operation type.
            property_type: Property type.

        Returns:
            Statistics for this location.
        """
        logger.info("Scraping %s %s in %s", operation, property_type, location_slug)

        stats = {
            "listings_processed": 0,
            "listings_created": 0,
            "listings_updated": 0,
            "pages_scraped": 0,
            "segments_scraped": 0,
        }

        # Start with first segment (no price limit)
        segment = ScrapeSegment(
            location_slug=location_slug,
            operation=operation,
            property_type=property_type,
            max_price=self.config.filters.max_price,
            min_price=self.config.filters.min_price,
        )

        # Process segments until no more are needed
        while True:
            segment_stats = await self._scrape_segment_async(session, segment)
            for key in stats:
                value = segment_stats.get(key)
                if value is not None and isinstance(value, int):
                    stats[key] += value
            stats["segments_scraped"] += 1

            # Check if we need another segment
            next_max_price = segment_stats.get("next_max_price")
            if next_max_price is None:
                # No more segments needed
                break

            # Create new segment with lower max price
            if segment.min_price is not None and next_max_price <= segment.min_price:
                # Reached minimum price boundary
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

        Args:
            session: Database session.
            segment: The segment to scrape.

        Returns:
            Statistics including "next_max_price" if more segments needed.
        """
        logger.info("Scraping segment (async): %s", segment)

        stats: dict[str, int | None] = {
            "listings_processed": 0,
            "listings_created": 0,
            "listings_updated": 0,
            "pages_scraped": 0,
            "next_max_price": None,
        }

        # Build initial URL (sorted by price descending for segmentation)
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
            logger.error("Failed to fetch first page: %s", first_result.error)
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
            len(listings),
            total_pages,
        )

        if total_pages <= 1 or not metadata.has_next_page:
            session.commit()
            return stats

        # Batch fetch remaining pages
        # Fetch in batches to avoid overwhelming the system
        batch_size = self.concurrency * 2

        for batch_start in range(2, total_pages + 1, batch_size):
            batch_end = min(batch_start + batch_size - 1, total_pages)

            logger.info(
                "Fetching pages %d-%d concurrently...",
                batch_start,
                batch_end,
            )

            results = await self._fetch_pages_batch(base_url, batch_start, batch_end)

            # Process results sequentially (sorted by page number)
            for result in sorted(results, key=lambda r: r.page_num):
                if result.html is None:
                    logger.warning(
                        "Skipping failed page %d: %s", result.page_num, result.error
                    )
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
        listings: list[ParsedListingCard],
        metadata: SearchMetadata,
        stats: dict[str, int | None],
    ) -> int | None:
        """Process parsed listings and update stats.

        Args:
            session: Database session.
            segment: The segment being scraped.
            listings: Parsed listing cards from the page.
            metadata: Page metadata including lowest price.
            stats: Statistics dictionary to update.

        Returns:
            Lowest price on this page, or None if no priced listings.
        """
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
            metadata.page,
            len(listings),
            metadata.lowest_price_on_page,
        )

        return metadata.lowest_price_on_page

    def _upsert_listing_card(
        self,
        session: Session,
        segment: ScrapeSegment,
        card: ParsedListingCard,
    ) -> bool:
        """Upsert a listing from a card.

        Args:
            session: Database session.
            segment: The segment being scraped.
            card: Parsed listing card data.

        Returns:
            True if created, False if updated.
        """
        # Get or lookup concelho
        concelho = self._get_concelho(session, segment.location_slug)

        # Try to find existing listing by idealista_id
        existing = (
            session.query(Listing).filter_by(idealista_id=card.idealista_id).first()
        )

        now = datetime.now(UTC)

        if existing:
            # Update existing listing
            return self._update_listing(session, existing, card, now)
        else:
            # Create new listing
            return self._create_listing(session, concelho, card, now)

    def _get_concelho(self, session: Session, location_slug: str) -> Concelho | None:
        """Get concelho by slug with caching.

        Args:
            session: Database session.
            location_slug: Location slug.

        Returns:
            Concelho instance or None if not found.
        """
        if location_slug not in self._concelho_cache:
            concelho = session.query(Concelho).filter_by(slug=location_slug).first()
            self._concelho_cache[location_slug] = concelho
            if concelho is None:
                logger.warning("Concelho not found for slug: %s", location_slug)
        return self._concelho_cache[location_slug]

    def _create_listing(
        self,
        session: Session,
        concelho: Concelho | None,
        card: ParsedListingCard,
        now: datetime,
    ) -> bool:
        """Create a new listing from card data.

        Args:
            session: Database session.
            concelho: Associated concelho (may be None).
            card: Parsed listing card data.
            now: Current timestamp.

        Returns:
            True (always creates).
        """
        # Parse typology and area from details_raw
        typology, area_gross, bedrooms = self._parse_details(card.details_raw)

        listing = Listing(
            idealista_id=card.idealista_id,
            concelho_id=concelho.id if concelho else None,
            operation=card.operation,
            property_type=card.property_type,
            url=self._normalize_url(card.url),
            title=card.title,
            price=card.price,
            typology=typology,
            area_gross=area_gross,
            bedrooms=bedrooms,
            agency_name=card.agency_name,
            agency_url=card.agency_url,
            image_url=card.image_url,
            tags=",".join(card.tags) if card.tags else None,
            description=card.description,
            first_seen=now,
            last_seen=now,
            is_active=True,
            raw_data={
                "summary_location": card.summary_location,
                "details_raw": card.details_raw,
            },
        )
        session.add(listing)
        logger.debug("Created listing: %d - %s", card.idealista_id, card.title)
        return True

    def _update_listing(
        self,
        session: Session,
        listing: Listing,
        card: ParsedListingCard,
        now: datetime,
    ) -> bool:
        """Update an existing listing from card data.

        Args:
            session: Database session.
            listing: Existing listing to update.
            card: Parsed listing card data.
            now: Current timestamp.

        Returns:
            False (always updates).
        """
        # Track changes for history
        changes: dict[str, dict[str, int | None]] = {}

        # Check for price change
        if card.price != listing.price:
            changes["price"] = {"old": listing.price, "new": card.price}

            # Create history record
            history = ListingHistory(
                listing_id=listing.id,
                price=listing.price,
                scraped_at=now,
                changes={"price": {"old": listing.price, "new": card.price}},
            )
            session.add(history)

        # Update fields
        listing.title = card.title
        listing.price = card.price
        listing.agency_name = card.agency_name
        listing.agency_url = card.agency_url
        listing.image_url = card.image_url
        listing.tags = ",".join(card.tags) if card.tags else None
        listing.last_seen = now
        listing.is_active = True

        # Update typology and area if parsed
        typology, area_gross, bedrooms = self._parse_details(card.details_raw)
        if typology:
            listing.typology = typology
        if area_gross:
            listing.area_gross = area_gross
        if bedrooms:
            listing.bedrooms = bedrooms

        if changes:
            logger.debug(
                "Updated listing %d with changes: %s",
                card.idealista_id,
                changes,
            )
        else:
            logger.debug("Updated listing %d (no price change)", card.idealista_id)

        return False

    def _parse_details(
        self, details_raw: list[str]
    ) -> tuple[str | None, float | None, int | None]:
        """Parse details from raw detail strings.

        Args:
            details_raw: List of detail strings like ["T3", "110 m² área bruta"].

        Returns:
            Tuple of (typology, area_gross, bedrooms).
        """
        import contextlib
        import re

        typology: str | None = None
        area_gross: float | None = None
        bedrooms: int | None = None

        for detail in details_raw:
            detail_lower = detail.lower()

            # Parse typology (T0, T1, T2, etc.)
            typology_match = re.match(r"^(t\d\+?)$", detail_lower)
            if typology_match:
                typology = typology_match.group(1).upper()
                # Extract bedrooms from typology
                bedrooms_match = re.search(r"(\d+)", typology)
                if bedrooms_match:
                    bedrooms = int(bedrooms_match.group(1))
                continue

            # Parse area (e.g., "110 m²" or "110 m² área bruta")
            area_match = re.search(r"([\d.,]+)\s*m²", detail)
            if area_match:
                area_str = area_match.group(1).replace(".", "").replace(",", ".")
                with contextlib.suppress(ValueError):
                    area_gross = float(area_str)
                continue

            # Parse bedrooms if not from typology (e.g., "3 quartos")
            bedrooms_match = re.search(r"(\d+)\s*quarto", detail_lower)
            if bedrooms_match and bedrooms is None:
                bedrooms = int(bedrooms_match.group(1))

        return typology, area_gross, bedrooms

    def _normalize_url(self, url: str) -> str:
        """Normalize a listing URL to absolute form.

        Args:
            url: Relative or absolute URL.

        Returns:
            Absolute URL.
        """
        from idealista_scraper.scraping.listings_scraper import IDEALISTA_BASE_URL

        if url.startswith("http"):
            return url
        return f"{IDEALISTA_BASE_URL}{url}"

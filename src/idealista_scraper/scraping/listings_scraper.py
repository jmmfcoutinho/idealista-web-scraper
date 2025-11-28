"""Listings scraper for extracting listing cards from search results.

This module implements the listings scraper that traverses Idealista search
result pages with price segmentation and stores cover info into the listings table.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy.orm import Session

from idealista_scraper.config import RunConfig
from idealista_scraper.db import Concelho, Listing, ListingHistory, ScrapeRun
from idealista_scraper.scraping.client import WAIT_SELECTOR_SEARCH_RESULTS, PageClient
from idealista_scraper.scraping.selectors import (
    ParsedListingCard,
    parse_listings_page,
)
from idealista_scraper.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

# Base URL for Idealista Portugal
IDEALISTA_BASE_URL = "https://www.idealista.pt"

# Maximum pages Idealista shows (60 pages x 30 listings = 1,800 max results)
MAX_PAGES_LIMIT = 60


# -----------------------------------------------------------------------------
# URL Building Helpers
# -----------------------------------------------------------------------------


def build_search_url(
    location_slug: str,
    operation: Literal["comprar", "arrendar"],
    property_type: str = "casas",
    page: int = 1,
    max_price: int | None = None,
    min_price: int | None = None,
    order: str | None = None,
) -> str:
    """Build an Idealista search URL.

    Args:
        location_slug: Location slug (e.g., "cascais", "lisboa-distrito").
        operation: Operation type ("comprar" or "arrendar").
        property_type: Property type (e.g., "casas", "apartamentos").
        page: Page number (1-based).
        max_price: Maximum price filter (optional).
        min_price: Minimum price filter (optional).
        order: Sorting order (e.g., "precos-desc" for descending price).

    Returns:
        Full URL for the search page.
    """
    # Base path: /{operation}-{property_type}/{location}/
    path = f"/{operation}-{property_type}/{location_slug}/"

    # Build query parameters
    params: list[str] = []

    # Add price filters
    if max_price is not None:
        params.append(f"maxPrice={max_price}")
    if min_price is not None:
        params.append(f"minPrice={min_price}")

    # Add sorting
    if order:
        params.append(f"ordem={order}")

    # Add pagination
    if page > 1:
        params.append(f"pagina={page}")

    # Build full URL
    url = f"{IDEALISTA_BASE_URL}{path}"
    if params:
        url += "?" + "&".join(params)

    return url


def build_paginated_url(base_url: str, page: int) -> str:
    """Add or update pagination to an existing URL.

    Args:
        base_url: Base search URL.
        page: Page number to add.

    Returns:
        URL with pagination parameter.
    """
    if page <= 1:
        return base_url

    if "?" in base_url:
        # Check if pagina already exists
        if "pagina=" in base_url:
            # Replace existing page number
            import re

            return re.sub(r"pagina=\d+", f"pagina={page}", base_url)
        return f"{base_url}&pagina={page}"
    return f"{base_url}?pagina={page}"


# -----------------------------------------------------------------------------
# Data Classes
# -----------------------------------------------------------------------------


@dataclass
class ScrapeSegment:
    """Represents a price segment for scraping.

    Attributes:
        location_slug: Location being scraped.
        operation: Operation type.
        property_type: Property type.
        max_price: Maximum price for this segment (None = no limit).
        min_price: Minimum price for this segment (None = no limit).
    """

    location_slug: str
    operation: Literal["comprar", "arrendar"]
    property_type: str
    max_price: int | None = None
    min_price: int | None = None

    def __str__(self) -> str:
        """Return string representation."""
        price_range = ""
        if self.min_price is not None or self.max_price is not None:
            min_str = f"{self.min_price:,}" if self.min_price else "0"
            max_str = f"{self.max_price:,}" if self.max_price else "∞"
            price_range = f" [{min_str}€ - {max_str}€]"
        return (
            f"{self.location_slug}/{self.operation}/{self.property_type}{price_range}"
        )


# -----------------------------------------------------------------------------
# Listings Scraper
# -----------------------------------------------------------------------------


class ListingsScraper:
    """Scrapes listing cards for configured locations and operations.

    Does not visit detail pages; only cover info. Implements price
    segmentation to handle locations with more than 1,800 results
    (60 pages x 30 listings).

    Attributes:
        client: Page client for fetching HTML pages.
        session_factory: Factory function to create database sessions.
        config: Run configuration with locations and scraping settings.
    """

    def __init__(
        self,
        client: PageClient,
        session_factory: Callable[[], Session],
        config: RunConfig,
    ) -> None:
        """Initialize the ListingsScraper.

        Args:
            client: Page client for fetching HTML pages.
            session_factory: Factory function to create database sessions.
            config: Run configuration with locations and settings.
        """
        self.client = client
        self.session_factory = session_factory
        self.config = config
        self._concelho_cache: dict[str, Concelho | None] = {}

    def run(self) -> dict[str, int]:
        """Run scraping according to the configuration.

        Iterates over configured locations, operations, and property types,
        applying price segmentation when necessary.

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
        logger.info("Starting listings scraper run")

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
                        segment_stats = self._scrape_location(
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
                "Listings scraper completed: %d listings processed "
                "(%d created, %d updated), %d pages, %d segments",
                stats["listings_processed"],
                stats["listings_created"],
                stats["listings_updated"],
                stats["pages_scraped"],
                stats["segments_scraped"],
            )

            return stats

        except Exception as e:
            logger.exception("Listings scraper failed: %s", e)
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

    def _create_scrape_run(self, session: Session) -> ScrapeRun:
        """Create a new scrape run record.

        Args:
            session: Database session.

        Returns:
            The created ScrapeRun instance.
        """
        scrape_run = ScrapeRun(
            run_type="scrape",
            status="running",
            started_at=datetime.now(UTC),
            config=self.config.model_dump(),
        )
        session.add(scrape_run)
        session.commit()
        return scrape_run

    def _scrape_location(
        self,
        session: Session,
        location_slug: str,
        operation: Literal["comprar", "arrendar"],
        property_type: str,
    ) -> dict[str, int]:
        """Scrape all listings for a location with price segmentation.

        Uses price segmentation strategy:
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
        logger.info(
            "Scraping %s %s in %s",
            operation,
            property_type,
            location_slug,
        )

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
            segment_stats = self._scrape_segment(session, segment)
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

    def _scrape_segment(
        self,
        session: Session,
        segment: ScrapeSegment,
    ) -> dict[str, int | None]:
        """Scrape a single price segment.

        Args:
            session: Database session.
            segment: The segment to scrape.

        Returns:
            Statistics including "next_max_price" if more segments needed.
        """
        logger.info("Scraping segment: %s", segment)

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

        page = 1
        lowest_price_seen: int | None = None
        max_pages = min(
            self.config.scraping.max_pages or MAX_PAGES_LIMIT,
            MAX_PAGES_LIMIT,
        )

        while page <= max_pages:
            url = build_paginated_url(base_url, page)
            logger.debug("Fetching page %d: %s", page, url)

            try:
                html = self.client.get_html(
                    url, wait_selector=WAIT_SELECTOR_SEARCH_RESULTS
                )
                listings, metadata = parse_listings_page(
                    html, segment.operation, segment.property_type
                )
            except RuntimeError as e:
                logger.error("Failed to fetch page %d: %s", page, e)
                break

            # Process listings
            for card in listings:
                created = self._upsert_listing_card(session, segment, card)
                stats["listings_processed"] = (stats["listings_processed"] or 0) + 1
                if created:
                    stats["listings_created"] = (stats["listings_created"] or 0) + 1
                else:
                    stats["listings_updated"] = (stats["listings_updated"] or 0) + 1

            stats["pages_scraped"] = (stats["pages_scraped"] or 0) + 1

            # Track lowest price for segmentation
            if metadata.lowest_price_on_page is not None and (
                lowest_price_seen is None
                or metadata.lowest_price_on_page < lowest_price_seen
            ):
                lowest_price_seen = metadata.lowest_price_on_page

            # Commit after each page
            session.commit()

            logger.info(
                "Page %d/%s: %d listings (total: %d, lowest: %s)",
                page,
                metadata.last_page or "?",
                len(listings),
                metadata.total_count,
                metadata.lowest_price_on_page,
            )

            # Check if we need to continue
            if not metadata.has_next_page:
                logger.debug("No more pages available")
                break

            # Check if we've hit the Idealista limit and need segmentation
            if page >= MAX_PAGES_LIMIT:
                if lowest_price_seen is not None:
                    logger.info(
                        "Reached page limit (%d). Will segment at price: %d",
                        MAX_PAGES_LIMIT,
                        lowest_price_seen,
                    )
                    stats["next_max_price"] = lowest_price_seen
                break

            page += 1

        return stats

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
        if url.startswith("http"):
            return url
        return f"{IDEALISTA_BASE_URL}{url}"

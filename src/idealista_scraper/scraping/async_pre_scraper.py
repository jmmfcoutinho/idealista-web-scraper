"""Async pre-scraper for extracting districts and concelhos.

This module implements an async version of the pre-scraper that populates
the `districts` and `concelhos` tables by fetching and parsing the Idealista
homepage and district concelhos pages concurrently.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from idealista_scraper.db import Concelho, District, ScrapeRun
from idealista_scraper.scraping.async_client import AsyncPageClient
from idealista_scraper.scraping.client import (
    WAIT_SELECTOR_DISTRICT_CONCELHOS,
    WAIT_SELECTOR_HOMEPAGE,
)
from idealista_scraper.scraping.selectors import (
    ParsedConcelhoLink,
    ParsedDistrictInfo,
    parse_concelhos_page,
    parse_homepage_districts,
)
from idealista_scraper.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

# Base URL for Idealista Portugal
IDEALISTA_BASE_URL = "https://www.idealista.pt"


@dataclass
class DistrictConcelhosResult:
    """Result of fetching concelhos for a district.

    Attributes:
        district_slug: The district's URL slug.
        concelhos: List of parsed concelho links.
        error: Error message if failed, None otherwise.
    """

    district_slug: str
    concelhos: list[ParsedConcelhoLink]
    error: str | None = None


class AsyncPreScraper:
    """Async pre-scraper for extracting districts and concelhos.

    Uses asyncio.gather() with Semaphore to fetch multiple district
    concelhos pages concurrently while respecting concurrency limits.

    Attributes:
        client: Async page client for fetching HTML pages.
        session_factory: Factory function to create database sessions.
        concurrency: Maximum number of concurrent browser sessions.
    """

    def __init__(
        self,
        client: AsyncPageClient,
        session_factory: Callable[[], Session],
        concurrency: int = 5,
    ) -> None:
        """Initialize the AsyncPreScraper.

        Args:
            client: Async page client for fetching HTML pages.
            session_factory: Factory function to create database sessions.
            concurrency: Number of concurrent browser sessions (1-20).
        """
        self.client = client
        self.session_factory = session_factory
        self.concurrency = concurrency
        self._semaphore: asyncio.Semaphore | None = None

    async def run(self) -> dict[str, int]:
        """Run the async pre-scraper and persist results.

        Fetches the Idealista homepage, parses district information,
        and concurrently fetches concelho information for each district.

        Returns:
            Dictionary with counts: {
                "districts_created": int,
                "districts_updated": int,
                "concelhos_created": int,
                "concelhos_updated": int,
            }

        Raises:
            RuntimeError: If scraping repeatedly fails.
        """
        logger.info(
            "Starting async pre-scraper (concurrency=%d)",
            self.concurrency,
        )

        self._semaphore = asyncio.Semaphore(self.concurrency)
        session = self.session_factory()
        scrape_run = self._create_scrape_run(session)

        try:
            # Fetch and parse homepage
            logger.info("Fetching Idealista homepage")
            homepage_html = await self.client.get_html(
                IDEALISTA_BASE_URL, wait_selector=WAIT_SELECTOR_HOMEPAGE
            )
            districts_info = parse_homepage_districts(homepage_html)
            logger.info("Parsed %d districts from homepage", len(districts_info))

            # Track statistics
            stats = {
                "districts_created": 0,
                "districts_updated": 0,
                "concelhos_created": 0,
                "concelhos_updated": 0,
            }

            # Find districts that need concelho fetching
            districts_needing_concelhos = [d for d in districts_info if not d.concelhos]

            if districts_needing_concelhos:
                logger.info(
                    "Fetching concelhos for %d districts concurrently",
                    len(districts_needing_concelhos),
                )

                # Fetch concelhos for all districts concurrently
                concelho_results = await self._fetch_all_concelhos(
                    [d.slug for d in districts_needing_concelhos]
                )

                # Build a map of district slug to concelhos
                concelho_map: dict[str, list[ParsedConcelhoLink]] = {}
                for result in concelho_results:
                    if result.concelhos:
                        concelho_map[result.district_slug] = result.concelhos
                    elif result.error:
                        logger.warning(
                            "Failed to fetch concelhos for %s: %s",
                            result.district_slug,
                            result.error,
                        )

                # Update district info with fetched concelhos
                for district in districts_info:
                    if district.slug in concelho_map:
                        district.concelhos = concelho_map[district.slug]

            # Process each district
            for district_info in districts_info:
                district_stats = self._process_district(session, district_info)
                for key in stats:
                    stats[key] += district_stats.get(key, 0)

            # Update scrape run status
            scrape_run.status = "success"
            scrape_run.ended_at = datetime.now(UTC)
            session.commit()

            logger.info(
                "Async pre-scraper completed: %d districts created, %d updated, "
                "%d concelhos created, %d updated",
                stats["districts_created"],
                stats["districts_updated"],
                stats["concelhos_created"],
                stats["concelhos_updated"],
            )

            return stats

        except Exception as e:
            logger.exception("Async pre-scraper failed: %s", e)
            scrape_run.status = "failed"
            scrape_run.error_message = str(e)
            scrape_run.ended_at = datetime.now(UTC)
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
            run_type="prescrape-async",
            status="running",
            started_at=datetime.now(UTC),
            config={"concurrency": self.concurrency},
        )
        session.add(scrape_run)
        session.commit()
        return scrape_run

    async def _fetch_concelhos_for_district(
        self, district_slug: str
    ) -> DistrictConcelhosResult:
        """Fetch concelho information for a district with semaphore control.

        Args:
            district_slug: The district's URL slug.

        Returns:
            DistrictConcelhosResult with concelhos or error.
        """
        if self._semaphore is None:
            msg = "Semaphore not initialized - call run() first"
            raise RuntimeError(msg)

        # Build URL for the concelhos page
        url = f"{IDEALISTA_BASE_URL}/comprar-casas/{district_slug}/concelhos-freguesias"

        async with self._semaphore:
            try:
                logger.debug("Fetching concelhos for district: %s", district_slug)
                html = await self.client.get_html(
                    url, wait_selector=WAIT_SELECTOR_DISTRICT_CONCELHOS
                )
                concelhos = parse_concelhos_page(html)
                logger.debug(
                    "Parsed %d concelhos from %s", len(concelhos), district_slug
                )
                return DistrictConcelhosResult(
                    district_slug=district_slug,
                    concelhos=concelhos,
                )
            except Exception as e:
                logger.warning("Failed to fetch concelhos for %s: %s", district_slug, e)
                return DistrictConcelhosResult(
                    district_slug=district_slug,
                    concelhos=[],
                    error=str(e),
                )

    async def _fetch_all_concelhos(
        self, district_slugs: list[str]
    ) -> list[DistrictConcelhosResult]:
        """Fetch concelhos for multiple districts concurrently.

        Args:
            district_slugs: List of district URL slugs.

        Returns:
            List of DistrictConcelhosResult objects.
        """
        tasks = [self._fetch_concelhos_for_district(slug) for slug in district_slugs]
        results = await asyncio.gather(*tasks)
        return list(results)

    def _process_district(
        self,
        session: Session,
        district_info: ParsedDistrictInfo,
    ) -> dict[str, int]:
        """Process a single district and its concelhos.

        Args:
            session: Database session.
            district_info: Parsed district information.

        Returns:
            Dictionary with counts for this district.
        """
        stats = {
            "districts_created": 0,
            "districts_updated": 0,
            "concelhos_created": 0,
            "concelhos_updated": 0,
        }

        # Upsert district
        district, created = self._upsert_district(session, district_info)
        if district.id is None:
            session.flush()  # Ensure district has an ID

        if created:
            stats["districts_created"] = 1
        else:
            stats["districts_updated"] = 1

        # Upsert concelhos
        for concelho_link in district_info.concelhos:
            created = self._upsert_concelho(session, district, concelho_link)
            if created:
                stats["concelhos_created"] += 1
            else:
                stats["concelhos_updated"] += 1

        session.commit()

        logger.debug(
            "Processed district '%s' with %d concelhos",
            district_info.name,
            len(district_info.concelhos),
        )

        return stats

    def _upsert_district(
        self,
        session: Session,
        district_info: ParsedDistrictInfo,
    ) -> tuple[District, bool]:
        """Upsert a district record.

        Args:
            session: Database session.
            district_info: Parsed district information.

        Returns:
            Tuple of (District instance, created flag).
        """
        # Try to find existing district by slug
        existing = session.query(District).filter_by(slug=district_info.slug).first()

        now = datetime.now(UTC)

        if existing:
            # Update existing district
            existing.name = district_info.name
            if district_info.listing_count is not None:
                existing.listing_count = district_info.listing_count
            existing.last_scraped = now
            logger.debug("Updated district: %s", district_info.name)
            return existing, False
        else:
            # Create new district
            district = District(
                name=district_info.name,
                slug=district_info.slug,
                listing_count=district_info.listing_count,
                last_scraped=now,
            )
            session.add(district)
            logger.debug("Created district: %s", district_info.name)
            return district, True

    def _upsert_concelho(
        self,
        session: Session,
        district: District,
        concelho_link: ParsedConcelhoLink,
    ) -> bool:
        """Upsert a concelho record.

        Args:
            session: Database session.
            district: Parent district.
            concelho_link: Parsed concelho link information.

        Returns:
            True if created, False if updated.
        """
        # Try to find existing concelho by slug
        existing = session.query(Concelho).filter_by(slug=concelho_link.slug).first()

        now = datetime.now(UTC)

        if existing:
            # Update existing concelho
            existing.name = concelho_link.name
            existing.district_id = district.id
            existing.last_scraped = now
            logger.debug("Updated concelho: %s", concelho_link.name)
            return False
        else:
            # Create new concelho
            concelho = Concelho(
                district_id=district.id,
                name=concelho_link.name,
                slug=concelho_link.slug,
                last_scraped=now,
            )
            session.add(concelho)
            logger.debug("Created concelho: %s", concelho_link.name)
            return True

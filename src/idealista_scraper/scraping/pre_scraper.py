"""Pre-scraper for extracting districts and concelhos from Idealista homepage.

This module implements the pre-scraper that populates the `districts` and
`concelhos` tables by fetching and parsing the Idealista homepage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from idealista_scraper.db import Concelho, District, ScrapeRun
from idealista_scraper.scraping.client import (
    WAIT_SELECTOR_DISTRICT_CONCELHOS,
    WAIT_SELECTOR_HOMEPAGE,
    PageClient,
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


class PreScraper:
    """Extracts districts and concelhos from the Idealista homepage.

    This corresponds to Phase 4 (Part 1) of the implementation plan.
    The pre-scraper fetches the homepage, parses district and concelho
    information, and persists the data to the database.

    Attributes:
        client: Page client for fetching HTML pages.
        session_factory: Factory function to create database sessions.
    """

    def __init__(
        self,
        client: PageClient,
        session_factory: Callable[[], Session],
    ) -> None:
        """Initialize the PreScraper.

        Args:
            client: Page client for fetching HTML pages.
            session_factory: Factory function to create database sessions.
        """
        self.client = client
        self.session_factory = session_factory

    def run(self) -> dict[str, int]:
        """Run the pre-scraper and persist results.

        Fetches the Idealista homepage, parses district and concelho
        information, and upserts the data into the database.

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
        logger.info("Starting pre-scraper run")

        session = self.session_factory()
        scrape_run = self._create_scrape_run(session)

        try:
            # Fetch and parse homepage
            logger.info("Fetching Idealista homepage")
            homepage_html = self.client.get_html(
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
                "Pre-scraper completed: %d districts created, %d updated, "
                "%d concelhos created, %d updated",
                stats["districts_created"],
                stats["districts_updated"],
                stats["concelhos_created"],
                stats["concelhos_updated"],
            )

            return stats

        except Exception as e:
            logger.exception("Pre-scraper failed: %s", e)
            scrape_run.status = "failed"
            scrape_run.error_message = str(e)
            scrape_run.ended_at = datetime.now(UTC)
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
            run_type="prescrape",
            status="running",
            started_at=datetime.now(UTC),
        )
        session.add(scrape_run)
        session.commit()
        return scrape_run

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
        district = self._upsert_district(session, district_info)
        if district.id is None:
            session.flush()  # Ensure district has an ID

        stats["districts_created" if stats else "districts_updated"] = 1

        # Get concelhos - either from homepage or by fetching the concelhos page
        concelhos = district_info.concelhos
        if not concelhos:
            # Try fetching the concelhos page for this district
            concelhos = self._fetch_concelhos_for_district(district_info.slug)

        # Upsert concelhos
        for concelho_link in concelhos:
            created = self._upsert_concelho(session, district, concelho_link)
            if created:
                stats["concelhos_created"] += 1
            else:
                stats["concelhos_updated"] += 1

        session.commit()

        logger.debug(
            "Processed district '%s' with %d concelhos",
            district_info.name,
            len(concelhos),
        )

        return stats

    def _upsert_district(
        self,
        session: Session,
        district_info: ParsedDistrictInfo,
    ) -> District:
        """Upsert a district record.

        Args:
            session: Database session.
            district_info: Parsed district information.

        Returns:
            The upserted District instance.
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
            return existing
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
            return district

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

    def _fetch_concelhos_for_district(
        self, district_slug: str
    ) -> list[ParsedConcelhoLink]:
        """Fetch concelho information for a district.

        Args:
            district_slug: The district's URL slug.

        Returns:
            List of parsed concelho links.
        """
        # Build URL for the concelhos page
        # Format: /comprar-casas/{distrito}-distrito/concelhos-freguesias
        url = f"{IDEALISTA_BASE_URL}/comprar-casas/{district_slug}/concelhos-freguesias"

        logger.debug("Fetching concelhos for district: %s", district_slug)

        try:
            html = self.client.get_html(
                url, wait_selector=WAIT_SELECTOR_DISTRICT_CONCELHOS
            )
            concelhos = parse_concelhos_page(html)
            logger.debug("Parsed %d concelhos from %s", len(concelhos), url)
            return concelhos
        except RuntimeError as e:
            logger.warning("Failed to fetch concelhos for %s: %s", district_slug, e)
            return []

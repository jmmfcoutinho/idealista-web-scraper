"""Detail scraper for enriching listings with full details.

This module implements the details scraper that visits individual listing
pages and enriches the database with additional information like descriptions,
energy ratings, features, and characteristics.
"""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from idealista_scraper.db import Listing, ScrapeRun
from idealista_scraper.scraping.client import WAIT_SELECTOR_LISTING_DETAIL, PageClient
from idealista_scraper.scraping.selectors import (
    ParsedListingDetail,
    parse_listing_detail,
)
from idealista_scraper.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


class DetailsScraper:
    """Loads individual listing pages and enriches listings in the database.

    Visits listing detail pages to extract additional information that
    is not available on search result cards, such as full descriptions,
    energy certificates, characteristics, and more.

    Attributes:
        client: Page client for fetching HTML pages.
        session_factory: Factory function to create database sessions.
        max_listings: Maximum number of listings to process (None = no limit).
    """

    def __init__(
        self,
        client: PageClient,
        session_factory: Callable[[], Session],
        max_listings: int | None = None,
    ) -> None:
        """Initialize the DetailsScraper.

        Args:
            client: Page client for fetching HTML pages.
            session_factory: Factory function to create database sessions.
            max_listings: Maximum number of listings to process.
        """
        self.client = client
        self.session_factory = session_factory
        self.max_listings = max_listings

    def run(self) -> dict[str, int]:
        """Scrape details for a subset of listings.

        The subset is determined by:
        - Listings that are missing key detail fields (description, energy_class)
        - Limited by `max_listings` if specified

        Returns:
            Dictionary with statistics: {
                "listings_processed": int,
                "listings_enriched": int,
                "listings_failed": int,
            }

        Raises:
            RuntimeError: If scraping repeatedly fails.
        """
        logger.info(
            "Starting details scraper run (max_listings=%s)",
            self.max_listings,
        )

        session = self.session_factory()
        scrape_run = self._create_scrape_run(session)

        stats = {
            "listings_processed": 0,
            "listings_enriched": 0,
            "listings_failed": 0,
        }

        try:
            # Get listings that need details
            listings = self._get_listings_needing_details(session)
            total_to_process = len(listings)

            logger.info("Found %d listings needing details", total_to_process)

            for i, listing in enumerate(listings, 1):
                logger.info(
                    "Processing listing %d/%d: %d (%s)",
                    i,
                    total_to_process,
                    listing.idealista_id,
                    listing.url,
                )

                success = self._scrape_listing_detail(listing)
                stats["listings_processed"] += 1

                if success:
                    stats["listings_enriched"] += 1
                else:
                    stats["listings_failed"] += 1

                # Commit after each listing for durability
                session.commit()

            # Update scrape run status
            scrape_run.status = "success"
            scrape_run.ended_at = datetime.now(UTC)
            scrape_run.listings_processed = stats["listings_processed"]
            scrape_run.listings_created = stats["listings_enriched"]  # Reuse field
            scrape_run.listings_updated = stats["listings_failed"]  # Reuse field
            session.commit()

            logger.info(
                "Details scraper completed: %d processed, %d enriched, %d failed",
                stats["listings_processed"],
                stats["listings_enriched"],
                stats["listings_failed"],
            )

            return stats

        except Exception as e:
            logger.exception("Details scraper failed: %s", e)
            scrape_run.status = "failed"
            scrape_run.error_message = str(e)
            scrape_run.ended_at = datetime.now(UTC)
            scrape_run.listings_processed = stats["listings_processed"]
            scrape_run.listings_created = stats["listings_enriched"]
            scrape_run.listings_updated = stats["listings_failed"]
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
            run_type="scrape-details",
            status="running",
            started_at=datetime.now(UTC),
            config={"max_listings": self.max_listings},
        )
        session.add(scrape_run)
        session.commit()
        return scrape_run

    def _get_listings_needing_details(self, session: Session) -> list[Listing]:
        """Get listings that need detail enrichment.

        Selects listings where key detail fields are missing:
        - description is NULL
        - energy_class is NULL
        - year_built is NULL

        Args:
            session: Database session.

        Returns:
            List of Listing objects needing details.
        """
        from sqlalchemy import or_

        query = (
            session.query(Listing)
            .filter(Listing.is_active.is_(True))
            .filter(
                or_(
                    Listing.description.is_(None),
                    Listing.energy_class.is_(None),
                )
            )
            .order_by(Listing.last_seen.desc())
        )

        if self.max_listings is not None:
            query = query.limit(self.max_listings)

        return list(query.all())

    def _scrape_listing_detail(self, listing: Listing) -> bool:
        """Scrape and update details for a single listing.

        Args:
            listing: The listing to enrich.

        Returns:
            True if successful, False if failed.
        """
        try:
            html = self.client.get_html(
                listing.url,
                wait_selector=WAIT_SELECTOR_LISTING_DETAIL,
            )
            detail = parse_listing_detail(html)
            self._update_listing_from_detail(listing, detail)

            logger.debug(
                "Enriched listing %d with: description=%s, energy=%s, reference=%s",
                listing.idealista_id,
                "yes" if detail.description else "no",
                detail.energy_class or "none",
                detail.reference or "none",
            )
            return True

        except RuntimeError as e:
            logger.error(
                "Failed to fetch details for listing %d: %s",
                listing.idealista_id,
                e,
            )
            return False

    def _update_listing_from_detail(
        self,
        listing: Listing,
        detail: ParsedListingDetail,
    ) -> None:
        """Update a listing with data from the detail page.

        Args:
            listing: The listing to update.
            detail: Parsed detail page data.
        """
        # Update description if available
        if detail.description:
            listing.description = detail.description

        # Update reference if available
        if detail.reference:
            listing.reference = detail.reference

        # Update energy class if available
        if detail.energy_class:
            listing.energy_class = self._normalize_energy_class(detail.energy_class)

        # Update location if available
        if detail.location:
            self._parse_location(listing, detail.location)

        # Parse features from features_raw
        self._parse_features(listing, detail.features_raw)

        # Parse equipment (pool, garden, AC, etc.)
        self._parse_equipment(listing, detail.equipment)

        # Parse characteristics
        self._parse_characteristics(listing, detail.characteristics)

        # Update tags if we have new ones
        if detail.tags:
            existing_tags = set(listing.tags.split(",")) if listing.tags else set()
            new_tags = existing_tags | set(detail.tags)
            listing.tags = ",".join(sorted(new_tags))

        # Store raw detail data
        if listing.raw_data is None:
            listing.raw_data = {}
        listing.raw_data["detail"] = {
            "features_raw": detail.features_raw,
            "equipment": detail.equipment,
            "characteristics": detail.characteristics,
            "photo_count": detail.photo_count,
        }

        # Update last_seen timestamp
        listing.last_seen = datetime.now(UTC)

    def _normalize_energy_class(self, energy_class: str) -> str:
        """Normalize energy class string.

        Args:
            energy_class: Raw energy class string.

        Returns:
            Normalized energy class (A, A+, B, B-, C, etc.)
        """
        if not energy_class:
            return ""

        # Extract letter and modifier from text like "A+", "B-", "C"
        match = re.search(r"([A-Ga-g])([+-])?", energy_class)
        if match:
            letter = match.group(1).upper()
            modifier = match.group(2) or ""
            return f"{letter}{modifier}"

        return energy_class.strip().upper()

    def _parse_location(self, listing: Listing, location: str) -> None:
        """Parse location string into structured fields.

        Location strings are typically comma-separated:
        "Street Name, Neighborhood, Parish, Municipality"

        Args:
            listing: The listing to update.
            location: Raw location string.
        """
        if not location:
            return

        parts = [p.strip() for p in location.split(",")]

        # Try to extract structured location (order varies)
        if len(parts) >= 1 and not listing.street:
            listing.street = parts[0]
        if len(parts) >= 2 and not listing.neighborhood:
            listing.neighborhood = parts[1]
        if len(parts) >= 3 and not listing.parish:
            listing.parish = parts[2]

    def _parse_equipment(self, listing: Listing, equipment: list[str]) -> None:
        """Parse equipment list into boolean fields.

        Equipment items are simple strings like:
        - "Ar condicionado"
        - "Piscina"
        - "Jardim"
        - "Terraço"

        Args:
            listing: The listing to update.
            equipment: List of equipment items.
        """
        for item in equipment:
            item_lower = item.lower()

            # Air conditioning
            if "ar condicionado" in item_lower:
                listing.has_air_conditioning = True

            # Pool
            if "piscina" in item_lower:
                listing.has_pool = True

            # Garden
            if "jardim" in item_lower:
                listing.has_garden = True

            # Terrace
            if "terraço" in item_lower or "terraco" in item_lower:
                listing.has_terrace = True

            # Balcony
            if "varanda" in item_lower:
                listing.has_balcony = True

            # Central heating
            if "aquecimento" in item_lower:
                listing.has_central_heating = True

    def _parse_features(self, listing: Listing, features_raw: list[str]) -> None:
        """Parse feature strings into structured fields.

        Features include things like:
        - "3 quartos" (bedrooms)
        - "2 casas de banho" (bathrooms)
        - "150 m²" (area)
        - "T3" (typology)
        - "4º andar" (floor)

        Args:
            listing: The listing to update.
            features_raw: List of raw feature strings.
        """
        for feature in features_raw:
            feature_lower = feature.lower()

            # Bedrooms: "3 quartos", "3 quarto"
            if "quarto" in feature_lower and listing.bedrooms is None:
                match = re.search(r"(\d+)\s*quarto", feature_lower)
                if match:
                    listing.bedrooms = int(match.group(1))

            # Bathrooms: "2 casas de banho", "8 casas de banho", "2 wc"
            if (
                "casas de banho" in feature_lower
                or "casa de banho" in feature_lower
                or "wc" in feature_lower
            ) and listing.bathrooms is None:
                match = re.search(r"(\d+)", feature_lower)
                if match:
                    listing.bathrooms = int(match.group(1))

            # Area: "150 m²", "150 m² área bruta", "150 m² área útil"
            if "m²" in feature_lower:
                match = re.search(r"([\d.,]+)\s*m²", feature_lower)
                if match:
                    area_str = match.group(1).replace(".", "").replace(",", ".")
                    with contextlib.suppress(ValueError):
                        area = float(area_str)
                        if "útil" in feature_lower and listing.area_useful is None:
                            listing.area_useful = area
                        elif listing.area_gross is None:
                            listing.area_gross = area

            # Floor: "4º andar", "rés-do-chão", "cave"
            if (
                "andar" in feature_lower
                or "rés" in feature_lower
                or "cave" in feature_lower
            ) and listing.floor is None:
                listing.floor = feature.strip()

            # Typology: "T3", "T2+1"
            if re.match(r"^t\d", feature_lower) and listing.typology is None:
                listing.typology = feature.upper()

            # Garage: "Garagem incluída", "Lugar de garagem"
            if "garagem" in feature_lower or "lugar de garagem" in feature_lower:
                listing.has_garage = True

            # Elevator: "com elevador"
            if "elevador" in feature_lower:
                listing.has_elevator = True

            # Condition: "bom estado", "novo", "para recuperar"
            if "estado" in feature_lower and listing.condition is None:
                listing.condition = feature.strip()

    def _parse_characteristics(
        self,
        listing: Listing,
        characteristics: dict[str, str],
    ) -> None:
        """Parse characteristics dict into structured fields.

        Characteristics come from the listing detail page and include
        things like:
        - "Ano de construção": "2010"
        - "Estado": "Usado"
        - "Elevador": "Sim"

        Args:
            listing: The listing to update.
            characteristics: Dictionary of characteristic key-value pairs.
        """
        for key, value in characteristics.items():
            key_lower = key.lower()
            value_lower = value.lower()

            # Year built
            if "ano" in key_lower and (
                "construção" in key_lower or "construcao" in key_lower
            ):
                with contextlib.suppress(ValueError):
                    listing.year_built = int(value.strip())

            # Condition
            if "estado" in key_lower and listing.condition is None:
                listing.condition = value.strip()

            # Elevator
            if "elevador" in key_lower:
                listing.has_elevator = value_lower in ("sim", "yes", "true", "1")

            # Garage / parking
            if (
                "garagem" in key_lower
                or "estacionamento" in key_lower
                or "parque" in key_lower
            ):
                listing.has_garage = (
                    value_lower in ("sim", "yes", "true", "1") or value_lower.isdigit()
                )

            # Pool
            if "piscina" in key_lower:
                listing.has_pool = value_lower in ("sim", "yes", "true", "1")

            # Garden
            if "jardim" in key_lower:
                listing.has_garden = value_lower in ("sim", "yes", "true", "1")

            # Terrace
            if "terraço" in key_lower or "terraco" in key_lower:
                listing.has_terrace = value_lower in ("sim", "yes", "true", "1")

            # Balcony
            if "varanda" in key_lower:
                listing.has_balcony = value_lower in ("sim", "yes", "true", "1")

            # Air conditioning
            if "ar condicionado" in key_lower:
                listing.has_air_conditioning = value_lower in (
                    "sim",
                    "yes",
                    "true",
                    "1",
                )

            # Central heating
            if "aquecimento central" in key_lower:
                listing.has_central_heating = value_lower in ("sim", "yes", "true", "1")

            # Energy class (backup if not found elsewhere)
            if (
                "certificado" in key_lower
                and "energ" in key_lower
                and listing.energy_class is None
            ):
                listing.energy_class = self._normalize_energy_class(value)

            # Price per sqm
            if (
                "preço" in key_lower
                and "m²" in key_lower
                and listing.price_per_sqm is None
            ):
                price_match = re.search(r"([\d.,]+)", value)
                if price_match:
                    price_str = price_match.group(1).replace(".", "").replace(",", ".")
                    with contextlib.suppress(ValueError):
                        listing.price_per_sqm = float(price_str)

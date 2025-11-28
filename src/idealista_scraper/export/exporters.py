"""Export functions for CSV and Parquet formats.

This module provides functions to export listing data from the database
to CSV and Parquet formats with optional filtering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from idealista_scraper.db.models import Concelho, District, Listing
from idealista_scraper.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


@dataclass
class ExportFilters:
    """Filters for exporting listings.

    Attributes:
        districts: List of district slugs to filter by.
        concelhos: List of concelho slugs to filter by.
        operation: Operation type filter ("comprar" or "arrendar").
        since: Export listings seen since this datetime.
        active_only: If True, only export active listings.
    """

    districts: list[str] = field(default_factory=list)
    concelhos: list[str] = field(default_factory=list)
    operation: str | None = None
    since: datetime | None = None
    active_only: bool = True


# Columns to export (in order)
EXPORT_COLUMNS: list[str] = [
    # Identifiers
    "id",
    "idealista_id",
    "url",
    # Location
    "district_name",
    "district_slug",
    "concelho_name",
    "concelho_slug",
    "street",
    "neighborhood",
    "parish",
    # Listing info
    "operation",
    "property_type",
    "title",
    "description",
    # Pricing
    "price",
    "price_per_sqm",
    # Property characteristics
    "typology",
    "bedrooms",
    "bathrooms",
    "area_gross",
    "area_useful",
    "floor",
    # Features
    "has_elevator",
    "has_garage",
    "has_pool",
    "has_garden",
    "has_terrace",
    "has_balcony",
    "has_air_conditioning",
    "has_central_heating",
    "is_luxury",
    "has_sea_view",
    # Property details
    "energy_class",
    "condition",
    "year_built",
    # Agency
    "agency_name",
    "agency_url",
    "reference",
    # Metadata
    "tags",
    "image_url",
    "first_seen",
    "last_seen",
    "is_active",
]


def _build_query(
    session: Session,
    filters: ExportFilters,
) -> list[Listing]:
    """Build and execute a query for listings with filters.

    Args:
        session: Database session.
        filters: Export filters to apply.

    Returns:
        List of Listing objects matching the filters.
    """
    # Build the base query with eager loading
    stmt = select(Listing).options(
        joinedload(Listing.concelho).joinedload(Concelho.district)
    )

    # Apply active_only filter
    if filters.active_only:
        stmt = stmt.where(Listing.is_active == True)  # noqa: E712

    # Apply operation filter
    if filters.operation:
        stmt = stmt.where(Listing.operation == filters.operation)

    # Apply since filter
    if filters.since:
        stmt = stmt.where(Listing.last_seen >= filters.since)

    # Apply concelho filter
    if filters.concelhos:
        stmt = stmt.join(Listing.concelho).where(Concelho.slug.in_(filters.concelhos))

    # Apply district filter
    if filters.districts:
        if not filters.concelhos:
            stmt = stmt.join(Listing.concelho)
        stmt = stmt.join(Concelho.district).where(District.slug.in_(filters.districts))

    # Order by last_seen descending
    stmt = stmt.order_by(Listing.last_seen.desc())

    result = session.execute(stmt)
    return list(result.scalars().unique().all())


def _listings_to_dataframe(listings: list[Listing]) -> pd.DataFrame:
    """Convert a list of Listing objects to a pandas DataFrame.

    Args:
        listings: List of Listing objects.

    Returns:
        DataFrame with listing data.
    """
    rows: list[dict[str, object]] = []

    for listing in listings:
        row: dict[str, object] = {
            # Identifiers
            "id": listing.id,
            "idealista_id": listing.idealista_id,
            "url": listing.url,
            # Location from relationships
            "district_name": (
                listing.concelho.district.name if listing.concelho else None
            ),
            "district_slug": (
                listing.concelho.district.slug if listing.concelho else None
            ),
            "concelho_name": listing.concelho.name if listing.concelho else None,
            "concelho_slug": listing.concelho.slug if listing.concelho else None,
            "street": listing.street,
            "neighborhood": listing.neighborhood,
            "parish": listing.parish,
            # Listing info
            "operation": listing.operation,
            "property_type": listing.property_type,
            "title": listing.title,
            "description": listing.description,
            # Pricing
            "price": listing.price,
            "price_per_sqm": listing.price_per_sqm,
            # Property characteristics
            "typology": listing.typology,
            "bedrooms": listing.bedrooms,
            "bathrooms": listing.bathrooms,
            "area_gross": listing.area_gross,
            "area_useful": listing.area_useful,
            "floor": listing.floor,
            # Features
            "has_elevator": listing.has_elevator,
            "has_garage": listing.has_garage,
            "has_pool": listing.has_pool,
            "has_garden": listing.has_garden,
            "has_terrace": listing.has_terrace,
            "has_balcony": listing.has_balcony,
            "has_air_conditioning": listing.has_air_conditioning,
            "has_central_heating": listing.has_central_heating,
            "is_luxury": listing.is_luxury,
            "has_sea_view": listing.has_sea_view,
            # Property details
            "energy_class": listing.energy_class,
            "condition": listing.condition,
            "year_built": listing.year_built,
            # Agency
            "agency_name": listing.agency_name,
            "agency_url": listing.agency_url,
            "reference": listing.reference,
            # Metadata
            "tags": listing.tags,
            "image_url": listing.image_url,
            "first_seen": listing.first_seen,
            "last_seen": listing.last_seen,
            "is_active": listing.is_active,
        }
        rows.append(row)

    # Create DataFrame and reorder columns
    df = pd.DataFrame(rows)

    # Ensure column order (only include columns that exist)
    existing_columns = [col for col in EXPORT_COLUMNS if col in df.columns]
    if existing_columns:
        df = df[existing_columns]

    return df


def export_listings_to_csv(
    session_factory: Callable[[], Session],
    path: Path,
    filters: ExportFilters,
) -> int:
    """Export listings to a CSV file.

    Args:
        session_factory: Factory to create database sessions.
        path: Output CSV path.
        filters: Filters to limit exported data.

    Returns:
        Number of listings exported.
    """
    logger.info("Exporting listings to CSV: %s", path)
    logger.debug("Export filters: %s", filters)

    with session_factory() as session:
        listings = _build_query(session, filters)
        logger.info("Found %d listings matching filters", len(listings))

        if not listings:
            logger.warning("No listings to export")
            # Create empty file with headers
            df = pd.DataFrame(columns=EXPORT_COLUMNS)
            df.to_csv(path, index=False)
            return 0

        df = _listings_to_dataframe(listings)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Export to CSV
    df.to_csv(path, index=False)
    logger.info("Exported %d listings to %s", len(df), path)

    return len(df)


def export_listings_to_parquet(
    session_factory: Callable[[], Session],
    path: Path,
    filters: ExportFilters,
) -> int:
    """Export listings to a Parquet file.

    Args:
        session_factory: Factory to create database sessions.
        path: Output Parquet path.
        filters: Filters to limit exported data.

    Returns:
        Number of listings exported.
    """
    logger.info("Exporting listings to Parquet: %s", path)
    logger.debug("Export filters: %s", filters)

    with session_factory() as session:
        listings = _build_query(session, filters)
        logger.info("Found %d listings matching filters", len(listings))

        if not listings:
            logger.warning("No listings to export")
            # Create empty file with headers
            df = pd.DataFrame(columns=EXPORT_COLUMNS)
            df.to_parquet(path, index=False)
            return 0

        df = _listings_to_dataframe(listings)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Export to Parquet
    df.to_parquet(path, index=False, engine="pyarrow")
    logger.info("Exported %d listings to %s", len(df), path)

    return len(df)

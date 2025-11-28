"""SQLAlchemy ORM models for the Idealista scraper.

This module defines all database models for storing scraped real estate
listings from Idealista Portugal, including geographic entities, listings,
price history, and scrape run metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from idealista_scraper.db.base import Base

if TYPE_CHECKING:
    pass


class District(Base):
    """A Portuguese district (distrito).

    Represents the top-level geographic division in Portugal.

    Attributes:
        id: Primary key.
        name: Full name of the district (e.g., "Lisboa").
        slug: URL-friendly identifier (e.g., "lisboa").
        listing_count: Number of listings in this district (from Idealista).
        last_scraped: Timestamp of the last scrape.
        created_at: Timestamp when this record was created.
        concelhos: Relationship to municipalities in this district.
    """

    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    listing_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_scraped: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    concelhos: Mapped[list[Concelho]] = relationship(
        "Concelho", back_populates="district", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return a string representation of the district."""
        return f"<District(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class Concelho(Base):
    """A Portuguese municipality (concelho).

    Represents a municipality within a district.

    Attributes:
        id: Primary key.
        district_id: Foreign key to the parent district.
        name: Full name of the municipality.
        slug: URL-friendly identifier.
        listing_count: Number of listings in this municipality.
        last_scraped: Timestamp of the last scrape.
        created_at: Timestamp when this record was created.
        district: Relationship to the parent district.
        listings: Relationship to listings in this municipality.
    """

    __tablename__ = "concelhos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    district_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("districts.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    listing_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_scraped: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    district: Mapped[District] = relationship("District", back_populates="concelhos")
    listings: Mapped[list[Listing]] = relationship(
        "Listing", back_populates="concelho", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return a string representation of the municipality."""
        return f"<Concelho(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class Listing(Base):
    """A real estate listing from Idealista.

    Represents a property listing with all extracted information from
    both listing cards and detail pages.

    Attributes:
        id: Primary key.
        idealista_id: Unique identifier from Idealista.
        concelho_id: Foreign key to the municipality.
        operation: Type of operation ("comprar" or "arrendar").
        property_type: Type of property (e.g., "casas", "apartamentos").
        url: Full URL to the listing on Idealista.
        title: Listing title.
        price: Current price in euros.
        price_per_sqm: Price per square meter.
        area_gross: Gross area in square meters.
        area_useful: Useful (net) area in square meters.
        typology: Property typology (e.g., "T3").
        bedrooms: Number of bedrooms.
        bathrooms: Number of bathrooms.
        floor: Floor number.
        has_elevator: Whether the building has an elevator.
        has_garage: Whether the property has a garage.
        has_pool: Whether the property has a pool.
        has_garden: Whether the property has a garden.
        has_terrace: Whether the property has a terrace.
        has_balcony: Whether the property has a balcony.
        has_air_conditioning: Whether the property has air conditioning.
        has_central_heating: Whether the property has central heating.
        is_luxury: Whether the property is marked as luxury.
        has_sea_view: Whether the property has a sea view.
        energy_class: Energy certificate class (e.g., "A", "B", "C").
        condition: Property condition (e.g., "Novo", "Usado").
        year_built: Year the property was built.
        street: Street name from the detail page.
        neighborhood: Neighborhood name.
        parish: Parish (freguesia) name.
        description: Full description text.
        agency_name: Real estate agency name.
        agency_url: URL to the agency profile.
        reference: Internal reference number.
        tags: Comma-separated list of tags.
        image_url: URL to the main image.
        first_seen: Timestamp when the listing was first scraped.
        last_seen: Timestamp when the listing was last seen.
        is_active: Whether the listing is currently active.
        raw_data: JSON blob with the full parsed data.
        created_at: Timestamp when this record was created.
        updated_at: Timestamp when this record was last updated.
        concelho: Relationship to the municipality.
        history: Relationship to price/change history records.
    """

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idealista_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    concelho_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concelhos.id"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    property_type: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Basic info
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_per_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Size and layout
    area_gross: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_useful: Mapped[float | None] = mapped_column(Float, nullable=True)
    typology: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Features (booleans)
    has_elevator: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_garage: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_pool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_garden: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_terrace: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_balcony: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_air_conditioning: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_central_heating: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_luxury: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_sea_view: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Property details
    energy_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Location details
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parish: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Description and agency
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agency_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agency_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Metadata
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Raw data storage
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    concelho: Mapped[Concelho] = relationship("Concelho", back_populates="listings")
    history: Mapped[list[ListingHistory]] = relationship(
        "ListingHistory", back_populates="listing", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return a string representation of the listing."""
        return (
            f"<Listing(id={self.id}, idealista_id={self.idealista_id}, "
            f"price={self.price}, operation='{self.operation}')>"
        )


class ListingHistory(Base):
    """Historical record of listing changes.

    Tracks price changes and other modifications to a listing over time.

    Attributes:
        id: Primary key.
        listing_id: Foreign key to the listing.
        price: Price at the time of this record.
        scraped_at: Timestamp when this history was recorded.
        changes: JSON blob with changed fields and their old/new values.
        listing: Relationship to the parent listing.
    """

    __tablename__ = "listing_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("listings.id"), nullable=False
    )
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    listing: Mapped[Listing] = relationship("Listing", back_populates="history")

    def __repr__(self) -> str:
        """Return a string representation of the history record."""
        return (
            f"<ListingHistory(id={self.id}, listing_id={self.listing_id}, "
            f"price={self.price}, scraped_at='{self.scraped_at}')>"
        )


class ScrapeRun(Base):
    """Record of a scraper run.

    Tracks the status, timing, and configuration of each scraper execution.

    Attributes:
        id: Primary key.
        started_at: Timestamp when the run started.
        ended_at: Timestamp when the run ended (if completed).
        status: Current status ("running", "success", "failed").
        run_type: Type of run ("prescrape", "scrape", "scrape-details").
        config: JSON snapshot of the configuration used.
        error_message: Error message if the run failed.
        listings_processed: Number of listings processed.
        listings_created: Number of new listings created.
        listings_updated: Number of existing listings updated.
    """

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Statistics
    listings_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    listings_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    listings_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        """Return a string representation of the scrape run."""
        return (
            f"<ScrapeRun(id={self.id}, run_type='{self.run_type}', "
            f"status='{self.status}', started_at='{self.started_at}')>"
        )

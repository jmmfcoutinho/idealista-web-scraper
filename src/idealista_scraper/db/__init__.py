"""Database module for the Idealista scraper.

This module provides SQLAlchemy ORM models and database utilities
for persisting scraped data.

Public API:
    - Base: SQLAlchemy declarative base class
    - create_engine_from_url: Create a SQLAlchemy engine
    - get_session_factory: Create a session factory
    - init_db: Initialize database tables
    - District: ORM model for districts
    - Concelho: ORM model for municipalities
    - Listing: ORM model for property listings
    - ListingHistory: ORM model for listing change history
    - ScrapeRun: ORM model for scrape run metadata
"""

from __future__ import annotations

from idealista_scraper.db.base import (
    Base,
    create_engine_from_url,
    get_session_factory,
    init_db,
)
from idealista_scraper.db.models import (
    Concelho,
    District,
    Listing,
    ListingHistory,
    ScrapeRun,
)

__all__ = [
    "Base",
    "Concelho",
    "District",
    "Listing",
    "ListingHistory",
    "ScrapeRun",
    "create_engine_from_url",
    "get_session_factory",
    "init_db",
]
